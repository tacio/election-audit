"""Compact typed analytical Parquet over a consistent committed-shard snapshot.

Recovery shards remain an ingestion detail. Analytical consumers open these large
parts, never one checkpoint per electoral unit. No ordinary event lake is emitted.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from election_audit.national_migration import atomic, sha
from election_audit.national_parallel import encoded, load
from election_audit.national_resources import apply
from election_audit.national_summary_tools import verify_shard

VERSION = "source-summary-analysis-release-v1"


def allocated(path):
    return sum(p.stat().st_blocks * 512 for p in [Path(path), *Path(path).rglob("*")])


def settle_budget(live_path, output) -> None:
    actual = allocated(output)
    with closing(sqlite3.connect(live_path)) as budget:
        budget.execute("PRAGMA synchronous=FULL")
        budget.execute("BEGIN IMMEDIATE")
        row = budget.execute(
            "SELECT reserved,state FROM analysis_reservations WHERE output=?", (str(output),)
        ).fetchone()
        if row is None:
            raise ValueError("Published analysis has no quota provenance")
        if row[1] == "reserved":
            if actual > row[0]:
                raise OSError("Published allocation exceeds reserved analytical allowance")
            budget.execute(
                "UPDATE metadata SET value=CAST(value AS INTEGER)-?+? WHERE key='released_bytes'",
                (row[0], actual),
            )
            budget.execute(
                "UPDATE analysis_reservations SET state='published',actual=? WHERE output=?",
                (actual, str(output)),
            )
        budget.commit()


def publish_release(directory, output, *, target_bytes=128 * 1024**2):
    if not 1024**2 <= target_bytes <= 256 * 1024**2:
        raise ValueError("Parquet targets must be 1..256MiB; portable default128MiB")
    directory, output = Path(directory).absolute(), Path(output).absolute()
    spec = load(directory)
    r = spec["resources"]
    if sha(spec["scope"]) != spec["scope_sha256"]:
        raise ValueError("Frozen source scope changed")
    for cert in json.loads(Path(spec["relocation_registry"]["path"]).read_text())["certificates"]:
        if any(output.is_relative_to(Path(cert[k])) for k in ("root", "old_root")):
            raise ValueError("Analysis output must remain outside raw originals")
    # One finalizer, no worker pool: retain supervisor/headroom while giving the
    # Arrow process a bounded address space under the shared4GiB RSS cgroup.
    apply(
        {
            **r,
            "worker_address_space_bytes": r["aggregate_memory_bytes"] - r["parent_allowance_bytes"],
        },
        worker=True,
    )
    import pyarrow as pa
    import pyarrow.parquet as pq

    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < r["hdd_reserve_bytes"] + r[
        "future_budget_bytes"
    ] + min(8 * 1024**3, r["output_budget_bytes"]):
        raise OSError("Analytical publication reserve failed")
    lock = (Path(spec["store"]) / ".lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        live_path = Path(spec["store"]) / "work.sqlite"
        if output.exists():
            if output.is_symlink():
                raise ValueError("Analysis output cannot be a symlink")
            manifest = json.loads((output / "manifest.json").read_text())
            expected = hashlib.sha256(
                encoded({k: v for k, v in manifest.items() if k != "release_id"}).encode()
            ).hexdigest()
            if (
                manifest["release_id"] != expected
                or manifest["producer_job_id"] != spec["job_id"]
                or sha(output / "audit-state.sqlite") != manifest["audit_state_sha256"]
            ):
                raise ValueError("Existing analytical release identity mismatch")
            expected_files = set(manifest["files"]) | {"manifest.json", "audit-state.sqlite"}
            actual_files = set()
            for path in output.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Analytical artifact cannot contain symlinks")
                if path.is_file():
                    actual_files.add(str(path.relative_to(output)))
            if actual_files != expected_files:
                raise ValueError("Analytical artifact inventory differs")
            for relative, pin in manifest["files"].items():
                path = output / relative
                if (
                    Path(relative).is_absolute()
                    or ".." in Path(relative).parts
                    or path.is_symlink()
                    or sha(path) != pin["sha256"]
                    or path.stat().st_size != pin["bytes"]
                ):
                    raise ValueError("Existing analytical part checksum mismatch")
            settle_budget(live_path, output)
            return manifest
        temporary = Path(tempfile.mkdtemp(prefix=".summary-release-", dir=output.parent))
        ledger = temporary / "audit-state.sqlite"
        with closing(sqlite3.connect(live_path)) as budget:
            budget.execute("PRAGMA synchronous=FULL")
            budget.execute("BEGIN IMMEDIATE")
            budget.execute("INSERT OR IGNORE INTO metadata VALUES('released_bytes','0')")
            budget.execute(
                "CREATE TABLE IF NOT EXISTS analysis_reservations(output TEXT PRIMARY KEY,reserved INTEGER,actual INTEGER,state TEXT)"
            )
            meta = dict(
                budget.execute(
                    "SELECT key,CAST(value AS INTEGER) FROM metadata WHERE key!='initialised'"
                )
            )
            allowance = min(
                8 * 1024**3,
                r["output_budget_bytes"]
                - min(2 * 1024**3, r["output_budget_bytes"] // 4)
                - meta["bytes"]
                - meta["released_bytes"],
            )
            if allowance < 1024**2:
                raise OSError("Combined recovery/analysis output budget exhausted")
            budget.execute(
                "UPDATE metadata SET value=CAST(value AS INTEGER)+? WHERE key='released_bytes'",
                (allowance,),
            )
            budget.execute(
                "INSERT INTO analysis_reservations VALUES(?,?,NULL,'reserved')",
                (str(output), allowance),
            )
            budget.commit()
        with (
            closing(
                sqlite3.connect(
                    (Path(spec["store"]) / "work.sqlite").as_uri() + "?mode=ro", uri=True
                )
            ) as source,
            closing(sqlite3.connect(ledger)) as snapshot,
        ):
            source.backup(snapshot)
        with ledger.open("rb") as stream:
            os.fsync(stream.fileno())
        schemas = {
            "source_summaries": pa.schema(
                [
                    ("object_sha256", pa.binary(32)),
                    ("parser_status", pa.string()),
                    ("observed_lines", pa.int64()),
                    ("observed_events", pa.int64()),
                    ("observed_unknown", pa.int64()),
                    ("observed_authorizations", pa.int64()),
                    ("observed_completions", pa.int64()),
                    ("observed_manual_requests", pa.int64()),
                    ("error_count", pa.int64()),
                    ("diagnostics_json", pa.string()),
                    ("session_readiness", pa.string()),
                    ("clock_readiness", pa.string()),
                    ("feature_readiness", pa.string()),
                ]
            ),
            "members": pa.schema(
                [
                    ("object_sha256", pa.binary(32)),
                    ("member", pa.int32()),
                    ("locator_json", pa.string()),
                    ("first_sequence", pa.int64()),
                    ("physical_lines", pa.int64()),
                    ("observed_events", pa.int64()),
                    ("observed_unknown", pa.int64()),
                    ("first_reading", pa.string()),
                    ("last_reading", pa.string()),
                    ("minimum_reading", pa.string()),
                    ("maximum_reading", pa.string()),
                    ("raw_reversals", pa.int64()),
                    ("stream_changes", pa.int64()),
                ]
            ),
            "blocks": pa.schema(
                [
                    ("object_sha256", pa.binary(32)),
                    ("member", pa.int32()),
                    ("first_line", pa.int64()),
                    ("last_line", pa.int64()),
                    ("block_sha256", pa.binary(32)),
                    ("bytes", pa.int64()),
                    ("observed_events", pa.int64()),
                    ("observed_unknown", pa.int64()),
                ]
            ),
            "source_index": pa.schema(
                [
                    ("object_sha256", pa.binary(32)),
                    ("cas_relative_path", pa.string()),
                    ("bytes", pa.int64()),
                    ("round", pa.int32()),
                    ("publisher_witnesses", pa.int64()),
                    ("processing_scope", pa.string()),
                    ("summary_state", pa.string()),
                ]
            ),
            "source_witnesses": pa.schema(
                [
                    ("object_sha256", pa.binary(32)),
                    ("uf", pa.string()),
                    ("municipality", pa.string()),
                    ("zone", pa.string()),
                    ("section", pa.string()),
                    ("official_url", pa.string()),
                    ("processing_scope", pa.string()),
                    ("summary_state", pa.string()),
                ]
            ),
        }
        files = {}
        tables = {}
        spent = ledger.stat().st_size
        if spent > allowance:
            raise OSError("Audit snapshot exceeds analytical output allowance")

        class Writer:
            def __init__(self, name) -> None:
                self.name = name
                self.schema = schemas[name]
                self.rows = []
                self.buffer_bytes = 0
                self.count = 0
                self.part = 0
                self.writer = None
                self.sink = None
                self.paths = []

            def open(self) -> None:
                path = temporary / self.name / f"part-{self.part:05d}.parquet"
                path.parent.mkdir(exist_ok=True)
                self.path = path
                self.sink = pa.OSFile(str(path), "wb")
                self.writer = pq.ParquetWriter(
                    self.sink, self.schema, compression="zstd", use_dictionary=True
                )

            def put(self, row) -> None:
                size = sum(len(v) if isinstance(v, (str, bytes)) else 16 for v in row.values())
                if size > 32 * 1024**2:
                    raise MemoryError("Analytical row exceeds bounded payload")
                if self.rows and (len(self.rows) >= 2048 or self.buffer_bytes + size > 8 * 1024**2):
                    self.flush()
                self.rows.append(row)
                self.buffer_bytes += size
                self.count += 1

            def flush(self) -> None:
                if not self.rows:
                    return
                if self.writer is None:
                    self.open()
                self.writer.write_table(pa.Table.from_pylist(self.rows, schema=self.schema))
                self.rows = []
                self.buffer_bytes = 0
                if self.sink.tell() >= target_bytes:
                    self.close_part()

            def close_part(self) -> None:
                nonlocal spent
                if self.writer is None:
                    return
                self.writer.close()
                self.sink.close()
                self.writer = self.sink = None
                size = self.path.stat().st_size
                if size > target_bytes + 64 * 1024**2:
                    raise MemoryError("Parquet part exceeded bounded row-group overshoot")
                with self.path.open("rb") as f:
                    os.fsync(f.fileno())
                relative = str(self.path.relative_to(temporary))
                files[relative] = {"sha256": sha(self.path), "bytes": size}
                self.paths.append(relative)
                spent += size
                self.part += 1
                if spent > allowance:
                    raise OSError("Bounded analytical output allowance exceeded")

            def finish(self) -> None:
                self.flush()
                self.close_part()
                if not self.paths:
                    self.open()
                    self.close_part()
                tables[self.name] = {"rows": self.count, "files": self.paths}

        writers = {name: Writer(name) for name in schemas}
        with closing(sqlite3.connect(ledger, uri=True)) as snapshot:
            for (group,) in snapshot.execute("SELECT id FROM groups ORDER BY id"):
                path = Path(spec["store"]) / "shards" / group[:2] / group
                marker = verify_shard(path, spec["job_id"])
                with closing(
                    sqlite3.connect(
                        (path / "summary.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
                    )
                ) as shard:
                    mapping = {
                        row[0]: bytes.fromhex(row[1])
                        for row in shard.execute("SELECT object_id,sha FROM objects")
                    }
                    if sorted(v.hex() for v in mapping.values()) != marker["objects"]:
                        raise ValueError("Analytical source population differs")
                    for object_id, payload in shard.execute(
                        "SELECT object_id,payload FROM objects ORDER BY object_id"
                    ):
                        d = json.loads(payload)
                        c = d["counts"]
                        k = d["event_kinds"]
                        writers["source_summaries"].put(
                            dict(
                                zip(
                                    schemas["source_summaries"].names,
                                    [
                                        mapping[object_id],
                                        d["status"],
                                        c.get("lines", 0),
                                        c.get("events", 0),
                                        k.get("unknown", 0),
                                        k.get("authorization_message", 0),
                                        k.get("completion_message", 0),
                                        k.get("manual_request_message", 0),
                                        sum(
                                            n
                                            for code, severity, n in d["diagnostics"]
                                            if severity == "error"
                                        ),
                                        encoded(d["diagnostics"]),
                                        "unavailable",
                                        "unavailable",
                                        "unavailable_structural_only",
                                    ],
                                    strict=True,
                                )
                            )
                        )
                    for object_id, payload in shard.execute(
                        "SELECT object_id,payload FROM members ORDER BY object_id,member"
                    ):
                        member = json.loads(payload)
                        writers["members"].put(
                            dict(
                                zip(
                                    schemas["members"].names,
                                    [
                                        mapping[object_id],
                                        member[0],
                                        encoded(member[1]),
                                        *member[2:],
                                    ],
                                    strict=True,
                                )
                            )
                        )
                    for row in shard.execute(
                        "SELECT * FROM blocks ORDER BY object_id,member,first_line"
                    ):
                        writers["blocks"].put(
                            dict(
                                zip(
                                    schemas["blocks"].names,
                                    [mapping[row[0]], *row[1:]],
                                    strict=True,
                                )
                            )
                        )
            snapshot.execute(
                "ATTACH DATABASE ? AS scope", (Path(spec["scope"]).as_uri() + "?mode=ro",)
            )
            for h, path, size, n, processing, state in snapshot.execute(
                "SELECT s.sha256,min(s.path),min(s.bytes),count(*),min(s.processing_scope),w.status FROM scope.observations s LEFT JOIN work w ON w.sha=s.sha256 GROUP BY s.sha256 ORDER BY s.sha256"
            ):
                state = (
                    "deferred_protected_or_stress"
                    if processing != "eligible_structural_preprocessing"
                    else (state or "outside_requested_selection")
                )
                writers["source_index"].put(
                    dict(
                        zip(
                            schemas["source_index"].names,
                            [bytes.fromhex(h), path, size, spec["round"], n, processing, state],
                            strict=True,
                        )
                    )
                )
            for h, uf, mun, zone, section, url, processing, state in snapshot.execute(
                "SELECT s.sha256,s.uf,s.municipality,s.zone,s.section,s.url,s.processing_scope,w.status FROM scope.observations s LEFT JOIN work w ON w.sha=s.sha256 ORDER BY s.url"
            ):
                state = (
                    "deferred_protected_or_stress"
                    if processing != "eligible_structural_preprocessing"
                    else (state or "outside_requested_selection")
                )
                writers["source_witnesses"].put(
                    dict(
                        zip(
                            schemas["source_witnesses"].names,
                            [bytes.fromhex(h), uf, mun, zone, section, url, processing, state],
                            strict=True,
                        )
                    )
                )
            counters = dict(
                snapshot.execute(
                    "SELECT key,CAST(value AS INTEGER) FROM metadata WHERE key!='initialised'"
                )
            )
        for writer in writers.values():
            writer.finish()
        manifest = {
            "version": VERSION,
            "producer_job_id": spec["job_id"],
            "source_scope_sha256": spec["scope_sha256"],
            "registry_sha256": spec["relocation_registry"]["sha256"],
            "audit_state_sha256": sha(ledger),
            "tables": tables,
            "files": files,
            "target_part_bytes": target_bytes,
            "completed_source_objects": counters["completed"],
            "requested_source_objects": counters["total"],
            "complete_requested_scope": counters["completed"] == counters["total"],
            "full_national_complete": False,
            "scientific_eligibility": "unavailable_structural_only",
            "unknown_policy": "uncommitted/excluded/outside-selection summaries are absent, never zero; observed counts on partial parses are lower-bound observations, not complete totals",
            "raw_dependencies": "immutable original CAS required only for forensic replay; ordinary analytical queries require these Parquet tables only",
            "checkpoint_dependencies": "SQLite ingestion shards are not required for ordinary Parquet analytical queries; retained for recovery/evidence",
            "no_event_lake": True,
            "writer_code_sha256": sha(Path(__file__)),
            "pyarrow_version": pa.__version__,
            "population_rule": "Available source witnesses are not the expected registered population; absent publisher units require independent coverage/composition inputs",
        }
        manifest["release_id"] = hashlib.sha256(encoded(manifest).encode()).hexdigest()
        atomic(temporary / "manifest.json", manifest)
        for child in [p for p in temporary.iterdir() if p.is_dir()]:
            fd = os.open(child, os.O_DIRECTORY)
            os.fsync(fd)
            os.close(fd)
        fd = os.open(temporary, os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
        if allocated(temporary) > allowance:
            raise OSError("Analytical allocated-byte cap exceeded before publication")
        os.rename(temporary, output)
        fd = os.open(output.parent, os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
        settle_budget(live_path, output)
        return manifest
    except BaseException:
        # Retain unpublished diagnostics; no success manifest/destination exists.
        raise
    finally:
        lock.close()
