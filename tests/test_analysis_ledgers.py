"""Immutable analysis history, holdout access and conditional arithmetic fixtures."""

import copy
import unittest

from election_audit.analysis import validate_evidence, validate_populations
from election_audit.analysis_ledgers import (
    VERSION,
    access_status,
    conditional_impact,
    validate_records,
)
from election_audit.publication import PublicationError

CASE = {
    "outcome": "turnout",
    "subgroup": "all",
    "window": "election_day",
    "scale": "location",
    "model_variant": "no_first_round",
    "historical_comparison": "none",
}


def record(identifier, kind, payload, *, run="run", refs=()):
    return {
        "record_id": identifier,
        "version": VERSION,
        "record_kind": kind,
        "analysis_run_id": None if kind in {"protocol", "analysis_run", "model_config"} else run,
        "created_at": "2026-10-29T00:00:00+00:00",
        "references": list(refs),
        "payload": payload,
    }


def protocol_records():
    return [
        record(
            "protocol",
            "protocol",
            {
                "state": "frozen",
                "family": [CASE],
                "question": "conditional_unusualness",
                "partition_id": "p",
            },
        ),
        record(
            "config",
            "model_config",
            {
                "estimator": "empirical_median_MAD",
                "hyperparameters": {"scale_floor": "untrained"},
                "seed": "s",
                "fitted": False,
            },
        ),
        record(
            "run",
            "analysis_run",
            {
                "protocol_id": "protocol",
                "snapshot_ids": ["snapshot"],
                "source_configuration": {"feature_version": "audit-features-v1"},
                "model_config_ids": ["config"],
            },
            refs=["protocol", "config"],
        ),
    ]


def assignments():
    return [
        {
            "partition_id": "p",
            "stable_location_id": stable,
            "partition_name": name,
            "principal_section_id": principal,
            "eligible": True,
        }
        for stable, name, principal in (("cal", "calibration", "s1"), ("test", "test", "s2"))
    ]


def impact():
    anchor = {"object_sha256": "a" * 64, "record_locator": "reviewed caps row"}
    return {
        "target": {
            "snapshot_id": "snapshot",
            "election_id": "e2",
            "contest_id": "p",
            "candidate_a": "a",
            "candidate_b": "b",
        },
        "mechanism": "removal_exact",
        "affected_population": [
            {
                "principal_section_id": "s",
                "a": 60,
                "b": 30,
                "other": 10,
                "cap": 20,
                "cap_unit": "completed_presidential_ballots",
                "cap_evidence": anchor,
            }
        ],
        "overlap_handling": "disjoint_principals",
        "population_evidence": anchor,
        "final_margin": 10,
        "margin_assumptions": "assume coherent final A-B margin 10, same target contest, independent corroboration outstanding",
    }


class LedgerTests(unittest.TestCase):
    def validated(self, incoming, inherited=()):
        return validate_records(inherited, incoming, partition_ids={"p"}, snapshot_ids={"snapshot"})

    def test_append_resume_reordering_conflicts_and_missing_refs(self) -> None:
        fresh, records = self.validated(list(reversed(protocol_records())))
        self.assertEqual(len(fresh), 3)
        self.assertEqual(self.validated(protocol_records(), records.values())[0], [])
        conflict = copy.deepcopy(protocol_records()[0])
        conflict["payload"]["question"] = "changed"
        with self.assertRaisesRegex(PublicationError, "immutable"):
            self.validated([conflict], records.values())
        broken = protocol_records()
        broken[2]["references"].append("missing")
        with self.assertRaises(PublicationError):
            self.validated(broken)

    def test_all_outcomes_and_null_results_complete_snapshot_and_exploratory(self) -> None:
        explored = record(
            "outcome",
            "exploration",
            {
                **CASE,
                "protocol_id": "protocol",
                "family_status": "frozen",
                "result": None,
                "null_result": True,
            },
        )
        snapshot = record(
            "done",
            "analysis_snapshot",
            {
                "exploration_ids": ["outcome"],
                "status": "complete",
                "all_explorations_recorded": True,
            },
        )
        self.assertEqual(len(self.validated([snapshot, explored, *protocol_records()])[0]), 5)
        snapshot["payload"]["exploration_ids"] = []
        with self.assertRaisesRegex(PublicationError, "omits"):
            self.validated([snapshot, explored, *protocol_records()])
        explored["payload"]["window"] = "searched_window"
        with self.assertRaisesRegex(PublicationError, "outside frozen"):
            self.validated([explored, *protocol_records()])
        explored["payload"]["family_status"] = "exploratory"
        self.validated([explored, *protocol_records()])

    def test_calibration_score_investigation_populations_and_no_inference(self) -> None:
        calibration = record(
            "calibration",
            "calibration",
            {
                "partition_id": "p",
                "unit_population": ["cal"],
                "n_cal": 1,
                "assumptions": ["exchangeability unassessed", "no fitted model"],
                "exchangeability": "unassessed",
                "score_config_id": "config",
            },
        )
        score = record(
            "score",
            "score",
            {
                "unit_key": "test",
                "score": 1.5,
                "score_config_id": "config",
                "calibration_id": "calibration",
                "interpretation": "descriptive_only",
            },
        )
        investigation = record(
            "case",
            "investigation",
            {
                "unit_keys": ["test"],
                "score_ids": ["score"],
                "alternative_explanations": ["missing block", "clock error"],
                "corroboration": [],
                "candidate_blinded": True,
                "conclusion": "unresolved",
            },
        )
        inspection = record(
            "inspection",
            "test_access",
            {
                "partition_id": "p",
                "purpose": "review scores",
                "inspection": True,
                "protocol_id": "protocol",
            },
        )
        fresh, records = self.validated(
            [*protocol_records(), calibration, score, investigation, inspection]
        )
        validate_populations(assignments(), records, fresh)
        calibration["payload"]["unit_population"] = ["test"]
        fresh, records = self.validated([*protocol_records(), calibration, score])
        with self.assertRaisesRegex(PublicationError, "non-calibration"):
            validate_populations(assignments(), records, fresh)
        calibration["payload"]["unit_population"] = ["cal"]
        score["payload"]["unit_key"] = "stale"
        fresh, records = self.validated([*protocol_records(), calibration, score])
        with self.assertRaisesRegex(PublicationError, "Score unit"):
            validate_populations(assignments(), records, fresh)
        score["payload"]["interpretation"] = "fraud_pvalue"
        with self.assertRaises(PublicationError):
            self.validated([*protocol_records(), calibration, score])
        fitted = protocol_records()
        fitted[1]["payload"]["fitted"] = True
        with self.assertRaises(PublicationError):
            self.validated(fitted)

    def test_test_inspection_contaminates_future_reseeded_holdout(self) -> None:
        inspection = record(
            "inspection",
            "test_access",
            {
                "partition_id": "p",
                "purpose": "frozen diagnostic review",
                "inspection": True,
                "protocol_id": "protocol",
            },
        )
        fresh, records = self.validated([*protocol_records(), inspection])
        status = access_status(assignments(), records)
        self.assertEqual(status[0]["access_state"], "development_inspected")
        new_assignment = {**assignments()[1], "partition_id": "newseed"}
        self.assertEqual(
            access_status([*assignments(), new_assignment], records)[1]["access_state"],
            "development_inspected",
        )
        future = record(
            "future", "protocol", {**protocol_records()[0]["payload"], "partition_id": "newseed"}
        )
        with self.assertRaisesRegex(PublicationError, "development data"):
            validate_populations(
                [*assignments(), new_assignment], {**records, "future": future}, [future]
            )

    def test_conditional_bounds_overlap_unknown_margin_caps_and_tie(self) -> None:
        payload = impact()
        result = conditional_impact(payload)
        self.assertEqual(result["margin_change_bounds"], [-20, 20])
        self.assertEqual(result["corrected_margin_bounds"], [-10, 30])
        payload["mechanism"] = "switching_cap"
        self.assertEqual(conditional_impact(payload)["margin_change_bounds"], [0, 40])
        payload["final_margin"] = 0
        self.assertEqual(conditional_impact(payload)["strict_win_switch_threshold"], 1)
        payload["final_margin"] = None
        self.assertEqual(conditional_impact(payload)["availability"], "unavailable")
        payload = impact()
        payload["affected_population"] *= 2
        self.assertIn("overlap", conditional_impact(payload)["reason"])
        payload = impact()
        payload["affected_population"][0]["cap_unit"] = "attempts"
        self.assertEqual(conditional_impact(payload)["availability"], "unavailable")
        payload = impact()
        payload["affected_population"][0]["cap"] = 101
        with self.assertRaises(ValueError):
            conditional_impact(payload)

    def test_anchor_requires_preserved_source_bytes(self) -> None:
        with self.assertRaisesRegex(PublicationError, "frozen source object"):
            validate_evidence(impact(), {"b" * 64})
        validate_evidence(impact(), {"a" * 64})

    def test_query_reserves_untouched_outcomes_and_exposes_only_training_view(self) -> None:
        import duckdb

        from election_audit.analysis import protect_test_query

        with duckdb.connect() as db:
            db.execute("CREATE TABLE test_partition_status (access_state VARCHAR)")
            db.execute("INSERT INTO test_partition_status VALUES ('untouched')")
            document = {"combined_tables": {"test_partition_status": {}}}
            for sql in (
                "SELECT * FROM audit_features",
                "SELECT * FROM section_results",
                "SELECT * FROM parent_0.main.anonymous_cycle",
            ):
                with self.subTest(sql=sql), self.assertRaisesRegex(PublicationError, "reserved"):
                    protect_test_query(db, document, sql)
            protect_test_query(db, document, "SELECT * FROM training_features")
            protect_test_query(db, document, "SELECT * FROM analysis_ledger")
            db.execute("UPDATE test_partition_status SET access_state='development_inspected'")
            protect_test_query(db, document, "SELECT * FROM audit_features")
