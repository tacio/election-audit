"""Metadata-only stratified workload profiling and budgeted structural benchmarks."""

from __future__ import annotations

import argparse
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
from contextlib import closing
from pathlib import Path

from election_audit.elections import election_for_round
from election_audit.national import (
    DIAGNOSTIC_POLICY,
    LIMITS,
    VERSION,
    _lock,
    _read_json,
    _sync_dir,
    _write_json,
    freeze_census,
    guard,
    preflight,
    process_object,
    read_config,
    source_connection,
)
from election_audit.source_inventory import canonical, digest, hash_file, utc_now

REGIONS = {
    **dict.fromkeys("ac am ap pa ro rr to".split(), "north"),
    **dict.fromkeys("al ba ce ma pb pe pi rn se".split(), "northeast"),
    **dict.fromkeys("df go ms mt".split(), "center_west"),
    **dict.fromkeys("es mg rj sp".split(), "southeast"),
    **dict.fromkeys("pr rs sc".split(), "south"),
    "zz": "overseas",
}


def profile_source(spec, output, scratch):
    """Freeze file metadata in SQLite, without reading electoral/log outcomes."""
    output, scratch = Path(output).resolve(), Path(scratch).resolve()
    if output.exists():
        raise ValueError("Profile output must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    guard(output.parent, scratch, 2 * 1024**3)
    temporary = Path(tempfile.mkdtemp(prefix=".profile-", dir=output.parent))
    started = time.monotonic()
    hasher_rows, count = hashlib.sha256(), 0
    election = election_for_round(spec["round"])
    base = (
        f"https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/{election.pleito_code}/dados/"
    )
    pattern = re.compile(re.escape(base) + r"([a-z]{2})/(\d{5})/(\d{4})/(\d{4})/.+")
    try:
        with (
            closing(source_connection(spec)) as source,
            closing(sqlite3.connect(temporary / "profile.sqlite")) as out,
        ):
            run = source.execute("SELECT id,status FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            if run is None or run["status"] != "finished":
                raise ValueError("Workload profile requires a finished acquisition")
            out.execute("PRAGMA temp_store=FILE")
            out.execute("PRAGMA cache_size=-16384")
            out.execute(
                "CREATE TABLE sources(uf TEXT,municipality TEXT,zone TEXT,section TEXT,url TEXT PRIMARY KEY,path TEXT,sha256 TEXT,bytes INTEGER)"
            )
            for row in source.execute(
                "SELECT url,path,sha256,bytes FROM files WHERE url>=? AND url<? AND (url LIKE '%-log.jez' OR url LIKE '%-log.dat') ORDER BY url",
                (base, base + "\uffff"),
            ):
                match = pattern.fullmatch(row["url"])
                if not match or match[1] not in spec["ufs"]:
                    continue
                if (
                    not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                    or type(row["bytes"]) is not int
                    or row["bytes"] <= 0
                ):
                    raise ValueError("Invalid source metadata")
                values = (*match.groups(), row["url"], row["path"], row["sha256"], row["bytes"])
                out.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)", values)
                hasher_rows.update(canonical(values) + b"\n")
                count += 1
            source.rollback()
            if not count:
                raise ValueError("No log mappings in declared scope")
            out.execute("CREATE INDEX source_hash ON sources(uf,sha256,url)")
            out.execute(
                "CREATE TABLE ranked AS WITH unique_content AS (SELECT *,row_number() OVER(PARTITION BY uf,sha256 ORDER BY url) AS witness_rank FROM sources) SELECT uf,municipality,zone,section,url,path,sha256,bytes,ntile(4) OVER(PARTITION BY uf ORDER BY bytes,sha256) AS size_band FROM unique_content WHERE witness_rank=1"
            )
            out.execute("CREATE INDEX ranked_scope ON ranked(uf,size_band,sha256)")
            strata = [
                dict(
                    zip(
                        (
                            "uf",
                            "size_band",
                            "objects",
                            "source_bytes",
                            "minimum_bytes",
                            "maximum_bytes",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in out.execute(
                    "SELECT uf,size_band,count(*),sum(bytes),min(bytes),max(bytes) FROM ranked GROUP BY uf,size_band ORDER BY uf,size_band"
                )
            ]
            out.commit()
        with (temporary / "profile.sqlite").open("rb") as f:
            os.fsync(f.fileno())
        _write_json(
            temporary / "profile.json",
            {
                "version": "national-workload-profile-v1",
                "source": spec,
                "source_run": dict(run),
                "captured_at": utc_now(),
                "selection_inputs": "source URL/hash/size/geography only; no log or electoral outcomes",
                "source_rows": count,
                "source_rows_sha256": hasher_rows.hexdigest(),
                "strata": strata,
                "profile_elapsed_seconds": time.monotonic() - started,
                "files": {
                    "profile.sqlite": dict(
                        zip(
                            ("sha256", "bytes"),
                            hash_file(temporary / "profile.sqlite"),
                            strict=True,
                        )
                    )
                },
            },
        )
        temporary.rename(output)
        _sync_dir(output.parent)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return output


def select_sample(profile, output, *, per_band=2, exclusions=None):
    if type(per_band) is not int or not 1 <= per_band <= 32:
        raise ValueError("per_band must be between1 and32")
    profile, output = Path(profile).resolve(), Path(output).resolve()
    document = _read_json(profile / "profile.json")
    excluded = None
    if exclusions is not None:
        exclusions = Path(exclusions).resolve()
        if exclusions.stat().st_size > 16 * 1024**2:
            raise ValueError("Exclusion registry exceeds bounded selection allowance")
        excluded = _read_json(exclusions)
        if (
            excluded.get("version") != "structural-sample-exclusions-v1"
            or excluded.get("round") != document["source"]["round"]
        ):
            raise ValueError("Exclusions must match the profiled round")
        if (
            not isinstance(excluded.get("section_keys"), list)
            or len(excluded["section_keys"]) > 100000
        ):
            raise ValueError("Need bounded explicit exclusion section keys")
        for key in excluded["section_keys"]:
            if (
                not isinstance(key, list)
                or len(key) != 4
                or not all(isinstance(v, str) for v in key)
                or not re.fullmatch(r"[a-z]{2}/\d{5}/\d{4}/\d{4}", "/".join(key))
            ):
                raise ValueError("Malformed excluded section key")
    if hash_file(profile / "profile.sqlite") != (
        document["files"]["profile.sqlite"]["sha256"],
        document["files"]["profile.sqlite"]["bytes"],
    ):
        raise ValueError("Profile integrity mismatch")
    with closing(
        sqlite3.connect((profile / "profile.sqlite").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        eligible = "ranked"
        if excluded is not None:
            db.execute(
                "CREATE TEMP TABLE excluded(uf TEXT,municipality TEXT,zone TEXT,section TEXT,PRIMARY KEY(uf,municipality,zone,section))"
            )
            db.executemany(
                "INSERT OR IGNORE INTO excluded VALUES(?,?,?,?)", excluded["section_keys"]
            )
            eligible = "(SELECT r.* FROM ranked r WHERE NOT EXISTS(SELECT 1 FROM excluded e WHERE e.uf=r.uf AND e.municipality=r.municipality AND e.zone=r.zone AND e.section=r.section))"
        sampled = {
            r["url"]: {**dict(r), "selection_reason": "hash_rank_within_size_quartile"}
            for r in db.execute(
                f"WITH ordered AS (SELECT *,row_number() OVER(PARTITION BY uf,size_band ORDER BY sha256,url) AS selection_rank FROM {eligible}) SELECT * FROM ordered WHERE selection_rank<=? ORDER BY uf,size_band,sha256",
                (per_band,),
            )
        }
        for row in db.execute(
            f"WITH ordered AS (SELECT *,row_number() OVER(PARTITION BY uf ORDER BY bytes DESC,sha256,url) AS tail_rank FROM {eligible}) SELECT * FROM ordered WHERE tail_rank=1 ORDER BY uf"
        ):
            if row["url"] in sampled:
                sampled[row["url"]]["selection_reason"] += "+maximum_size_tail"
            else:
                sampled[row["url"]] = {**dict(row), "selection_reason": "maximum_size_tail"}
    units = sorted(sampled.values(), key=lambda r: (r["uf"], r["size_band"], r["sha256"]))
    if not units:
        raise ValueError("No eligible source after exclusions")
    source = {
        **document["source"],
        "section_keys": sorted(
            {(r["uf"], r["municipality"], r["zone"], r["section"]) for r in units}
        ),
    }
    source["section_keys"] = [list(key) for key in source["section_keys"]]
    config = {"version": VERSION, "sources": [source]}
    sample = {
        "version": "national-workload-sample-v1",
        "profile": str(profile),
        "profile_sha256": hash_file(profile / "profile.json")[0],
        "per_band": per_band,
        "units": units,
        "config": config,
        "config_id": digest(config),
        "regions": dict(Counter(REGIONS[u["uf"]] for u in units)),
        "sampling_limits": "deterministic content-hash ranks within UF size quartiles plus deliberate maximum-size tails; all versions in selected sections retained; not a random electoral-outcome sample or national certification",
    }
    if excluded is not None:
        sample["exclusions"] = {
            "path": str(exclusions),
            "sha256": hash_file(exclusions)[0],
            "section_count": len(excluded["section_keys"]),
            "evidence": excluded.get("evidence"),
            "selection_effect": "hash ranks and maximum-size tails are chosen only among nonexcluded sections; original UF size bands retained",
        }
    sample["sample_id"] = digest(sample)
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "sample.json", sample)
    _write_json(output / "config.json", config)
    # Conservative inspection history: propagate to both-round stable locations in Phase15.
    _write_json(
        output / "inspection.json",
        {
            "version": "phase11-development-inspection-v1",
            "sample_id": sample["sample_id"],
            "registered_at": utc_now(),
            "section_keys": source["section_keys"],
            "round": source["round"],
            "state": "development_inspected",
            "required_propagation": "Exclude each selected section and all subsequently linked stable polling locations across both rounds from untouched tests; unknown location identity is not test eligible",
            "purpose": "candidate-independent structural resource/diagnostic validation; no candidate results inspected",
            "before_log_outcome_inspection": True,
        },
    )
    return sample


def _progress(directory, value):
    temporary = directory / ".progress.tmp"
    temporary.write_bytes(canonical(value) + b"\n")
    temporary.replace(directory / "progress.json")


def run_sample(sample_dir, store, scratch, *, output_budget_bytes=2 * 1024**3):
    sample_dir, store, scratch = (
        Path(sample_dir).resolve(),
        Path(store).resolve(),
        Path(scratch).resolve(),
    )
    sample = _read_json(sample_dir / "sample.json")
    if (sample_dir / "benchmark.json").exists():
        return _read_json(sample_dir / "benchmark.json")
    config = read_config(sample_dir / "config.json")
    if digest(config) != sample["config_id"]:
        raise ValueError("Sample configuration differs from frozen selection")
    if type(output_budget_bytes) is not int or output_budget_bytes <= 0:
        raise ValueError("Need explicit output budget")
    pre = preflight(config, store, scratch)
    guard(store, scratch, pre["selected_source_bytes"] + output_budget_bytes)
    started = time.monotonic()
    sample_targets = {u["sha256"]: u for u in sample["units"]}
    records, remaining = [], output_budget_bytes
    with _lock(store, "national"):
        census = freeze_census(config, store, scratch)
        with closing(
            sqlite3.connect((census / "census.sqlite").as_uri() + "?mode=ro", uri=True)
        ) as db:
            db.row_factory = sqlite3.Row
            total = db.execute(
                "SELECT count(DISTINCT sha256) FROM file_observation WHERE url LIKE '%-log.jez' OR url LIKE '%-log.dat'"
            ).fetchone()[0]
            for row in db.execute(
                "SELECT * FROM file_observation WHERE url LIKE '%-log.jez' OR url LIKE '%-log.dat' GROUP BY sha256 ORDER BY sha256"
            ):
                before = time.monotonic()
                _progress(
                    sample_dir,
                    {
                        "state": "running",
                        "pid": os.getpid(),
                        "started": started,
                        "elapsed_seconds": time.monotonic() - started,
                        "completed_objects": len(records),
                        "expected_objects": total,
                        "remaining_output_budget_bytes": remaining,
                    },
                )
                target = process_object(dict(row), store, scratch, output_budget_bytes=remaining)
                artifact = _read_json(target / "artifact.json")
                size = sum(f["bytes"] for f in artifact["files"].values())
                remaining -= size + (target / "artifact.json").stat().st_size + 65
                unit = sample_targets.get(row["sha256"])
                records.append(
                    {
                        "uf": row["uf"],
                        "region": REGIONS[row["uf"]],
                        "source_sha256": row["sha256"],
                        "source_bytes": row["bytes"],
                        "source_url": row["url"],
                        "source_sample_target": unit is not None,
                        "size_band": unit["size_band"] if unit else None,
                        "selection_reason": unit["selection_reason"]
                        if unit
                        else "additional_version_of_selected_section",
                        "artifact": str(target),
                        "artifact_json_sha256": hash_file(target / "artifact.json")[0],
                        "counts": artifact["counts"],
                        "parser_status": artifact["parser"]["status"],
                        "diagnostics": artifact["parser"].get("diagnostics", []),
                        "output_bytes": size,
                        "seconds_including_verification": time.monotonic() - before,
                        "new_parse_seconds": artifact["elapsed_seconds"],
                    }
                )
                print(
                    json.dumps(
                        {
                            "completed": len(records),
                            "expected": total,
                            "uf": row["uf"],
                            "source_bytes": row["bytes"],
                            "events": artifact["counts"]["events"],
                            "status": artifact["parser"]["status"],
                        }
                    ),
                    flush=True,
                )

    def distributions(values):
        values = sorted(values)
        return {
            "n": len(values),
            "min": values[0],
            "median": values[(len(values) - 1) // 2],
            "p95": values[min(len(values) - 1, int(0.95 * len(values)))],
            "max": values[-1],
        }

    grouped = []
    for uf in sorted({r["uf"] for r in records}):
        selected = [r for r in records if r["uf"] == uf]
        grouped.append(
            {
                "uf": uf,
                "objects": len(selected),
                "source_bytes": sum(r["source_bytes"] for r in selected),
                "output_bytes": sum(r["output_bytes"] for r in selected),
                "output_ratio": distributions(
                    [r["output_bytes"] / r["source_bytes"] for r in selected]
                ),
                "elapsed_per_object": distributions(
                    [r["seconds_including_verification"] for r in selected]
                ),
            }
        )
    report = {
        "version": "national-workload-benchmark-v1",
        "sample_id": sample["sample_id"],
        "diagnostic_policy": DIAGNOSTIC_POLICY,
        "finished_at": utc_now(),
        "source_module_sha256": hash_file(Path(__file__))[0],
        "national_module_sha256": hash_file(Path(__file__).with_name("national.py"))[0],
        "preflight": pre,
        "records": records,
        "groups": grouped,
        "elapsed_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "source_bytes": sum(r["source_bytes"] for r in records),
        "output_bytes": sum(r["output_bytes"] for r in records),
        "output_budget_bytes": output_budget_bytes,
        "remaining_output_budget_bytes": remaining,
        "events": sum(r["counts"]["events"] for r in records),
        "partial_objects": sum(r["parser_status"] != "complete" for r in records),
        "output_ratio": distributions([r["output_bytes"] / r["source_bytes"] for r in records]),
        "seconds_per_object": distributions([r["seconds_including_verification"] for r in records]),
        "sample_limits": sample["sampling_limits"],
        "national_processing_complete": False,
    }
    _write_json(sample_dir / "benchmark.json", report)
    _progress(
        sample_dir,
        {
            "state": "complete",
            "pid": os.getpid(),
            "completed_objects": len(records),
            "expected_objects": total,
            "elapsed_seconds": report["elapsed_seconds"],
        },
    )
    return report


def run_compact_sample(
    sample_dir,
    output,
    store,
    scratch,
    *,
    output_budget_bytes=2 * 1024**3,
    compare_payload_report=None,
    batch_rows=16384,
):
    """Budgeted same-source compact experiment, retaining originals in registered CAS."""
    from election_audit.national_storage import iter_compact, payload_rows, process_compact_original

    sample_dir, output, store, scratch = (
        Path(p).resolve() for p in (sample_dir, output, store, scratch)
    )
    sample = _read_json(sample_dir / "sample.json")
    profile = Path(sample["profile"])
    profile_doc = _read_json(profile / "profile.json")
    if hash_file(profile / "profile.json")[0] != sample["profile_sha256"]:
        raise ValueError("Frozen workload profile changed")
    if hash_file(profile / "profile.sqlite") != (
        profile_doc["files"]["profile.sqlite"]["sha256"],
        profile_doc["files"]["profile.sqlite"]["bytes"],
    ):
        raise ValueError("Frozen workload metadata changed")
    if (output / "benchmark.json").exists():
        existing = _read_json(output / "benchmark.json")
        if existing["sample_id"] != sample["sample_id"]:
            raise ValueError("Existing compact report belongs to a different sample")
        return existing
    output.mkdir(parents=True, exist_ok=True)
    comparisons = {}
    if compare_payload_report:
        payload_report = _read_json(Path(compare_payload_report))
        if payload_report["sample_id"] != sample["sample_id"]:
            raise ValueError("Payload comparison uses a different sample")
        comparisons = {r["source_sha256"]: r for r in payload_report["records"]}
    guard(store, scratch, output_budget_bytes)
    records, remaining = [], output_budget_bytes
    started = time.monotonic()
    with (
        _lock(store, "national"),
        closing(
            sqlite3.connect((profile / "profile.sqlite").as_uri() + "?mode=ro", uri=True)
        ) as db,
    ):
        db.row_factory = sqlite3.Row
        for unit in sample["units"]:
            _progress(
                output,
                {
                    "state": "running",
                    "pid": os.getpid(),
                    "completed_objects": len(records),
                    "expected_objects": len(sample["units"]),
                    "remaining_output_budget_bytes": remaining,
                    "elapsed_seconds": time.monotonic() - started,
                },
            )
            source = db.execute("SELECT * FROM sources WHERE url=?", (unit["url"],)).fetchone()
            if source is None or source["sha256"] != unit["sha256"]:
                raise ValueError("Selected source missing from frozen metadata")
            row = {**dict(source), "source_root": profile_doc["source"]["root"]}
            before = time.monotonic()
            artifact = process_compact_original(
                row, store, scratch, output_budget_bytes=remaining, batch_rows=batch_rows
            )
            checkpoint = _read_json(artifact / "checkpoint.json")
            size = (
                sum(f["bytes"] for f in checkpoint["files"].values())
                + (artifact / "checkpoint.json").stat().st_size
                + 65
            )
            remaining -= size
            equality = "not_compared_to_payload"
            actual, actual_n = hashlib.sha256(), 0
            for event in iter_compact(artifact / "events"):
                actual.update(canonical(event) + b"\n")
                actual_n += 1
            if actual_n != checkpoint["counts"]["events"]:
                raise ValueError("Compact checkpoint event count mismatch")
            equality = "full_logical_stream_verified_against_pinned_digest"
            if unit["sha256"] in comparisons:
                ref = comparisons[unit["sha256"]]
                original_path = Path(ref["artifact"])
                if hash_file(original_path / "artifact.json")[0] != ref["artifact_json_sha256"]:
                    raise ValueError("Payload comparison checkpoint changed")
                original_doc = _read_json(original_path / "artifact.json")
                from election_audit.national import _verify_files

                _verify_files(original_path, original_doc)
                expected = hashlib.sha256()
                expected_n = 0
                for event in payload_rows(original_path / "events.parquet"):
                    expected.update(canonical(event) + b"\n")
                    expected_n += 1
                if (
                    expected_n != actual_n
                    or expected.digest() != actual.digest()
                    or checkpoint["counts"] != original_doc["counts"]
                ):
                    raise ValueError(
                        "Compact representation differs from full logical source events"
                    )
                equality = "exact_full_event_stream_digest_and_counts_match"
            record = {
                "uf": unit["uf"],
                "region": REGIONS[unit["uf"]],
                "source_sha256": unit["sha256"],
                "source_bytes": unit["bytes"],
                "size_band": unit["size_band"],
                "selection_reason": unit["selection_reason"],
                "artifact": str(artifact),
                "counts": checkpoint["counts"],
                "parser_status": checkpoint["parser"]["status"],
                "diagnostics": checkpoint["parser"]["diagnostics"],
                "output_bytes": size,
                "processing_seconds": checkpoint["elapsed_seconds"],
                "seconds_including_validation": time.monotonic() - before,
                "logical_equality": equality,
                "original_storage": "read_verified_registered_CAS; external_dependency; no_raw_copy",
            }
            records.append(record)
            _progress(
                output,
                {
                    "state": "running",
                    "pid": os.getpid(),
                    "completed_objects": len(records),
                    "expected_objects": len(sample["units"]),
                    "remaining_output_budget_bytes": remaining,
                    "elapsed_seconds": time.monotonic() - started,
                },
            )
            print(
                json.dumps(
                    {
                        "compact_completed": len(records),
                        "expected": len(sample["units"]),
                        "uf": unit["uf"],
                        "output_bytes": size,
                        "logical_equality": equality,
                    }
                ),
                flush=True,
            )

    def dist(values):
        values = sorted(values)
        return {
            "n": len(values),
            "min": values[0],
            "median": values[(len(values) - 1) // 2],
            "p95": values[min(len(values) - 1, int(0.95 * len(values)))],
            "max": values[-1],
        }

    report = {
        "version": "compact-workload-benchmark-v1",
        "sample_id": sample["sample_id"],
        "finished_at": utc_now(),
        "records": records,
        "elapsed_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "events": sum(r["counts"]["events"] for r in records),
        "source_bytes": sum(r["source_bytes"] for r in records),
        "output_bytes": sum(r["output_bytes"] for r in records),
        "output_budget_bytes": output_budget_bytes,
        "remaining_output_budget_bytes": remaining,
        "output_ratio": dist([r["output_bytes"] / r["source_bytes"] for r in records]),
        "processing_seconds": dist([r["processing_seconds"] for r in records]),
        "partial_objects": sum(r["parser_status"] != "complete" for r in records),
        "raw_original_bytes_copied": 0,
        "original_retention": "registered external collector CAS must remain available; not self-contained original snapshots",
        "resources": {
            "aggregate_memory_budget_bytes": LIMITS["memory_bytes"],
            "workers": 1,
            "requested_event_batch_rows": batch_rows,
            "reuse_note": "verified existing checkpoints keep their original physical batch layout",
            "memory_enforcement": "bounded archives and byte/row batches; no OS RSS limit",
        },
        "national_processing_complete": False,
        "sampling_limits": sample["sampling_limits"],
    }
    _write_json(output / "benchmark.json", report)
    _progress(
        output,
        {
            "state": "complete",
            "pid": os.getpid(),
            "completed_objects": len(records),
            "expected_objects": len(sample["units"]),
            "elapsed_seconds": report["elapsed_seconds"],
        },
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("profile", "select", "run", "compact"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--scratch", type=Path, default=Path(".local-state/national-scratch"))
    parser.add_argument("--per-band", type=int, default=2)
    parser.add_argument("--exclusions", type=Path)
    parser.add_argument("--output-budget-gib", type=float, default=2)
    parser.add_argument("--batch-rows", type=int, default=2048)
    parser.add_argument("--tuning-config", type=Path)
    parser.add_argument("--memory-gib", type=float, default=4)
    parser.add_argument("--hdd-reserve-gib", type=float, default=20)
    parser.add_argument("--ssd-reserve-gib", type=float, default=10)
    parser.add_argument("--scratch-gib", type=float, default=8)
    args = parser.parse_args(argv)
    if args.action == "profile":
        if args.config is None or args.output is None:
            parser.error("profile needs config and output")
        config = read_config(args.config)
        if len(config["sources"]) != 1:
            parser.error("profile one round at a time")
        print(profile_source(config["sources"][0], args.output, args.scratch))
    elif args.action == "select":
        if args.profile is None or args.output is None:
            parser.error("select needs profile and output")
        sample = select_sample(
            args.profile, args.output, per_band=args.per_band, exclusions=args.exclusions
        )
        print(
            json.dumps(
                {
                    "sample_id": sample["sample_id"],
                    "units": len(sample["units"]),
                    "regions": sample["regions"],
                }
            )
        )
    elif args.action == "compact":
        if args.sample is None or args.store is None or args.output is None:
            parser.error("compact needs sample, store and output")
        from election_audit.national_tuning import configure_production, limits, recommendation

        policy = limits(
            int(args.memory_gib * 1024**3),
            int(args.output_budget_gib * 1024**3),
            900,
            int(args.hdd_reserve_gib * 1024**3),
            int(args.ssd_reserve_gib * 1024**3),
            int(args.scratch_gib * 1024**3),
        )
        if args.tuning_config:
            selected = recommendation(args.tuning_config)
            policy, args.batch_rows = selected["resources"], selected["event_batch_rows"]
        configure_production(policy)
        report = run_compact_sample(
            args.sample,
            args.output,
            args.store,
            args.scratch,
            output_budget_bytes=int(args.output_budget_gib * 1024**3),
            batch_rows=args.batch_rows,
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("events", "output_bytes", "elapsed_seconds", "partial_objects")
                }
            )
        )
    else:
        if args.sample is None or args.store is None:
            parser.error("run needs sample and store")
        report = run_sample(
            args.sample,
            args.store,
            args.scratch,
            output_budget_bytes=int(args.output_budget_gib * 1024**3),
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("events", "output_bytes", "elapsed_seconds", "partial_objects")
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
