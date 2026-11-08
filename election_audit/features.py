"""Disk-backed, evidence-qualified feature releases and reviewed round populations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.contracts import load_contract
from election_audit.source_inventory import canonical, digest
from election_audit.types import JSON, Argv, Row

# (value, numerator, denominator, unavailability reason) of one feature component.
type Measure = tuple[Any, Any, Any, str | None]

VERSION = "feature-release-v1"
FEATURES = load_contract("features")["features"]
BATCH = 2048


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def _anchor(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(re.fullmatch(r"[0-9a-f]{64}", value.get("object_sha256", "")))
        and bool(value.get("record_locator"))
    )


def _db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def _initialize(db: sqlite3.Connection) -> None:
    db.executescript("""
      CREATE TABLE units(unit_key TEXT PRIMARY KEY,round INTEGER,uf TEXT,municipality_tse TEXT,zone TEXT,section TEXT,
       principal_section_id TEXT,location_id TEXT,stable_location_id TEXT,source_snapshot_id TEXT,source_ready INTEGER,payload TEXT);
      CREATE TABLE counts(unit_key TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE members(unit_key TEXT,member_key TEXT,PRIMARY KEY(unit_key,member_key));
      CREATE TABLE features(unit_key TEXT,feature_id TEXT,component TEXT,value REAL,numerator REAL,denominator REAL,
       readiness_state TEXT,unavailable_reason TEXT,payload TEXT,PRIMARY KEY(unit_key,feature_id,component));
      CREATE TABLE links(location_id TEXT PRIMARY KEY,stable_location_id TEXT,payload TEXT);
      CREATE TABLE comparisons(stable_location_id TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE operations(unit_key TEXT,session_id TEXT,payload TEXT,PRIMARY KEY(unit_key,session_id));
      CREATE INDEX geography ON units(round,uf,municipality_tse,zone,section);
      CREATE INDEX identities ON units(source_snapshot_id,principal_section_id);
    """)


def _store_unit(
    db: sqlite3.Connection, unit: Row, counts: JSON, members: Iterable[str] = ()
) -> None:
    required = ("round", "uf", "municipality_tse", "zone", "section", "source_snapshot_id")
    if any(unit.get(k) in (None, "") for k in required):
        raise ValueError("Unit requires explicit round/geography/source identity")
    if unit["round"] not in (1, 2):
        raise ValueError("Unsupported round")
    unit = {**unit, "stable_location_id": None}
    unit["unit_key"] = digest([unit[k] for k in required])
    unit.setdefault("principal_section_id", unit["unit_key"])
    unit.setdefault("location_id", None)
    unit.setdefault("source_ready", False)
    key = unit["unit_key"]
    prior = db.execute("SELECT payload FROM units WHERE unit_key=?", (key,)).fetchone()
    if prior:
        if (
            prior[0] != canonical(unit).decode()
            or db.execute("SELECT payload FROM counts WHERE unit_key=?", (key,)).fetchone()[0]
            != canonical(counts).decode()
        ):
            raise ValueError("Conflicting duplicate electoral unit")
        return
    db.execute(
        "INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            key,
            *[
                unit.get(k)
                for k in (
                    "round",
                    "uf",
                    "municipality_tse",
                    "zone",
                    "section",
                    "principal_section_id",
                    "location_id",
                    "stable_location_id",
                    "source_snapshot_id",
                )
            ],
            int(unit["source_ready"]),
            canonical(unit).decode(),
        ),
    )
    db.execute("INSERT INTO counts VALUES(?,?)", (key, canonical(counts).decode()))
    for member in members:
        db.execute("INSERT INTO members VALUES(?,?)", (key, member))


def verified_member_sections(principal: Any, payload: JSON) -> list[str]:
    """Recover preserved BWEB composition without inventing unknown members."""

    def code(value: Any) -> str:
        token = str(value).strip()
        if not re.fullmatch(r"[0-9]{1,4}", token) or int(token) < 1:
            raise ValueError("Invalid composition section code")
        return token.zfill(4)

    principal = code(principal)
    raw = payload.get("composition_raw")
    raw_members = None
    if raw is not None:
        token = str(raw).strip()
        if token in {"#NULO#", "#NULO", "-1", ""}:
            raw_members = [principal]
        elif token not in {"#NE#", "#NE", "-3"}:
            aggregated = [code(value) for value in token.split("/")]
            if principal in aggregated or len(aggregated) != len(set(aggregated)):
                raise ValueError("Duplicate/self aggregated composition section")
            raw_members = [principal, *aggregated]
    explicit = payload.get("member_sections")
    if explicit is not None:
        if not isinstance(explicit, list) or not explicit:
            raise ValueError("Explicit composition requires a nonempty member array")
        members = [code(value) for value in explicit]
        if len(members) != len(set(members)) or principal not in members:
            raise ValueError("Explicit composition must contain principal exactly once")
        if raw_members is not None and set(members) != set(raw_members):
            raise ValueError("Explicit/raw composition conflict")
        return sorted(members)
    return sorted(raw_members) if raw_members is not None else []


def ingest_verification(
    db: sqlite3.Connection, path: str | Path, ufs: Collection[str] | None = None
) -> JSON:
    path = Path(path).resolve()
    if path.is_dir():
        path /= "evidence.sqlite"
    before = _sha(path)
    artifact_path = path.parent / "artifact.json"
    if not artifact_path.exists():
        raise ValueError("Completed verification artifact is required")
    artifact = json.loads(artifact_path.read_text())
    pin = artifact["files"][path.name]
    if pin["sha256"] != before or pin["bytes"] != path.stat().st_size:
        raise ValueError("Verification artifact checksum mismatch")
    with _db(path) as source:
        for row in source.execute(
            "SELECT * FROM section_result ORDER BY round,uf,municipality,zone,section"
        ):
            if ufs and row["uf"] not in ufs:
                continue
            payload = json.loads(row["payload"])
            state = row["state"]
            # Canonical linkage is producer evidence, not inferred from arithmetic.
            linked = (
                payload.get("binary_link")
                in (
                    "verified",
                    "matched",
                    "matched_totalized_binary",
                    "exact_identity_and_counts_match",
                )
                or isinstance(payload.get("binary_link"), dict)
                and payload["binary_link"].get("state") in ("verified", "matched")
            )
            ready = (
                state in ("verified", "ready", "reconciled", "eligible", "content_verified")
                and linked
                and payload.get("complete_choices") is True
            )
            location = payload.get("location_id")
            if not location and payload.get("location_code"):
                location = ":".join(
                    map(
                        str,
                        [
                            2026,
                            row["round"],
                            row["uf"],
                            row["municipality"],
                            row["zone"],
                            payload["location_code"],
                        ],
                    )
                )
            unit = {
                "round": row["round"],
                "uf": row["uf"],
                "municipality_tse": row["municipality"],
                "zone": row["zone"],
                "section": row["section"],
                "location_id": location,
                "source_snapshot_id": before,
                "source_ready": ready,
                "lineage_keys": {
                    "evidence_sha256": before,
                    "record_locator": "section_result:"
                    + ":".join(
                        map(
                            str,
                            [
                                row["round"],
                                row["uf"],
                                row["municipality"],
                                row["zone"],
                                row["section"],
                            ],
                        )
                    ),
                },
            }
            members = verified_member_sections(row["section"], payload)
            members = [
                ":".join([row["uf"], row["municipality"], row["zone"], str(m).zfill(4)])
                for m in members
            ]
            _store_unit(db, unit, payload, members)
    if _sha(path) != before:
        raise ValueError("Electoral evidence changed during capture")
    return {"kind": "verification", "path": str(path), "sha256": before}


def ingest_release(
    db: sqlite3.Connection, path: str | Path, ufs: Collection[str] | None = None
) -> JSON:
    from election_audit.publication import inspect_release, open_release
    from election_audit.release_tools import resolve_release

    path = resolve_release(path)
    document = inspect_release(path)
    with open_release(path, _verified_document=document) as source:
        sql = """SELECT s.payload,e.payload,c.snapshot_id,c.location_id,c.principal_section_id,r.payload
          FROM section_composition c JOIN section s ON s.section_id=c.principal_section_id
          JOIN election e ON e.election_id=s.election_id
          LEFT JOIN section_results r ON r.snapshot_id=c.snapshot_id AND r.principal_section_id=c.principal_section_id
          WHERE c.member_section_id=c.principal_section_id ORDER BY c.snapshot_id,c.principal_section_id"""
        cursor = source.execute(sql)
        while batch := cursor.fetchmany(BATCH):
            for sec, election, snapshot, location, principal, result in batch:
                sec, election = json.loads(sec), json.loads(election)
                if ufs and sec["uf"] not in ufs:
                    continue
                result = json.loads(result) if result else {}
                counts = {
                    **result.get("totals", {}),
                    "choices": result.get("candidate_votes", {}),
                    "complete_choices": result.get("availability") == "ready",
                }
                unit = {
                    "round": election["round"],
                    "uf": sec["uf"],
                    "municipality_tse": sec["municipality_tse"],
                    "zone": sec["zone"],
                    "section": sec["section_code"],
                    "location_id": location,
                    "principal_section_id": principal,
                    "source_snapshot_id": snapshot,
                    "source_ready": result.get("availability") == "ready",
                    "lineage_keys": {
                        "parent_release_id": path.name,
                        "snapshot_id": snapshot,
                        "principal_section_id": principal,
                        "result_version_id": result.get("result_version_id"),
                    },
                }
                _store_unit(db, unit, counts)
        cursor = source.execute(
            "SELECT c.snapshot_id,c.principal_section_id,s.uf,s.municipality_tse,s.zone,s.section_code FROM section_composition c JOIN section s ON c.member_section_id=s.section_id"
        )
        while batch := cursor.fetchmany(BATCH):
            for snapshot, principal, uf, mu, zone, section in batch:
                db.execute(
                    "INSERT OR IGNORE INTO members SELECT unit_key,? FROM units WHERE source_snapshot_id=? AND principal_section_id=?",
                    (":".join([uf, mu, zone, section]), snapshot, principal),
                )
    return {
        "kind": "immutable_release",
        "release_id": path.name,
        "manifest_identity": document["identity"],
    }


def apply_links(db: sqlite3.Connection, document: JSON | None = None) -> None:
    if document is None:
        return
    if document.get("version") != "reviewed-feature-links-v1":
        raise ValueError("Unsupported reviewed location links")
    for link in document["links"]:
        if (
            not link.get("verified")
            or not link.get("stable_location_id")
            or not _anchor(link.get("evidence"))
        ):
            raise ValueError("Stable links require reviewed source evidence")
        if not db.execute(
            "SELECT 1 FROM units WHERE location_id=?", (link["location_id"],)
        ).fetchone():
            raise ValueError("Stale location link")
        db.execute(
            "INSERT INTO links VALUES(?,?,?)",
            (link["location_id"], link["stable_location_id"], canonical(link).decode()),
        )
    db.execute(
        "UPDATE units SET stable_location_id=(SELECT stable_location_id FROM links WHERE links.location_id=units.location_id)"
    )


def ingest_operations(db: sqlite3.Connection, path: str | Path) -> JSON:
    path = Path(path).resolve()
    manifest = json.loads((path / "artifact.json").read_text())
    for name, spec in manifest.get("files", {}).items():
        relative = spec.get("path", name) if isinstance(spec, dict) else name
        source = (path / relative).resolve()
        if not source.is_relative_to(path):
            raise ValueError("Unsafe operational path")
        if isinstance(spec, dict) and spec.get("sha256") and _sha(source) != spec["sha256"]:
            raise ValueError("Corrupt operational source")
    session_sources = []
    for name, spec in manifest.get("files", {}).items():
        relative = spec.get("path", name) if isinstance(spec, dict) else name
        if Path(relative).name == "sessions.parquet":
            session_sources.append((path / relative).resolve())
    for source in sorted(session_sources):
        for batch in pq.ParquetFile(source).iter_batches(batch_size=BATCH):
            for record in batch.to_pylist():
                row = json.loads(record["payload"])
                for witness in row.get("witnesses", []):
                    match = re.search(
                        r"/dados/([a-z]{2})/(\d{5})/(\d{4})/(\d{4})/", witness.get("url", "")
                    )
                    if not match:
                        continue
                    uf, mu, zone, sec = match.groups()
                    for (unit_key,) in db.execute(
                        "SELECT unit_key FROM units WHERE round=? AND uf=? AND municipality_tse=? AND zone=? AND section=?",
                        (row["round"], uf, mu, zone, sec),
                    ):
                        prior = db.execute(
                            "SELECT payload FROM operations WHERE unit_key=? AND session_id=?",
                            (unit_key, row["session_id"]),
                        ).fetchone()
                        encoded = canonical(row).decode()
                        if prior and prior[0] != encoded:
                            raise ValueError("Conflicting operational session")
                        db.execute(
                            "INSERT OR IGNORE INTO operations VALUES(?,?,?)",
                            (unit_key, row["session_id"], encoded),
                        )
    return {"kind": "operational_review", "artifact_sha256": _sha(path / "artifact.json")}


def measures(
    unit: Row,
    counts: JSON,
    operations: list[Row],
    candidate_a: str | None = None,
    candidate_b: str | None = None,
) -> dict[tuple[str, str], Measure]:
    totals = counts
    ready = bool(unit["source_ready"])
    numbers: list[Any] = [
        totals.get(f) for f in ("eligible_electors", "attending_voters", "abstaining_electors")
    ]
    accounting = (
        all(type(n) is int and n >= 0 for n in numbers) and numbers[0] == numbers[1] + numbers[2]
    )
    complete = totals.get("complete_choices") is True
    total = totals.get("total_presidential_ballots")
    choices = totals.get("choices", {})
    choices = {str(k): v.get("count") if isinstance(v, dict) else v for k, v in choices.items()}
    candidate = {
        k: v for k, v in choices.items() if re.fullmatch(r"[0-9]{1,2}", k) and 1 <= int(k) <= 94
    }
    legal = totals.get("legal_final_counts_ready") is True
    result: dict[tuple[str, str], Measure] = {}

    def ratio(
        feature: str,
        component: str,
        numerator: Any,
        denominator: Any,
        reason: str | None = None,
    ) -> None:
        if reason is None and (numerator is None or denominator is None):
            reason = "missing_input"
        if reason is None and denominator <= 0:
            reason = "zero_denominator"
        result[(feature, component)] = (
            numerator / denominator if reason is None else None,
            numerator,
            denominator,
            reason,
        )

    ratio(
        "turnout_target",
        "turnout",
        totals.get("attending_voters"),
        totals.get("eligible_electors"),
        None if ready and accounting else "unreconciled_result",
    )
    if (
        unit["round"] == 2
        and candidate_a
        and candidate_b
        and candidate_a != candidate_b
        and set(candidate) == {candidate_a, candidate_b}
    ):
        a, b = candidate.get(candidate_a), candidate.get(candidate_b)
        denom = a + b if type(a) is int and type(b) is int else None
        for code, label in [(candidate_a, "candidate_a_share"), (candidate_b, "candidate_b_share")]:
            ratio(
                "candidate_share_target",
                label,
                candidate.get(code),
                denom,
                None
                if ready and complete and legal
                else "incomplete_or_legally_unreconciled_choices",
            )
    else:
        result[("candidate_share_target", "candidate_a_share")] = (
            None,
            None,
            None,
            "fixed_candidate_pair_required",
        )
    for field, component in [("blank_votes", "blank_share"), ("null_votes", "null_share")]:
        ratio(
            "blank_null_targets",
            component,
            totals.get(field),
            total,
            None if ready and complete and legal else "incomplete_or_legally_unreconciled_choices",
        )
    if (
        ready
        and complete
        and legal
        and type(total) is int
        and total > 0
        and all(type(v) is int for v in candidate.values())
    ):
        special = totals.get("special_votes")
        unresolved = totals.get("unresolved_votes")
        strict = (
            None
            if special is None or unresolved is None
            else int(
                sum(v == total for v in candidate.values()) == 1
                and totals.get("blank_votes") == 0
                and totals.get("null_votes") == 0
                and special == 0
                and unresolved == 0
            )
        )
        result[("unanimous_results", "strict_unanimity")] = (
            strict,
            strict,
            1,
            None if strict is not None else "unknown_special_or_unresolved_category",
        )
        valid = sum(candidate.values())
        result[("unanimous_results", "all_valid_unanimity")] = (
            int(sum(v == valid for v in candidate.values()) == 1) if valid > 0 else None,
            None,
            1,
            None if valid > 0 else "zero_denominator",
        )
    result[("population_coverage", "observed_principal")] = (1, 1, 1, None)
    result[("audit_features", "registered_families")] = (len(FEATURES), len(FEATURES), None, None)
    result[("integrity", "section_accounting")] = (int(accounting), int(accounting), 1, None)
    result[("integrity", "signature_verification")] = (
        None,
        None,
        None,
        "signature_verification_not_supplied",
    )
    result[("peer_covariates", "electorate")] = (
        totals.get("eligible_electors"),
        totals.get("eligible_electors"),
        None,
        None if accounting else "missing_input",
    )
    result[("section_results", "reconciled")] = (int(ready), int(ready), 1, None)
    for feature in FEATURES:
        if not any(k[0] == feature["id"] for k in result):
            result[(feature["id"], "availability")] = (None, None, None, "missing_validated_inputs")
    if operations:
        completed = sum(r.get("cycles_completed", 0) or 0 for r in operations)
        known = all(
            r.get("session_kind") == "official_vota"
            and r.get("overlap_readiness") == "deduplicated"
            and r.get("attendance_reconciled") is True
            for r in operations
        )
        result[("session_summary", "completed_cycles")] = (
            completed if known else None,
            completed,
            len(operations),
            None if known else "unreconciled_or_overlapping_sessions",
        )
    return result


def derive_features(
    db: sqlite3.Connection, candidate_a: str | None = None, candidate_b: str | None = None
) -> None:
    definitions = {f["id"]: f for f in FEATURES}
    for unitrow in db.execute("SELECT * FROM units ORDER BY unit_key"):
        unit = dict(unitrow)
        unit.update(json.loads(unit.pop("payload")))
        unit["stable_location_id"] = unitrow["stable_location_id"]
        counts = json.loads(
            db.execute(
                "SELECT payload FROM counts WHERE unit_key=?", (unit["unit_key"],)
            ).fetchone()[0]
        )
        ops = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT payload FROM operations WHERE unit_key=?", (unit["unit_key"],)
            )
        ]
        for (feature, component), (value, num, den, reason) in measures(
            unit, counts, ops, candidate_a, candidate_b
        ).items():
            definition = definitions[feature]
            readiness = "ready" if reason is None and value is not None else "unavailable"
            row = {
                "unit_key": unit["unit_key"],
                "snapshot_id": unit["source_snapshot_id"],
                "feature_id": feature,
                "component": component,
                "specification_version": VERSION + ":retrospective-descriptive",
                "value": value,
                "numerator": num,
                "denominator": den,
                "unit": "proportion"
                if component
                in {
                    "turnout",
                    "candidate_a_share",
                    "candidate_b_share",
                    "blank_share",
                    "null_share",
                }
                else "indicator"
                if component in {"strict_unanimity", "all_valid_unanimity", "reconciled"}
                else "count",
                "readiness_state": readiness,
                "readiness": readiness,
                "unavailable_reason": reason,
                "analytical_role": definition["analytical_role"],
                "lineage_keys": unit.get("lineage_keys", {}),
                "details": {
                    "definition": definition["definition"],
                    "required_inputs": definition["requires"],
                    "scientific_inference": "not_established",
                    "stable_location_id": unit.get("stable_location_id"),
                },
                **{
                    k: unit.get(k)
                    for k in ("round", "uf", "municipality_tse", "zone", "location_id")
                },
            }
            db.execute(
                "INSERT INTO features VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    unit["unit_key"],
                    feature,
                    component,
                    value,
                    num,
                    den,
                    readiness,
                    reason,
                    canonical(row).decode(),
                ),
            )


def derive_rounds(db: sqlite3.Connection) -> None:
    groups = db.execute(
        "SELECT DISTINCT stable_location_id FROM units WHERE stable_location_id IS NOT NULL ORDER BY 1"
    )
    for (stable,) in groups:
        units = [
            dict(r) for r in db.execute("SELECT * FROM units WHERE stable_location_id=?", (stable,))
        ]
        rounds = {r["round"] for r in units}
        reason = None
        if rounds != {1, 2}:
            reason = "missing_first_or_second_round"
        if any(not r["source_ready"] for r in units):
            reason = "unreconciled_result"
        links = [
            json.loads(r[0])
            for r in db.execute("SELECT payload FROM links WHERE stable_location_id=?", (stable,))
        ]
        if not all(
            all(
                link.get(f) is True
                for f in ("composition_reviewed", "transfers_reviewed", "electorate_reviewed")
            )
            for link in links
        ):
            reason = "unreviewed_composition_transfers_or_electorate"
        sets = {}
        for turn in (1, 2):
            members = []
            for u in units:
                if u["round"] == turn:
                    members += [
                        r[0]
                        for r in db.execute(
                            "SELECT member_key FROM members WHERE unit_key=?", (u["unit_key"],)
                        )
                    ]
            if len(members) != len(set(members)):
                reason = "overlapping_principals"
            sets[turn] = set(members)
        if not sets[1] or sets[1] != sets[2]:
            reason = "incomparable_member_population"
        sums: dict[int, dict[str, Any]] = {}
        for turn in (1, 2):
            records = [
                json.loads(
                    db.execute(
                        "SELECT payload FROM counts WHERE unit_key=?", (u["unit_key"],)
                    ).fetchone()[0]
                )
                for u in units
                if u["round"] == turn
            ]
            sums[turn] = {
                f: sum(r[f] for r in records)
                if records and all(type(r.get(f)) is int for r in records)
                else None
                for f in ("eligible_electors", "attending_voters", "total_presidential_ballots")
            }
        delta = (
            sums[2]["eligible_electors"] - sums[1]["eligible_electors"]
            if all(sums[t]["eligible_electors"] is not None for t in (1, 2))
            else None
        )
        candidate_vectors = {}
        for turn in (1, 2):
            vector = {}
            for u in units:
                if u["round"] != turn:
                    continue
                counts = json.loads(
                    db.execute(
                        "SELECT payload FROM counts WHERE unit_key=?", (u["unit_key"],)
                    ).fetchone()[0]
                )
                for code, count in counts.get("choices", {}).items():
                    count = count.get("count") if isinstance(count, dict) else count
                    if code not in {"95", "96", "97"} and type(count) is int:
                        vector[code] = vector.get(code, 0) + count
            candidate_vectors[turn] = vector
        row = {
            "stable_location_id": stable,
            "candidate_vectors": candidate_vectors,
            "readiness_state": "ready" if reason is None else "unavailable",
            "unavailable_reason": reason,
            "round_totals": sums,
            "electorate_change": delta,
            "member_population": sorted(sets[1]) if reason is None else None,
            "candidate_transfer_inference": "unavailable",
            "source_unit_keys": [u["unit_key"] for u in units],
            "lineage_keys": [link["evidence"] for link in links],
        }
        db.execute("INSERT INTO comparisons VALUES(?,?)", (stable, canonical(row).decode()))


def _write_table(db: sqlite3.Connection, table: str, output: Path) -> JSON:
    files = []
    schema = pa.schema([("payload", pa.string())])
    if table in ("units", "features"):
        query = f"SELECT u.round,u.uf,t.payload FROM {table} t JOIN units u ON u.unit_key=t.unit_key ORDER BY u.round,u.uf,t.unit_key"
    else:
        query = f"SELECT 0,'all',payload FROM {table} ORDER BY 3"
    current = None
    writer: pq.ParquetWriter | None = None
    count = 0
    file: Path | None = None
    batch = []

    def close() -> None:
        if writer and file is not None:  # both set when a partition opens
            if batch:
                writer.write_table(pa.Table.from_arrays([pa.array(batch)], schema=schema))
                batch.clear()
            writer.close()
            files.append(
                {
                    "path": str(file.relative_to(output)),
                    "sha256": _sha(file),
                    "rows": count,
                    "bytes": file.stat().st_size,
                }
            )

    for turn, uf, payload in db.execute(query):
        partition = (turn, uf)
        if current != partition:
            close()
            current = partition
            count = 0
            file = output / "facts" / table / f"round={turn}" / f"uf={uf}" / "part-000.parquet"
            file.parent.mkdir(parents=True, exist_ok=True)
            writer = pq.ParquetWriter(file, schema, compression="zstd")
        batch.append(payload)
        count += 1
        if len(batch) == BATCH:
            assert writer is not None  # opened with the first partition
            writer.write_table(pa.Table.from_arrays([pa.array(batch)], schema=schema))
            batch.clear()
    close()
    return {"files": files, "rows": sum(f["rows"] for f in files)}


def publish_features(
    electoral: Iterable[str | Path],
    output: str | Path,
    *,
    links: JSON | None = None,
    operations: Iterable[str | Path] = (),
    candidate_a: str | None = None,
    candidate_b: str | None = None,
    ufs: Collection[str] | None = None,
) -> JSON:
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".features-", dir=output.parent))
    try:
        db = sqlite3.connect(staging / "features.sqlite")
        db.row_factory = sqlite3.Row
        _initialize(db)
        sources = []
        for source in electoral:
            path = Path(source)
            sources.append(
                ingest_verification(db, path, ufs=ufs)
                if path.name == "evidence.sqlite" or (path / "evidence.sqlite").exists()
                else ingest_release(db, path, ufs=ufs)
            )
        apply_links(db, links)
        for source in operations:
            sources.append(ingest_operations(db, source))
        derive_features(db, candidate_a, candidate_b)
        derive_rounds(db)
        db.commit()
        # Keep the updated stable identity in portable unit payloads.
        for row in db.execute("SELECT unit_key,stable_location_id,payload FROM units"):
            unit = json.loads(row["payload"])
            unit["stable_location_id"] = row["stable_location_id"]
            db.execute(
                "UPDATE units SET payload=? WHERE unit_key=?",
                (canonical(unit).decode(), row["unit_key"]),
            )
        db.commit()
        tables = {
            name: _write_table(db, name, staging) for name in ("units", "features", "comparisons")
        }
        availability = [
            dict(r)
            for r in db.execute(
                "SELECT feature_id,readiness_state,count(*) AS rows FROM features GROUP BY 1,2 ORDER BY 1,2"
            )
        ]
        db.close()
        manifest = {
            "version": VERSION,
            "producer_sha256": _sha(Path(__file__)),
            "registry_sha256": digest(FEATURES),
            "sources": sources,
            "candidate_pair": [candidate_a, candidate_b],
            "links": links,
            "tables": tables,
            "availability": availability,
            "catalog": {"path": "features.sqlite", "sha256": _sha(staging / "features.sqlite")},
            "scope": "explicit_inputs_only",
            "ufs": list(ufs) if ufs else None,
            "outcome_access": "not_partitioned; no automatic dashboard outcome export",
            "historical_extensions": [2022, 2018],
        }
        manifest["release_id"] = digest(manifest)
        (staging / "manifest.json").write_bytes(canonical(manifest) + b"\n")
        staging.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(staging)
        raise


def features_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--electoral", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--links", type=Path)
    parser.add_argument("--operational", type=Path, action="append", default=[])
    parser.add_argument("--candidate-a")
    parser.add_argument("--candidate-b")
    parser.add_argument("--ufs", nargs="+")
    args = parser.parse_args(argv)
    doc = json.loads(args.links.read_text()) if args.links else None
    print(
        json.dumps(
            publish_features(
                args.electoral,
                args.output,
                links=doc,
                operations=args.operational,
                candidate_a=args.candidate_a,
                candidate_b=args.candidate_b,
                ufs=args.ufs,
            ),
            ensure_ascii=False,
        )
    )
    return 0
