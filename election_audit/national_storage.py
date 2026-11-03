"""Lossless structural event encoding; deterministic IDs are reconstructed on read."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.national import _read_json, _sync_dir, _write_json
from election_audit.source_inventory import canonical, hash_file, identity

FORMAT = "structural-events-compact-v1"
FIELDS = {
    "event_id",
    "object_sha256",
    "record_locator",
    "source_sequence",
    "source_line_sha256",
    "device_timestamp_raw",
    "device_id_raw",
    "application",
    "level",
    "event_kind",
    "selection_state",
    "parser_version",
}
TEXT_FIELDS = ("device_timestamp_raw", "device_id_raw", "application", "level", "event_kind")
SCHEMA = pa.schema(
    [
        ("source_sequence", pa.int64()),
        ("line_number", pa.int64()),
        ("member_key", pa.int32()),
        ("source_line_sha256", pa.binary(32)),
        *[(f, pa.string()) for f in TEXT_FIELDS],
    ]
)


def write_compact(rows, directory, *, object_sha256, parser_version, config, batch_rows=2048):
    """Consume bounded rows, preserving every logical field and an exact stream digest."""
    if type(batch_rows) is not int or batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "events.parquet"
    members, keys, batch = [], {}, []
    member_bytes, batch_bytes, count, previous = 0, 0, 0, 0
    logical = hashlib.sha256()
    try:
        with pq.ParquetWriter(
            output, SCHEMA, compression="zstd", use_dictionary=list(TEXT_FIELDS)
        ) as writer:
            for row in rows:
                if (
                    set(row) != FIELDS
                    or row["object_sha256"] != object_sha256
                    or row["parser_version"] != parser_version
                    or row["selection_state"] != "context_unresolved"
                ):
                    raise ValueError("Unsupported structural event shape or context")
                locator = row["record_locator"]
                if (
                    set(locator)
                    != {"archive_segments", "line_start", "line_end", "byte_start", "byte_end"}
                    or locator["byte_start"] is not None
                    or locator["byte_end"] is not None
                    or type(locator["line_start"]) is not int
                    or locator["line_start"] <= 0
                    or locator["line_end"] != locator["line_start"]
                ):
                    raise ValueError("Unsupported event locator")
                if row["event_id"] != identity(
                    "structural-event", [object_sha256, locator, parser_version, config]
                ):
                    raise ValueError("Event identity is inconsistent with its source")
                if type(row["source_sequence"]) is not int or row["source_sequence"] <= previous:
                    raise ValueError("Source sequence must strictly increase")
                previous = row["source_sequence"]
                sha = row["source_line_sha256"]
                if not isinstance(sha, str) or len(sha) != 64 or sha != sha.lower():
                    raise ValueError("Invalid original line digest")
                binary = bytes.fromhex(sha)
                if len(binary) != 32 or not all(isinstance(row[f], str) for f in TEXT_FIELDS):
                    raise ValueError("Invalid structural field type")
                encoded = canonical(locator["archive_segments"])
                if encoded not in keys:
                    member_bytes += len(encoded)
                    if member_bytes > 16 * 1024**2:
                        raise ValueError("Compact member template budget exceeded")
                    keys[encoded] = len(members)
                    members.append(json.loads(encoded))
                compact = {
                    "source_sequence": row["source_sequence"],
                    "line_number": locator["line_start"],
                    "member_key": keys[encoded],
                    "source_line_sha256": binary,
                    **{f: row[f] for f in TEXT_FIELDS},
                }
                batch.append(compact)
                batch_bytes += len(encoded) + sum(len(row[f].encode()) for f in TEXT_FIELDS) + 64
                logical.update(canonical(row) + b"\n")
                count += 1
                if len(batch) >= batch_rows or batch_bytes >= 8 * 1024**2:
                    writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                    batch = []
                    batch_bytes = 0
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
        with output.open("rb") as f:
            os.fsync(f.fileno())
        _write_json(
            directory / "compact.json",
            {
                "version": FORMAT,
                "object_sha256": object_sha256,
                "parser_version": parser_version,
                "config": config,
                "selection_state": "context_unresolved",
                "members": members,
                "count": count,
                "logical_events_sha256": logical.hexdigest(),
                "files": {
                    "events.parquet": dict(zip(("sha256", "bytes"), hash_file(output), strict=True))
                },
            },
        )
        _sync_dir(directory)
    except BaseException:
        # Caller owns unpublished staging; no corrupt success marker is produced.
        raise
    return directory


def iter_compact(directory, *, batch_rows=2048):
    directory = Path(directory)
    doc = _read_json(directory / "compact.json")
    if doc["version"] != FORMAT:
        raise ValueError("Unsupported compact event format")
    file = directory / "events.parquet"
    if file.is_symlink() or hash_file(file) != (
        doc["files"]["events.parquet"]["sha256"],
        doc["files"]["events.parquet"]["bytes"],
    ):
        raise ValueError("Compact event integrity mismatch")
    logical = hashlib.sha256()
    count = 0
    for batch in pq.ParquetFile(file).iter_batches(batch_size=batch_rows):
        for item in batch.to_pylist():
            key = item["member_key"]
            if type(key) is not int or not 0 <= key < len(doc["members"]):
                raise ValueError("Invalid compact member key")
            locator = {
                "archive_segments": doc["members"][key],
                "line_start": item["line_number"],
                "line_end": item["line_number"],
                "byte_start": None,
                "byte_end": None,
            }
            row = {
                "event_id": identity(
                    "structural-event",
                    [doc["object_sha256"], locator, doc["parser_version"], doc["config"]],
                ),
                "object_sha256": doc["object_sha256"],
                "record_locator": locator,
                "source_sequence": item["source_sequence"],
                "source_line_sha256": item["source_line_sha256"].hex(),
                "selection_state": doc["selection_state"],
                "parser_version": doc["parser_version"],
                **{f: item[f] for f in TEXT_FIELDS},
            }
            logical.update(canonical(row) + b"\n")
            count += 1
            yield row
    if count != doc["count"] or logical.hexdigest() != doc["logical_events_sha256"]:
        raise ValueError("Compact logical event digest mismatch")


def payload_rows(path):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=2048, columns=["payload"]):
        for value in batch.column(0).to_pylist():
            yield json.loads(value)


def registered_original(row):
    """A verified external CAS dependency; explicitly not a self-contained snapshot."""
    from election_audit.national import _validate_row
    from election_audit.source_inventory import safe_source

    _validate_row(row)
    from election_audit.national_relocation import relocated_root

    root = relocated_root(row["source_root"], row["path"], row["sha256"], row["bytes"])
    relative = Path(row["path"])
    if (
        len(relative.parts) != 3
        or relative.parts[:2] != ("objects", row["sha256"][:2])
        or relative.name not in (row["sha256"] + ".jez", row["sha256"] + ".dat")
    ):
        raise ValueError("Source is not in the collector content-addressed namespace")
    lexical = root / relative
    if lexical.is_symlink():
        raise ValueError("CAS reference cannot be a symlink")
    source = safe_source(root, str(relative))
    if hash_file(source) != (row["sha256"], row["bytes"]):
        raise ValueError("Registered original digest mismatch")
    return {
        "version": "registered-collector-cas-v1",
        "kind": "external_original_dependency",
        "self_contained": False,
        "root": str(root),
        "relative_path": str(relative),
        "object_sha256": row["sha256"],
        "bytes": row["bytes"],
        "official_url": row["url"],
        "requirement": "retain this source store; verify original bytes on every processing/cache use; no original bytes copied or modified",
    }


def resolve_original(reference):
    if (
        reference.get("version") != "registered-collector-cas-v1"
        or reference.get("self_contained") is not False
    ):
        raise ValueError("Unsupported original reference")
    row = {
        "source_root": reference["root"],
        "path": reference["relative_path"],
        "sha256": reference["object_sha256"],
        "bytes": reference["bytes"],
        "url": reference["official_url"],
    }
    verified = registered_original(row)
    return Path(verified["root"]) / verified["relative_path"]


def process_compact_original(row, store, scratch, *, output_budget_bytes, batch_rows=16384):
    """Publish lossless compact facts while retaining the registered raw CAS in place."""
    import resource
    import shutil
    import tempfile
    import time

    from election_audit.archive_parsing import ParseConfig
    from election_audit.national import (
        DIAGNOSTIC_POLICY,
        LIMITS,
        _compact_jsonl,
        _destinations,
        _lock,
        _parse_bounded,
        _verify_files,
        guard,
    )
    from election_audit.source_inventory import digest, utc_now

    if type(output_budget_bytes) is not int or output_budget_bytes <= 0:
        raise ValueError("Explicit positive compact output budget required")
    if type(batch_rows) is not int or not 1 <= batch_rows <= 65536:
        raise ValueError("Compact batch_rows must be between 1 and 65536")
    store, scratch = Path(store).resolve(), Path(scratch).resolve()
    _destinations({"sources": [{"root": row["source_root"]}]}, store, scratch)
    reference = registered_original(row)
    config = ParseConfig().__dict__
    key = digest([row["sha256"], FORMAT, DIAGNOSTIC_POLICY, config])
    target = store / "compact" / key[:2] / key
    with _lock(store, "compact-" + row["sha256"]):
        if target.exists():
            doc = _read_json(target / "checkpoint.json")
            if doc["version"] != FORMAT or doc["object_sha256"] != row["sha256"]:
                raise ValueError("Compact checkpoint identity mismatch")
            _verify_files(target, doc)
            resolve_original(doc["original_reference"])
            return target
        guard(store, scratch, min(output_budget_bytes, 8 * 1024**3))
        scratch.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="compact-object-", dir=scratch))
        staging = Path(tempfile.mkdtemp(prefix=".compact-", dir=target.parent))
        started = time.monotonic()
        try:
            parser = _parse_bounded(resolve_original(reference), work, row["sha256"])

            def events():
                with (work / "events.jsonl").open() as source:
                    for line in source:
                        yield json.loads(line)

            write_compact(
                events(),
                staging / "events",
                object_sha256=row["sha256"],
                parser_version=parser["parser_version"],
                config=parser["config"],
                batch_rows=batch_rows,
            )
            issues = _compact_jsonl(work / "issues.jsonl", staging / "issues.parquet", 2048)
            files = {
                str(f.relative_to(staging)): dict(
                    zip(("sha256", "bytes"), hash_file(f), strict=True)
                )
                for f in staging.rglob("*")
                if f.is_file()
            }
            actual = sum(s["bytes"] for s in files.values())
            if actual + 1024**2 > output_budget_bytes:
                raise OSError("Compact output budget exhausted before publication")
            guard(store, scratch)
            resolve_original(reference)
            _write_json(
                staging / "checkpoint.json",
                {
                    "version": FORMAT,
                    "diagnostic_policy": DIAGNOSTIC_POLICY,
                    "object_sha256": row["sha256"],
                    "source_bytes": row["bytes"],
                    "original_reference": reference,
                    "self_contained_originals": False,
                    "parser": parser,
                    "counts": {
                        "events": _read_json(staging / "events/compact.json")["count"],
                        "issues": issues,
                    },
                    "files": files,
                    "elapsed_seconds": time.monotonic() - started,
                    "resources": {
                        "aggregate_memory_budget_bytes": LIMITS["memory_bytes"],
                        "workers": 1,
                        "event_batch_rows": batch_rows,
                        "event_batch_byte_limit": 8 * 1024**2,
                        "memory_enforcement": "bounded archives and byte/row batches; no OS RSS limit",
                    },
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "published_at": utc_now(),
                    "scientific_eligibility": "unavailable_structural_only",
                    "overlap_resolution": "not_performed_cross_object",
                },
            )
            staging.rename(target)
            _sync_dir(target.parent)
        except BaseException as exc:
            shutil.rmtree(staging)
            failure_directory = store / "failures"
            failure_directory.mkdir(parents=True, exist_ok=True)
            _write_json(
                failure_directory / ("compact-" + key + "-" + str(time.time_ns()) + ".json"),
                {
                    "version": FORMAT,
                    "object_sha256": row["sha256"],
                    "at": utc_now(),
                    "exception_type": type(exc).__name__,
                    "state": "failed_not_published",
                },
            )
            raise
        finally:
            shutil.rmtree(work)
    return target
