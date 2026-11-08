"""Append-only research execution journal and fail-closed final-evaluation proof."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

from election_audit.research_protocol import hash_file, load_protocol, read_only
from election_audit.source_inventory import canonical, digest, utc_now
from election_audit.types import JSON

VERSION = "research-journal-v2"
KINDS = {
    "model_run",
    "prediction",
    "evaluation",
    "simulation",
    "null_result",
    "test_access",
    "final_evaluation",
    "investigation",
    "impact",
}


def open_journal(path: str | Path, protocol: str | Path) -> sqlite3.Connection:
    document = load_protocol(protocol)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS journal_identity(name TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS ledger(record_id TEXT PRIMARY KEY,record_kind TEXT NOT NULL,analysis_run_id TEXT,payload TEXT NOT NULL,references_json TEXT NOT NULL,created_at TEXT NOT NULL,previous_hash TEXT NOT NULL,record_hash TEXT UNIQUE NOT NULL);
      CREATE UNIQUE INDEX IF NOT EXISTS one_final ON ledger(record_kind) WHERE record_kind='final_evaluation';
      CREATE TABLE IF NOT EXISTS unit_partition(unit_key TEXT PRIMARY KEY,stable_location_id TEXT,partition_name TEXT,uf TEXT,municipality_tse TEXT,round INTEGER,source_ready INTEGER);
      CREATE TABLE IF NOT EXISTS evaluation_unit(evaluation_id TEXT,unit_key TEXT,PRIMARY KEY(evaluation_id,unit_key));
      CREATE TABLE IF NOT EXISTS access_unit(access_id TEXT,unit_key TEXT,PRIMARY KEY(access_id,unit_key));
    """)
    identity = canonical(
        {
            "version": VERSION,
            "protocol_id": document["protocol_id"],
            "partition_id": document["partition_id"],
            "catalog_sha256": document["catalog_sha256"],
            "partition_rows_sha256": document["partition_rows_sha256"],
            "feature_release_id": document["identity"]["feature_release_id"],
        }
    ).decode()
    old = db.execute("SELECT payload FROM journal_identity WHERE name='identity'").fetchone()
    if old and old[0] != identity:
        db.close()
        raise ValueError("Journal belongs to another frozen protocol")
    if not old:
        db.execute("INSERT INTO journal_identity VALUES('identity',?)", (identity,))
        with read_only(Path(protocol) / "research.sqlite") as source:
            db.executemany(
                "INSERT INTO unit_partition VALUES(?,?,?,?,?,?,?)",
                source.execute("SELECT * FROM unit_partition"),
            )
        db.commit()
    return db


def append_record(
    db: sqlite3.Connection,
    record_id: str,
    kind: str,
    payload: JSON,
    *,
    references: Iterable[str] = (),
    analysis_run_id: str | None = None,
) -> str:
    if (
        kind not in KINDS
        or not isinstance(record_id, str)
        or not record_id
        or not isinstance(payload, dict)
    ):
        raise ValueError("Invalid versioned research record")
    identity = json.loads(
        db.execute("SELECT payload FROM journal_identity WHERE name='identity'").fetchone()[0]
    )
    if (
        payload.get("protocol_id") != identity["protocol_id"]
        or payload.get("partition_id") != identity["partition_id"]
    ):
        raise ValueError("Record protocol/partition differs from frozen journal")
    references = sorted(set(references))
    if any(
        not db.execute("SELECT 1 FROM ledger WHERE record_id=?", (ref,)).fetchone()
        for ref in references
    ):
        raise ValueError("Missing immutable research reference")
    encoded, refs = canonical(payload).decode(), canonical(references).decode()
    existing = db.execute(
        "SELECT record_kind,analysis_run_id,payload,references_json FROM ledger WHERE record_id=?",
        (record_id,),
    ).fetchone()
    if existing:
        if tuple(existing) != (kind, analysis_run_id, encoded, refs):
            raise ValueError("Conflicting immutable research record")
        return record_id
    if (
        kind in {"test_access", "evaluation"}
        and payload.get("stage") == "final"
        and db.execute(
            "SELECT 1 FROM ledger WHERE record_kind=? AND json_extract(payload, '$.stage')='final' LIMIT 1",
            (kind,),
        ).fetchone()
    ):
        raise ValueError("Final test access/evaluation is one-use; later work is exploratory")
    if kind == "final_evaluation":
        raise ValueError("Final evaluations require record_final_evaluation")
    previous = db.execute("SELECT record_hash FROM ledger ORDER BY rowid DESC LIMIT 1").fetchone()
    previous = previous[0] if previous else "0" * 64
    created = utc_now()
    record_hash = digest([record_id, kind, analysis_run_id, payload, references, created, previous])
    db.execute(
        "INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",
        (record_id, kind, analysis_run_id, encoded, refs, created, previous, record_hash),
    )
    return record_id


def _same_population(db: sqlite3.Connection, table: str, id_column: str, record_id: str) -> bool:
    # Difference queries are disk-backed, including the empty-population case.
    expected = db.execute(
        "SELECT count(*) FROM unit_partition WHERE partition_name='test'"
    ).fetchone()[0]
    if expected == 0:
        return False
    actual = db.execute(
        f"SELECT count(*) FROM {table} WHERE {id_column}=?", (record_id,)
    ).fetchone()[0]
    if actual != expected:
        return False
    return not db.execute(
        f"SELECT unit_key FROM {table} WHERE {id_column}=? EXCEPT SELECT unit_key FROM unit_partition WHERE partition_name='test' LIMIT 1",
        (record_id,),
    ).fetchone()


def record_evaluation_units(
    db: sqlite3.Connection, evaluation_id: str, unit_keys: Iterable[Any], *, access: bool = False
) -> None:
    table, column = ("access_unit", "access_id") if access else ("evaluation_unit", "evaluation_id")
    record = db.execute(
        "SELECT record_kind FROM ledger WHERE record_id=?", (evaluation_id,)
    ).fetchone()
    if not record or record[0] != ("test_access" if access else "evaluation"):
        raise ValueError("Unit rows require the corresponding access/evaluation record")
    for key in unit_keys:
        unit = db.execute(
            "SELECT partition_name FROM unit_partition WHERE unit_key=?", (key,)
        ).fetchone()
        if not unit or unit[0] != "test":
            raise ValueError("Final population includes non-test/unknown units")
        db.execute(f"INSERT OR IGNORE INTO {table} VALUES(?,?)", (evaluation_id, key))


def record_final_evaluation(
    db: sqlite3.Connection, record_id: str, *, model_run_id: str, evaluation_id: str, access_id: str
) -> str:
    """Atomically validate and seal exactly one final evaluation per protocol."""
    identity = json.loads(
        db.execute("SELECT payload FROM journal_identity WHERE name='identity'").fetchone()[0]
    )
    payload = {
        "state": "complete",
        "protocol_id": identity["protocol_id"],
        "partition_id": identity["partition_id"],
        "model_run_id": model_run_id,
        "evaluation_id": evaluation_id,
        "access_id": access_id,
    }
    existing = db.execute("SELECT payload FROM ledger WHERE record_id=?", (record_id,)).fetchone()
    if existing:
        if existing[0] != canonical(payload).decode() or not _validate_final(db, record_id):
            raise ValueError("Conflicting or corrupted final evaluation")
        return record_id
    if db.execute("SELECT 1 FROM ledger WHERE record_kind='final_evaluation' LIMIT 1").fetchone():
        raise ValueError("Final evaluation has already been used")
    refs = {model_run_id: "model_run", evaluation_id: "evaluation", access_id: "test_access"}
    for ref, kind in refs.items():
        row = db.execute(
            "SELECT record_kind,payload FROM ledger WHERE record_id=?", (ref,)
        ).fetchone()
        if not row or row[0] != kind:
            raise ValueError("Final evaluation lacks matching model/access/evaluation references")
        p = json.loads(row[1])
        if (
            p.get("protocol_id") != identity["protocol_id"]
            or p.get("partition_id") != identity["partition_id"]
        ):
            raise ValueError("Final reference belongs to another protocol/partition")
        if kind == "model_run" and (p.get("fitted") is not True or p.get("state") != "complete"):
            raise ValueError("Final evaluation requires a completed fitted model")
        if kind in {"evaluation", "test_access"} and (
            p.get("state") != "complete"
            or p.get("model_run_id") != model_run_id
            or p.get("stage") != "final"
        ):
            raise ValueError("Final access and evaluation must use the frozen model")
    if not _same_population(
        db, "evaluation_unit", "evaluation_id", evaluation_id
    ) or not _same_population(db, "access_unit", "access_id", access_id):
        raise ValueError("Final evaluation/access must cover the exact protected test population")
    previous = db.execute("SELECT record_hash FROM ledger ORDER BY rowid DESC LIMIT 1").fetchone()
    previous = previous[0] if previous else "0" * 64
    created, references = utc_now(), sorted(refs)
    rh = digest(
        [record_id, "final_evaluation", model_run_id, payload, references, created, previous]
    )
    db.execute(
        "INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",
        (
            record_id,
            "final_evaluation",
            model_run_id,
            canonical(payload).decode(),
            canonical(references).decode(),
            created,
            previous,
            rh,
        ),
    )
    return record_id


def _validate_final(db: sqlite3.Connection, record_id: str) -> bool:
    rows = db.execute(
        "SELECT record_id,record_kind,analysis_run_id,payload,references_json,created_at,previous_hash,record_hash FROM ledger ORDER BY rowid"
    )
    previous = "0" * 64
    marker = None
    for row in rows:
        rid, kind, run, payload, refs, created, prior, pin = row
        if (
            prior != previous
            or digest([rid, kind, run, json.loads(payload), json.loads(refs), created, prior])
            != pin
        ):
            return False
        previous = pin
        if rid == record_id and kind == "final_evaluation":
            marker = json.loads(payload)
    if not marker or marker.get("state") != "complete":
        return False
    identity = json.loads(
        db.execute("SELECT payload FROM journal_identity WHERE name='identity'").fetchone()[0]
    )
    partition_hash = __import__("hashlib").sha256()
    for partition_row in db.execute("SELECT * FROM unit_partition ORDER BY unit_key"):
        partition_hash.update(canonical(list(partition_row)) + b"\n")
    if partition_hash.hexdigest() != identity["partition_rows_sha256"]:
        return False
    if any(marker.get(k) != identity[k] for k in ("protocol_id", "partition_id")):
        return False
    model = db.execute(
        "SELECT record_kind,payload FROM ledger WHERE record_id=?", (marker["model_run_id"],)
    ).fetchone()
    if (
        not model
        or model[0] != "model_run"
        or json.loads(model[1]).get("fitted") is not True
        or json.loads(model[1]).get("state") != "complete"
    ):
        return False
    for key, kind, table, column in [
        ("evaluation_id", "evaluation", "evaluation_unit", "evaluation_id"),
        ("access_id", "test_access", "access_unit", "access_id"),
    ]:
        row = db.execute(
            "SELECT record_kind,payload FROM ledger WHERE record_id=?", (marker[key],)
        ).fetchone()
        if not row or row[0] != kind:
            return False
        p = json.loads(row[1])
        if (
            p.get("stage") != "final"
            or p.get("state") != "complete"
            or p.get("model_run_id") != marker["model_run_id"]
            or any(p.get(k) != identity[k] for k in ("protocol_id", "partition_id"))
            or not _same_population(db, table, column, marker[key])
        ):
            return False
    return True


def final_evaluation_complete(db: Any, document: JSON | None = None) -> bool:
    """Dashboard seam: ordinary inspection is never a final-evaluation certificate."""
    try:
        rows = db.execute(
            "SELECT record_id FROM ledger WHERE record_kind='final_evaluation'"
        ).fetchall()
        return len(rows) == 1 and _validate_final(db, rows[0][0])
    except sqlite3.Error, KeyError, TypeError, ValueError:
        return False
    except Exception:
        # DuckDB connections on old releases lack the new journal tables.
        return False


def snapshot_journal(db: sqlite3.Connection, output: str | Path) -> Path:
    """Atomically freeze a journal; mutable execution state is never a release."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".journal-", dir=output.parent))
    try:
        db.commit()
        with closing(sqlite3.connect(staging / "research.sqlite")) as target:
            db.backup(target)
        document = {
            "version": VERSION,
            "sha256": hash_file(staging / "research.sqlite"),
            "final_evaluation_complete": final_evaluation_complete(db),
        }
        (staging / "journal.json").write_bytes(canonical(document) + b"\n")
        staging.rename(output)
        return output
    except BaseException:
        shutil.rmtree(staging)
        raise
