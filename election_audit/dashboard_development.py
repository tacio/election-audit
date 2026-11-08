"""Compose an exploration export from a frozen protocol, never protected outcomes."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path

import pyarrow.parquet as pq

from election_audit.dashboard_data import _hash, _relative, publish_dataset
from election_audit.research_protocol import load_protocol
from election_audit.source_inventory import digest
from election_audit.types import Row

ALLOWED = ("training", "calibration", "development_inspected")


def export_development(
    features: str | Path,
    protocol: str | Path,
    output: str | Path,
    *,
    predictions: str | Path | None = None,
    cases: str | Path | None = None,
    operations: Iterable[str | Path] = (),
) -> Path:
    """Use SQL joins against pinned partitions before retrieving any outcome values."""
    features, protocol = Path(features).resolve(), Path(protocol).resolve()
    frozen = load_protocol(protocol)
    source = json.loads((features / "manifest.json").read_text())
    catalog = (features / _relative(source["catalog"]["path"])).resolve()
    if not catalog.is_relative_to(features) or _hash(catalog) != source["catalog"]["sha256"]:
        raise ValueError("Feature catalogue checksum mismatch")
    if (
        source["release_id"] != frozen["identity"]["feature_release_id"]
        or source["catalog"]["sha256"] != frozen["identity"]["feature_catalog_sha256"]
    ):
        raise ValueError("Features do not belong to frozen protocol")
    notes = [
        "AC development pilot only; no national inference. Test and municipal-stress outcomes are physically excluded.",
        "Training, calibration and previously inspected units only. No final evaluation has been opened.",
        "First-round comparisons and verified geographic coordinates are unavailable in this release.",
        "Model scores are descriptive, not fraud probabilities; independent corroboration remains unavailable.",
        "Operational records are a small observed sample; clocks/exposure and BU-count reconciliation remain qualified.",
    ]
    pins = {"features": source["catalog"]["sha256"], "protocol": frozen["catalog_sha256"]}
    if predictions is not None:
        pins["evaluation"] = _hash(Path(predictions) / "evaluation.json")
    if cases is not None:
        pins["case_artifact"] = _hash(Path(cases) / "artifact.json")
    pins["operations"] = [_hash(Path(p) / "artifact.json") for p in operations]
    with closing(sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "ATTACH DATABASE ? AS frozen", [(protocol / "research.sqlite").as_uri() + "?mode=ro"]
        )
        db.execute("PRAGMA query_only=ON")
        allowed = "p.partition_name IN ('training','calibration','development_inspected')"

        def context(key: str) -> Row:
            row = db.execute(
                "SELECT u.payload,p.partition_name FROM units u JOIN frozen.unit_partition p USING(unit_key) WHERE u.unit_key=? AND "
                + allowed,
                (key,),
            ).fetchone()
            if row is None:
                raise ValueError("Outcome belongs to protected or unknown unit")
            return {**json.loads(row[0]), "partition_name": row[1]}

        def coverage() -> Iterator[Row]:
            for row in db.execute(
                "SELECT uf,round,partition_name,count(*) AS units,sum(source_ready) AS source_ready_units FROM frozen.unit_partition GROUP BY uf,round,partition_name ORDER BY 1,2,3"
            ):
                yield {
                    **dict(row),
                    "readiness": "coverage_metadata_only",
                    "protected_outcomes": row["partition_name"] not in ALLOWED,
                }

        def electoral() -> Iterator[Row]:
            query = (
                "SELECT u.payload AS unit,c.payload AS counts,p.partition_name FROM units u JOIN counts c USING(unit_key) JOIN frozen.unit_partition p USING(unit_key) WHERE "
                + allowed
                + " ORDER BY u.unit_key"
            )
            for row in db.execute(query):
                unit, counts = json.loads(row["unit"]), json.loads(row["counts"])
                # Do not repeat aggregate candidate-destination references in per-unit exports.
                counts.pop("candidate_destinations", None)
                n, votes = counts.get("eligible_electors"), counts.get("total_presidential_ballots")
                counts["turnout"] = (
                    counts["attending_voters"] / n
                    if n and counts.get("attending_voters") is not None
                    else None
                )
                counts["blank_share"] = (
                    counts["blank_votes"] / votes
                    if votes and counts.get("blank_votes") is not None
                    else None
                )
                counts["null_share"] = (
                    counts["null_votes"] / votes
                    if votes and counts.get("null_votes") is not None
                    else None
                )
                yield {
                    **unit,
                    **counts,
                    "partition_name": row["partition_name"],
                    "readiness": "ready" if unit.get("source_ready") else "unavailable",
                }

        def feature_rows(family: str | None = None) -> Iterator[Row]:
            sql = (
                "SELECT f.payload,u.payload AS unit,p.partition_name FROM features f JOIN units u USING(unit_key) JOIN frozen.unit_partition p USING(unit_key) WHERE "
                + allowed
            )
            params = ()
            if family:
                sql += " AND f.feature_id=?"
                params = (family,)
            for row in db.execute(sql + " ORDER BY f.unit_key,f.feature_id,f.component", params):
                yield {
                    **json.loads(row["unit"]),
                    **json.loads(row["payload"]),
                    "partition_name": row["partition_name"],
                }

        def comparisons() -> Iterator[Row]:
            sql = (
                "SELECT c.payload FROM comparisons c WHERE EXISTS (SELECT 1 FROM units u JOIN frozen.unit_partition p USING(unit_key) WHERE u.stable_location_id=c.stable_location_id AND "
                + allowed
                + ") AND NOT EXISTS (SELECT 1 FROM units u JOIN frozen.unit_partition p USING(unit_key) WHERE u.stable_location_id=c.stable_location_id AND NOT ("
                + allowed
                + "))"
            )
            for row in db.execute(sql):
                yield json.loads(row[0])

        def prediction_rows() -> Iterator[Row]:
            if predictions is None:
                return
            directory = Path(predictions).resolve()
            evaluation = json.loads((directory / "evaluation.json").read_text())
            if (
                evaluation["protocol_id"] != frozen["protocol_id"]
                or evaluation["partition_id"] != frozen["partition_id"]
                or evaluation.get("stage") != "development"
                or _hash(directory / "predictions.jsonl") != evaluation["predictions_sha256"]
            ):
                raise ValueError("Prediction artifact identity mismatch")
            pins["predictions"] = evaluation["predictions_sha256"]
            yield {
                **evaluation,
                "record_kind": "development_evaluation",
                "readiness": "descriptive_only",
                "round": 2,
                "uf": "ac",
            }
            with (directory / "predictions.jsonl").open() as stream:
                for line in stream:
                    row = json.loads(line)
                    unit = context(row["unit_key"])
                    if (
                        unit["partition_name"] != "calibration"
                        or row["model_run_id"] != evaluation["model_run_id"]
                    ):
                        raise ValueError(
                            "Development predictions must match calibration population and model"
                        )
                    qs = row.get("quantiles", [])
                    yield {
                        **unit,
                        **row,
                        "record_kind": "calibration_prediction",
                        "predicted_lower": qs[0] if len(qs) == 5 else None,
                        "predicted_median": qs[2] if len(qs) == 5 else None,
                        "predicted_upper": qs[4] if len(qs) == 5 else None,
                        "readiness": "descriptive_only",
                    }

        def case_rows() -> Iterator[Row]:
            if cases is None:
                return
            directory = Path(cases).resolve()
            artifact = json.loads((directory / "artifact.json").read_text())
            if (
                artifact["protocol_id"] != frozen["protocol_id"]
                or artifact["partition_id"] != frozen["partition_id"]
            ):
                raise ValueError("Case artifact belongs to another protocol")
            spec = artifact["files"]["cases.jsonl"]
            if _hash(directory / "cases.jsonl") != spec["sha256"]:
                raise ValueError("Case artifact checksum mismatch")
            pins["cases"] = spec["sha256"]
            with (directory / "cases.jsonl").open() as stream:
                for line in stream:
                    row = json.loads(line)
                    yield {
                        **context(row["unit_key"]),
                        **row,
                        "record_kind": "investigation",
                        "readiness": "unresolved_independent_corroboration",
                    }

        def models() -> Iterator[Row]:
            yield from prediction_rows()
            yield from case_rows()

        def operational_rows() -> Iterator[Row]:
            for directory in operations:
                directory = Path(directory).resolve()
                artifact_body = (directory / "artifact.json").read_bytes()
                import hashlib

                if (
                    hashlib.sha256(artifact_body).hexdigest()
                    != (directory / "artifact.json.sha256").read_text().strip()
                ):
                    raise ValueError("Operational artifact metadata checksum mismatch")
                artifact = json.loads(artifact_body)
                for filename in ("sessions.parquet", "cycles.parquet"):
                    if _hash(directory / filename) != artifact["files"][filename]["sha256"]:
                        raise ValueError("Operational source checksum mismatch")
                counts = Counter()
                for batch in pq.ParquetFile(directory / "cycles.parquet").iter_batches(
                    batch_size=2048
                ):
                    for raw in batch.to_pylist():
                        c = json.loads(raw["payload"])
                        counts[(c["session_id"], c["completion_state"])] += 1
                for batch in pq.ParquetFile(directory / "sessions.parquet").iter_batches(
                    batch_size=2048
                ):
                    for raw in batch.to_pylist():
                        session = json.loads(raw["payload"])
                        identities = set()
                        for witness in session.get("witnesses", []):
                            m = re.search(
                                r"/arquivo-urna/(3220|3221)/dados/([a-z]{2})/(\d{5})/(\d{4})/(\d{4})/",
                                witness.get("url", ""),
                            )
                            if m:
                                pleito, uf, municipality, zone, section = m.groups()
                                identities.add(
                                    (1 if pleito == "3220" else 2, uf, municipality, zone, section)
                                )
                        if len(identities) != 1:
                            continue
                        row = db.execute(
                            "SELECT u.payload,p.partition_name FROM units u JOIN frozen.unit_partition p USING(unit_key) WHERE u.round=? AND u.uf=? AND u.municipality_tse=? AND u.zone=? AND u.section=? AND "
                            + allowed,
                            next(iter(identities)),
                        ).fetchone()
                        if row is None or session.get("round") != next(iter(identities))[0]:
                            continue
                        unit = json.loads(row[0])
                        yield {
                            **unit,
                            **session,
                            "partition_name": row[1],
                            "observed_completed_cycles": counts[
                                (session["session_id"], "completed")
                            ],
                            "observed_unresolved_cycles": counts[
                                (session["session_id"], "unresolved")
                            ],
                            "readiness": "observed_sample_only_clocks_unresolved",
                        }

        tables = {
            "coverage": coverage(),
            "electoral": electoral(),
            "features": feature_rows(),
            "unanimity": feature_rows("unanimous_results"),
            "rounds": comparisons(),
            "models": models(),
            "operations": operational_rows(),
        }
        identity = digest(
            [
                "development-dashboard-v1",
                source["release_id"],
                frozen["protocol_id"],
                frozen["partition_id"],
                pins,
            ]
        )
        result = publish_dataset(
            tables, output, release_id=identity, access_state="development_only", notes=notes
        )
    proof = {
        "protocol_id": frozen["protocol_id"],
        "partition_id": frozen["partition_id"],
        "source_pins": pins,
        "allowed_partitions": list(ALLOWED),
        "excluded_partitions": ["test", "municipal_stress", "unavailable"],
        "partition_counts": frozen["partition_counts"],
    }
    (Path(output) / "access-proof.json").write_text(
        json.dumps(proof, sort_keys=True, indent=2) + "\n"
    )
    return result
