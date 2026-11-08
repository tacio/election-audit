"""Development export SQL boundary excludes protected outcomes and checks source pins."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from election_audit.dashboard_data import AuditDataset
from election_audit.dashboard_development import export_development
from election_audit.research_protocol import hash_file, load_protocol, publish_protocol


class DevelopmentDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.features = self.root / "features"
        self.features.mkdir()
        c = sqlite3.connect(self.features / "features.sqlite")
        c.executescript(
            "CREATE TABLE units(unit_key TEXT PRIMARY KEY,stable_location_id TEXT,uf TEXT,municipality_tse TEXT,round INTEGER,source_ready INTEGER,payload TEXT,zone TEXT,section TEXT); CREATE TABLE counts(unit_key TEXT PRIMARY KEY,payload TEXT); CREATE TABLE features(unit_key TEXT,feature_id TEXT,component TEXT,payload TEXT); CREATE TABLE comparisons(stable_location_id TEXT,payload TEXT);"
        )
        for i in range(200):
            key = f"unit-{i}"
            unit = {
                "unit_key": key,
                "stable_location_id": f"location-{i}",
                "uf": "ac",
                "municipality_tse": f"{i // 20:05d}",
                "round": 2,
                "source_ready": True,
                "zone": "0001",
                "section": f"{i:04d}",
            }
            c.execute(
                "INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    unit["stable_location_id"],
                    "ac",
                    unit["municipality_tse"],
                    2,
                    1,
                    json.dumps(unit),
                    "0001",
                    unit["section"],
                ),
            )
            counts = {
                "eligible_electors": 100,
                "attending_voters": 70,
                "total_presidential_ballots": 70,
                "blank_votes": 0,
                "null_votes": 1,
                "choices": {"13": {"count": i}, "22": {"count": 69 - i}},
            }
            c.execute("INSERT INTO counts VALUES(?,?)", (key, json.dumps(counts)))
            c.execute(
                "INSERT INTO features VALUES(?,?,?,?)",
                (
                    key,
                    "turnout_target",
                    "turnout",
                    json.dumps(
                        {
                            **unit,
                            "feature_id": "turnout_target",
                            "component": "turnout",
                            "value": 0.7,
                            "readiness": "ready",
                        }
                    ),
                ),
            )
        c.commit()
        c.close()
        (self.features / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "feature-release-v1",
                    "release_id": "fixture",
                    "catalog": {
                        "path": "features.sqlite",
                        "sha256": hash_file(self.features / "features.sqlite"),
                    },
                }
            )
        )
        self.protocol = publish_protocol(self.features, self.root / "protocol")
        self.frozen = load_protocol(self.protocol)

    def test_physical_exclusion_metadata_counts_and_source_identity(self) -> None:
        output = export_development(self.features, self.protocol, self.root / "export")
        d = AuditDataset.open(output)
        with closing(sqlite3.connect(self.protocol / "research.sqlite")) as c:
            protected = {
                r[0]
                for r in c.execute(
                    "SELECT unit_key FROM unit_partition WHERE partition_name IN ('test','municipal_stress')"
                )
            }
            expected = c.execute(
                "SELECT count(*) FROM unit_partition WHERE partition_name IN ('training','calibration','development_inspected')"
            ).fetchone()[0]
        self.assertTrue(protected)
        self.assertEqual(d.page("electoral", limit=1000)["total"], expected)
        for table in ("electoral", "features"):
            rows = d.page(table, limit=1000)["rows"]
            self.assertFalse({r["unit_key"] for r in rows} & protected)
            self.assertTrue(
                all(
                    r["partition_name"] in ("training", "calibration", "development_inspected")
                    for r in rows
                )
            )
        self.assertEqual(sum(r["units"] for r in d.page("coverage")["rows"]), 200)
        self.assertEqual(d.manifest["access_state"], "development_only")
        self.assertEqual(d.options("features", "feature_id"), ["turnout_target"])
        self.assertNotIn("test", d.options("electoral", "partition_name"))
        self.assertEqual(d.page("features", filters={"component": "turnout"})["total"], expected)
        self.assertEqual(d.page("electoral")["rows"][0]["blank_share"], 0)
        proof = json.loads((output.parent / "access-proof.json").read_text())
        self.assertEqual(proof["protocol_id"], self.frozen["protocol_id"])

    def test_injected_protected_prediction_aborts_publication(self) -> None:
        with closing(sqlite3.connect(self.protocol / "research.sqlite")) as c:
            key = c.execute(
                "SELECT unit_key FROM unit_partition WHERE partition_name='test' LIMIT 1"
            ).fetchone()[0]
        p = self.root / "predictions"
        p.mkdir()
        (p / "predictions.jsonl").write_text(
            json.dumps({"unit_key": key, "model_run_id": "model", "observed": 0.9}) + "\n"
        )
        (p / "evaluation.json").write_text(
            json.dumps(
                {
                    "protocol_id": self.frozen["protocol_id"],
                    "partition_id": self.frozen["partition_id"],
                    "stage": "development",
                    "model_run_id": "model",
                    "predictions_sha256": hash_file(p / "predictions.jsonl"),
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "protected"):
            export_development(self.features, self.protocol, self.root / "blocked", predictions=p)
        self.assertFalse((self.root / "blocked").exists())

    def test_wrong_feature_release_is_rejected(self) -> None:
        p = self.features / "manifest.json"
        d = json.loads(p.read_text())
        d["release_id"] = "wrong"
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "frozen protocol"):
            export_development(self.features, self.protocol, self.root / "wrong")
