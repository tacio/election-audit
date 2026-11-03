"""Bounded disk-backed national inventory and structural work checkpoints.

This format deliberately does not certify reconstructed sessions or electoral results.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import resource
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.archive_parsing import PARSER_VERSION, ParseConfig, _Parser
from election_audit.elections import election_for_round
from election_audit.source_inventory import (
    ALL_UFS,
    canonical,
    digest,
    hash_file,
    safe_source,
    utc_now,
)

VERSION = "national-structural-v1"
DIAGNOSTIC_POLICY = "streamed-errors-event-addressable-info-v2"
DEFAULT_STORE = Path("/media/tacio/HDD/Data/tse/audit/2026")
DEFAULT_SCRATCH = Path(".local-state/national-scratch")
LIMITS = {
    "workers": 4,
    "threads": 4,
    "memory_bytes": 4 * 1024**3,
    "spill_bytes": 8 * 1024**3,
    "reserve_bytes": 10 * 1024**3,
    "hdd_reserve_bytes": 20 * 1024**3,
    "batch_rows": 2048,
}


def read_config(path):
    doc = json.loads(Path(path).read_text())
    if set(doc) != {"version", "sources"} or doc["version"] != VERSION:
        raise ValueError("Expected national-structural-v1 sources configuration")
    if not isinstance(doc["sources"], list) or not doc["sources"]:
        raise ValueError("Need at least one source")
    normalized, rounds = [], set()
    for source in doc["sources"]:
        required = {"round", "root", "manifest", "ufs"}
        if not required <= set(source) or set(source) - required - {"section_keys"}:
            raise ValueError(
                "Source requires round/root/manifest/ufs; only section_keys is optional"
            )
        election = election_for_round(source["round"])
        if election.round in rounds:
            raise ValueError("Duplicate source round")
        rounds.add(election.round)
        ufs = sorted(set(source["ufs"]))
        if not ufs or not set(ufs) <= set(ALL_UFS):
            raise ValueError("Explicit known UF population required")
        normalized.append(
            {
                "round": election.round,
                "root": str(Path(source["root"]).resolve()),
                "manifest": str(Path(source["manifest"]).resolve()),
                "ufs": ufs,
            }
        )
        if "section_keys" in source:
            keys = source["section_keys"]
            if not isinstance(keys, list) or not keys:
                raise ValueError("section_keys must be a nonempty explicit selection")
            for key in keys:
                if (
                    not isinstance(key, (list, tuple))
                    or len(key) != 4
                    or key[0] not in ufs
                    or any(
                        not isinstance(v, str) or not v.isdigit() or len(v) != width
                        for v, width in zip(key[1:], (5, 4, 4), strict=True)
                    )
                ):
                    raise ValueError(
                        "section_keys require known UF and zero-padded municipality/zone/section"
                    )
            normalized[-1]["section_keys"] = [
                list(key) for key in sorted(set(tuple(k) for k in keys))
            ]
    return {"version": VERSION, "sources": sorted(normalized, key=lambda x: x["round"])}


def source_connection(spec):
    db = sqlite3.connect(Path(spec["manifest"]).as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def selected_rows(db, spec):
    """Use indexed lexical URL ranges; never fetch a national table into Python."""
    e = election_for_round(spec["round"])
    base = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/"
    wrong = base + ("3221/" if e.round == 1 else "3220/")
    if db.execute(
        "SELECT 1 FROM files WHERE url>=? AND url<? LIMIT 1", (wrong, wrong + "\uffff")
    ).fetchone():
        raise ValueError(f"Manifest contains another round; requested round {e.round}")
    for uf in spec["ufs"]:
        index = f"{base}{e.pleito_code}/config/{uf}/{uf}-p{int(e.pleito_code):06d}-cs.json"
        row = db.execute("SELECT * FROM files WHERE url=?", (index,)).fetchone()
        if row is None:
            raise ValueError(f"Missing authoritative index: round {e.round}/{uf}")
        yield uf, dict(row)
        prefixes = [f"{base}{e.pleito_code}/dados/{uf}/"]
        if "section_keys" in spec:
            prefixes = [
                f"{base}{e.pleito_code}/dados/{'/'.join(key)}/"
                for key in spec["section_keys"]
                if key[0] == uf
            ]
        for prefix in prefixes:
            found = False
            for row in db.execute(
                "SELECT * FROM files WHERE url>=? AND url<? ORDER BY url",
                (prefix, prefix + "\uffff"),
            ):
                found = True
                yield uf, dict(row)
            if not found and "section_keys" in spec:
                raise ValueError("Selected section has no source mapping")


def guard(store, scratch, extra=0, *, reserve_bytes=None):
    if reserve_bytes is None:
        reserve_bytes = LIMITS["reserve_bytes"]
    existing = []
    for location in (store, scratch):
        p = Path(location)
        while not p.exists():
            p = p.parent
        existing.append(p)
    if existing[0].stat().st_dev == existing[1].stat().st_dev:
        checks = [
            (
                existing[0],
                max(reserve_bytes, LIMITS["hdd_reserve_bytes"]) + LIMITS["spill_bytes"] + extra,
            )
        ]
    else:
        checks = [
            (existing[0], max(reserve_bytes, LIMITS["hdd_reserve_bytes"]) + extra),
            (existing[1], reserve_bytes + LIMITS["spill_bytes"]),
        ]
    for p, needed in checks:
        if shutil.disk_usage(p).free < needed:
            raise OSError(f"Capacity reserve failed at {p}; need {needed} free bytes")


def preflight(
    config, store=DEFAULT_STORE, scratch=DEFAULT_SCRATCH, *, reserve_bytes=LIMITS["reserve_bytes"]
):
    result = {
        "version": VERSION,
        "config_id": digest(config),
        "limits": LIMITS,
        "sources": [],
        "capacity_status": "not_checked",
        "full_pipeline_ready": False,
        "remaining": [
            "cross-object copied-history reconstruction",
            "streamed electoral derivatives and model releases",
        ],
    }
    for spec in config["sources"]:
        counts, sizes, found = Counter(), Counter(), Counter()
        with closing(source_connection(spec)) as db:
            for uf, row in selected_rows(db, spec):
                counts[uf] += 1
                sizes[uf] += row["bytes"]
                found["log" if row["url"].endswith(("-log.jez", "-log.dat")) else "metadata"] += 1
            db.rollback()
        result["sources"].append(
            {
                "round": spec["round"],
                "files_by_uf": dict(counts),
                "source_bytes_by_uf": dict(sizes),
                "kinds": dict(found),
            }
        )
    selected_bytes = sum(sum(r["source_bytes_by_uf"].values()) for r in result["sources"])
    guard(store, scratch, selected_bytes, reserve_bytes=reserve_bytes)
    result.update(
        capacity_status="source_copy_budget_fits_output_expansion_not_yet_certified",
        selected_source_bytes=selected_bytes,
    )
    return result


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _lock(store, name):
    directory = Path(store) / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / name).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _validate_row(row):
    if (
        not isinstance(row.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        or type(row.get("bytes")) is not int
        or row["bytes"] < 0
    ):
        raise ValueError("Invalid file metadata")


def _destinations(config, store, scratch):
    for source in config["sources"]:
        raw = Path(source["root"]).resolve()
        if any(p == raw or p.is_relative_to(raw) for p in (store, scratch)):
            raise ValueError("Derived paths must be outside raw roots")


def _write_json(path, document):
    encoded = canonical(document) + b"\n"
    with Path(path).open("xb") as f:
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())
    with Path(str(path) + ".sha256").open("x") as f:
        f.write(hashlib.sha256(encoded).hexdigest() + "\n")
        f.flush()
        os.fsync(f.fileno())
    _sync_dir(Path(path).parent)


def _read_json(path):
    body = Path(path).read_bytes()
    if hashlib.sha256(body).hexdigest() != Path(str(path) + ".sha256").read_text().strip():
        raise ValueError("Artifact metadata checksum mismatch")
    return json.loads(body)


def _verify_files(directory, document):
    for name, expected in document["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe artifact path")
        target = directory / name
        if target.is_symlink() or not target.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Unsafe artifact path")
        if hash_file(target) != (expected["sha256"], expected["bytes"]):
            raise ValueError("Completed artifact is corrupt; refusing to reuse")


def freeze_census(config, store, scratch, *, reserve_bytes=LIMITS["reserve_bytes"]):
    store, scratch = Path(store).resolve(), Path(scratch).resolve()
    _destinations(config, store, scratch)
    with _lock(store, "census-" + digest(config)):
        return _freeze_census(config, store, scratch, reserve_bytes=reserve_bytes)


def _freeze_census(config, store, scratch, *, reserve_bytes=LIMITS["reserve_bytes"]):
    """Atomic frozen SQLite metadata; original manifest connections always query-only."""
    store, scratch = Path(store).resolve(), Path(scratch).resolve()
    for source in config["sources"]:
        raw = Path(source["root"])
        if (
            store == raw
            or store.is_relative_to(raw)
            or scratch == raw
            or scratch.is_relative_to(raw)
        ):
            raise ValueError("Derived paths must be outside raw roots")
    store.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    key = digest(config)
    target = store / "censuses" / key
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        doc = _read_json(target / "census.json")
        if doc["config"] != config:
            raise ValueError("Census configuration conflict")
        _verify_files(target, doc)
        with closing(
            sqlite3.connect((target / "census.sqlite").as_uri() + "?mode=ro", uri=True)
        ) as catalog:
            for sha, size in catalog.execute(
                "SELECT sha256,bytes FROM file_observation WHERE url NOT LIKE '%-log.jez' AND url NOT LIKE '%-log.dat' GROUP BY sha256,bytes"
            ):
                if hash_file(store / "objects" / sha[:2] / sha) != (sha, size):
                    raise ValueError("Frozen metadata original corrupt")
        return target
    preflight(config, store, scratch, reserve_bytes=reserve_bytes)
    staging = Path(tempfile.mkdtemp(prefix=".census-", dir=target.parent))
    try:
        with closing(sqlite3.connect(staging / "census.sqlite")) as out:
            out.executescript("""
              CREATE TABLE file_observation(round INTEGER,uf TEXT,url TEXT,sha256 TEXT,bytes INTEGER,path TEXT,source_root TEXT,payload TEXT,PRIMARY KEY(round,url));
              CREATE TABLE section_observation(round INTEGER,uf TEXT,run TEXT,municipality TEXT,zone TEXT,section TEXT,status TEXT,payload TEXT);
              CREATE INDEX file_hash ON file_observation(sha256);
              CREATE INDEX file_scope ON file_observation(round,uf);
              CREATE INDEX section_scope ON section_observation(round,uf);
            """)
            counts, byte_counts, row_digest = Counter(), Counter(), hashlib.sha256()
            for spec in config["sources"]:
                with closing(source_connection(spec)) as db:
                    for uf, row in selected_rows(db, spec):
                        _validate_row(row)
                        safe_source(Path(spec["root"]), row["path"])
                        if not row["url"].endswith(("-log.jez", "-log.dat")):
                            if row["bytes"] > 16 * 1024**2:
                                raise ValueError(
                                    "Metadata object exceeds bounded index/auxiliary limit"
                                )
                            frozen_metadata = _frozen_object(
                                {**row, "source_root": spec["root"]}, store, scratch, reserve_bytes
                            )
                            if row["bytes"] > 16 * 1024**2:
                                raise ValueError(
                                    "Metadata object exceeds bounded index/auxiliary limit"
                                )
                            metadata = json.loads(frozen_metadata.read_bytes())
                            if str(metadata.get("f", "")).lower() != "o":
                                raise ValueError("Nonofficial metadata")
                            if (
                                row["url"].endswith("-cs.json")
                                and str(metadata.get("cdp"))
                                != election_for_round(spec["round"]).pleito_code
                            ):
                                raise ValueError("Index pleito mismatch")
                        if row["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
                            raise ValueError("Invalid file metadata")
                        out.execute(
                            "INSERT INTO file_observation VALUES (?,?,?,?,?,?,?,?)",
                            (
                                spec["round"],
                                uf,
                                row["url"],
                                row["sha256"],
                                row["bytes"],
                                row["path"],
                                spec["root"],
                                canonical(row).decode(),
                            ),
                        )
                        row_digest.update(canonical([spec["round"], uf, row]) + b"\n")
                        counts[f"{spec['round']}/{uf}"] += 1
                        byte_counts[f"{spec['round']}/{uf}"] += row["bytes"]
                    selections = [("uf=?", (uf,)) for uf in spec["ufs"]]
                    if "section_keys" in spec:
                        selections = [
                            ("uf=? AND municipality=? AND zone=? AND section=?", tuple(key))
                            for key in spec["section_keys"]
                        ]
                    for predicate, parameters in selections:
                        for row in db.execute(
                            f"SELECT * FROM sections WHERE {predicate} ORDER BY run,municipality,zone,section",
                            parameters,
                        ):
                            r = dict(row)
                            uf = r["uf"]
                            out.execute(
                                "INSERT INTO section_observation VALUES (?,?,?,?,?,?,?,?)",
                                (
                                    spec["round"],
                                    uf,
                                    r["run"],
                                    r["municipality"],
                                    r["zone"],
                                    r["section"],
                                    r["status"],
                                    canonical(r).decode(),
                                ),
                            )
                            row_digest.update(canonical([spec["round"], "section", r]) + b"\n")
                    db.rollback()
                out.commit()
            files = {
                "census.sqlite": dict(
                    zip(("sha256", "bytes"), hash_file(staging / "census.sqlite"), strict=True)
                )
            }
        _write_json(
            staging / "census.json",
            {
                "version": VERSION,
                "config": config,
                "captured_at": utc_now(),
                "rows_sha256": row_digest.hexdigest(),
                "files": files,
                "file_counts": dict(counts),
                "source_bytes": dict(byte_counts),
                "historical_mapping": "current files retain current mapping only; section histories do not establish old bytes",
            },
        )
        staging.rename(target)
        _sync_dir(target.parent)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return target


def _frozen_object(row, store, scratch, reserve_bytes):
    _validate_row(row)
    with _lock(store, "original-" + row["sha256"]):
        return _copy_frozen_object(row, store, scratch, reserve_bytes)


def _copy_frozen_object(row, store, scratch, reserve_bytes):
    target = store / "objects" / row["sha256"][:2] / row["sha256"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hash_file(target) != (row["sha256"], row["bytes"]):
            raise ValueError("Frozen original corrupt")
        return target
    guard(store, scratch, row["bytes"], reserve_bytes=reserve_bytes)
    src = safe_source(Path(row["source_root"]), row["path"])
    temp = target.with_name("." + target.name + ".part")
    hasher, length = hashlib.sha256(), 0
    with src.open("rb") as original, temp.open("wb") as copy:
        while body := original.read(1024 * 1024):
            copy.write(body)
            hasher.update(body)
            length += len(body)
        copy.flush()
        os.fsync(copy.fileno())
    if (hasher.hexdigest(), length) != (row["sha256"], row["bytes"]):
        temp.unlink()
        raise ValueError("Original changed or is missing/corrupt")
    temp.replace(target)
    _sync_dir(target.parent)
    return target


def _compact_jsonl(source, output, batch_rows):
    schema = pa.schema([("payload", pa.string())])
    count, batch, batch_bytes = 0, [], 0
    with pq.ParquetWriter(output, schema, compression="zstd") as writer, source.open() as rows:
        for line in rows:
            json.loads(line)
            batch.append(line.rstrip("\n"))
            batch_bytes += len(line.encode("utf-8"))
            count += 1
            if len(batch) >= batch_rows or batch_bytes >= 8 * 1024**2:
                writer.write_table(pa.table({"payload": batch}, schema=schema))
                batch, batch_bytes = [], 0
        if batch:
            writer.write_table(pa.table({"payload": batch}, schema=schema))
    with Path(output).open("rb") as saved:
        os.fsync(saved.fileno())
    return count


class _BudgetWriter:
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget

    def write(self, body):
        if len(body) > self.budget[0]:
            raise OSError("Per-object scratch budget exceeded")
        self.budget[0] -= len(body)
        return self.stream.write(body)


class _StreamingParser(_Parser):
    """Exact diagnostic counts; unknown-message info is addressable in event rows."""

    def __init__(self, *args):
        super().__init__(*args)
        self.diagnostics = Counter()

    def issue(self, code, segments, *, line=None, severity="error", **details):
        self.counts["issues_seen"] += 1
        self.diagnostics[(code, severity)] += 1
        self.incomplete |= severity == "error"
        if code == "unsupported_message_class" and severity == "info":
            self.counts["issues_aggregated"] += 1
            return
        self.issues.write(
            canonical(
                {
                    "issue_code": code,
                    "severity": severity,
                    "record_locator": {
                        "archive_segments": segments,
                        "line_start": line,
                        "line_end": line,
                        "byte_start": None,
                        "byte_end": None,
                    },
                    "details": details,
                }
            )
            + b"\n"
        )
        self.counts["issues_written"] += 1


def _parse_bounded(frozen, work, sha):
    config = ParseConfig()
    json_budget = max(
        0, LIMITS["spill_bytes"] - config.max_total_bytes - config.max_directory_bytes
    )
    budget = [json_budget]
    with (work / "events.jsonl").open("xb") as events, (work / "issues.jsonl").open("xb") as issues:
        parser = _StreamingParser(
            sha, config, work, _BudgetWriter(events, budget), _BudgetWriter(issues, budget)
        )
        with frozen.open("rb") as original:
            parser.archive(original)
        if not parser.log_members:
            parser.issue("missing_log_member", [])
        for stream in (events, issues):
            stream.flush()
            os.fsync(stream.fileno())
    if hash_file(frozen)[0] != sha:
        raise ValueError("Frozen original changed during parsing")
    return {
        "parser_version": PARSER_VERSION,
        "diagnostic_policy": DIAGNOSTIC_POLICY,
        "diagnostics": [
            {
                "issue_code": code,
                "severity": severity,
                "count": n,
                "representation": "event_rows_with_event_kind_unknown"
                if code == "unsupported_message_class" and severity == "info"
                else "streamed_issue_rows",
            }
            for (code, severity), n in sorted(parser.diagnostics.items())
        ],
        "config": config.__dict__,
        "counts": dict(parser.counts),
        "status": "partial" if parser.incomplete else "complete",
        "log_members": parser.log_members,
        "scratch_bytes": json_budget - budget[0],
        "scratch_json_budget_bytes": json_budget,
    }


def resume(
    config,
    store=DEFAULT_STORE,
    scratch=DEFAULT_SCRATCH,
    *,
    max_objects=None,
    reserve_bytes=LIMITS["reserve_bytes"],
    output_budget_bytes=None,
):
    """Freeze metadata once, then process unique content with immutable checkpoints."""
    if max_objects is not None and (type(max_objects) is not int or max_objects < 1):
        raise ValueError("max_objects must be positive")
    if output_budget_bytes is not None and (
        type(output_budget_bytes) is not int or output_budget_bytes <= 0
    ):
        raise ValueError("output_budget_bytes must be positive")
    if max_objects is None and (type(output_budget_bytes) is not int or output_budget_bytes <= 0):
        raise ValueError(
            "Unbounded processing requires an explicit output budget from reviewed benchmarks"
        )
    store, scratch = Path(store).resolve(), Path(scratch).resolve()
    _destinations(config, store, scratch)
    with _lock(store, "national"):
        census = freeze_census(config, store, scratch, reserve_bytes=reserve_bytes)
        with closing(sqlite3.connect(census / "census.sqlite")) as db:
            db.row_factory = sqlite3.Row
            processed = 0
            cursor = db.execute(
                "SELECT * FROM file_observation WHERE url LIKE '%-log.jez' OR url LIKE '%-log.dat' GROUP BY sha256 ORDER BY sha256"
            )
            for row in cursor:
                if max_objects is not None and processed >= max_objects:
                    break
                target_key = digest(
                    [row["sha256"], VERSION, ParseConfig().__dict__, DIAGNOSTIC_POLICY]
                )
                reused = (store / "structural" / target_key[:2] / target_key).exists()
                result = process_object(
                    dict(row),
                    store,
                    scratch,
                    reserve_bytes=reserve_bytes,
                    output_budget_bytes=output_budget_bytes,
                )
                if output_budget_bytes is not None and not reused:
                    document = _read_json(result / "artifact.json")
                    output_budget_bytes -= sum(spec["bytes"] for spec in document["files"].values())
                    output_budget_bytes -= (result / "artifact.json").stat().st_size + 65
                processed += 1
    return status(store, config_id=digest(config))


def process_object(
    row, store, scratch, *, reserve_bytes=LIMITS["reserve_bytes"], output_budget_bytes=None
):
    store, scratch = Path(store).resolve(), Path(scratch).resolve()
    _validate_row(row)
    _destinations({"sources": [{"root": row["source_root"]}]}, store, scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    with _lock(store, "structural-" + row["sha256"]):
        return _process_object(
            row,
            store,
            scratch,
            reserve_bytes=reserve_bytes,
            output_budget_bytes=output_budget_bytes,
        )


def _process_object(row, store, scratch, *, reserve_bytes, output_budget_bytes):
    store, scratch = Path(store), Path(scratch)
    key = digest([row["sha256"], VERSION, ParseConfig().__dict__, DIAGNOSTIC_POLICY])
    target = store / "structural" / key[:2] / key
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        document = _read_json(target / "artifact.json")
        if document.get("object_sha256") != row["sha256"] or document.get("version") != VERSION:
            raise ValueError("Structural checkpoint identity mismatch")
        _verify_files(target, document)
        original = store / "objects" / row["sha256"][:2] / row["sha256"]
        if hash_file(original) != (row["sha256"], row["bytes"]):
            raise ValueError("Frozen original corrupt")
        return target
    guard(store, scratch, reserve_bytes=reserve_bytes)
    started = time.monotonic()
    frozen = _frozen_object(row, store, scratch, reserve_bytes)
    work = Path(tempfile.mkdtemp(prefix="national-object-", dir=scratch))
    staging = Path(tempfile.mkdtemp(prefix=".structural-", dir=target.parent))
    try:
        parsed_doc = _parse_bounded(frozen, work, row["sha256"])
        derived_bound = (
            sum((work / (name + ".jsonl")).stat().st_size for name in ("events", "issues"))
            + 1024**2
        )
        if output_budget_bytes is not None and derived_bound > output_budget_bytes:
            raise OSError("Reviewed derived-output budget exhausted before publication")
        guard(store, scratch, derived_bound, reserve_bytes=reserve_bytes)
        parsed = work
        counts = {}
        for name in ("events", "issues"):
            counts[name] = _compact_jsonl(
                parsed / (name + ".jsonl"), staging / (name + ".parquet"), LIMITS["batch_rows"]
            )
        files = {
            name: dict(zip(("sha256", "bytes"), hash_file(staging / name), strict=True))
            for name in ("events.parquet", "issues.parquet")
        }
        actual_output_bytes = sum(spec["bytes"] for spec in files.values())
        if output_budget_bytes is not None and actual_output_bytes + 1024**2 > output_budget_bytes:
            raise OSError("Reviewed derived-output budget exhausted before publication")
        guard(store, scratch, reserve_bytes=reserve_bytes)
        document = {
            "version": VERSION,
            "object_sha256": row["sha256"],
            "source_bytes": row["bytes"],
            "diagnostic_policy": DIAGNOSTIC_POLICY,
            "parser": parsed_doc,
            "counts": counts,
            "files": files,
            "elapsed_seconds": time.monotonic() - started,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "scientific_eligibility": "unavailable_structural_only",
            "overlap_resolution": "not_performed_cross_object",
        }
        _write_json(staging / "artifact.json", document)
        staging.rename(target)
        _sync_dir(target.parent)
    except BaseException as exc:
        failure_dir = store / "failures"
        failure_dir.mkdir(exist_ok=True)
        with (failure_dir / (key + ".jsonl")).open("ab") as failures:
            failures.write(
                canonical(
                    {
                        "object_sha256": row["sha256"],
                        "at": utc_now(),
                        "state": "failed",
                        "exception_type": type(exc).__name__,
                        "successful_publication": False,
                    }
                )
                + b"\n"
            )
            failures.flush()
            os.fsync(failures.fileno())
        _sync_dir(failure_dir)
        shutil.rmtree(staging)
        raise
    finally:
        shutil.rmtree(work)
    return target


def status(store=DEFAULT_STORE, *, config_id=None):
    store = Path(store)
    result = {
        "version": VERSION,
        "censuses": [],
        "structural_objects": 0,
        "events": 0,
        "issues": 0,
        "structural_output_bytes": 0,
        "partial_structural_objects": 0,
        "legacy_structural_objects": 0,
        "diagnostic_policy": DIAGNOSTIC_POLICY,
        "issues_total": 0,
        "issues_aggregated": 0,
        "expected_structural_objects": None,
        "structural_processing_complete": False,
        "full_pipeline_complete": False,
        "limitations": [
            "structural parsing only; no canonical results, sessions or fitted models",
            "national expansion requires measured output budget",
        ],
    }
    candidates = [store / "censuses" / config_id] if config_id else (store / "censuses").glob("*")
    for directory in candidates:
        if not directory.name.startswith(".") and (directory / "census.json").exists():
            doc = _read_json(directory / "census.json")
            _verify_files(directory, doc)
            result["censuses"].append(
                {
                    "id": directory.name,
                    "file_counts": doc["file_counts"],
                    "source_bytes": doc["source_bytes"],
                }
            )
    scoped = None
    if config_id:
        catalog = store / "censuses" / config_id / "census.sqlite"
        if not catalog.exists():
            raise ValueError("Requested census does not exist")
        scoped = sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True)
        result["expected_structural_objects"] = scoped.execute(
            "SELECT count(DISTINCT sha256) FROM file_observation WHERE url LIKE '%-log.jez' OR url LIKE '%-log.dat'"
        ).fetchone()[0]
    try:
        for path in (store / "structural").glob("*/*/artifact.json"):
            doc = _read_json(path)
            if (
                scoped
                and not scoped.execute(
                    "SELECT 1 FROM file_observation WHERE sha256=? LIMIT 1", (doc["object_sha256"],)
                ).fetchone()
            ):
                continue
            _verify_files(path.parent, doc)
            if doc.get("diagnostic_policy") != DIAGNOSTIC_POLICY:
                result["legacy_structural_objects"] += 1
                continue
            result["issues_total"] += doc["parser"]["counts"].get("issues_seen", 0)
            result["issues_aggregated"] += doc["parser"]["counts"].get("issues_aggregated", 0)
            result["structural_objects"] += 1
            result["structural_output_bytes"] += sum(
                spec["bytes"] for spec in doc["files"].values()
            )
            result["partial_structural_objects"] += doc["parser"]["status"] != "complete"
            for name in ("events", "issues"):
                result[name] += doc["counts"][name]
        if scoped:
            result["structural_processing_complete"] = (
                result["structural_objects"] == result["expected_structural_objects"]
            )
    finally:
        if scoped:
            scoped.close()
    return result


def national_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "resume", "status"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument(
        "--max-objects", type=int, help="Explicit diagnostic bound, never national completeness"
    )
    parser.add_argument(
        "--output-budget-gib",
        type=float,
        help="Reviewed additional derived-output allowance; required for unbounded runs",
    )
    args = parser.parse_args(argv)
    if args.max_objects is not None and args.max_objects < 1:
        parser.error("max-objects must be positive")
    if args.action != "status" and args.config is None:
        parser.error("--config required")
    if args.action == "status":
        result = status(
            args.store, config_id=digest(read_config(args.config)) if args.config else None
        )
    else:
        config = read_config(args.config)
        if args.action == "preflight":
            result = preflight(config, args.store, args.scratch)
        else:
            result = resume(
                config,
                args.store,
                args.scratch,
                max_objects=args.max_objects,
                output_budget_bytes=None
                if args.output_budget_gib is None
                else int(args.output_budget_gib * 1024**3),
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(national_main())
