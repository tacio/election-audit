"""Failure-oriented checks for declarative contract interfaces."""

import unittest

from election_audit.contracts import load_contract, validate_contracts, validate_rows


class ContractTests(unittest.TestCase):
    def test_registry_references_are_many_to_one(self):
        self.assertEqual(validate_contracts(), [])

    def test_nullable_fields_require_reason_without_zero_imputation(self):
        row = {
            "device_id": "d1",
            "serial_raw": None,
            "hardware_model": "UE2022",
            "identity_state": "unresolved",
        }
        self.assertTrue(any("null reason" in e for e in validate_rows("physical_device", [row])))
        row["field_states"] = {"serial_raw": "unknown"}
        self.assertEqual(validate_rows("physical_device", [row]), [])
        self.assertTrue(
            any("duplicate key" in e for e in validate_rows("physical_device", [row, row]))
        )

    def test_hash_type_and_explicit_time_offset(self):
        row = {
            "observation_id": "o1",
            "run_id": "r1",
            "official_url": "https://example.test/a",
            "retrieval_url": "https://example.test/a",
            "object_sha256": "not-a-hash",
            "observed_at": "2026-10-25T17:00:00",
            "http_status": True,
            "etag": None,
            "last_modified_raw": None,
            "observation_status": "success",
            "field_states": {"etag": "not_published", "last_modified_raw": "not_published"},
        }
        errors = validate_rows("source_observation", [row])
        self.assertTrue(any("invalid sha256" in e for e in errors))
        self.assertTrue(any("invalid instant" in e for e in errors))
        self.assertTrue(any("invalid integer" in e for e in errors))
        row.update(object_sha256="a" * 64, observed_at="2026-10-25T17:00:00-03:00", http_status=200)
        self.assertEqual(validate_rows("source_observation", [row]), [])

    def test_different_grains_and_anonymous_cycles(self):
        tables = load_contract()["tables"]
        self.assertEqual(tables["section_contest_totals"]["primary_key"], ["result_version_id"])
        self.assertEqual(
            tables["vote_choice_count"]["primary_key"], ["result_version_id", "vote_choice_id"]
        )
        fields = tables["anonymous_cycle"]["fields"]
        self.assertFalse({"candidacy_id", "vote_choice_id", "voter_id", "rdv_row"} & fields.keys())
        lifecycle = tables["processing_event"]["fields"]
        self.assertTrue(lifecycle["result_version_id"]["nullable"])
        self.assertIn("event_time_raw", lifecycle)

    def test_statistical_targets_have_explicit_prerequisites(self):
        features = {f["id"]: f for f in load_contract("features")["features"]}
        for name in (
            "turnout_target",
            "candidate_share_target",
            "blank_null_targets",
            "conditional_unusualness",
            "conditional_margin_bounds",
            "counterfactual_excess",
        ):
            self.assertTrue(features[name]["requires"])
            self.assertTrue(features[name]["unavailable_when"])
        self.assertIn("clocks", features["late_voting"]["requires"])
        self.assertNotIn("bu2", features["processing_event_availability"]["requires"])
