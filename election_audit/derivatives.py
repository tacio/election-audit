"""Immutable manifest-driven extensions that reuse verified parent facts in place."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.archive_parsing import _read_checked, _write_checked
from election_audit.electoral_imports import (
    CONTRACT_TABLES,
    EXTENSIONS,
    checked_path,
    read_import,
    table_schema,
)
from election_audit.publication import (
    ARROW,
    FACTS,
    SCHEMA,
    TYPES,
    PublicationError,
    ResourceConfig,
    _batches,
    _columns,
    _configure,
    _guard,
    _point_current,
    _safe_store,
    _table_summary,
    _validate,
    resolve_release,
)
from election_audit.snapshots import _fsync_directory
from election_audit.source_inventory import canonical, digest, hash_file

VERSION = "derivative-release-v1"
RESULT_FACTS = {
    "vote_choice_count",
    "result_version",
    "section_contest_totals",
    "processing_event",
    "record_lineage",
}


def _identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise PublicationError("Unsafe derivative table/column identifier")
    return '"' + name + '"'


def _parent_path(path, document):
    parent = document["identity"]["parent"]
    locator = parent["locator"]
    if (
        not isinstance(locator, str)
        or Path(locator).is_absolute()
        or ":" in locator
        or "\\" in locator
    ):
        raise PublicationError("Unsafe relative parent locator")
    candidate = path / locator
    # Parents may be siblings (..); symlinks at every hop remain forbidden.
    cursor = path
    for part in Path(locator).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PublicationError("Symlink in parent locator")
    candidate = candidate.resolve()
    if candidate.name != parent["release_id"]:
        raise PublicationError("Parent release pin mismatch")
    return candidate


def inspect_derivative(path, document, *, seen=None, cache=None):
    """Verify each chain member once, including pinned manifests and exact local files."""
    from election_audit.publication import inspect_release

    seen, cache = set() if seen is None else seen, {} if cache is None else cache
    path = Path(path).resolve()
    if path in seen or len(seen) >= 32:
        raise PublicationError("Cyclic/overdeep derivative parent chain")
    seen.add(path)
    try:
        if document["identity"]["version"] != VERSION or digest(document["identity"]) != path.name:
            raise PublicationError("Invalid derivative identity")
        parent = _parent_path(path, document)
        if parent in seen:
            raise PublicationError("Cyclic derivative parent chain")
        pin = document["identity"]["parent"]
        if hash_file(parent / "release.json")[0] != pin["manifest_sha256"]:
            raise PublicationError("Pinned parent manifest integrity mismatch")
        if parent not in cache:
            raw = _read_checked(parent, "release.json")
            cache[parent] = (
                inspect_derivative(parent, raw, seen=seen, cache=cache)
                if raw["identity"]["version"] == VERSION
                else inspect_release(parent)
            )
        parent_doc = cache[parent]
        declared = {"audit.duckdb", "import.json", "import.json.sha256"}
        for name, spec in document["tables"].items():
            _identifier(name)
            if spec["mode"] not in {"append", "replace"} or not spec["key"]:
                raise PublicationError("Invalid derivative table mode/key")
            for field, kind in spec["columns"].items():
                _identifier(field)
                if kind not in TYPES:
                    raise PublicationError("Invalid derivative column type")
            if not set(spec["key"]) <= set(spec["columns"]):
                raise PublicationError("Invalid derivative table key")
            if name in SCHEMA:
                contract = table_schema(name)
                if spec["columns"] != contract["columns"] or spec["key"] != contract["key"]:
                    raise PublicationError("Derivative changes published contract schema")
                if spec["mode"] == "replace" and name != "canonical_result":
                    raise PublicationError("Contract input extensions must be append-only")
            for locator in spec["files"]:
                if not locator.startswith(f"facts/{name}/") or not locator.endswith(".parquet"):
                    raise PublicationError("Derivative fact locator/table mismatch")
                if locator in declared:
                    raise PublicationError("Repeated derivative fact locator")
                declared.add(locator)
        declared |= set(document["originals"])
        if declared != set(document["files"]):
            raise PublicationError("Derivative file manifest is incomplete")
        for locator, spec in document["files"].items():
            file = checked_path(path, locator)
            if hash_file(file) != (spec["sha256"], spec["byte_length"]):
                raise PublicationError("Derivative file integrity mismatch")
        for locator in document["originals"]:
            if (
                not re.fullmatch(r"originals/[0-9a-f]{64}", locator)
                or document["files"][locator]["sha256"] != Path(locator).name
            ):
                raise PublicationError("Original byte identity mismatch")
        inherited = parent_doc.get("combined_tables", parent_doc["tables"])
        if set(document["combined_tables"]) != set(inherited) | set(document["tables"]):
            raise PublicationError("Combined derivative table manifest mismatch")
        for name, spec in document["combined_tables"].items():
            _identifier(name)
            source = document["tables"].get(name, inherited.get(name))
            if "columns" in source:
                expected_columns, expected_key = source["columns"], source["key"]
            else:
                from election_audit.publication import EXTRA_KEYS

                expected_columns = _columns(name)
                expected_key = SCHEMA[name]["primary_key"] if name in SCHEMA else EXTRA_KEYS[name]
            if spec["columns"] != expected_columns or spec["key"] != expected_key:
                raise PublicationError("Combined derivative schema mismatch")
            if (
                type(spec["rows"]) is not int
                or spec["rows"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", spec["logical_sha256"])
            ):
                raise PublicationError("Invalid combined table digest/count")
        imported = _read_checked(path, "import.json")
        if (
            imported["bundle"] != document["identity"]["adapter"]
            or document["verification_status"] != imported["verification_status"]
            or document["verification_status"]
            != (
                "official_layout_verified"
                if imported["bundle"].get("adapter") == "tse-bweb-2026-v1"
                else "normalized_only"
            )
            or document["electoral_validation"] != imported["real_bu_validation"]
        ):
            raise PublicationError("Derivative import provenance mismatch")
        if (
            imported["normalized_schema_sha256"] != document["identity"]["normalized_schema_sha256"]
            or digest(imported["source_discovery"])
            != document["identity"]["source_discovery_sha256"]
        ):
            raise PublicationError("Derivative schema/source evidence pin mismatch")
        if document["identity"]["config"] != document["settings_applied"]:
            raise PublicationError("Derivative resource provenance mismatch")
        result = dict(document)
        result["_parent_document"] = parent_doc
        result["_parent_path"] = str(parent)
        return result
    finally:
        seen.remove(path)


def release_layers(path, document):
    if document["identity"]["version"] == VERSION:
        yield from release_layers(Path(document["_parent_path"]), document["_parent_document"])
    yield Path(path), document


def allowed_fact_paths(path, document):
    return [
        str(root / locator)
        for root, doc in release_layers(path, document)
        for spec in doc["tables"].values()
        for locator in spec["files"]
    ]


def _empty_sql(columns):
    return (
        "SELECT "
        + ",".join(f"CAST(NULL AS {TYPES[k]}) AS {_identifier(n)}" for n, k in columns.items())
        + ", CAST(NULL AS JSON) AS payload WHERE false"
    )


def attach_layers(connection, path, document):
    """Connection-local views over read-only parent databases and original Parquet."""
    views, schemas = {}, {}
    for number, (root, doc) in enumerate(release_layers(path, document)):
        alias = f"parent_{number}"
        database = str(root / "audit.duckdb").replace("'", "''")
        connection.execute(f"ATTACH '{database}' AS {alias} (READ_ONLY)")
        derivative = doc["identity"]["version"] == VERSION
        for name, spec in doc["tables"].items():
            ident = _identifier(name)
            columns = spec["columns"] if derivative else _columns(name)
            local = f"layer_{number}_{name}"
            files = [str(root / file) for file in spec["files"]]
            if files:
                literals = ",".join("'" + p.replace("'", "''") + "'" for p in files)
                sql = f"SELECT * FROM read_parquet([{literals}], hive_partitioning=false)"
            elif (derivative and spec.get("storage") == "facts") or (
                not derivative and name in FACTS
            ):
                sql = _empty_sql(columns)
            else:
                source = _identifier("local_" + name) if derivative else ident
                sql = f"SELECT * FROM {alias}.main.{source}"
            if name in views and spec.get("mode", "append") == "append":
                if schemas[name] != columns:
                    raise PublicationError("Append extension changes inherited schema")
                sql = f"SELECT * FROM {views[name]} UNION {sql}"
            connection.execute(f"CREATE TEMP VIEW {local} AS {sql}")
            views[name], schemas[name] = local, columns
    for name, local in views.items():
        connection.execute(f"CREATE TEMP VIEW {_identifier(name)} AS SELECT * FROM {local}")
    return schemas


def open_derivative(path, document, *, config=None):
    config = config or ResourceConfig(**document["settings_applied"])
    # Every attached database is read-only; the coordinator stores temporary views.
    connection = duckdb.connect()
    connection.execute(f"SET threads={config.duckdb_threads}")
    connection.execute(f"SET memory_limit='{config.memory_bytes}B'")
    connection.execute("SET max_temp_directory_size='0B'")
    try:
        attach_layers(connection, path, document)
        names = document.get("combined_tables", {})
        if {"audit_features", "location_partition", "test_partition_status"} <= set(names):
            connection.execute("""CREATE TEMP VIEW training_features AS SELECT f.* FROM audit_features f
                WHERE EXISTS (SELECT 1 FROM location_partition p
                  WHERE p.snapshot_id=json_extract_string(f.payload,'$.snapshot_id')
                    AND p.principal_section_id=json_extract_string(f.payload,'$.lineage_keys.principal_section_id')
                    AND p.partition_name IN ('training','calibration')
                    AND NOT EXISTS (SELECT 1 FROM test_partition_status t
                      WHERE t.stable_location_id=p.stable_location_id AND t.access_state='untouched'))""")
        return connection
    except BaseException:
        connection.close()
        raise


def _encoded(columns, rows):
    values = []
    for row in rows:
        item = {
            k: canonical(row.get(k)).decode()
            if kind == "json" and row.get(k) is not None
            else row.get(k)
            for k, kind in columns.items()
        }
        item["payload"] = canonical(row).decode()
        values.append(item)
    return pa.Table.from_pylist(
        values,
        schema=pa.schema(
            [(k, ARROW[kind]) for k, kind in columns.items()] + [("payload", pa.string())]
        ),
    )


def _store_table(
    connection, staging, name, rows, schema, config, *, mode="append", facts=False, partitions=None
):
    columns = schema["columns"]
    files = []
    if facts:
        for batch_number, batch in enumerate(_batches(rows, config.batch_rows)):
            groups = {}
            for row in batch:
                partition = partitions(row) if partitions else ("unknown", "unknown", "unknown")
                if any(not re.fullmatch(r"[a-zA-Z0-9_-]+", str(p)) for p in partition):
                    raise PublicationError("Unsafe derivative partition")
                groups.setdefault(partition, []).append(row)
            for (year, round_, uf), group in groups.items():
                locator = f"facts/{name}/year={year}/round={round_}/uf={uf}/{batch_number}.parquet"
                file = staging / locator
                file.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(_encoded(columns, group), file, compression="zstd")
                files.append(locator)
    else:
        definition = ",".join(f"{_identifier(k)} {TYPES[kind]}" for k, kind in columns.items())
        connection.execute(f'CREATE TABLE "local_{name}" ({definition}, payload JSON NOT NULL)')
        for batch in _batches(rows, config.batch_rows):
            connection.register("incoming", _encoded(columns, batch))
            connection.execute(f'INSERT INTO "local_{name}" SELECT * FROM incoming')
            connection.unregister("incoming")
    return {**schema, "mode": mode, "storage": "facts" if facts else "compact", "files": files}


def _check_keys(connection, tables):
    for name, spec in tables.items():
        keys = ",".join(_identifier(k) for k in spec["key"])
        null = " OR ".join(f"{_identifier(k)} IS NULL" for k in spec["key"])
        if connection.execute(f'SELECT count(*) FROM "{name}" WHERE {null}').fetchone()[0]:
            raise PublicationError(f"Null extension key: {name}")
        if connection.execute(
            f'SELECT count(*) FROM (SELECT {keys} FROM "{name}" GROUP BY {keys} HAVING count(*)>1)'
        ).fetchone()[0]:
            raise PublicationError(f"Conflicting immutable parent/child key: {name}")


def publish_derivative(parent, bundle, store, *, config=None, _analysis=False):
    """Explicit normalized import → immutable child. No base bytes are rewritten/copied."""
    from election_audit.electoral_results import derive_electoral, validate_electoral
    from election_audit.publication import inspect_release, open_release

    config = config or ResourceConfig()
    parent = resolve_release(parent)
    parent_doc = inspect_release(parent)
    if _analysis:
        from election_audit.analysis import read_analysis

        imported = read_analysis(bundle, config)
    else:
        imported = read_import(bundle, max_rows=config.max_events)
    if sum(map(len, imported["tables"].values())) > config.max_events:
        raise PublicationError("Bounded normalized import row limit exceeded")
    store = Path(store).resolve()
    _safe_store(store)
    if any((ancestor / "release.json").exists() for ancestor in (store, *store.parents)):
        raise PublicationError("Derivative store must be outside immutable releases")
    store.mkdir(parents=True, exist_ok=True)
    _guard(store, config)
    releases = store / "releases"
    releases.mkdir(exist_ok=True)
    # Relocatable pin: relative between release directories, never a mutable current pointer.
    parent_pin = {
        "release_id": parent.name,
        "manifest_sha256": hash_file(parent / "release.json")[0],
        "locator": os.path.relpath(parent, releases / ("0" * 64)),
    }
    identity = {
        "version": VERSION,
        "parent": parent_pin,
        "import": imported["bundle_sha256"],
        "adapter": imported["identity"],
        "normalized_schema_sha256": imported["normalized_schema_sha256"],
        "source_discovery_sha256": digest(imported["source_discovery"]),
        "config": asdict(config),
    }
    if _analysis:
        identity["producer"] = "analysis-v1"
    target = releases / digest(identity)
    with (store / ".writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublicationError("Another derivative writer holds store lock") from exc
        if target.exists():
            inspect_release(target)
            _point_current(store, target.name)
            return target
        staging = Path(tempfile.mkdtemp(prefix=".building-", dir=releases))
        connection = None
        try:
            connection = duckdb.connect(str(staging / "audit.duckdb"))
            _configure(connection, staging / "spill", config)
            # Input context is read from the verified parent, never acquisition.
            if _analysis:
                from election_audit.analysis import derive_analysis

                tables = {}
                generated, schemas = derive_analysis(
                    parent, parent_doc, imported["analysis"], config
                )

                def partition(row):
                    return ("unknown", "unknown", "unknown")
            else:
                with open_release(parent, _verified_document=parent_doc) as source:
                    inherited, inherited_rows = {}, 0
                    for name in set(CONTRACT_TABLES) | set(EXTENSIONS) | {"source_object"}:
                        if name not in (parent_doc.get("combined_tables") or parent_doc["tables"]):
                            continue
                        rows = source.execute(f'SELECT payload FROM "{name}"').fetchmany(
                            config.max_events + 1
                        )
                        inherited_rows += len(rows)
                        if inherited_rows > config.max_events:
                            raise PublicationError("Bounded inherited electoral row limit exceeded")
                        inherited[name] = [json.loads(r[0]) for r in rows]
                # Only compact electoral dimensions/results are loaded here; parent operational
                # event/cycle/lineage Parquet is reused and never materialized in Python.
                tables = imported["tables"]
                combined = {}
                electoral_names = set(tables) | set(inherited)
                for name in electoral_names:
                    if name in {"record_lineage", "source_observation"}:
                        continue
                    unique = {
                        canonical(r): r for r in inherited.get(name, []) + tables.get(name, [])
                    }
                    combined[name] = list(unique.values())
                if sum(map(len, combined.values())) > config.max_events:
                    raise PublicationError("Bounded combined electoral row limit exceeded")
                generated, schemas = derive_electoral(combined)
                validate_electoral(combined, generated)
                versions = {r["result_version_id"]: r for r in combined.get("result_version", [])}
                sections = {r["section_id"]: r for r in combined.get("section", [])}
                elections = {r["election_id"]: r for r in combined.get("election", [])}

                def partition(row):
                    version = versions.get(row.get("result_version_id"), {})
                    section = sections.get(
                        row.get("principal_section_id", version.get("principal_section_id")), {}
                    )
                    election = elections.get(section.get("election_id"), {})
                    return (
                        str(election.get("year", "unknown")),
                        str(election.get("round", "unknown")),
                        section.get("uf", "unknown"),
                    )

            manifest = {}
            for name, rows in {**tables, **generated}.items():
                _guard(store, config)
                schema = schemas.get(name) or table_schema(name)
                manifest[name] = _store_table(
                    connection,
                    staging,
                    name,
                    rows,
                    schema,
                    config,
                    mode="append"
                    if _analysis
                    and name
                    in {
                        "partition_plan",
                        "location_partition",
                        "analysis_ledger",
                        "impact_scenario",
                    }
                    else "replace"
                    if name in generated
                    else "append",
                    facts=name in RESULT_FACTS or (_analysis and name == "audit_features"),
                    partitions=partition,
                )
            for sha, data in imported["originals"].items():
                path = staging / "originals" / sha
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
            _write_checked(
                staging,
                "import.json",
                {
                    "bundle": imported["identity"],
                    "verification_status": imported["verification_status"],
                    "normalized_schema_sha256": imported["normalized_schema_sha256"],
                    "source_discovery": imported["source_discovery"],
                    "real_bu_validation": imported["real_bu_validation"],
                    **({"analysis": imported["analysis"]} if _analysis else {}),
                },
            )
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            if (staging / "spill").exists():
                shutil.rmtree(staging / "spill")
            document = {
                "identity": identity,
                "tables": manifest,
                "settings_applied": asdict(config),
                "originals": [f"originals/{sha}" for sha in sorted(imported["originals"])],
                "national_status": "partial_national",
                "electoral_validation": imported["real_bu_validation"],
                "verification_status": imported["verification_status"],
            }
            # Use the pinned verified parent without a second physical corpus scan.
            verified = {**document, "_parent_document": parent_doc, "_parent_path": str(parent)}
            with open_derivative(staging, verified, config=config) as db:
                schema_map = {}
                from election_audit.publication import EXTRA_KEYS

                for _, doc in release_layers(staging, verified):
                    schema_map.update(
                        {
                            n: s
                            if "key" in s
                            else {
                                "key": SCHEMA[n]["primary_key"] if n in SCHEMA else EXTRA_KEYS[n],
                                "columns": _columns(n),
                            }
                            for n, s in doc["tables"].items()
                        }
                    )
                _check_keys(db, schema_map)
                deferred = _validate(db, sorted(set(schema_map) & set(SCHEMA)))
                document["deferred_checks"] = deferred
                document["combined_tables"] = {
                    name: {**schema_map[name], **_table_summary(db, name)}
                    for name in sorted(schema_map)
                }
            document["files"] = {
                str(p.relative_to(staging)): {
                    "sha256": hash_file(p)[0],
                    "byte_length": p.stat().st_size,
                }
                for p in sorted(staging.rglob("*"))
                if p.is_file()
            }
            for p in staging.rglob("*"):
                if p.is_file():
                    with p.open("rb") as handle:
                        os.fsync(handle.fileno())
            _write_checked(staging, "release.json", document)
            _fsync_directory(staging)
            _guard(store, config)
            staging.rename(target)
            _fsync_directory(releases)
            _point_current(store, target.name)
            return target
        except BaseException:
            if connection:
                connection.close()
            if staging.exists():
                shutil.rmtree(staging)
            raise


def validate_derivative(path, document):
    from election_audit.electoral_results import derive_electoral
    from election_audit.release_tools import validate_release

    parent_validation = validate_release(
        document["_parent_path"], _verified_document=document["_parent_document"]
    )
    with open_derivative(path, document) as connection:
        _check_keys(connection, document["combined_tables"])
        deferred = _validate(connection, sorted(set(document["combined_tables"]) & set(SCHEMA)))
        for name, spec in document["combined_tables"].items():
            if any(value != spec[key] for key, value in _table_summary(connection, name).items()):
                raise PublicationError(f"Derivative logical digest mismatch: {name}")
        if document["identity"].get("producer") == "analysis-v1":
            from election_audit.analysis import validate_analysis

            validate_analysis(path, document, connection)
            return {
                "release_id": path.name,
                "integrity": "passed",
                "logical_digests": "passed",
                "grains_foreign_keys": "passed",
                "analysis": "foundation_only_no_fitting",
                "national_status": "partial_national",
                "electoral_validation": document["electoral_validation"],
                "parent_chain": [parent_validation],
            }
        data, retained = {}, 0
        limit = document["settings_applied"]["max_events"]
        for name in document["combined_tables"]:
            if name not in CONTRACT_TABLES and name not in EXTENSIONS and name != "source_object":
                continue
            rows = connection.execute(f'SELECT payload FROM "{name}"').fetchmany(limit + 1)
            retained += len(rows)
            if retained > limit:
                raise PublicationError("Bounded validation electoral row limit exceeded")
            data[name] = [json.loads(r[0]) for r in rows]
        expected, _ = derive_electoral(data)
        for name, rows in expected.items():
            total = sum(
                int.from_bytes(hashlib.sha256(canonical(r)).digest(), "big") for r in rows
            ) % (1 << 256)
            summary = {
                "rows": len(rows),
                "logical_sha256": hashlib.sha256(f"{len(rows)}:{total}".encode()).hexdigest(),
            }
            if any(
                value != document["combined_tables"][name][key] for key, value in summary.items()
            ):
                raise PublicationError(f"Electoral derivation mismatch: {name}")
    if (
        deferred != document["deferred_checks"]
        or document["identity"]["config"] != document["settings_applied"]
    ):
        raise PublicationError("Derivative validation provenance mismatch")
    return {
        "release_id": path.name,
        "integrity": "passed",
        "logical_digests": "passed",
        "grains_foreign_keys": "passed",
        "national_status": "partial_national",
        "electoral_validation": document["electoral_validation"],
        "verification_status": document.get("verification_status", "normalized_only"),
        "deferred_checks": deferred,
        "parent_chain": [parent_validation],
        "reconciliation": document["electoral_validation"],
    }


def derivative_main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    for key, default in asdict(ResourceConfig()).items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        result = publish_derivative(
            args.parent,
            args.bundle,
            args.store,
            config=ResourceConfig(**{key: getattr(args, key) for key in asdict(ResourceConfig())}),
        )
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.error(str(exc))
    print(result)
    return 0
