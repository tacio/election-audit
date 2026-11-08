"""Clock boundaries, lifecycle absence and denominator fixtures."""

import copy
import unittest
from typing import Any

from election_audit.operational_marts import (
    coverage_rows,
    late_session_row,
    processing_availability_rows,
)


def inputs(
    completion: str | None = "2026-10-25T20:00:00+00:00", confidence: str = "verified"
) -> list[Any]:
    session = {
        "session_id": "s",
        "snapshot_id": "snap",
        "principal_section_id": "section",
        "target_selection_state": "selected",
    }
    summary = {
        "blockers": [],
        "opening_event_ids": ["open"],
        "closing_event_ids": ["close"],
        "exposure_readiness": "ready",
    }
    cycles = [{"completion_state": "completed", "end_event_id": "done"}]
    events = [
        {"event_id": key, "normalized_at": time, "clock_confidence": confidence}
        for key, time in [
            ("open", "2026-10-25T11:00:00+00:00"),
            ("done", completion),
            ("close", "2026-10-25T20:30:00+00:00"),
        ]
    ]
    return [session, summary, cycles, events, {"uf": "AC"}, {"election_date": "2026-10-25"}]


class OperationalMartTests(unittest.TestCase):
    def test_strict_boundary_offsets_and_open_vs_completion(self) -> None:
        at = late_session_row(*inputs())
        self.assertEqual(at["completed_cycles_after17"], 0)
        self.assertTrue(at["remaining_open_at17"])
        later = late_session_row(*inputs("2026-10-25T20:00:01+00:00"))
        self.assertEqual(later["completed_cycles_after17"], 1)
        local = late_session_row(*inputs("2026-10-25T16:00:01-04:00"))
        self.assertEqual(later, local)
        args = inputs()
        args[3][2]["normalized_at"] = "2026-10-25T20:00:00+00:00"
        self.assertFalse(late_session_row(*args)["remaining_open_at17"])

    def test_unresolved_context_clocks_missing_closing_and_overseas(self) -> None:
        unknown = late_session_row(*inputs(None, "unresolved"))
        self.assertEqual(unknown["unknown_completion_clock_cycles"], 1)
        self.assertIsNone(unknown["remaining_open_at17"])
        self.assertIsNone(unknown["after17_share"])
        args = inputs("2026-10-25T20:01:00+00:00")
        args[1]["closing_event_ids"] = []
        late = late_session_row(*args)
        self.assertEqual(late["completed_cycles_after17"], 1)
        self.assertIsNone(late["remaining_open_at17"])
        args[0]["target_selection_state"] = "unresolved"
        self.assertIsNone(late_session_row(*args)["completed_cycles_after17"])
        args = inputs()
        args[4]["uf"] = "ZZ"
        overseas = late_session_row(*args)
        self.assertIsNone(overseas["cutoff_at"])
        self.assertIsNone(overseas["completed_cycles_after17"])
        self.assertEqual(overseas["convention"], "overseas_unavailable")

    def test_bounded_clock_sensitivity_and_cross_shard_uncertainty(self) -> None:
        args = inputs("2026-10-25T20:00:00+00:00", "bounded")
        row = late_session_row(
            *args, clock_bounds={"done": ["2026-10-25T19:59:59+00:00", "2026-10-25T20:00:01+00:00"]}
        )
        self.assertEqual(row["clock_sensitivity_after17_lower"], 0)
        self.assertEqual(row["clock_sensitivity_after17_upper"], 1)
        self.assertEqual(row["classifiable_completed_cycles"], 0)
        self.assertEqual(row["unknown_completion_clock_cycles"], 1)
        row = late_session_row(*inputs(), cross_shard_overlap=True)
        self.assertIsNone(row["completed_cycles_after17"])
        self.assertIn("cross_shard_overlap_unresolved", row["blockers"])

    def test_missing_lifecycle_never_uses_headers_and_repeats_do_not_multiply_population(
        self,
    ) -> None:
        context = {
            "snapshot_id": "snap",
            "context_tables": {
                "source_package": [{"package_id": "p", "section_id": "s"}],
                "source_observation": [
                    {
                        "observation_id": "obs",
                        "observed_at": "2026-10-26T01:00:00Z",
                        "last_modified_raw": "2026-10-25T20:00:00Z",
                    }
                ],
                "package_asset": [{"package_id": "p", "asset_observation_id": "obs"}] * 3,
                "section_composition": [],
            },
        }
        rows = list(processing_availability_rows(context))
        self.assertEqual(len(rows), 5)
        for row in rows[:4]:
            self.assertEqual(row["normalized_event_count"], 0)
            self.assertEqual(row["availability_state"], "missing_source")
            self.assertIsNone(row["first_event_at"])
        self.assertEqual(rows[4]["normalized_event_count"], 1)
        self.assertEqual(rows[4]["event_kind"], "observation")
        lifecycle = {
            "processing_event_id": "e",
            "package_id": "p",
            "event_kind": "receipt",
            "event_at": "2026-10-25T21:00:00Z",
            "availability_state": "observed",
            "confidence": "verified",
        }
        repeated = copy.deepcopy(lifecycle)
        repeated["processing_event_id"] = "e2"
        receipt = list(processing_availability_rows(context, [lifecycle, repeated]))[0]
        self.assertEqual(receipt["expected_package_denominator"], 1)
        self.assertEqual(receipt["normalized_event_count"], 2)

    def test_expected_members_and_unknown_population_are_retained(self) -> None:
        context = {
            "snapshot_id": "snap",
            "context_tables": {
                "section": [{"section_id": "one", "uf": "AC"}, {"section_id": "two", "uf": "AC"}],
                "coverage_ledger": [
                    {
                        "section_id": "one",
                        "installation_state": "unknown",
                        "log_availability": "missing",
                        "bu_availability": "unknown",
                        "parse_state": "not_attempted",
                    }
                ],
                "section_composition": [],
            },
        }
        rows = list(coverage_rows(context, []))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["log_availability"], "missing")
        self.assertEqual(rows[1]["expected_population_status"], "unknown")
