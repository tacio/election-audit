"""Atomic immutable snapshot publication and offline inspection.

Only this module writes derived snapshot storage. It never writes acquisition
roots, opens raw archives, fetches URLs or publishes a DuckDB database.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import platform
import shutil
import sqlite3
import tempfile
from collections.abc import Collection
from importlib import metadata
from pathlib import Path

from election_audit.contracts import load_contract, validate_rows
from election_audit.coverage import (
    PACKAGE_STATUS_MAP,
    PACKAGE_STATUS_VERSION,
    PENDING_SNAPSHOT,
    SELECTION_VERSION,
    build_population,
)
from election_audit.elections import ElectionDescriptor, election_for_round
from election_audit.source_inventory import (
    ALL_UFS,
    DEFAULT_UFS,
    SectionKey,
    canonical,
    digest,
    hash_file,
    identity,
    inventory_sources,
    safe_source,
    utc_now,
)
from election_audit.types import JSON, Argv, Row

SNAPSHOT_FORMAT = "election-audit-snapshot-v1"


class SnapshotError(ValueError):
    """Invalid or changing input, incomplete publication or damaged snapshot."""


def runtime_provenance() -> JSON:
    versions = {}
    for package in ("election-audit", "duckdb", "pyarrow"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    paths = [
        Path(__file__),
        *(
            Path(__file__).with_name(name)
            for name in ("source_inventory.py", "coverage.py", "contracts.py")
        ),
    ]
    return {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "packages": versions,
        "implementation_sha256": {path.name: hash_file(path)[0] for path in paths},
        "schema_sha256": digest(load_contract()),
        "selection_version": SELECTION_VERSION,
        "package_status_version": PACKAGE_STATUS_VERSION,
        "package_status_mapping": PACKAGE_STATUS_MAP,
        "git_revision": None,
        "git_revision_state": "not_collected",
    }


def _bind_tables(tables: dict[str, list[Row]], snapshot_id: str) -> dict[str, list[Row]]:
    tables = copy.deepcopy(tables)
    for name in ("section_composition", "coverage_ledger"):
        for row in tables[name]:
            row["snapshot_id"] = snapshot_id
    for row in tables["record_lineage"]:
        if row["derived_table"] in ("section_composition", "coverage_ledger"):
            key = json.loads(row["derived_key"])
            key[0] = snapshot_id
            row["derived_key"] = canonical(key).decode()
    return tables


def _identity_payload(payload: JSON) -> JSON:
    value = copy.deepcopy(payload)
    value["tables"] = _bind_tables(value["tables"], PENDING_SNAPSHOT)
    return value


def snapshot_tables(document: JSON) -> dict[str, list[Row]]:
    """All emitted contract tables, including snapshot/membership wrapper rows."""
    return {
        **document["payload"]["tables"],
        "snapshot": [document["snapshot"]],
        "snapshot_observation": document["snapshot_observation"],
    }


def _validate_document(document: JSON) -> None:
    if document.get("format_version") != SNAPSHOT_FORMAT:
        raise SnapshotError("Unsupported snapshot format")
    snapshot = document["snapshot"]
    expected_digest = digest(_identity_payload(document["payload"]))
    if snapshot["inventory_sha256"] != expected_digest or snapshot["snapshot_id"] != identity(
        "snapshot", expected_digest
    ):
        raise SnapshotError("Snapshot identity/inventory digest mismatch")
    tables = snapshot_tables(document)
    schema = document["payload"]["schema"]
    if (
        snapshot["contract_version"] != schema["contract_version"]
        or snapshot["selection_policy"] != document["payload"]["provenance"]["selection_version"]
    ):
        raise SnapshotError("Snapshot contract/selection version mismatch")
    errors = []
    for name, rows in tables.items():
        errors.extend(validate_rows(name, rows, schema=schema))
    # These in-memory keys protect the emitted source/coverage subset. General
    # publication-time semantic/electoral reconciliation remains a later phase.
    for name, rows in tables.items():
        for fk in schema["tables"][name]["foreign_keys"]:
            target = {
                tuple(row[field] for field in fk["references"])
                for row in tables.get(fk["table"], [])
            }
            for row in rows:
                values = tuple(row[field] for field in fk["fields"])
                if None not in values and values not in target:
                    errors.append(f"{name}: missing {fk['table']} foreign row")
    if errors:
        raise SnapshotError("; ".join(errors[:10]))


def _fsync_directory(path: str | Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_verified(source: Path, target: Path, expected_digest: str, expected_bytes: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    hasher, length = hashlib.sha256(), 0
    # Copy bytes rather than hard-linking: later raw replacement/corruption cannot
    # mutate the snapshot's inode. Hash the exact bytes written, not an earlier read.
    with source.open("rb") as original, target.open("xb") as destination:
        while body := original.read(1024 * 1024):
            hasher.update(body)
            length += len(body)
            destination.write(body)
        destination.flush()
        os.fsync(destination.fileno())
    if hasher.hexdigest() != expected_digest or length != expected_bytes:
        raise SnapshotError(f"Object changed after inventory: {expected_digest}")
    _fsync_directory(target.parent)


def publish_snapshot(
    inventory: JSON, population: JSON, store: Path, *, reserve_bytes: int = 0
) -> Path:
    """Materialize one captured input idempotently; existing snapshots never change.

    Interrupted staging directories are ignored on restart, never treated as
    completed snapshots. Re-publishing the same captured inventory returns its
    verified existing snapshot; a new capture may receive a new identity/time.
    """
    store = Path(store).resolve()
    source_root = Path(inventory["source_root"]).resolve()
    if store == source_root or store.is_relative_to(source_root):
        raise SnapshotError("Snapshot store must be outside the acquisition root")
    if reserve_bytes < 0:
        raise SnapshotError("Reserve cannot be negative")
    tables = copy.deepcopy(population["tables"])
    for row in tables["source_object"]:
        sha = row["object_sha256"]
        row["storage_locator"] = f"objects/{sha[:2]}/{sha}"
    payload = {
        "provenance": runtime_provenance(),
        "schema": load_contract(),
        "inventory": inventory,
        "tables": tables,
        "coverage_summary": population["coverage_summary"],
        "section_evidence": population["section_evidence"],
        "metadata_issues": population["metadata_issues"],
    }
    inventory_digest = digest(_identity_payload(payload))
    snapshot_id = identity("snapshot", inventory_digest)
    scope = {
        **inventory["selection"],
        "national_status": population["coverage_summary"]["national_status"],
    }
    snapshot = {
        "snapshot_id": snapshot_id,
        "created_at": utc_now(),
        "contract_version": load_contract()["contract_version"],
        "selection_policy": SELECTION_VERSION,
        "population_scope": canonical(scope).decode(),
        "inventory_sha256": inventory_digest,
        "manifest_locator": inventory["manifest_locator"],
        "manifest_captured_at": inventory["manifest_captured_at"],
    }
    payload["tables"] = _bind_tables(tables, snapshot_id)
    document = {
        "format_version": SNAPSHOT_FORMAT,
        "snapshot": snapshot,
        "payload": payload,
        "snapshot_observation": [
            {"snapshot_id": snapshot_id, "observation_id": row["observation_id"]}
            for row in tables["source_observation"]
        ],
    }
    _validate_document(document)
    store.mkdir(parents=True, exist_ok=True)
    target = store / inventory_digest
    # This is a separate derived-store lock, never the collector's lock.
    with (store / ".snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            existing = inspect_snapshot(target, verify_objects=True)
            if existing["snapshot"]["snapshot_id"] != snapshot_id:
                raise SnapshotError("Existing snapshot has another identity")
            return target
        required = sum(row["byte_length"] for row in tables["source_object"])
        if shutil.disk_usage(store).free < required + reserve_bytes:
            raise SnapshotError(
                f"Insufficient space: need {required} object bytes plus {reserve_bytes} reserve"
            )
        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-building-", dir=store))
        try:
            originals = {row["object_sha256"]: row for row in inventory["source_object"]}
            for row in tables["source_object"]:
                original = originals[row["object_sha256"]]
                _copy_verified(
                    safe_source(source_root, original["storage_locator"]),
                    temporary / row["storage_locator"],
                    row["object_sha256"],
                    row["byte_length"],
                )
            encoded = canonical(document) + b"\n"
            for name, body in (
                ("snapshot.json", encoded),
                ("snapshot.sha256", (hashlib.sha256(encoded).hexdigest() + "\n").encode()),
            ):
                with (temporary / name).open("xb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
            if (temporary / "objects").exists():
                _fsync_directory(temporary / "objects")
            _fsync_directory(temporary)
            temporary.rename(target)
            _fsync_directory(store)
        except BaseException:
            shutil.rmtree(temporary)
            raise
    return target


def create_snapshot(
    root: Path,
    store: Path,
    ufs: Collection[str] = DEFAULT_UFS,
    *,
    section_keys: Collection[SectionKey] | None = None,
    reserve_bytes: int = 0,
    election: ElectionDescriptor | dict | None = None,
    source_manifest: Path | None = None,
) -> Path:
    inventory = inventory_sources(
        root, ufs, section_keys=section_keys, election=election, source_manifest=source_manifest
    )
    return publish_snapshot(
        inventory, build_population(inventory), store, reserve_bytes=reserve_bytes
    )


def inspect_snapshot(path: Path, *, verify_objects: bool = False) -> JSON:
    """Load a complete snapshot; never resolve or reread its original raw root."""
    path = Path(path)
    if path.name == "snapshot.json":
        path = path.parent
    try:
        encoded = (path / "snapshot.json").read_bytes()
        if hashlib.sha256(encoded).hexdigest() != (path / "snapshot.sha256").read_text().strip():
            raise SnapshotError("Snapshot file checksum mismatch")
        document = json.loads(encoded)
        _validate_document(document)
        for row in document["payload"]["tables"]["source_object"]:
            source = safe_source(path, row["storage_locator"])
            if not source.is_file() or source.stat().st_size != row["byte_length"]:
                raise SnapshotError(f"Snapshot object missing or resized: {row['object_sha256']}")
            if verify_objects and hash_file(source) != (row["object_sha256"], row["byte_length"]):
                raise SnapshotError(f"Snapshot object checksum mismatch: {row['object_sha256']}")
        return document
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Incomplete or invalid snapshot: {exc}") from exc


def snapshot_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze selected local inputs without modifying acquisition"
    )
    parser.add_argument(
        "--source", type=Path, required=True, help="Raw acquisition root (marker is followed)"
    )
    parser.add_argument(
        "--store", type=Path, required=True, help="Derived snapshot store outside the raw root"
    )
    parser.add_argument("--round", type=int, choices=(1, 2), default=2)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--ufs", nargs="+", choices=ALL_UFS, default=DEFAULT_UFS)
    parser.add_argument(
        "--section",
        action="append",
        help="Bound assets to UF/MUNICIPALITY/ZONE/SECTION; repeatable; indexes remain whole-UF",
    )
    parser.add_argument(
        "--reserve-gib",
        type=float,
        default=10,
        help="Free-space reserve after object copies (default 10)",
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.reserve_gib) or args.reserve_gib < 0:
        parser.error("--reserve-gib must be finite and nonnegative")
    selected = None if args.section is None else [tuple(value.split("/")) for value in args.section]
    try:
        path = create_snapshot(
            args.source,
            args.store,
            args.ufs,
            section_keys=selected,
            reserve_bytes=int(args.reserve_gib * 1024**3),
            election=election_for_round(args.round),
            source_manifest=args.source_manifest,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(path)
    return 0


def inspect_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a frozen snapshot, independently of live acquisition"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--verify-objects",
        action="store_true",
        help="Rehash frozen copies as well as checking metadata/lengths",
    )
    args = parser.parse_args(argv)
    try:
        document = inspect_snapshot(args.path, verify_objects=args.verify_objects)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "snapshot": document["snapshot"],
                "coverage": document["payload"]["coverage_summary"],
                "objects_rehashed": args.verify_objects,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
