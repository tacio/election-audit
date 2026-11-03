"""Executable fitting smoke and protected-data regression using synthetic outcomes."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from election_audit.research_evaluation import final_evaluation_complete
from election_audit.research_models import (
    _load_model,
    evaluate_models,
    fit_models,
    perturb_mechanism,
    run_mechanism_validation,
)
from election_audit.research_protocol import hash_file, publish_protocol


def fixture(root):
    source = root / "features"
    source.mkdir()
    with sqlite3.connect(source / "features.sqlite") as db:
        db.executescript(
            "CREATE TABLE units(unit_key TEXT,round INTEGER,uf TEXT,municipality_tse TEXT,zone TEXT,stable_location_id TEXT,source_ready INTEGER,payload TEXT);CREATE TABLE features(unit_key TEXT,feature_id TEXT,component TEXT,value REAL,numerator REAL,denominator REAL,readiness_state TEXT);"
        )
        for n in range(300):
            key = f"unit-{n}"
            value = 0.4 + (n % 30) / 100
            db.execute(
                "INSERT INTO units VALUES(?,?,?,?,?,?,?,?)",
                (key, 2, "ac", str(n // 3).zfill(5), "0001", f"location-{n}", 1, "{}"),
            )
            db.execute(
                "INSERT INTO features VALUES(?,?,?,?,?,?,?)",
                (key, "turnout_target", "turnout", value, value * 100, 100, "ready"),
            )
            db.execute(
                "INSERT INTO features VALUES(?,?,?,?,?,?,?)",
                (key, "peer_covariates", "electorate", 100 + n, None, None, "ready"),
            )
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "version": "feature-release-v1",
                "release_id": "synthetic-model-fixture",
                "catalog": {
                    "path": "features.sqlite",
                    "sha256": hash_file(source / "features.sqlite"),
                },
            }
        )
    )
    protocol = root / "protocol"
    publish_protocol(source, protocol)
    return source, protocol


class ResearchModelTests(unittest.TestCase):
    def test_fit_reproducibility_integrity_and_final_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, protocol = fixture(root)
            first = fit_models(source, protocol, root / "model-a")
            second = fit_models(source, protocol, root / "model-b")
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["metrics"], second["metrics"])
            with sqlite3.connect(protocol / "research.sqlite") as db:
                training = {
                    r[0]
                    for r in db.execute(
                        "SELECT unit_key FROM unit_partition WHERE partition_name='training'"
                    )
                }
                test = {
                    r[0]
                    for r in db.execute(
                        "SELECT unit_key FROM unit_partition WHERE partition_name='test'"
                    )
                }
            _, model = _load_model(root / "model-a")
            self.assertEqual({r["unit_key"] for r in model["training"]}, training)
            self.assertFalse(training & test)
            dev = evaluate_models(source, protocol, root / "model-a", root / "development")
            self.assertEqual(dev["stage"], "development")
            result = evaluate_models(source, protocol, root / "model-a", root / "final", final=True)
            self.assertEqual(result["eligible_predictions"], len(test))
            with sqlite3.connect(root / "model-a" / "journal.sqlite") as db:
                self.assertTrue(final_evaluation_complete(db))
            with self.assertRaises(ValueError):
                evaluate_models(
                    source, protocol, root / "model-a", root / "second-final", final=True
                )
            with (root / "model-b" / "model.pickle").open("ab") as stream:
                stream.write(b"damage")
            with self.assertRaises(ValueError):
                _load_model(root / "model-b")

    def test_changed_source_and_matrix_bound_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, protocol = fixture(root)
            with self.assertRaises(ValueError):
                fit_models(source, protocol, root / "bounded", max_rows=1)
            with sqlite3.connect(source / "features.sqlite") as db:
                db.execute("UPDATE features SET value=0.99 WHERE unit_key='unit-1'")
            with self.assertRaises(ValueError):
                fit_models(source, protocol, root / "changed")


class MechanismValidationTests(unittest.TestCase):
    def test_count_caps_and_redacted_history_transforms(self):
        records = [
            {
                "group": "ac:1",
                "a": 30,
                "b": 40,
                "other": 10,
                "electorate": 100,
                "events": [{"kind": "complete", "timestamp": 1}],
            }
        ]
        original = copy.deepcopy(records)
        for mechanism in [
            "additions",
            "switching",
            "turnout_reduction",
            "duplicated_history",
            "missing_history",
            "clock_error",
        ]:
            result = perturb_mechanism(
                records, mechanism, seed=42, fraction=1, concentration="dispersed"
            )
            self.assertTrue(result[0]["injected"])
            self.assertEqual(records, original)
            self.assertLessEqual(result[0]["a"] + result[0]["b"] + result[0]["other"], 100)
        records[0]["a"] = 50
        saturated = perturb_mechanism(
            records, "additions", seed=42, fraction=1, concentration="municipal"
        )
        self.assertFalse(saturated[0]["injected"])

    def test_resume_invokes_refit_and_pins_inputs(self):
        records = [{"group": "ac:1", "a": 30, "b": 40, "other": 10, "electorate": 100}]
        spec = {
            "mechanisms": ["switching"],
            "concentration": ["dispersed"],
            "affected_fractions": [0, 1],
            "seed": 42,
            "repetitions": 2,
        }
        calls = []

        def refit(train, cal, test, seed):
            calls.append(seed)
            self.assertIsNot(train, records)
            return [r["injected"] for r in test]

        with tempfile.TemporaryDirectory() as tmp:
            first = run_mechanism_validation(
                records,
                records,
                records,
                tmp,
                fit_calibrate_score=refit,
                callback_id="synthetic-refit-v1",
                specification=spec,
            )
            self.assertEqual(first["states"], {"complete": 4})
            self.assertEqual(len(calls), 4)
            run_mechanism_validation(
                records,
                records,
                records,
                tmp,
                fit_calibrate_score=refit,
                callback_id="synthetic-refit-v1",
                specification=spec,
            )
            self.assertEqual(len(calls), 4)
            with self.assertRaises(ValueError):
                run_mechanism_validation(
                    records,
                    records,
                    records,
                    tmp,
                    fit_calibrate_score=refit,
                    callback_id="changed-refit",
                    specification=spec,
                )
