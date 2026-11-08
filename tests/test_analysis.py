"""Synthetic feature arithmetic and immutable analysis derivative integration."""

import json
from pathlib import Path
from typing import Any

import test_analysis_ledgers
import test_derivatives
import test_snapshots
from test_electoral_imports import bundle_at, row

from election_audit.analysis import VERSION, publish_analysis, registry
from election_audit.derivatives import publish_derivative
from election_audit.publication import (
    PublicationError,
    inspect_release,
    open_release,
    resolve_release,
)
from election_audit.release_tools import query_release, report_release, validate_release
from election_audit.types import one


class AnalysisTests(test_snapshots.SourceFixture):
    frozen_parse = test_derivatives.DerivativeTests.frozen_parse
    parent_and_bundle = test_derivatives.DerivativeTests.parent_and_bundle

    def analysis_fixture(self, extra: dict[str, Any] | None = None) -> tuple[Path, Path, Path]:
        base, parent, bundle, _ = self.parent_and_bundle()
        electoral = publish_derivative(parent, bundle, base / "warehouse")
        spec = {
            "version": VERSION,
            "cutoff_at": "2026-10-29T00:00:00+00:00",
            "candidate_a": "a",
            "candidate_b": "b",
            **(extra or {}),
        }
        config = base / "analysis.json"
        config.write_text(json.dumps(spec))
        return base, electoral, config

    def test_registry_covers_all_contracts_and_roles(self) -> None:
        definitions = registry()
        self.assertEqual(len(definitions), 21)
        device = next(r for r in definitions if r["feature_id"] == "device_logistics")
        self.assertEqual(
            device["specifications"]["operational_adjusted"]["device_logistics"], "adjustment"
        )
        self.assertEqual(
            device["specifications"]["mechanism"]["device_logistics"], "possible_mechanism"
        )
        self.assertTrue(
            all(r["source_tables"] and r["components"] and r["requires"] for r in definitions)
        )

    def test_features_child_values_unknowns_validation_and_parent_preservation(self) -> None:
        base, parent, config = self.analysis_fixture()
        before = inspect_release(parent)
        child = publish_analysis(parent, config, base / "warehouse")
        self.assertEqual(child, publish_analysis(parent, config, base / "warehouse"))
        self.assertEqual(before, inspect_release(parent))
        self.assertEqual(validate_release(child)["integrity"], "passed")
        self.assertEqual(
            query_release(
                child,
                "SELECT DISTINCT value,numerator,denominator FROM audit_features WHERE feature_id='turnout_target'",
            )["rows"],
            [(0.5, 10.0, 20.0)],
        )
        self.assertEqual(
            query_release(child, "SELECT count(*) FROM audit_feature_registry")["rows"], [(21,)]
        )
        self.assertEqual(
            query_release(
                child,
                "SELECT count(*) FROM audit_features WHERE feature_id='conditional_unusualness' AND value IS NOT NULL",
            )["rows"],
            [(0,)],
        )
        self.assertEqual(
            query_release(
                child,
                "SELECT count(*) FROM audit_features WHERE json_extract(payload,'$.scientific_eligible')::BOOLEAN",
            )["rows"],
            [(0,)],
        )
        self.assertFalse((child / "facts" / "anonymous_cycle").exists())
        self.assertEqual(
            query_release(child, "SELECT count(*) FROM anonymous_cycle")["rows"], [(1,)]
        )

    def test_partition_persisted_unknown_identity_and_bilingual_report(self) -> None:
        base, parent, config = self.analysis_fixture(
            {
                "partition": {
                    "version": "location-partition-v1",
                    "seed": "synthetic",
                    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
                    "links": [],
                    "municipal_holdout": [],
                }
            }
        )
        child = publish_analysis(parent, config, base / "warehouse")
        self.assertEqual(validate_release(child)["integrity"], "passed")
        self.assertEqual(
            query_release(child, "SELECT DISTINCT partition_name FROM location_partition")["rows"],
            [("unavailable",)],
        )
        self.assertEqual(
            query_release(child, "SELECT count(*) FROM partition_plan")["rows"], [(1,)]
        )
        report_release(child, base / "analysis-reports")
        self.assertTrue((base / "analysis-reports" / "report.en.md").is_file())
        self.assertTrue((base / "analysis-reports" / "report.pt-BR.md").is_file())
        findings = json.loads((base / "analysis-reports" / "findings.json").read_text())
        self.assertIn("features", findings["calculations"])
        self.assertIn("partitions", findings["calculations"])
        self.assertEqual(len(findings["parent_chain"]), 3)

    def test_append_only_ledger_child_atomic_conflict_and_restart(self) -> None:
        base, parent, config = self.analysis_fixture(
            {
                "partition": {
                    "version": "location-partition-v1",
                    "seed": "synthetic",
                    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
                    "links": [],
                    "municipal_holdout": [],
                }
            }
        )
        first = publish_analysis(parent, config, base / "warehouse")
        partition = query_release(first, "SELECT partition_id FROM partition_plan")["rows"][0][0]
        snapshot = query_release(first, "SELECT snapshot_id FROM snapshot LIMIT 1")["rows"][0][0]
        records = test_analysis_ledgers.protocol_records()
        records[0]["payload"]["partition_id"] = partition
        records[2]["payload"]["snapshot_ids"] = [snapshot]
        spec = json.loads(config.read_text())
        spec["records"] = records
        config.write_text(json.dumps(spec))
        second = publish_analysis(first, config, base / "warehouse")
        self.assertEqual(validate_release(second)["integrity"], "passed")
        self.assertEqual(
            query_release(second, "SELECT count(*) FROM analysis_ledger")["rows"], [(3,)]
        )
        self.assertEqual(
            query_release(first, "SELECT count(*) FROM analysis_ledger")["rows"], [(0,)]
        )
        self.assertEqual(
            query_release(second, "SELECT count(*) FROM partition_plan")["rows"], [(1,)]
        )
        self.assertEqual(second, publish_analysis(first, config, base / "warehouse"))
        records[0]["payload"]["question"] = "changed existing protocol"
        config.write_text(json.dumps(spec))
        with self.assertRaisesRegex(PublicationError, "immutable"):
            publish_analysis(second, config, base / "warehouse")
        self.assertEqual(resolve_release(base / "warehouse"), second)
        self.assertFalse(list((base / "warehouse" / "releases").glob(".building-*")))

    def test_publication_rejects_unresolved_identity_evidence(self) -> None:
        base, parent, config = self.analysis_fixture(
            {
                "partition": {
                    "version": "location-partition-v1",
                    "seed": "synthetic",
                    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
                    "links": [
                        {
                            "location_id": "unknown",
                            "stable_location_id": "assertion",
                            "verified": True,
                            "evidence": {
                                "object_sha256": "a" * 64,
                                "record_locator": "unpreserved review",
                            },
                        }
                    ],
                    "municipal_holdout": [],
                }
            }
        )
        with self.assertRaisesRegex(PublicationError, "frozen source object"):
            publish_analysis(parent, config, base / "warehouse")

    def test_real_derivative_holdout_gate_and_immutable_access_child(self) -> None:
        from election_audit.analysis_partitions import partition_tables
        from election_audit.source_inventory import hash_file

        base, parent, bundle, data = self.parent_and_bundle()
        with open_release(parent) as db:
            section = json.loads(
                one(db.execute("SELECT payload FROM section LIMIT 1").fetchone())[0]
            )
            snapshot = one(db.execute("SELECT snapshot_id FROM snapshot LIMIT 1").fetchone())[0]
        new_section = {**section, "section_id": "linked-principal", "section_code": "9999"}
        data["section"] = [new_section]
        data["location"] = [
            row(
                "location",
                location_id="reviewed-location",
                election_id=section["election_id"],
                uf=section["uf"],
                municipality_tse=section["municipality_tse"],
                zone=section["zone"],
                location_code="9999",
            )
        ]
        data["section_composition"] = [
            row(
                "section_composition",
                snapshot_id=snapshot,
                member_section_id="linked-principal",
                principal_section_id="linked-principal",
                location_id="reviewed-location",
            )
        ]
        bundle_at(bundle.parent, data)
        electoral = publish_derivative(parent, bundle, base / "warehouse")
        partition = {
            "version": "location-partition-v1",
            "seed": "0",
            "fractions": {"training": 0.1, "calibration": 0.1, "test": 0.8},
            "links": [
                {
                    "location_id": "reviewed-location",
                    "stable_location_id": "verified-stable",
                    "verified": True,
                    "evidence": {
                        "object_sha256": hash_file(bundle.parent / "location.jsonl")[0],
                        "record_locator": "normalized synthetic location row 1",
                    },
                }
            ],
            "municipal_holdout": [],
        }
        with open_release(electoral) as db:
            for seed in range(100):
                partition["seed"] = str(seed)
                plans, assignments = partition_tables(db, partition, 100_000)
                if any(r["partition_name"] == "test" for r in assignments):
                    break
            else:
                self.fail("synthetic test seed not found")
        config = base / "analysis.json"
        spec = {
            "version": VERSION,
            "cutoff_at": "2026-10-29T00:00:00+00:00",
            "partition": partition,
        }
        config.write_text(json.dumps(spec))
        untouched = publish_analysis(electoral, config, base / "warehouse")
        self.assertEqual(
            query_release(untouched, "SELECT access_state FROM test_partition_status")["rows"],
            [("untouched",)],
        )
        with self.assertRaisesRegex(PublicationError, "reserved"):
            query_release(untouched, "SELECT * FROM section_results")
        self.assertEqual(
            query_release(untouched, "SELECT count(*) FROM training_features")["rows"], [(0,)]
        )
        records = test_analysis_ledgers.protocol_records()
        records[0]["payload"]["partition_id"] = plans[0]["partition_id"]
        records[2]["payload"]["snapshot_ids"] = [snapshot]
        records.append(
            test_analysis_ledgers.record(
                "inspection",
                "test_access",
                {
                    "partition_id": plans[0]["partition_id"],
                    "purpose": "synthetic protocol review",
                    "inspection": True,
                    "protocol_id": "protocol",
                },
            )
        )
        spec["records"] = records
        config.write_text(json.dumps(spec))
        inspected = publish_analysis(untouched, config, base / "warehouse")
        self.assertEqual(validate_release(inspected)["integrity"], "passed")
        self.assertEqual(
            query_release(inspected, "SELECT access_state FROM test_partition_status")["rows"],
            [("development_inspected",)],
        )
        self.assertEqual(
            query_release(inspected, "SELECT count(*) FROM section_results")["rows"], [(2,)]
        )
        self.assertEqual(
            query_release(untouched, "SELECT access_state FROM test_partition_status")["rows"],
            [("untouched",)],
        )
