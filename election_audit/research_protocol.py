"""Frozen disk-backed research partitions and append-only inspected-location history."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from election_audit.source_inventory import canonical, digest, utc_now

VERSION = "research-protocol-v2"
DEFAULT_DESIGN = {
    "version": VERSION,
    "seed": 42,
    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
    "municipal_stress_fraction": 0.1,
    "outcomes": [
        "turnout",
        "candidate_a_share",
        "candidate_b_share",
        "blank_share",
        "null_share",
        "operational_duration",
        "operational_gap",
    ],
    "variants": [
        "current_cycle",
        "no_first_round",
        "operational_adjusted",
        "operational_mechanism",
    ],
    "joint_score": "maximum_normalized_interval_exceedance",
    "quantiles": [0.025, 0.25, 0.5, 0.75, 0.975],
    "forest": {
        "n_estimators": 256,
        "max_depth": 24,
        "min_samples_leaf": [25, 100],
        "n_jobs": 4,
        "training_folds": 3,
    },
    "multiplicity": {"method": "BY", "alpha": 0.05, "valid_pvalues_required": True},
    "simulations": {
        "seed": 42,
        "repetitions": 100,
        "affected_fractions": [0, 0.01, 0.05, 0.10],
        "concentration": ["dispersed", "municipal"],
        "mechanisms": [
            "additions",
            "switching",
            "turnout_reduction",
            "duplicated_history",
            "missing_history",
            "clock_error",
        ],
    },
    "inference": "descriptive_by_default; exchangeability_not_established_by_diagnostics",
    "historical_extensions": [2022, 2018],
}


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def read_only(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    try:
        yield db
    finally:
        db.close()


def valid_anchor(anchor):
    return (
        isinstance(anchor, dict)
        and isinstance(anchor.get("object_sha256"), str)
        and len(anchor["object_sha256"]) == 64
        and all(c in "0123456789abcdef" for c in anchor["object_sha256"])
        and isinstance(anchor.get("record_locator"), str)
        and bool(anchor["record_locator"])
    )


def record_inspection(registry, stable_location_id, *, reason, evidence):
    """An append-only registry survives reseeding and new source populations."""
    if (
        not isinstance(stable_location_id, str)
        or not stable_location_id
        or not reason
        or not valid_anchor(evidence)
    ):
        raise ValueError("Inspection needs stable identity, reason and preserved-record anchor")
    path = Path(registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS inspection(record_id TEXT PRIMARY KEY,stable_location_id TEXT NOT NULL,reason TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL)"
        )
        key = digest([stable_location_id, reason, evidence])
        db.execute(
            "INSERT OR IGNORE INTO inspection VALUES(?,?,?,?,?)",
            (key, stable_location_id, reason, canonical(evidence).decode(), utc_now()),
        )
    return key


def _probability(seed, kind, identity):
    return int(digest([VERSION, seed, kind, identity]), 16) / (1 << 256)


def load_protocol(path):
    path = Path(path).resolve()
    document = json.loads((path / "protocol.json").read_text())
    if document.get("version") != VERSION or document.get("protocol_id") != digest(
        document["identity"]
    ):
        raise ValueError("Protocol identity mismatch")
    if document["identity"]["design"]["version"] != VERSION:
        raise ValueError("Unknown frozen research design")
    if hash_file(path / "research.sqlite") != document["catalog_sha256"]:
        raise ValueError("Protocol partition catalogue changed")
    return document


def publish_protocol(feature_release, output, *, inspected=None, seed=42):
    """Stream units into an immutable population; no outcome values are loaded."""
    if type(seed) is not int:
        raise ValueError("Seed must be an integer")
    feature_release = Path(feature_release).resolve()
    source = json.loads((feature_release / "manifest.json").read_text())
    if source.get("version") != "feature-release-v1":
        raise ValueError("Expected feature-release-v1")
    spec = source["catalog"]
    relative = Path(spec["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe feature catalogue locator")
    catalog = (feature_release / relative).resolve()
    if not catalog.is_relative_to(feature_release) or hash_file(catalog) != spec["sha256"]:
        raise ValueError("Feature catalogue pin mismatch")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".protocol-", dir=output.parent))
    db = None
    try:
        db = sqlite3.connect(staging / "research.sqlite")
        db.executescript("""
          CREATE TABLE unit_partition(unit_key TEXT PRIMARY KEY,stable_location_id TEXT,partition_name TEXT NOT NULL,uf TEXT,municipality_tse TEXT,round INTEGER,source_ready INTEGER);
          CREATE TABLE inspection_history(record_id TEXT PRIMARY KEY,stable_location_id TEXT,reason TEXT,evidence TEXT,created_at TEXT);
          CREATE INDEX partition_name ON unit_partition(partition_name);
          CREATE INDEX stable_location ON unit_partition(stable_location_id);
          CREATE TABLE location(stable_location_id TEXT PRIMARY KEY,uf TEXT,municipality_tse TEXT,partition_name TEXT);
          CREATE TABLE frozen_document(name TEXT PRIMARY KEY,payload TEXT NOT NULL);
        """)
        if inspected is not None:
            with read_only(inspected) as registry:
                for row in registry.execute("SELECT * FROM inspection ORDER BY record_id"):
                    if not valid_anchor(json.loads(row["evidence"])):
                        raise ValueError("Invalid persisted inspection evidence")
                    db.execute("INSERT INTO inspection_history VALUES(?,?,?,?,?)", tuple(row))
        design = {**DEFAULT_DESIGN, "seed": seed}
        row_hash = hashlib.sha256()
        count = 0
        with read_only(catalog) as features:
            for row in features.execute(
                "SELECT unit_key,stable_location_id,uf,municipality_tse,round,source_ready FROM units ORDER BY unit_key"
            ):
                row_hash.update(canonical(dict(row)) + b"\n")
                key, stable, uf, municipality, round_number, ready = tuple(row)
                if round_number not in (1, 2):
                    raise ValueError("Unsupported research round")
                partition = "unavailable"
                if stable:
                    if not uf or not municipality:
                        raise ValueError("Stable location requires explicit geography")
                    existing = db.execute(
                        "SELECT uf,municipality_tse,partition_name FROM location WHERE stable_location_id=?",
                        (stable,),
                    ).fetchone()
                    if existing and existing[:2] != (uf, municipality):
                        raise ValueError("Stable location conflicts across geographic strata")
                    if existing:
                        assigned = existing[2]
                    elif db.execute(
                        "SELECT 1 FROM inspection_history WHERE stable_location_id=? LIMIT 1",
                        (stable,),
                    ).fetchone():
                        assigned = "development_inspected"
                    elif _probability(seed, "municipality", [uf, municipality]) < 0.1:
                        assigned = "municipal_stress"
                    else:
                        number = _probability(seed, "location", [uf, municipality, stable])
                        assigned = (
                            "training"
                            if number < 0.6
                            else "calibration"
                            if number < 0.8
                            else "test"
                        )
                    db.execute(
                        "INSERT OR IGNORE INTO location VALUES(?,?,?,?)",
                        (stable, uf, municipality, assigned),
                    )
                    partition = assigned if ready else "unavailable"
                db.execute(
                    "INSERT INTO unit_partition VALUES(?,?,?,?,?,?,?)",
                    (key, stable, partition, uf, municipality, round_number, ready),
                )
                count += 1
                if count % 2048 == 0:
                    db.commit()
        inspection_hash = hashlib.sha256()
        for inspection_row in db.execute(
            "SELECT record_id,stable_location_id FROM inspection_history ORDER BY record_id"
        ):
            inspection_hash.update(canonical(list(inspection_row)) + b"\n")
        if hash_file(catalog) != spec["sha256"]:
            raise ValueError("Feature catalogue changed during partition freeze")
        identity = {
            "design": design,
            "feature_release_id": source["release_id"],
            "feature_catalog_sha256": spec["sha256"],
            "unit_population_sha256": row_hash.hexdigest(),
            "inspection_sha256": inspection_hash.hexdigest(),
        }
        # Only the compact design is JSON; population and inspection rows stay on disk.
        protocol_id = digest(identity)
        partition_hash = hashlib.sha256()
        for partition_row in db.execute("SELECT * FROM unit_partition ORDER BY unit_key"):
            partition_hash.update(canonical(list(partition_row)) + b"\n")
        db.execute(
            "INSERT INTO frozen_document VALUES(?,?)", ("identity", canonical(identity).decode())
        )
        db.commit()
        counts = dict(
            db.execute("SELECT partition_name,count(*) FROM unit_partition GROUP BY partition_name")
        )
        db.close()
        document = {
            "version": VERSION,
            "protocol_id": protocol_id,
            "partition_id": digest([protocol_id, "partition"]),
            "identity": identity,
            "catalog_sha256": hash_file(staging / "research.sqlite"),
            "unit_count": count,
            "partition_rows_sha256": partition_hash.hexdigest(),
            "partition_counts": counts,
            "created_at": utc_now(),
        }
        (staging / "protocol.json").write_bytes(canonical(document) + b"\n")
        staging.rename(output)
        return output
    except BaseException:
        if db is not None:
            db.close()
        shutil.rmtree(staging)
        raise


def research_protocol_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature_release", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspected-registry", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    print(
        publish_protocol(
            args.feature_release, args.output, inspected=args.inspected_registry, seed=args.seed
        )
    )
    return 0
