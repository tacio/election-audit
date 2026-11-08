"""Electoral arithmetic/selection fixtures: no real BU semantic validation claim."""

import copy
import unittest
from collections.abc import Sequence
from typing import Any

from test_electoral_imports import row

from election_audit.electoral_results import derive_electoral
from election_audit.publication import PublicationError


def anchor() -> dict[str, str]:
    return {"object_sha256": "a" * 64, "record_locator": '{"line":1}'}


def electoral_data() -> dict[str, list[dict[str, Any]]]:
    data = {
        "election": [
            row(
                "election",
                election_id="e2",
                year=2026,
                pleito_code="3221",
                election_code="6258",
                round=2,
                election_date="2026-10-25",
            )
        ],
        "snapshot": [{"snapshot_id": "snap"}],
        "section": [
            row(
                "section",
                section_id="s",
                election_id="e2",
                uf="ac",
                municipality_tse="00001",
                zone="0001",
                section_code="0001",
            )
        ],
        "section_composition": [
            row(
                "section_composition",
                snapshot_id="snap",
                member_section_id="s",
                principal_section_id="s",
            )
        ],
        "contest": [
            row(
                "contest",
                contest_id="p",
                election_id="e2",
                cargo_code="0001",
                jurisdiction_code="br",
            )
        ],
        "candidacy": [
            row(
                "candidacy",
                candidacy_id="candidate",
                contest_id="p",
                official_candidate_id="official",
                ballot_number="11",
            )
        ],
        "vote_choice": [
            row(
                "vote_choice",
                vote_choice_id=kind,
                contest_id="p",
                choice_code=kind,
                choice_kind=kind,
                candidacy_id="candidate" if kind == "candidate" else None,
            )
            for kind in ("candidate", "blank", "null", "special", "unresolved")
        ],
        "result_version": [
            row(
                "result_version",
                result_version_id="v",
                principal_section_id="s",
                contest_id="p",
                result_status="totalized",
            )
        ],
        "section_contest_totals": [
            row(
                "section_contest_totals",
                result_version_id="v",
                eligible_electors=20,
                attending_voters=10,
                abstaining_electors=10,
                total_presidential_ballots=10,
                valid_candidate_votes=10,
                blank_votes=0,
                null_votes=0,
                special_votes=0,
                unresolved_votes=0,
            )
        ],
        "vote_choice_count": [
            row(
                "vote_choice_count",
                result_version_id="v",
                vote_choice_id=kind,
                vote_count=10 if kind == "candidate" else 0,
            )
            for kind in ("candidate", "blank", "null", "special", "unresolved")
        ],
        "result_evidence": [
            {
                "result_version_id": "v",
                "snapshot_id": "snap",
                "official_target": True,
                "complete_choices": True,
                "expected_choice_ids": ["candidate", "blank", "null", "special", "unresolved"],
                "status_evidence": anchor(),
                "supersedes": [],
                "supersession_evidence": {},
            }
        ],
    }
    return data


def add_version(
    data: dict[str, list[dict[str, Any]]],
    vid: str,
    status: str = "totalized",
    supersedes: Sequence[str] = (),
) -> None:
    for name in ("result_version", "section_contest_totals", "result_evidence"):
        r = copy.deepcopy(data[name][0])
        r["result_version_id"] = vid
        if name == "result_version":
            r["result_status"] = status
        if name == "result_evidence":
            r["supersedes"] = list(supersedes)
            r["supersession_evidence"] = {old: anchor() for old in supersedes}
        data[name].append(r)
    data["vote_choice_count"] += [
        {**r, "result_version_id": vid}
        for r in data["vote_choice_count"]
        if r["result_version_id"] == "v"
    ]


class ElectoralTests(unittest.TestCase):
    def test_single_canonical_totals_and_denominators(self) -> None:
        generated, _ = derive_electoral(electoral_data())
        self.assertEqual(generated["canonical_result"][0]["result_version_id"], "v")
        self.assertEqual(generated["result_reconciliation"][0]["state"], "reconciled")
        self.assertTrue(generated["unanimous_results"][0]["strict_unanimity"])
        self.assertEqual(generated["section_results"][0]["turnout"], 0.5)
        self.assertEqual(
            generated["section_results"][0]["candidate_valid_shares"], {"candidate": 1.0}
        )

    def test_present_external_electorate_mismatch_blocks_readiness(self) -> None:
        data = electoral_data()
        data["electorate_reference"] = [
            {"snapshot_id": "snap", "principal_section_id": "s", "eligible_electors": 21}
        ]
        generated, _ = derive_electoral(data)
        self.assertEqual(
            generated["result_reconciliation"][0]["checks"]["electorate_reference"]["difference"],
            -1,
        )
        self.assertEqual(generated["result_reconciliation"][0]["state"], "mismatch")
        self.assertIsNone(generated["section_results"][0]["turnout"])

    def test_competing_version_without_snapshot_status_evidence_blocks_selection(self) -> None:
        data = electoral_data()
        add_version(data, "unassigned")
        data["result_evidence"] = data["result_evidence"][:1]
        generated, _ = derive_electoral(data)
        self.assertEqual(generated["canonical_result"][0]["selection_state"], "conflict")
        self.assertIsNone(generated["section_results"][0]["turnout"])

    def test_conflict_supersession_received_rejected_excluded(self) -> None:
        data = electoral_data()
        add_version(data, "new")
        self.assertEqual(
            derive_electoral(data)[0]["canonical_result"][0]["selection_state"], "conflict"
        )
        data["result_evidence"][1]["supersedes"] = ["v"]
        data["result_evidence"][1]["supersession_evidence"] = {"v": anchor()}
        self.assertEqual(
            derive_electoral(data)[0]["canonical_result"][0]["result_version_id"], "new"
        )
        for status in ("received", "rejected", "excluded"):
            data = electoral_data()
            data["result_version"][0]["result_status"] = status
            self.assertEqual(
                derive_electoral(data)[0]["canonical_result"][0]["selection_state"], "ineligible"
            )
        data = electoral_data()
        add_version(data, "new", supersedes=["v"])
        data["result_evidence"][0]["supersedes"] = ["new"]
        data["result_evidence"][0]["supersession_evidence"] = {"new": anchor()}
        with self.assertRaisesRegex(PublicationError, "Cyclic"):
            derive_electoral(data)

    def test_duplicate_candidate_and_wrong_round_or_contest_rejected(self) -> None:
        data = electoral_data()
        data["vote_choice"].append(
            {**data["vote_choice"][0], "vote_choice_id": "duplicate", "choice_code": "other"}
        )
        with self.assertRaisesRegex(PublicationError, "Duplicate candidate"):
            derive_electoral(data)
        data = electoral_data()
        data["contest"][0]["election_id"] = "other-round"
        with self.assertRaisesRegex(PublicationError, "election mismatch"):
            derive_electoral(data)

    def test_missing_zero_special_and_all_valid_unanimity(self) -> None:
        data = electoral_data()
        data["vote_choice_count"] = data["vote_choice_count"][:-1]
        mart = derive_electoral(data)[0]["unanimous_results"][0]
        self.assertIsNone(mart["strict_unanimity"])
        data = electoral_data()
        for key in ("total_presidential_ballots", "valid_candidate_votes", "attending_voters"):
            data["section_contest_totals"][0][key] = 0
        data["section_contest_totals"][0]["abstaining_electors"] = 20
        data["vote_choice_count"][0]["vote_count"] = 0
        self.assertIsNone(derive_electoral(data)[0]["unanimous_results"][0]["strict_unanimity"])
        for kind in ("blank", "null", "special", "unresolved"):
            data = electoral_data()
            data["section_contest_totals"][0]["valid_candidate_votes"] = 9
            data["section_contest_totals"][0][kind + "_votes"] = 1
            data["vote_choice_count"][0]["vote_count"] = 9
            next(r for r in data["vote_choice_count"] if r["vote_choice_id"] == kind)[
                "vote_count"
            ] = 1
            mart = derive_electoral(data)[0]["unanimous_results"][0]
            self.assertFalse(mart["strict_unanimity"])
            self.assertTrue(mart["all_valid_only_unanimity"])
        data = electoral_data()
        data["section_contest_totals"][0]["special_votes"] = None
        self.assertIsNone(derive_electoral(data)[0]["unanimous_results"][0]["strict_unanimity"])

    def test_aggregation_members_and_sessions_never_multiply_totals(self) -> None:
        data = electoral_data()
        data["section"].append(
            {**data["section"][0], "section_id": "member", "section_code": "0002"}
        )
        data["section_composition"].append(
            {**data["section_composition"][0], "member_section_id": "member"}
        )
        data["voting_session"] = [
            {"session_id": str(i), "principal_section_id": "s"} for i in range(5)
        ]
        generated, _ = derive_electoral(data)
        self.assertEqual(len(generated["section_results"]), 1)
        self.assertEqual(generated["section_results"][0]["totals"]["attending_voters"], 10)
        self.assertEqual(
            generated["section_results"][0]["session_candidate_attribution"], "unavailable"
        )

    def test_hierarchy_coverage_before_numeric_mismatch_and_ZZ(self) -> None:
        data = electoral_data()
        data["section"].append({**data["section"][0], "section_id": "zz", "uf": "zz"})
        ref = {
            "reference_id": "national",
            "snapshot_id": "snap",
            "contest_id": "p",
            "level": "national",
            "uf": "",
            "municipality_tse": "",
            "zone": "",
            "expected_principals": ["s", "zz"],
            "metrics": {"attending_voters": 21},
            "final": True,
        }
        data["final_result_reference"] = [ref]
        finding = derive_electoral(data)[0]["hierarchy_reconciliation"][0]
        self.assertEqual(finding["state"], "coverage_gap")
        self.assertTrue(finding["includes_ZZ"])
        self.assertIsNone(finding["metrics"]["attending_voters"]["difference"])
        ref["expected_principals"] = ["s"]
        finding = derive_electoral(data)[0]["hierarchy_reconciliation"][0]
        self.assertEqual(finding["state"], "mismatch")
        self.assertEqual(finding["metrics"]["attending_voters"]["difference"], -11)

    def test_timing_negative_corrected_and_naive_unknown(self) -> None:
        data = electoral_data()

        def event(eid: str, kind: str, time: str | None) -> dict[str, Any]:
            return row(
                "processing_event",
                processing_event_id=eid,
                observation_id="o",
                result_version_id="v",
                event_kind=kind,
                event_time_raw=time or "25/10/2026 17:00:00",
                event_at=time,
                availability_state="observed" if time else "unresolved",
                conversion_rule="offset_in_source" if time else None,
                confidence="verified" if time else "unresolved",
            )

        data["processing_event"] = [
            event("g", "generation", "2026-10-25T17:00:00+00:00"),
            event("r", "receipt", "2026-10-25T16:59:00+00:00"),
            event("r2", "receipt", "2026-10-25T17:01:00+00:00"),
            event("p", "publication", None),
        ]
        timing = derive_electoral(data)[0]["result_timing"]
        pairs = [r for r in timing if r["interval_type"] == "generation_to_receipt"]
        self.assertEqual([r["seconds"] for r in pairs], [-60, 60])
        self.assertTrue(all(r["repeated_or_corrected"] for r in pairs))
        self.assertTrue(
            all(
                r["seconds"] is None
                for r in timing
                if r["interval_type"] == "receipt_to_publication"
            )
        )

    def test_harmonized_rounds_disjoint_reviewed_and_aggregate_before_join(self) -> None:
        data = electoral_data()
        first = copy.deepcopy(data)
        for name in (
            "election",
            "section",
            "contest",
            "candidacy",
            "vote_choice",
            "result_version",
            "section_contest_totals",
            "vote_choice_count",
            "section_composition",
            "result_evidence",
            "snapshot",
        ):
            for r in first[name]:
                for key, value in list(r.items()):
                    if isinstance(value, str) and value in {
                        "e2",
                        "s",
                        "p",
                        "candidate",
                        "blank",
                        "null",
                        "special",
                        "unresolved",
                        "v",
                        "snap",
                    }:
                        r[key] = value + "1" if key != "choice_kind" else value
                if name == "election":
                    r["round"] = 1
                if name == "result_evidence":
                    r["expected_choice_ids"] = [v + "1" for v in r["expected_choice_ids"]]
            data[name] += first[name]
        data["harmonized_population"] = [
            row(
                "harmonized_population",
                population_id="common",
                harmonization_policy="reviewed",
                comparability_state="comparable",
            )
        ]
        data["harmonized_member"] = [
            row(
                "harmonized_member",
                population_id="common",
                snapshot_id=snap,
                principal_section_id=sid,
            )
            for snap, sid in (("snap", "s"), ("snap1", "s1"))
        ]
        self.assertEqual(
            derive_electoral(data)[0]["round_comparison"][0]["availability"],
            "incomparable_or_incomplete",
        )
        data["harmonization_evidence"] = [
            {
                "population_id": "common",
                "composition_reviewed": True,
                "transfers_reviewed": True,
                "electorate_reviewed": True,
                "evidence": [anchor()],
            }
        ]
        result = derive_electoral(data)[0]["round_comparison"][0]
        self.assertEqual(result["availability"], "comparable")
        self.assertEqual(result["turnout_difference"], 0)
        self.assertEqual([r["whole_principals"] for r in result["rounds"]], [1, 1])
        data["harmonized_member"].append(
            {**data["harmonized_member"][0], "population_id": "second"}
        )
        data["harmonized_population"].append(
            {**data["harmonized_population"][0], "population_id": "second"}
        )
        with self.assertRaisesRegex(PublicationError, "overlap"):
            derive_electoral(data)
