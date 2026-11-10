"""Investigation selection cannot expose test units or create unconditional fraud claims."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from election_audit.investigations import (
    build_cases,
    conditional_scenario,
    export_cases_dataset,
    geographic_sensitivity,
    read_national_margin,
    record_review,
)
from election_audit.research_protocol import hash_file, load_protocol, publish_protocol
from election_audit.source_inventory import canonical


class InvestigationTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Any, ...]:
        source = root / "features"
        source.mkdir()
        with sqlite3.connect(source / "features.sqlite") as db:
            db.execute(
                "CREATE TABLE units(unit_key TEXT,stable_location_id TEXT,uf TEXT,municipality_tse TEXT,round INTEGER,source_ready INTEGER,zone TEXT,section TEXT,source_snapshot_id TEXT,payload TEXT)"
            )
            db.executemany(
                "INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        str(i),
                        f"location-{i // 2}",
                        "ac",
                        str(i // 20),
                        2,
                        1,
                        "0001",
                        str(i),
                        "snapshot-1",
                        '{"lineage_keys":{"source":"fixture"}}',
                    )
                    for i in range(200)
                ],
            )
        (source / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "feature-release-v1",
                    "release_id": "synthetic",
                    "catalog": {
                        "path": "features.sqlite",
                        "sha256": hash_file(source / "features.sqlite"),
                    },
                }
            )
        )
        protocol = publish_protocol(source, root / "protocol")
        doc = load_protocol(protocol)
        with sqlite3.connect(protocol / "research.sqlite") as db:
            dev = [
                r[0]
                for r in db.execute(
                    "SELECT unit_key FROM unit_partition WHERE partition_name='calibration'"
                )
            ]
            test = db.execute(
                "SELECT unit_key FROM unit_partition WHERE partition_name='test' LIMIT 1"
            ).fetchone()[0]
        evaluation = root / "evaluation"
        evaluation.mkdir()
        predictions = [
            {
                "unit_key": k,
                "observed": 0.5,
                "quantiles": [0.1, 0.2, 0.3, 0.4, 0.6],
                "score": i / 10,
                "signed_residual": (-1 if i % 2 else 1) * 0.2,
                "tail_rank": 0.2,
                "interpretation": "descriptive_only",
                "model_run_id": "model-1",
            }
            for i, k in enumerate(dev)
        ]

        def pin(rows: list[dict[str, Any]]) -> None:
            (evaluation / "predictions.jsonl").write_bytes(
                b"".join(canonical(r) + b"\n" for r in rows)
            )
            (evaluation / "evaluation.json").write_text(
                json.dumps(
                    {
                        "stage": "development",
                        "state": "complete",
                        "protocol_id": doc["protocol_id"],
                        "partition_id": doc["partition_id"],
                        "model_run_id": "model-1",
                        "predictions_sha256": hash_file(evaluation / "predictions.jsonl"),
                    }
                )
            )

        pin(predictions)
        return source, protocol, evaluation, predictions, test, pin

    def test_development_symmetric_cases_control_export_and_review(self) -> None:
        from election_audit.dashboard_data import AuditDataset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, protocol, evaluation, predictions, test, pin = self.fixture(root)
            result = build_cases(
                source, protocol, evaluation, root / "cases", per_family=2, controls=3
            )
            self.assertEqual(result["counts"]["ranked_positive"], 2)
            self.assertEqual(result["counts"]["ranked_negative"], 2)
            packets = [json.loads(s) for s in (root / "cases/cases.jsonl").read_text().splitlines()]
            self.assertNotIn(test, [p["unit_key"] for p in packets])
            self.assertFalse(any(p["candidate_blinded"] for p in packets))  # xr1 P7-04
            export_cases_dataset(root / "cases", protocol, root / "dashboard")
            ds = AuditDataset.open(root / "dashboard/dataset.json")
            self.assertEqual(ds.manifest["access_state"], "development_only")
            rid = record_review(
                protocol,
                root / "journal.sqlite",
                packets[0],
                conclusion="unresolved",
                explanations=["local variation"],
            )
            self.assertEqual(
                rid,
                record_review(
                    protocol,
                    root / "journal.sqlite",
                    packets[0],
                    conclusion="unresolved",
                    explanations=["local variation"],
                ),
            )
            with self.assertRaises(ValueError):
                record_review(
                    protocol,
                    root / "journal.sqlite",
                    packets[0],
                    conclusion="fraud",
                    explanations=["score"],
                )
            with self.assertRaises(FileExistsError):
                build_cases(source, protocol, evaluation, root / "cases")

    def test_protected_prediction_and_changed_evidence_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, protocol, evaluation, rows, test, pin = self.fixture(root)
            pin([*rows, {**rows[0], "unit_key": test}])
            with self.assertRaisesRegex(ValueError, "Protected"):
                build_cases(source, protocol, evaluation, root / "cases")
            self.assertFalse((root / "cases").exists())
            pin(rows)
            (evaluation / "predictions.jsonl").write_text("{}")
            with self.assertRaisesRegex(ValueError, "changed"):
                build_cases(source, protocol, evaluation, root / "cases")

    def scenario(self) -> dict[str, Any]:
        return {
            "mechanism": "removal_exact",
            "population": [
                {
                    "round": 2,
                    "election": "6258",
                    "principal_section_id": "section-1",
                    "a": 7,
                    "b": 2,
                    "other": 1,
                    "cap": 3,
                }
            ],
            "assumed_margin": 10,
        }

    def test_conditional_caps_overlap_and_no_national_guess(self) -> None:
        doc = self.scenario()
        result = conditional_scenario(doc)
        self.assertEqual(result["margin_change_bounds"], [-2, 3])
        self.assertEqual(result["corrected_margin_bounds"], [7, 12])
        self.assertEqual(result["cap_status"], "hypothetical_caps")
        del doc["assumed_margin"]
        self.assertIsNone(conditional_scenario(doc)["corrected_margin_bounds"])
        doc["population"].append(dict(doc["population"][0]))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            conditional_scenario(doc)
        doc = self.scenario()
        doc["population"][0]["cap"] = 11
        with self.assertRaisesRegex(ValueError, "cap exceeds"):
            conditional_scenario(doc)
        doc = self.scenario()
        doc["mechanism"] = "switching_cap"
        self.assertEqual(conditional_scenario(doc)["margin_change_bounds"], [0, 6])
        doc["population"][0]["round"] = 1
        with self.assertRaises(ValueError):
            conditional_scenario(doc)

    def test_uf_reference_is_never_national(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ref.json"
            path.write_text(
                json.dumps(
                    {
                        "ele": "6258",
                        "t": "2",
                        "f": "o",
                        "tf": "s",
                        "dv": "s",
                        "tpabr": "uf",
                        "cdabr": "ac",
                        "and": "f",
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "not a UF"):
                read_national_margin(path, "13", "22")

    def test_geographic_full_pipeline_resume_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sensitivity"
            calls = []

            def callback(blocks: list[str], seed: int) -> dict[str, Any]:
                calls.append(seed)
                if seed == 44:
                    raise RuntimeError("interrupted")
                return {
                    "fit_rerun": True,
                    "selection_rerun": True,
                    "baseline_relative_excess": len(set(blocks)),
                }

            with self.assertRaises(RuntimeError):
                geographic_sensitivity(
                    ["a", "b", "c"], path, callback, pipeline_sha256="a" * 64, repetitions=5
                )
            resumed = []

            def full(blocks: list[str], seed: int) -> dict[str, Any]:
                resumed.append(seed)
                return {
                    "fit_rerun": True,
                    "selection_rerun": True,
                    "baseline_relative_excess": len(set(blocks)),
                }

            summary = geographic_sensitivity(
                ["a", "b", "c"], path, full, pipeline_sha256="a" * 64, repetitions=5
            )
            self.assertEqual(resumed, [44, 45, 46])
            self.assertEqual(summary["repetitions"], 5)
            self.assertEqual(
                summary,
                geographic_sensitivity(
                    ["a", "b", "c"], path, full, pipeline_sha256="a" * 64, repetitions=5
                ),
            )
            (path / "iteration-0000.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "integrity"):
                geographic_sensitivity(
                    ["a", "b", "c"], path, full, pipeline_sha256="a" * 64, repetitions=5
                )
            with self.assertRaisesRegex(ValueError, "full fit"):
                geographic_sensitivity(
                    ["a"],
                    Path(tmp) / "invalid",
                    lambda b, s: {"fit_rerun": False},
                    pipeline_sha256="a" * 64,
                    repetitions=2,
                )


if __name__ == "__main__":
    unittest.main()
