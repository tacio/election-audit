"""Frozen research populations, inspection persistence and final evaluation proofs."""

import json
import sqlite3
import tempfile
import unittest
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from election_audit.research_evaluation import (
    append_record,
    final_evaluation_complete,
    open_journal,
    record_evaluation_units,
    record_final_evaluation,
    snapshot_journal,
)
from election_audit.research_protocol import (
    hash_file,
    load_protocol,
    publish_protocol,
    record_inspection,
)


@contextmanager
def connection(path: str | Path) -> Generator[sqlite3.Connection]:
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class ResearchProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.feature = self.root / "features"
        self.feature.mkdir()
        db = sqlite3.connect(self.feature / "features.sqlite")
        db.execute(
            "CREATE TABLE units(unit_key TEXT PRIMARY KEY,stable_location_id TEXT,uf TEXT,municipality_tse TEXT,round INTEGER,source_ready INTEGER)"
        )
        for i in range(200):
            for round_number in (1, 2):
                db.execute(
                    "INSERT INTO units VALUES(?,?,?,?,?,?)",
                    (
                        f"{i:04d}-r{round_number}",
                        f"location-{i}",
                        "ac",
                        f"{i // 20:05d}",
                        round_number,
                        1,
                    ),
                )
        db.execute("INSERT INTO units VALUES('unknown',NULL,'ac','00000',2,1)")
        db.execute("INSERT INTO units VALUES('unready','location-unready','ac','00000',2,0)")
        db.commit()
        db.close()
        self.pin()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def pin(self) -> None:
        (self.feature / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "feature-release-v1",
                    "release_id": "features-1",
                    "catalog": {
                        "path": "features.sqlite",
                        "sha256": hash_file(self.feature / "features.sqlite"),
                    },
                }
            )
        )

    def protocol(self, name: str = "protocol", **kwargs: Any) -> tuple[Path, dict[str, Any]]:
        path = publish_protocol(self.feature, self.root / name, **kwargs)
        return path, load_protocol(path)

    def test_grouped_populations_reproducibility_unknowns_and_catalog_pins(self) -> None:
        a, doc = self.protocol()
        b, second = self.protocol("again")
        self.assertEqual(doc["protocol_id"], second["protocol_id"])
        self.assertEqual(sum(doc["partition_counts"].values()), 402)
        with connection(a / "research.sqlite") as db:
            self.assertFalse(
                db.execute(
                    "SELECT stable_location_id FROM unit_partition WHERE partition_name!='unavailable' GROUP BY stable_location_id HAVING count(DISTINCT partition_name)>1"
                ).fetchall()
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM unit_partition WHERE partition_name='unavailable'"
                ).fetchone()[0],
                2,
            )
            self.assertTrue(
                db.execute("SELECT 1 FROM unit_partition WHERE partition_name='test'").fetchone()
            )
        with connection(a / "research.sqlite") as db:
            db.execute(
                "UPDATE unit_partition SET partition_name='training' WHERE unit_key='unknown'"
            )
        with self.assertRaisesRegex(ValueError, "catalogue changed"):
            load_protocol(a)
        self.assertEqual(hash_file(b / "research.sqlite"), second["catalog_sha256"])

    def test_inspection_registry_survives_new_seed_and_both_rounds(self) -> None:
        original, _ = self.protocol()
        with connection(original / "research.sqlite") as db:
            stable = db.execute(
                "SELECT stable_location_id FROM unit_partition WHERE partition_name='test' LIMIT 1"
            ).fetchone()[0]
        registry = self.root / "inspection.sqlite"
        record_inspection(
            registry,
            stable,
            reason="previous_review",
            evidence={"object_sha256": "a" * 64, "record_locator": "case:1"},
        )
        new, _ = self.protocol("reseeded", inspected=registry, seed=99)
        with connection(new / "research.sqlite") as db:
            self.assertEqual(
                db.execute(
                    "SELECT DISTINCT partition_name FROM unit_partition WHERE stable_location_id=?",
                    (stable,),
                ).fetchall(),
                [("development_inspected",)],
            )
        with self.assertRaises(ValueError):
            record_inspection(registry, stable, reason="missing", evidence={})

    def test_conflicting_stable_geography_and_wrong_feature_pin_rejected(self) -> None:
        with connection(self.feature / "features.sqlite") as db:
            db.execute("UPDATE units SET uf='al' WHERE unit_key='0000-r2'")
        self.pin()
        with self.assertRaisesRegex(ValueError, "geographic strata"):
            self.protocol()
        with connection(self.feature / "features.sqlite") as db:
            db.execute("UPDATE units SET source_ready=0")
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            self.protocol("wrongpin")

    def journal(self) -> tuple[sqlite3.Connection, dict[str, Any], list[Any]]:
        protocol, doc = self.protocol()
        db = open_journal(self.root / "journal.sqlite", protocol)
        common = {"protocol_id": doc["protocol_id"], "partition_id": doc["partition_id"]}
        append_record(db, "model", "model_run", {**common, "fitted": True, "state": "complete"})
        append_record(
            db,
            "access",
            "test_access",
            {**common, "state": "complete", "stage": "final", "model_run_id": "model"},
            references=["model"],
        )
        append_record(
            db,
            "evaluation",
            "evaluation",
            {**common, "state": "complete", "stage": "final", "model_run_id": "model"},
            references=["model", "access"],
        )
        keys = [
            r[0]
            for r in db.execute("SELECT unit_key FROM unit_partition WHERE partition_name='test'")
        ]
        return db, common, keys

    def test_exact_population_final_proof_one_use_and_immutable_record_ids(self) -> None:
        db, common, keys = self.journal()
        self.assertFalse(final_evaluation_complete(db))
        with self.assertRaisesRegex(ValueError, "Conflicting immutable"):
            append_record(db, "model", "model_run", {**common, "fitted": False})
        with self.assertRaisesRegex(ValueError, "one-use"):
            append_record(db, "second-access", "test_access", {**common, "stage": "final"})
        with self.assertRaisesRegex(ValueError, "non-test"):
            record_evaluation_units(db, "evaluation", ["unknown"])
        record_evaluation_units(db, "evaluation", keys)
        record_evaluation_units(db, "access", keys[:-1], access=True)
        with self.assertRaisesRegex(ValueError, "exact protected"):
            record_final_evaluation(
                db, "final", model_run_id="model", evaluation_id="evaluation", access_id="access"
            )
        record_evaluation_units(db, "access", keys, access=True)
        record_final_evaluation(
            db, "final", model_run_id="model", evaluation_id="evaluation", access_id="access"
        )
        self.assertTrue(final_evaluation_complete(db))
        record_final_evaluation(
            db, "final", model_run_id="model", evaluation_id="evaluation", access_id="access"
        )
        with self.assertRaisesRegex(ValueError, "already been used"):
            record_final_evaluation(
                db,
                "second-final",
                model_run_id="model",
                evaluation_id="evaluation",
                access_id="access",
            )
        with self.assertRaisesRegex(ValueError, "require record_final"):
            append_record(db, "forged", "final_evaluation", common)
        db.close()

    def test_wrong_partition_references_and_tampered_proof_are_rejected(self) -> None:
        db, common, keys = self.journal()
        with self.assertRaisesRegex(ValueError, "protocol/partition"):
            append_record(db, "wrong", "null_result", {**common, "partition_id": "wrong"})
        with self.assertRaisesRegex(ValueError, "Missing immutable"):
            append_record(db, "missing", "null_result", common, references=["absent"])
        record_evaluation_units(db, "evaluation", keys)
        record_evaluation_units(db, "access", keys, access=True)
        record_final_evaluation(
            db, "final", model_run_id="model", evaluation_id="evaluation", access_id="access"
        )
        self.assertTrue(final_evaluation_complete(db))
        db.execute(
            "UPDATE unit_partition SET partition_name='training' WHERE unit_key=?", (keys[0],)
        )
        self.assertFalse(final_evaluation_complete(db))
        db.execute("UPDATE unit_partition SET partition_name='test' WHERE unit_key=?", (keys[0],))
        db.execute("UPDATE ledger SET payload='{}' WHERE record_id='model'")
        self.assertFalse(final_evaluation_complete(db))
        db.close()

    def test_frozen_snapshot_and_legacy_dashboard_are_fail_closed(self) -> None:
        db, common, _ = self.journal()
        out = snapshot_journal(db, self.root / "snapshot")
        pin = hash_file(out / "research.sqlite")
        append_record(db, "null", "null_result", {**common, "reason": "unavailable"})
        db.commit()
        self.assertEqual(hash_file(out / "research.sqlite"), pin)
        with self.assertRaises(FileExistsError):
            snapshot_journal(db, out)
        with connection(":memory:") as legacy:
            legacy.execute("CREATE TABLE analysis_ledger(record_kind TEXT,payload TEXT)")
            legacy.execute(
                "INSERT INTO analysis_ledger VALUES('final_evaluation','{\"state\":\"complete\"}')"
            )
            self.assertFalse(final_evaluation_complete(legacy))
        db.close()


if __name__ == "__main__":
    unittest.main()
