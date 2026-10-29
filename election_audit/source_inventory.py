"""Read-only, WAL-consistent adapter for the legacy acquisition manifest.

The legacy ``files`` table is a current URL map, not a per-run observation log.
No join from historical ``logs`` rows to current bytes is treated as history.
Only known URLs in the declared selection are read; object directories are never
walked. This module does not open archives or contact the network.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from scripts.download_tse_logs import BASE, manifest_path

INVENTORY_VERSION = "legacy-manifest-inventory-v1"
IDENTITY_VERSION = "canonical-json-sha256-v1"
DEFAULT_UFS = tuple("ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj".split())
ALL_UFS = tuple(
    "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz".split()
)
ELECTION = {
    "year": 2026,
    "pleito_code": "3221",
    "election_code": "6258",
    "round": 2,
    "election_date": "2026-10-25",
}


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(namespace: str, value) -> str:
    return f"{namespace}:v1:{digest(value)}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def section_key(row) -> tuple[str, str, str, str]:
    return row["uf"], row["municipality"], row["zone"], row["section"]


def section_directory(key) -> str:
    uf, municipality, zone, section = key
    return f"{BASE}/ele2026/arquivo-urna/3221/dados/{uf}/{municipality}/{zone}/{section}"


def aux_url(key) -> str:
    uf, municipality, zone, section = key
    return f"{section_directory(key)}/p003221-{uf}-m{municipality}-z{zone}-s{section}-aux.json"


def index_url(uf: str) -> str:
    return f"{BASE}/ele2026/arquivo-urna/3221/config/{uf}/{uf}-p003221-cs.json"


def safe_source(root: Path, relative: str) -> Path:
    """Confine reads to regular source objects, rejecting absolute/escaping paths."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe_storage_locator")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("unsafe_storage_locator")
    return target


def hash_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    length = 0
    with path.open("rb") as handle:
        while body := handle.read(1024 * 1024):
            hasher.update(body)
            length += len(body)
    return hasher.hexdigest(), length


def read_manifest(root: Path, ufs=DEFAULT_UFS, *, section_keys=None) -> dict:
    """Freeze selected rows in one read transaction, including committed WAL.

    ``mode=ro`` intentionally does not use SQLite's ``immutable`` flag, which
    would ignore a live WAL. No collector lock or write transaction is taken.
    Running rows mean unfinished at capture; they do not prove process liveness.
    """
    root = Path(root).resolve()
    ufs = tuple(sorted(set(ufs)))
    if not ufs or not set(ufs) <= set(ALL_UFS):
        raise ValueError("Selection must use known UFs, including ZZ")
    selected = None if section_keys is None else sorted(set(tuple(key) for key in section_keys))
    if selected is not None and (
        not selected
        or any(
            len(key) != 4
            or key[0] not in ufs
            or any(
                not value.isdigit() or len(value) != width
                for value, width in zip(key[1:], (5, 4, 4), strict=True)
            )
            for key in selected
        )
    ):
        raise ValueError(
            "Section keys require selected UF and zero-padded municipality/zone/section"
        )
    manifest = manifest_path(root).resolve()
    placeholders = ",".join("?" for _ in ufs)
    with closing(sqlite3.connect(manifest.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        # First SELECT establishes the consistent read view, before any other table.
        runs = [dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY id")]
        captured_at = utc_now()
        predicate = f"uf IN ({placeholders})"
        parameters = ufs
        if selected is not None:
            predicate = " OR ".join(
                "(uf=? AND municipality=? AND zone=? AND section=?)" for key in selected
            )
            parameters = tuple(value for key in selected for value in key)
        sections = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM sections WHERE {predicate} "
                "ORDER BY run,uf,municipality,zone,section",
                parameters,
            )
        ]
        logs = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM logs WHERE {predicate} ORDER BY run,url", parameters
            )
        ]
        urls = {
            f"{BASE}/comum/config/ele-c.json",
            *(index_url(uf) for uf in ufs),
            *(row["url"] for row in logs),
            *(aux_url(section_key(row)) for row in sections),
        }
        # Include current files even if collection stopped before recording logs.
        # An explicit section selection bounds raw-object reads for later pilots.
        prefixes = (
            [f"{section_directory(key)}/" for key in selected]
            if selected is not None
            else [f"{BASE}/ele2026/arquivo-urna/3221/dados/{uf}/" for uf in ufs]
        )
        files = {}
        for url in sorted(urls):
            row = connection.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone()
            if row is not None:
                files[url] = dict(row)
        for prefix in prefixes:
            for row in connection.execute(
                "SELECT * FROM files WHERE url >= ? AND url < ?", (prefix, prefix + "\uffff")
            ):
                files[row["url"]] = dict(row)
        connection.rollback()
    evidence = {
        "runs": runs,
        "sections": sections,
        "logs": logs,
        "files": [files[url] for url in sorted(files)],
    }
    return {
        "inventory_version": INVENTORY_VERSION,
        "identity_version": IDENTITY_VERSION,
        "source_root": str(root),
        "manifest_locator": str(manifest),
        "manifest_captured_at": captured_at,
        "selection": {"election": ELECTION, "ufs": list(ufs), "section_keys": selected},
        "manifest_rows_sha256": digest(evidence),
        "manifest_rows": evidence,
    }


def inventory_sources(root: Path, ufs=DEFAULT_UFS, *, section_keys=None) -> dict:
    """Hash selected current mappings, preserving failed/unknown historical cases.

    Current source observations are *new local inventory observations*, not HTTP
    requests. Their run and time describe this inventory. Original fetch times and
    validators remain verbatim in ``manifest_rows``. No HTTP status is invented.
    """
    inventory = read_manifest(root, ufs, section_keys=section_keys)
    capture_run = identity(
        "inventory-run", [inventory["manifest_rows_sha256"], inventory["manifest_captured_at"]]
    )
    objects, observations, checks = {}, [], []
    for row in inventory["manifest_rows"]["files"]:
        state, actual_digest, length = "verified", None, None
        try:
            actual_digest, length = hash_file(
                safe_source(Path(inventory["source_root"]), row["path"])
            )
            if actual_digest != row["sha256"] or length != row["bytes"]:
                state = "digest_or_size_mismatch"
        except FileNotFoundError:
            state = "missing_object"
        except (OSError, ValueError, TypeError) as exc:
            state = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        observation_id = identity("source-observation", [capture_run, row["url"], row, state])
        known = state == "verified"
        observation = {
            "observation_id": observation_id,
            "run_id": capture_run,
            "official_url": row["url"],
            "retrieval_url": row["url"],
            "object_sha256": row["sha256"] if known else None,
            "observed_at": inventory["manifest_captured_at"],
            "http_status": None,
            "etag": row["etag"],
            "last_modified_raw": row["last_modified"],
            "observation_status": "success"
            if known
            else "missing"
            if state == "missing_object"
            else "failed",
            "field_states": {"http_status": "unknown"},
        }
        for field in ("etag", "last_modified_raw"):
            if observation[field] is None:
                observation["field_states"][field] = "missing_source"
        if not known:
            observation["field_states"]["object_sha256"] = (
                "missing_source" if state == "missing_object" else "conflict"
            )
        else:
            objects.setdefault(
                row["sha256"],
                {
                    "object_sha256": row["sha256"],
                    "byte_length": row["bytes"],
                    "media_type": None,
                    "storage_locator": row["path"],
                    "field_states": {"media_type": "unknown"},
                },
            )
        observations.append(observation)
        checks.append(
            {
                "url": row["url"],
                "observation_id": observation_id,
                "storage_locator": row["path"],
                "expected_sha256": row["sha256"],
                "expected_bytes": row["bytes"],
                "actual_sha256": actual_digest,
                "actual_bytes": length,
                "state": state,
                "record_locator": {
                    "table": "files",
                    "primary_key": {"url": row["url"]},
                    "archive_segments": [],
                    "byte_range": None,
                },
            }
        )
    # Logs only advertise URLs/packages. They never prove which bytes a run saw.
    historical = [
        {
            **row,
            "object_sha256": None,
            "mapping_state": "historical_mapping_unknown",
            "record_locator": {
                "table": "logs",
                "primary_key": {"run": row["run"], "url": row["url"]},
                "archive_segments": [],
                "byte_range": None,
            },
        }
        for row in inventory["manifest_rows"]["logs"]
    ]
    inventory.update(
        {
            "source_object": sorted(objects.values(), key=lambda row: row["object_sha256"]),
            "source_observation": observations,
            "object_checks": checks,
            "historical_advertisements": historical,
        }
    )
    return inventory
