"""Immutable, bounded operational DuckDB/Parquet releases from frozen artifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.archive_parsing import FrozenParseReader, _read_checked, _rows, _write_checked
from election_audit.contracts import load_contract, validate_rows
from election_audit.reconstruction import (
    EXTRA_TABLES,
    TABLES,
    inspect_reconstruction,
    load_reconstruction_context,
    reconstruct_parse,
)
from election_audit.snapshots import _fsync_directory
from election_audit.source_inventory import canonical, digest, hash_file
from election_audit.types import JSON, Row, one

VERSION = "operational-release-v1"
FACTS = (
    "selected_event",
    "anonymous_cycle",
    "record_lineage",
    "parsing_issue",
    "event_evidence",
    "cycle_gaps",
    "interruptions",
)
EXTRA_KEYS = {
    "event_evidence": ["event_id"],
    "session_summaries": ["session_id"],
    "cycle_gaps": ["session_id", "previous_cycle_id", "next_cycle_id"],
    "interruptions": ["session_id", "start_event_id", "end_event_id"],
    "operational_coverage": ["snapshot_id", "section_id"],
    "processing_event_availability": ["snapshot_id", "package_id", "event_kind"],
    "late_voting": ["session_id"],
}
SCHEMA = load_contract()["tables"]
TYPES = {
    "text": "VARCHAR",
    "sha256": "VARCHAR",
    "integer": "BIGINT",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "instant": "TIMESTAMPTZ",
    "json": "JSON",
}
ARROW = {
    "text": pa.string(),
    "sha256": pa.string(),
    "integer": pa.int64(),
    "number": pa.float64(),
    "boolean": pa.bool_(),
    "date": pa.string(),
    "instant": pa.string(),
    "json": pa.string(),
}


class PublicationError(ValueError):
    """Input, integrity, cardinality or resource failure before publication."""


@dataclass(frozen=True)
class ResourceConfig:
    parser_workers: int = 4
    duckdb_threads: int = 4
    memory_bytes: int = 12 * 1024**3
    spill_bytes: int = 8 * 1024**3
    reserve_bytes: int = 10 * 1024**3
    batch_rows: int = 2048
    max_events: int = 100_000

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if type(value) is not int or value < (0 if key == "reserve_bytes" else 1):
                raise PublicationError(f"Invalid resource setting: {key}")
        if self.parser_workers > 64 or self.duckdb_threads > 64 or self.batch_rows > 100_000:
            raise PublicationError("Worker/thread/batch limit exceeded")


def _guard(path: str | Path, config: ResourceConfig, extra_bytes: int = 0) -> None:
    if shutil.disk_usage(path).free < config.reserve_bytes + config.spill_bytes + extra_bytes:
        raise PublicationError("SSD free space cannot preserve reserve plus spill cap")


def _configure(
    connection: duckdb.DuckDBPyConnection, temporary: str | Path, config: ResourceConfig
) -> None:
    connection.execute(f"SET threads={config.duckdb_threads}")
    connection.execute(f"SET memory_limit='{config.memory_bytes}B'")
    connection.execute(f"SET max_temp_directory_size='{config.spill_bytes}B'")
    connection.execute("SET temp_directory=?", [str(temporary)])
    connection.execute("SET preserve_insertion_order=false")


def _columns(name: str) -> dict[str, str]:
    if name in SCHEMA:
        return {key: spec["type"] for key, spec in SCHEMA[name]["fields"].items()}
    return dict.fromkeys(EXTRA_KEYS[name], "text")


def _create(connection: duckdb.DuckDBPyConnection, name: str) -> None:
    fields = ",".join(f'"{key}" {TYPES[kind]}' for key, kind in _columns(name).items())
    connection.execute(f'CREATE TABLE "{name}" ({fields}, payload JSON NOT NULL)')


def _encoded(name: str, rows: Iterable[Row]) -> pa.Table:
    columns = _columns(name)
    result = []
    for row in rows:
        item = {
            key: canonical(row.get(key)).decode()
            if kind == "json" and row.get(key) is not None
            else row.get(key)
            for key, kind in columns.items()
        }
        item["payload"] = canonical(row).decode()
        result.append(item)
    schema = pa.schema(
        [(key, ARROW[kind]) for key, kind in columns.items()] + [("payload", pa.string())]
    )
    return pa.Table.from_pylist(result, schema=schema)


def _batches[T](rows: Iterable[T], size: int) -> Iterator[list[T]]:
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _insert(connection: duckdb.DuckDBPyConnection, name: str, rows: list[Row]) -> None:
    if not rows:
        return
    connection.register("incoming", _encoded(name, rows))
    try:
        connection.execute(f'INSERT INTO "{name}" SELECT * FROM incoming')
    finally:
        connection.unregister("incoming")


def _fact_view(connection: duckdb.DuckDBPyConnection, name: str, files: Iterable[str]) -> None:
    literals = ",".join("'" + file.replace("'", "''") + "'" for file in files)
    connection.execute(
        f'CREATE TEMP VIEW "{name}" AS SELECT * FROM read_parquet([{literals}], hive_partitioning=false)'
    )


def _attach_facts(
    connection: duckdb.DuckDBPyConnection, path: Path, tables: Mapping[str, JSON]
) -> None:
    for name in FACTS:
        files = sorted(str(path / f) for f in tables.get(name, {}).get("files", []))
        if files:
            _fact_view(connection, name, files)
        else:
            _create(connection, name)


def _validate(connection: duckdb.DuckDBPyConnection, names: Iterable[str]) -> list[str]:
    """Verify grains, many-to-one joins and operational accounting on disk."""
    errors, unavailable = [], []
    for name in names:
        spec = SCHEMA.get(name)
        keys = [spec["primary_key"], *spec["unique_keys"]] if spec else [EXTRA_KEYS[name]]
        for key in keys:
            fields = ",".join(f'"{k}"' for k in key)
            count = one(
                connection.execute(
                    f'SELECT count(*) FROM (SELECT {fields} FROM "{name}" GROUP BY {fields} '
                    "HAVING count(*)>1)"
                ).fetchone()
            )[0]
            if count:
                errors.append(f"{name}: duplicate key {key}")
        if not spec:
            continue
        for key in spec["primary_key"]:
            if one(
                connection.execute(
                    f'SELECT count(*) FROM "{name}" WHERE "{key}" IS NULL'
                ).fetchone()
            )[0]:
                errors.append(f"{name}: null primary key")
        for fk in spec["foreign_keys"]:
            target = fk["table"]
            if target not in names:
                unavailable.append(f"{name}->{target}: frozen context unavailable")
                continue
            present = " AND ".join(f'a."{k}" IS NOT NULL' for k in fk["fields"])
            join = " AND ".join(
                f'a."{a}"=b."{b}"' for a, b in zip(fk["fields"], fk["references"], strict=True)
            )
            if one(
                connection.execute(
                    f'SELECT count(*) FROM "{name}" a WHERE {present} AND NOT EXISTS '
                    f'(SELECT 1 FROM "{target}" b WHERE {join})'
                ).fetchone()
            )[0]:
                errors.append(f"{name}: foreign key to {target}")
    if {"anonymous_cycle", "selected_event"} <= set(names):
        if one(
            connection.execute("""SELECT count(*) FROM anonymous_cycle c JOIN selected_event e
            ON c.end_event_id=e.event_id WHERE c.session_id<>e.session_id""").fetchone()
        )[0]:
            errors.append("anonymous_cycle: end event belongs to another session")
    if errors:
        raise PublicationError("; ".join(errors[:20]))
    return sorted(set(unavailable))


def _table_summary(connection: duckdb.DuckDBPyConnection, name: str) -> JSON:
    """Order-independent SHA-256 multiset digest with exact multiplicity."""
    cursor = connection.execute(f'SELECT payload FROM "{name}"')
    count, total = 0, 0
    while rows := cursor.fetchmany(2048):
        for (payload,) in rows:
            total = (total + int.from_bytes(hashlib.sha256(payload.encode()).digest(), "big")) % (
                1 << 256
            )
            count += 1
    return {
        "rows": count,
        "logical_sha256": hashlib.sha256(f"{count}:{total}".encode()).hexdigest(),
    }


def _validate_accounting(
    connection: duckdb.DuckDBPyConnection, context: JSON, selected_objects: Iterable[str]
) -> None:
    for name, key in (
        ("selected_event", "event_id"),
        ("anonymous_cycle", "cycle_id"),
        ("voting_session", "session_id"),
    ):
        missing = one(
            connection.execute(
                f'''SELECT count(*) FROM "{name}" t WHERE NOT EXISTS
            (SELECT 1 FROM record_lineage l WHERE l.derived_table=? AND
             json_extract_string(l.derived_key, '$[0]')=t."{key}")''',
                [name],
            ).fetchone()
        )[0]
        if missing:
            raise PublicationError(f"{name}: missing original-record lineage")
    if one(
        connection.execute("""SELECT count(*) FROM event_evidence e WHERE NOT EXISTS
        (SELECT 1 FROM selected_event s WHERE s.event_id=json_extract_string(e.payload, '$.canonical_event_id'))""").fetchone()
    )[0]:
        raise PublicationError("Evidence references missing canonical event")
    for (sha,) in connection.execute(
        "SELECT DISTINCT json_extract_string(payload, '$.object_sha256') FROM event_evidence"
    ).fetchall():
        if sha not in selected_objects:
            raise PublicationError("Event object outside declared disjoint partition")
    if one(
        connection.execute("""SELECT count(*) FROM session_summaries s JOIN
        (SELECT session_id, count(*) AS n FROM selected_event GROUP BY session_id) e USING(session_id)
        WHERE json_extract(s.payload, '$.observed_events')::BIGINT<>e.n""").fetchone()
    )[0]:
        raise PublicationError("Session event accounting mismatch")
    if one(
        connection.execute("""SELECT count(*) FROM session_summaries s WHERE
        json_extract(s.payload, '$.observed_cycles_by_state.completed')::BIGINT<>
        (SELECT count(*) FROM anonymous_cycle c WHERE c.session_id=s.session_id AND c.completion_state='completed')""").fetchone()
    )[0]:
        raise PublicationError("Session completed-cycle accounting mismatch")
    coverage = one(connection.execute("SELECT count(*) FROM operational_coverage").fetchone())[0]
    if coverage != len(context["context_tables"]["section"]):
        raise PublicationError("Expected/member coverage accounting mismatch")


def _safe_store(store: Path) -> None:
    for ancestor in (store, *store.parents):
        if any(
            (ancestor / name).exists()
            for name in (
                "manifest-location.json",
                "manifest.sqlite",
                "snapshot.json",
                "parse.json",
                "reconstruction.json",
            )
        ):
            raise PublicationError("Release store must be outside acquisition/frozen inputs")


def publish_release(
    shards: Iterable[Path],
    store: str | Path,
    *,
    config: ResourceConfig | None = None,
    hook: Callable[[str], None] | None = None,
) -> Path:
    """Publish disjoint bounded reconstruction shards; repeat runs verify immutable hits.

    `hook(stage)` is an interruption-test seam, never persisted executable input.
    One full context is retained; each row stream is consumed in bounded batches.
    """
    config = config or ResourceConfig()
    store = Path(store).resolve()
    _safe_store(store)
    store.mkdir(parents=True, exist_ok=True)
    _guard(store, config)
    shards = sorted({Path(p).resolve() for p in shards}, key=lambda p: p.name)
    if not shards:
        raise PublicationError("At least one reconstruction shard required")
    with (store / ".writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublicationError("Another release writer holds the store lock") from exc
        publications = [inspect_reconstruction(p) for p in shards]
        context = load_reconstruction_context(shards[0], publication=publications[0])
        parse_ids = {p["input_parse_id"] for p in publications}
        if len(parse_ids) != 1:
            raise PublicationError("All shards must share one frozen parse context")
        objects = set()
        for publication in publications:
            selected = set(publication["object_sha256"])
            if objects & selected:
                raise PublicationError("Reconstruction object groups overlap")
            objects.update(selected)
        inputs = {
            "version": VERSION,
            "shards": [p.name for p in shards],
            "parse_id": next(iter(parse_ids)),
            "config": asdict(config),
        }
        key = digest(inputs)
        parent = store / "releases"
        parent.mkdir(exist_ok=True)
        target = parent / key
        if target.exists():
            inspect_release(target)
            _point_current(store, key)
            return target
        staging = Path(tempfile.mkdtemp(prefix=".building-", dir=parent))
        connection = None
        try:
            connection = duckdb.connect(str(staging / "audit.duckdb"))
            _configure(connection, staging / "spill", config)
            _write_checked(staging, "context.json", context)
            compact = [n for n in (*TABLES, *EXTRA_TABLES) if n not in FACTS]
            compact += list(context["context_tables"])
            compact = sorted(set(compact))
            for name in compact:
                _create(connection, name)
            for name, rows in context["context_tables"].items():
                errors = validate_rows(name, rows)
                if errors:
                    raise PublicationError("; ".join(errors[:10]))
                for batch in _batches(rows, config.batch_rows):
                    _guard(store, config, sum(len(canonical(row)) for row in batch) * 2 + 1024**2)
                    _insert(connection, name, batch)
            # Frozen observations are unique even when several packages witness one object.
            if "source_observation" not in compact:
                observations = {
                    a["observation"]["observation_id"]: a["observation"]
                    for a in context["associations"]
                }
                _create(connection, "source_observation")
                compact.append("source_observation")
                for batch in _batches(observations.values(), config.batch_rows):
                    _insert(connection, "source_observation", batch)
            sections = {r["section_id"]: r for r in context["context_tables"]["section"]}
            elections = {r["election_id"]: r for r in context["context_tables"]["election"]}
            files = {name: [] for name in FACTS}
            for number, rows in enumerate(
                _batches(context.get("context_lineage", []), config.batch_rows)
            ):
                errors = validate_rows("record_lineage", rows)
                if errors:
                    raise PublicationError("; ".join(errors[:10]))
                relative = f"facts/record_lineage/year=unknown/round=unknown/uf=unknown/context-{number}.parquet"
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(_encoded("record_lineage", rows), path, compression="zstd")
                files["record_lineage"].append(relative)
            counts = {name: 0 for name in (*TABLES, *EXTRA_TABLES)}
            for index, shard in enumerate(shards):
                _guard(store, config)
                sessions = {r["session_id"]: r for r in _rows(shard / "voting_session.jsonl")}
                event_sessions = {
                    r["event_id"]: r["session_id"] for r in _rows(shard / "selected_event.jsonl")
                }
                cycle_sessions = {
                    r["cycle_id"]: r["session_id"] for r in _rows(shard / "anonymous_cycle.jsonl")
                }
                for name in (*TABLES, *EXTRA_TABLES):
                    for number, batch in enumerate(
                        _batches(_rows(shard / f"{name}.jsonl"), config.batch_rows)
                    ):
                        _guard(
                            store, config, sum(len(canonical(row)) for row in batch) * 2 + 1024**2
                        )
                        if name in SCHEMA:
                            errors = validate_rows(name, batch)
                            if errors:
                                raise PublicationError("; ".join(errors[:10]))
                        counts[name] += len(batch)
                        if name not in FACTS:
                            _insert(connection, name, batch)
                            continue
                        groups = {}
                        for row in batch:
                            sid = row.get("session_id")
                            if name == "event_evidence":
                                sid = event_sessions.get(row["canonical_event_id"])
                            elif name == "record_lineage":
                                derived = json.loads(row["derived_key"])[0]
                                sid = (
                                    derived
                                    if row["derived_table"] == "voting_session"
                                    else event_sessions.get(derived)
                                    if row["derived_table"] == "selected_event"
                                    else cycle_sessions.get(derived)
                                    if row["derived_table"] == "anonymous_cycle"
                                    else None
                                )
                            session = sessions.get(sid, {})
                            section = sections.get(session.get("principal_section_id"), {})
                            election = elections.get(section.get("election_id"), {})
                            partition = (
                                str(election.get("year", "unknown")),
                                str(election.get("round", "unknown")),
                                section.get("uf", "unknown"),
                            )
                            if any(not re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in partition):
                                raise PublicationError("Unsafe partition value")
                            groups.setdefault(partition, []).append(row)
                        for (year, round_, uf), rows in groups.items():
                            relative = f"facts/{name}/year={year}/round={round_}/uf={uf}/{index}-{number}.parquet"
                            path = staging / relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            pq.write_table(_encoded(name, rows), path, compression="zstd")
                            files[name].append(relative)
                if hook:
                    hook("shard_written")
            # Identical physical/configuration dimensions may be witnessed by multiple shards.
            for name in ("physical_device", "software_configuration"):
                connection.execute(
                    f'CREATE OR REPLACE TABLE "{name}" AS SELECT DISTINCT * FROM "{name}"'
                )
            table_manifest = {
                name: {
                    "rows": counts[name],
                    "files": files.get(name, []),
                }
                for name in counts
            }
            _attach_facts(connection, staging, table_manifest)
            names = sorted(set(compact) | set(FACTS))
            from election_audit.operational_marts import materialize_marts

            compact.extend(
                materialize_marts(
                    connection, context, objects, shards, cross_shard_overlap=len(shards) > 1
                )
            )
            names = sorted(set(names) | set(compact))
            deferred = _validate(connection, names)
            _validate_accounting(connection, context, objects)
            table_manifest = {
                name: {**_table_summary(connection, name), "files": files.get(name, [])}
                for name in names
            }
            # Views contain staging paths and belong only to this connection; do not persist them.
            for name in FACTS:
                connection.execute(
                    f'DROP VIEW IF EXISTS "{name}"' if files[name] else f'DROP TABLE "{name}"'
                )
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            if (staging / "spill").exists():
                shutil.rmtree(staging / "spill")
            hashes = {}
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    sha, size = hash_file(path)
                    hashes[str(path.relative_to(staging))] = {"sha256": sha, "byte_length": size}
                    with path.open("rb") as handle:
                        os.fsync(handle.fileno())
            publication = {
                "identity": inputs,
                "tables": table_manifest,
                "files": hashes,
                "compact_tables": compact,
                "deferred_checks": deferred,
                "metadata_lineage_state": "preserved"
                if context.get("context_lineage")
                else "unavailable_legacy_parse",
                "selected_objects": sorted(objects),
                "expected_objects": len(context["artifacts"]),
                "national_status": "partial_national",
                "cross_shard_overlap": "unresolved"
                if len(shards) > 1
                else "within_selected_group_only",
                "global_eligible_cycle_total": None,
                "scope": context["population_scope"],
                "coverage_summary": context["coverage_summary"],
                "settings_applied": asdict(config),
            }
            _write_checked(staging, "release.json", publication)
            _fsync_directory(staging)
            _guard(store, config)
            if hook:
                hook("before_release")
            staging.rename(target)
            _fsync_directory(parent)
            if hook:
                hook("before_current")
            _point_current(store, key)
            return target
        except BaseException:
            if connection:
                connection.close()
            if staging.exists():
                shutil.rmtree(staging)
            raise


def _point_current(store: Path, key: str) -> None:
    temporary = store / ".current-next"
    with temporary.open("w", encoding="ascii") as output:
        output.write(key + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(store / "current")
    _fsync_directory(store)


def resolve_release(path: str | Path) -> Path:
    path = Path(path).resolve()
    if (path / "current").is_file():
        key = (path / "current").read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise PublicationError("Invalid current pointer")
        return path / "releases" / key
    return path


def inspect_release(path: str | Path) -> JSON:
    path = resolve_release(path)
    document = _read_checked(path, "release.json")
    if document["identity"]["version"] == "derivative-release-v1":
        from election_audit.derivatives import inspect_derivative

        return inspect_derivative(path, document)
    if document["identity"]["version"] != VERSION or digest(document["identity"]) != path.name:
        raise PublicationError("Invalid release identity")
    compact = document.get("compact_tables", [])
    if len(compact) != len(set(compact)) or set(compact) & set(FACTS):
        raise PublicationError("Invalid compact table manifest")
    if set(document["tables"]) != set(compact) | set(FACTS):
        raise PublicationError("Release table manifest mismatch")
    declared = {"audit.duckdb", "context.json", "context.json.sha256"}
    for table, spec in document["tables"].items():
        if table not in FACTS and spec["files"]:
            raise PublicationError("Compact table cannot reference external facts")
        if len(spec["files"]) != len(set(spec["files"])):
            raise PublicationError("Repeated fact file")
        for locator in spec["files"]:
            if not locator.startswith(f"facts/{table}/") or not locator.endswith(".parquet"):
                raise PublicationError("Fact locator/table mismatch")
            declared.add(locator)
    if declared != set(document["files"]):
        raise PublicationError("Release file manifest is incomplete")
    for name, spec in document["files"].items():
        file = path / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or file.is_symlink()
            or not file.resolve().is_relative_to(path)
        ):
            raise PublicationError("Unsafe release file locator")
        if hash_file(file) != (spec["sha256"], spec["byte_length"]):
            raise PublicationError("Release file integrity mismatch")
    return document


def open_release(
    path: str | Path,
    *,
    config: ResourceConfig | None = None,
    _verified_document: JSON | None = None,
) -> duckdb.DuckDBPyConnection:
    """Verified, relocated read-only database plus connection-local fact views."""
    path = resolve_release(path)
    document = _verified_document if _verified_document is not None else inspect_release(path)
    if document["identity"]["version"] == "derivative-release-v1":
        from election_audit.derivatives import open_derivative

        return open_derivative(path, document, config=config)
    connection = duckdb.connect(str(path / "audit.duckdb"), read_only=True)
    config = config or ResourceConfig(**document["settings_applied"])
    # Query connections cannot spill into immutable release paths.
    connection.execute(f"SET threads={config.duckdb_threads}")
    connection.execute(f"SET memory_limit='{config.memory_bytes}B'")
    connection.execute("SET max_temp_directory_size='0B'")
    for name in FACTS:
        files = [str(path / f) for f in document["tables"][name]["files"]]
        if files:
            _fact_view(connection, name, files)
        else:
            columns = ",".join(
                f'CAST(NULL AS {TYPES[k]}) AS "{n}"' for n, k in _columns(name).items()
            )
            connection.execute(
                f'CREATE TEMP VIEW "{name}" AS SELECT {columns}, CAST(NULL AS JSON) AS payload WHERE false'
            )
    return connection


def build_from_parse(
    parse: str | Path,
    store: str | Path,
    *,
    config: ResourceConfig | None = None,
    evidence: Any = None,
    object_groups: list[list[str]] | None = None,
) -> Path:
    """Bounded object/group reconstruction, shared verified parse reader and context."""
    config = config or ResourceConfig()
    reader = FrozenParseReader(parse)
    groups = [[sha] for sha in sorted(reader.artifacts)] if object_groups is None else object_groups
    paths = [
        reconstruct_parse(
            reader.path,
            Path(store) / "operations",
            evidence=evidence,
            object_sha256=group,
            reader=reader,
            max_events=config.max_events,
        )
        for group in groups
    ]
    return publish_release(paths, store, config=config)


def build_from_snapshot(
    snapshot: str | Path,
    store: str | Path,
    *,
    config: ResourceConfig | None = None,
    evidence: Any = None,
) -> Path:
    """Frozen snapshot → parallel bounded parse → reconstruction → release."""
    from election_audit.archive_parsing import parse_snapshot

    config = config or ResourceConfig()
    parsed = parse_snapshot(snapshot, Path(store) / "parsed", workers=config.parser_workers)
    return build_from_parse(parsed, store, config=config, evidence=evidence)
