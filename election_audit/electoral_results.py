"""Evidence-driven electoral selection, reconciliation and four bounded result marts."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from election_audit.publication import SCHEMA, PublicationError
from election_audit.source_inventory import canonical
from election_audit.types import JSON, Row

type Tables = dict[str, list[Row]]

VERSION = (
    "electoral-results-v2"  # v2: supersession by any version; one snapshot per principal (xr1)
)
CATEGORY_FIELDS = {
    "candidate": "valid_candidate_votes",
    "blank": "blank_votes",
    "null": "null_votes",
    "special": "special_votes",
    "unresolved": "unresolved_votes",
}
TOTAL_FIELDS = [
    "eligible_electors",
    "attending_voters",
    "abstaining_electors",
    "total_presidential_ballots",
    *CATEGORY_FIELDS.values(),
]
MART_SCHEMAS = {
    "result_reconciliation": {
        "key": ["result_version_id"],
        "columns": {"result_version_id": "text"},
    },
    "hierarchy_reconciliation": {"key": ["reference_id"], "columns": {"reference_id": "text"}},
    "section_results": {
        "key": ["snapshot_id", "principal_section_id", "contest_id"],
        "columns": dict.fromkeys(["snapshot_id", "principal_section_id", "contest_id"], "text"),
    },
    "unanimous_results": {
        "key": ["snapshot_id", "principal_section_id", "contest_id"],
        "columns": dict.fromkeys(["snapshot_id", "principal_section_id", "contest_id"], "text"),
    },
    "result_timing": {
        "key": [
            "snapshot_id",
            "principal_section_id",
            "result_version_id",
            "interval_type",
            "start_event_id",
            "end_event_id",
        ],
        "columns": dict.fromkeys(
            [
                "snapshot_id",
                "principal_section_id",
                "result_version_id",
                "interval_type",
                "start_event_id",
                "end_event_id",
            ],
            "text",
        ),
    },
    "round_comparison": {
        "key": ["population_id", "first_contest_id", "second_contest_id"],
        "columns": dict.fromkeys(
            ["population_id", "first_contest_id", "second_contest_id"], "text"
        ),
    },
}


def _index(data: Tables, name: str, key: str) -> dict[Any, Row]:
    return {r[key]: r for r in data.get(name, [])}


def _known_sum(values: list[int | None]) -> int | None:
    """The sum when every value is known, otherwise None (unknown is not zero)."""
    known = [v for v in values if v is not None]
    return sum(known) if len(known) == len(values) else None


def _anchor(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("object_sha256"), str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", value["object_sha256"]))
        and isinstance(value.get("record_locator"), str)
        and bool(value["record_locator"])
    )


def validate_electoral(data: Tables, generated: Tables) -> None:
    """Reject invalid relations/evidence, retaining numerical mismatches as findings."""
    elections = _index(data, "election", "election_id")
    sections = _index(data, "section", "section_id")
    contests = _index(data, "contest", "contest_id")
    choices = _index(data, "vote_choice", "vote_choice_id")
    candidacies = _index(data, "candidacy", "candidacy_id")
    versions = _index(data, "result_version", "result_version_id")
    snapshots = _index(data, "snapshot", "snapshot_id")
    evidence = _index(data, "result_evidence", "result_version_id")
    compositions = {
        (r["snapshot_id"], r["member_section_id"]): r for r in data.get("section_composition", [])
    }
    objects = {r["object_sha256"] for r in data.get("source_object", [])}

    def anchor(value: Any) -> bool:
        return _anchor(value) and (not objects or value["object_sha256"] in objects)

    for choice in choices.values():
        candidate = candidacies.get(choice["candidacy_id"])
        if (
            choice["choice_kind"] == "candidate"
            and (not candidate or candidate["contest_id"] != choice["contest_id"])
        ) or (choice["choice_kind"] != "candidate" and choice["candidacy_id"] is not None):
            raise PublicationError("Vote choice/candidacy contest or category mismatch")
    candidates = [
        (c["contest_id"], c["candidacy_id"])
        for c in choices.values()
        if c["choice_kind"] == "candidate"
    ]
    if len(candidates) != len(set(candidates)):
        raise PublicationError("Duplicate candidate represented by multiple choices")
    for version in versions.values():
        sid, cid, vid = (
            version[k] for k in ("principal_section_id", "contest_id", "result_version_id")
        )
        if (
            sid not in sections
            or cid not in contests
            or sections[sid]["election_id"] != contests[cid]["election_id"]
        ):
            raise PublicationError("Result section/contest election mismatch")
        ev = evidence.get(vid)
        if not ev:
            continue  # Missing evidence makes canonical result unavailable.
        snapshot = snapshots.get(ev["snapshot_id"])
        if not snapshot:
            raise PublicationError("Result snapshot/round/election mismatch")
        if not anchor(ev["status_evidence"]):
            raise PublicationError("Result status requires original-record evidence anchor")
        if not isinstance(ev["expected_choice_ids"], list) or len(ev["expected_choice_ids"]) != len(
            set(ev["expected_choice_ids"])
        ):
            raise PublicationError("Invalid expected choice completeness ledger")
        if any(
            c not in choices or choices[c]["contest_id"] != cid for c in ev["expected_choice_ids"]
        ):
            raise PublicationError("Completeness ledger choice/contest mismatch")
        if not isinstance(ev["supersedes"], list) or not isinstance(
            ev["supersession_evidence"], dict
        ):
            raise PublicationError("Invalid supersession evidence")
        for old in ev["supersedes"]:
            predecessor = versions.get(old)
            if (
                old == vid
                or not predecessor
                or predecessor["principal_section_id"] != sid
                or predecessor["contest_id"] != cid
                or old not in evidence
                or evidence[old]["snapshot_id"] != ev["snapshot_id"]
                or not anchor(ev["supersession_evidence"].get(old))
            ):
                raise PublicationError(
                    "Supersession requires matching principal/contest/snapshot and evidence"
                )
    for vid in versions:

        def visit(current: str, ancestors: set[str]) -> None:
            if current in ancestors:
                raise PublicationError("Cyclic result supersession")
            for old in evidence.get(current, {}).get("supersedes", []):
                visit(old, ancestors | {current})

        visit(vid, set())
    for count in data.get("vote_choice_count", []):
        version, choice = (
            versions.get(count["result_version_id"]),
            choices.get(count["vote_choice_id"]),
        )
        if not version or not choice or version["contest_id"] != choice["contest_id"]:
            raise PublicationError("Choice count/result contest mismatch")
    locations = _index(data, "location", "location_id")
    for (snapshot, member), composition in compositions.items():
        principal = composition["principal_section_id"]
        p = compositions.get((snapshot, principal))
        if (
            not p
            or p["principal_section_id"] != principal
            or member not in sections
            or principal not in sections
            or snapshot not in snapshots
            or sections[member]["election_id"] != sections[principal]["election_id"]
        ):
            raise PublicationError("Composition requires same-election terminal principal self-map")
        location = composition["location_id"]
        if location and (
            location not in locations
            or locations[location]["election_id"] != sections[principal]["election_id"]
        ):
            raise PublicationError("Composition location/election mismatch")
    for ev in evidence.values():
        version = versions.get(ev["result_version_id"])
        if not version:
            raise PublicationError("Result evidence refers to missing version")
        composition = compositions.get((ev["snapshot_id"], version["principal_section_id"]))
        if (
            not composition
            or composition["principal_section_id"] != version["principal_section_id"]
        ):
            raise PublicationError("Result requires frozen principal composition")
    policies = _index(data, "harmonized_population", "population_id")
    disjoint = set()
    for member in data.get("harmonized_member", []):
        policy = policies.get(member["population_id"])
        comp = compositions.get((member["snapshot_id"], member["principal_section_id"]))
        if not policy or not comp or comp["member_section_id"] != comp["principal_section_id"]:
            raise PublicationError("Harmonized member must be whole principal population")
        # A principal enters a policy's populations once, whatever the snapshot: two snapshots
        # of one principal would count its electorate and votes twice (xr1-20261109-P5-03).
        key = (policy["harmonization_policy"], member["principal_section_id"])
        if key in disjoint:
            raise PublicationError("Harmonized populations overlap within policy")
        disjoint.add(key)
    for event in data.get("processing_event", []):
        if not event["package_id"] and not event["result_version_id"]:
            raise PublicationError("Processing event requires package/result subject")
        if event["event_kind"] not in {
            "receipt",
            "processing",
            "generation",
            "publication",
            "observation",
        }:
            raise PublicationError("Unknown processing event kind")
        version = versions.get(event["result_version_id"])
        if event["result_version_id"] and not version:
            raise PublicationError("Processing event refers to missing result")
        if version and event["package_id"] and event["package_id"] != version["package_id"]:
            raise PublicationError("Processing event package/result mismatch")
    if not elections:
        raise PublicationError("Electoral derivative requires frozen election context")


def _canonical(data: Tables) -> list[Row]:
    sections = _index(data, "section", "section_id")
    contests = _index(data, "contest", "contest_id")
    evidence = _index(data, "result_evidence", "result_version_id")
    versions = defaultdict(list)
    unassigned = defaultdict(list)
    for r in data.get("result_version", []):
        ev = evidence.get(r["result_version_id"])
        if ev:
            versions[(ev["snapshot_id"], r["principal_section_id"], r["contest_id"])].append(r)
        else:
            unassigned[(r["principal_section_id"], r["contest_id"])].append(r)
    population = set(versions)
    for r in data.get("section_composition", []):
        if r["member_section_id"] != r["principal_section_id"]:
            continue
        election = sections[r["principal_section_id"]]["election_id"]
        for c in contests.values():
            if c["election_id"] == election and c["cargo_code"] in {"1", "0001"}:
                population.add((r["snapshot_id"], r["principal_section_id"], c["contest_id"]))
    result = []
    for snapshot, principal, contest in sorted(population):
        observed = versions[(snapshot, principal, contest)]
        unknown = unassigned[(principal, contest)]
        eligible = [
            v
            for v in observed
            if v["result_status"] == "totalized"
            and evidence[v["result_version_id"]]["official_target"]
        ]
        # Any evidenced version can supersede, an annulment or rejection included; an
        # observed version of unknown status leaves the selection unresolved
        # (xr1-20261109-P5-08).
        superseded = {
            old for v in observed for old in evidence[v["result_version_id"]]["supersedes"]
        }
        survivors = [v for v in eligible if v["result_version_id"] not in superseded]
        unresolved = [
            v
            for v in unknown + observed
            if v["result_version_id"] not in superseded
            and (
                v in unknown
                and v["result_status"] in {"totalized", "unknown", "conflict"}
                or v["result_status"] == "conflict"
                # an unknown-status version competes only with an eligible one
                or v["result_status"] == "unknown"
                and bool(eligible)
            )
        ]
        state = (
            "conflict"
            if unresolved
            else "selected"
            if len(survivors) == 1
            else "conflict"
            if eligible
            else "ineligible"
            if observed or unknown
            else "missing"
        )
        result.append(
            {
                "snapshot_id": snapshot,
                "principal_section_id": principal,
                "contest_id": contest,
                "result_version_id": survivors[0]["result_version_id"]
                if state == "selected"
                else None,
                "selection_state": state,
                "selection_reason": canonical(
                    {
                        "rule": VERSION + ":official_status_and_evidenced_supersession",
                        "eligible_versions": sorted(v["result_version_id"] for v in eligible),
                        "superseded_versions": sorted(superseded),
                        "unresolved_versions": sorted(v["result_version_id"] for v in unresolved),
                    }
                ).decode(),
                "field_states": {}
                if state == "selected"
                else {"result_version_id": "conflict" if state == "conflict" else "missing_source"},
            }
        )
    return result


def _reconcile(data: Tables) -> list[Row]:
    choices = _index(data, "vote_choice", "vote_choice_id")
    evidence = _index(data, "result_evidence", "result_version_id")
    totals = _index(data, "section_contest_totals", "result_version_id")
    counts = defaultdict(list)
    for r in data.get("vote_choice_count", []):
        counts[r["result_version_id"]].append(r)
    result = []
    for version in data.get("result_version", []):
        vid, cid = version["result_version_id"], version["contest_id"]
        ev, total, observed = evidence.get(vid, {}), totals.get(vid, {}), counts[vid]
        expected = {c["vote_choice_id"] for c in choices.values() if c["contest_id"] == cid}
        actual = {c["vote_choice_id"] for c in observed}
        complete = (
            ev.get("complete_choices") is True
            and set(ev.get("expected_choice_ids", [])) == expected
            and actual == expected
            and bool(expected)
        )
        sums = dict.fromkeys(CATEGORY_FIELDS, 0)
        for count in observed:
            sums[choices[count["vote_choice_id"]]["choice_kind"]] += count["vote_count"]
        checks = {}

        def check(name: str, left: Any, right: Any) -> None:
            checks[name] = {
                "observed": left,
                "reference": right,
                "difference": left - right if left is not None and right is not None else None,
                "state": "unknown"
                if left is None or right is None
                else "matched"
                if left == right
                else "mismatch",
            }

        for kind, field in CATEGORY_FIELDS.items():
            check(field, sums[kind] if complete else None, total.get(field))
        categories = [total.get(field) for field in CATEGORY_FIELDS.values()]
        check(
            "category_sum",
            _known_sum(categories),
            total.get("total_presidential_ballots"),
        )
        check(
            "attendance_ballots",
            total.get("total_presidential_ballots"),
            total.get("attending_voters"),
        )
        attendance, abstention = total.get("attending_voters"), total.get("abstaining_electors")
        check(
            "electorate_accounting",
            attendance + abstention if attendance is not None and abstention is not None else None,
            total.get("eligible_electors"),
        )
        if attendance is not None and total.get("eligible_electors") is not None:
            checks["attendance_bound"] = {
                "state": "matched" if attendance <= total["eligible_electors"] else "mismatch",
                "difference": attendance - total["eligible_electors"],
            }
        electorate = next(
            (
                r
                for r in data.get("electorate_reference", [])
                if r["snapshot_id"] == ev.get("snapshot_id")
                and r["principal_section_id"] == version["principal_section_id"]
            ),
            None,
        )
        check(
            "electorate_reference",
            total.get("eligible_electors"),
            electorate["eligible_electors"] if electorate else None,
        )
        required = [
            v["state"]
            for k, v in checks.items()
            if k != "electorate_reference" or electorate is not None
        ]
        state = (
            "mismatch"
            if "mismatch" in required
            else "reconciled"
            if complete and set(required) == {"matched"}
            else "unavailable"
        )
        result.append(
            {
                "result_version_id": vid,
                "state": state,
                "complete_choices": complete,
                "missing_choices": sorted(expected - actual),
                "checks": checks,
                "category_counts": sums if complete else None,
            }
        )
    return result


def _hierarchy(data: Tables, canonical: list[Row]) -> list[Row]:
    sections = _index(data, "section", "section_id")
    contests = _index(data, "contest", "contest_id")
    totals = _index(data, "section_contest_totals", "result_version_id")
    snapshots = _index(data, "snapshot", "snapshot_id")
    selected = {
        (r["snapshot_id"], r["principal_section_id"], r["contest_id"]): r for r in canonical
    }
    output = []
    for ref in data.get("final_result_reference", []):
        expected = ref["expected_principals"]
        if (
            ref["level"] not in {"zone", "municipality", "uf", "national"}
            or not ref["final"]
            or not isinstance(expected, list)
            or len(expected) != len(set(expected))
        ):
            raise PublicationError(
                "Final hierarchy requires exact unique population and final status"
            )
        contest = contests.get(ref["contest_id"])
        snapshot = snapshots.get(ref["snapshot_id"])
        if not contest or not snapshot:
            raise PublicationError("Hierarchy reference election mismatch")
        for sid in expected:
            section = sections.get(sid)
            if not section or section["election_id"] != contest["election_id"]:
                raise PublicationError("Hierarchy population election mismatch")
            for field in {
                "uf": ["uf"],
                "municipality": ["uf", "municipality_tse"],
                "zone": ["uf", "municipality_tse", "zone"],
                "national": [],
            }[ref["level"]]:
                if section[field] != ref[field]:
                    raise PublicationError("Hierarchy population geography mismatch")
        eligible = [selected.get((ref["snapshot_id"], sid, ref["contest_id"])) for sid in expected]
        missing = [
            sid
            for sid, r in zip(expected, eligible, strict=True)
            if not r or r["selection_state"] != "selected"
        ]
        extra = [
            r["principal_section_id"]
            for r in canonical
            if r["snapshot_id"] == ref["snapshot_id"]
            and r["contest_id"] == ref["contest_id"]
            and r["selection_state"] == "selected"
            and r["principal_section_id"] not in expected
            and all(
                sections[r["principal_section_id"]][f] == ref[f]
                for f in {
                    "national": [],
                    "uf": ["uf"],
                    "municipality": ["uf", "municipality_tse"],
                    "zone": ["uf", "municipality_tse", "zone"],
                }[ref["level"]]
            )
        ]
        metrics = {}
        if not ref["metrics"]:
            raise PublicationError("Hierarchy requires at least one numeric metric")
        for field, reference in ref["metrics"].items():
            if field not in TOTAL_FIELDS:
                # Candidate totals are reconciled against EA20 by integrity check I4, not
                # here (xr1-20261109-P5-09).
                raise PublicationError(
                    f"Unsupported hierarchy metric {field!r}: this path reconciles only "
                    f"{', '.join(TOTAL_FIELDS)}; candidate totals are checked by I4"
                )
            if type(reference) is not int or reference < 0:
                raise PublicationError("Invalid hierarchy metric")
            values = [
                totals.get(r["result_version_id"], {}).get(field)
                for r in eligible
                if r and r["selection_state"] == "selected"
            ]
            known = (
                bool(expected) and not missing and not extra and all(v is not None for v in values)
            )
            observed = _known_sum(values) if known else None
            metrics[field] = {
                "observed": observed,
                "reference": reference,
                "difference": observed - reference if known else None,
            }
        state = (
            "coverage_gap"
            if missing or extra or not expected
            else "unavailable"
            if any(v["observed"] is None for v in metrics.values())
            else "mismatch"
            if any(v["difference"] for v in metrics.values())
            else "matched"
        )
        output.append(
            {
                "reference_id": ref["reference_id"],
                "state": state,
                "level": ref["level"],
                "missing_principals": missing,
                "extra_principals": extra,
                "metrics": metrics,
                "includes_ZZ": any(sections[s]["uf"].lower() == "zz" for s in expected),
            }
        )
    return output


def _section_marts(
    data: Tables, canonical: list[Row], reconciliation: list[Row]
) -> tuple[list[Row], list[Row]]:
    totals = _index(data, "section_contest_totals", "result_version_id")
    reconciled = {r["result_version_id"]: r for r in reconciliation}
    choices = _index(data, "vote_choice", "vote_choice_id")
    counts = defaultdict(list)
    for r in data.get("vote_choice_count", []):
        counts[r["result_version_id"]].append(r)
    results, unanimous = [], []
    for decision in canonical:
        vid = decision["result_version_id"]
        total = totals.get(vid, {})
        rec = reconciled.get(vid, {})
        complete = rec.get("state") == "reconciled"
        ballots, valid, electors = (
            total.get(k)
            for k in ("total_presidential_ballots", "valid_candidate_votes", "eligible_electors")
        )
        key = {k: decision[k] for k in ("snapshot_id", "principal_section_id", "contest_id")}

        def ratio(a: float | None, b: float | None) -> float | None:
            return a / b if complete and a is not None and b is not None and b > 0 else None

        result = {
            **key,
            "result_version_id": vid,
            "availability": "available"
            if complete
            else decision["selection_state"]
            if vid is None
            else rec.get("state", "missing_totals"),
            "totals": total,
            "turnout": ratio(total.get("attending_voters"), electors),
            "blank_share_all_ballots": ratio(total.get("blank_votes"), ballots),
            "null_share_all_ballots": ratio(total.get("null_votes"), ballots),
            "candidate_valid_shares": {
                choices[r["vote_choice_id"]]["candidacy_id"]: ratio(r["vote_count"], valid)
                for r in counts[vid]
                if choices[r["vote_choice_id"]]["choice_kind"] == "candidate"
            },
            "candidate_votes": {
                choices[r["vote_choice_id"]]["candidacy_id"]: r["vote_count"]
                for r in counts[vid]
                if choices[r["vote_choice_id"]]["choice_kind"] == "candidate"
            },
            "physical_urn_contributions": "unavailable_source_does_not_isolate_physical_contributions",
            "session_candidate_attribution": "unavailable",
        }
        results.append(result)
        candidate_counts = [
            r["vote_count"]
            for r in counts[vid]
            if choices[r["vote_choice_id"]]["choice_kind"] == "candidate"
        ]
        known = complete and ballots is not None and ballots > 0
        zero_other = all(
            total.get(k) == 0
            for k in ("blank_votes", "null_votes", "special_votes", "unresolved_votes")
        )
        unanimous.append(
            {
                **key,
                "result_version_id": vid,
                "availability": "available" if known else "unavailable",
                "strict_unanimity": (
                    sum(v == ballots for v in candidate_counts) == 1 and zero_other
                )
                if known
                else None,
                "all_valid_only_unanimity": sum(v == valid for v in candidate_counts) == 1
                if complete and valid is not None and valid > 0
                else None,
                "denominator_all_ballots": ballots if known else None,
                "denominator_valid_votes": valid if complete and valid and valid > 0 else None,
            }
        )
    return results, unanimous


def _timing(data: Tables) -> list[Row]:
    evidence = _index(data, "result_evidence", "result_version_id")
    events = defaultdict(lambda: defaultdict(list))
    for event in data.get("processing_event", []):
        if event["result_version_id"]:
            events[event["result_version_id"]][event["event_kind"]].append(event)
    result = []
    for version in data.get("result_version", []):
        vid = version["result_version_id"]
        ev = evidence.get(vid)
        if not ev:
            continue
        # Missing endpoints remain explicit. Repeated/corrected events produce distinct pairs.
        for start, end in (
            ("closing", "receipt"),
            ("generation", "receipt"),
            ("receipt", "processing"),
            ("receipt", "publication"),
            ("generation", "publication"),
        ):
            starts, ends = events[vid][start] or [None], events[vid][end] or [None]
            for a in starts:
                for b in ends:
                    known = all(
                        e
                        and e["event_at"]
                        and e["availability_state"] == "observed"
                        and e["confidence"] == "verified"
                        and e["conversion_rule"]
                        for e in (a, b)
                    )
                    seconds = (
                        (
                            datetime.fromisoformat(b["event_at"])
                            - datetime.fromisoformat(a["event_at"])
                        ).total_seconds()
                        if known and a and b
                        else None
                    )
                    result.append(
                        {
                            "snapshot_id": ev["snapshot_id"],
                            "principal_section_id": version["principal_section_id"],
                            "result_version_id": vid,
                            "interval_type": start + "_to_" + end,
                            "start_event_id": a["processing_event_id"] if a else "missing",
                            "end_event_id": b["processing_event_id"] if b else "missing",
                            "seconds": seconds,
                            "availability": "known_pair"
                            if known
                            else "unavailable_endpoint_or_clock",
                            "negative": seconds < 0 if seconds is not None else None,
                            "repeated_or_corrected": len(starts) > 1 or len(ends) > 1,
                            "pairing": "all_explicit_endpoint_pairs_no_latest_timestamp_selection",
                        }
                    )
    return result


def _rounds(data: Tables, section_results: list[Row]) -> list[Row]:
    evidence = _index(data, "harmonization_evidence", "population_id")
    sections = _index(data, "section", "section_id")
    elections = _index(data, "election", "election_id")
    contests = _index(data, "contest", "contest_id")
    snapshots = _index(data, "snapshot", "snapshot_id")
    result_index = {
        (r["snapshot_id"], r["principal_section_id"], r["contest_id"]): r for r in section_results
    }
    members = defaultdict(list)
    for r in data.get("harmonized_member", []):
        members[r["population_id"]].append(r)
    output = []
    for population in data.get("harmonized_population", []):
        pid = population["population_id"]
        groups = defaultdict(list)
        for member in members[pid]:
            election = sections[member["principal_section_id"]]["election_id"]
            if member["snapshot_id"] not in snapshots:
                raise PublicationError("Harmonized snapshot election mismatch")
            groups[election].append(member)
        first = [
            c
            for c in contests.values()
            if c["election_id"] in groups
            and elections[c["election_id"]]["round"] == 1
            and c["cargo_code"] in {"1", "0001"}
        ]
        second = [
            c
            for c in contests.values()
            if c["election_id"] in groups
            and elections[c["election_id"]]["round"] == 2
            and c["cargo_code"] in {"1", "0001"}
        ]
        pairs = [
            (a, b)
            for a in first
            for b in second
            if elections[a["election_id"]]["year"] == elections[b["election_id"]]["year"]
            and a["jurisdiction_code"] == b["jurisdiction_code"]
        ]
        if not pairs:
            output.append(
                {
                    "population_id": pid,
                    "first_contest_id": "unavailable",
                    "second_contest_id": "unavailable",
                    "availability": "missing_round_or_contest",
                    "rounds": None,
                }
            )
        for a, b in pairs:
            ev = evidence.get(pid, {})
            usable = (
                population["comparability_state"] == "comparable"
                and all(
                    ev.get(k) is True
                    for k in ("composition_reviewed", "transfers_reviewed", "electorate_reviewed")
                )
                and bool(ev.get("evidence"))
            )
            aggregates: list[dict[str, Any]] = []
            for contest in (a, b):
                rows = [
                    result_index.get(
                        (m["snapshot_id"], m["principal_section_id"], contest["contest_id"])
                    )
                    for m in groups[contest["election_id"]]
                ]
                present = [r for r in rows if r]
                available = (
                    bool(rows)
                    and len(present) == len(rows)
                    and all(r["availability"] == "available" for r in present)
                )
                usable = usable and available
                if available:
                    values = {
                        field: sum(r["totals"][field] for r in present) for field in TOTAL_FIELDS
                    }
                    candidate_votes = defaultdict(int)
                    for r in present:
                        # Candidacy IDs are contest-scoped; never imply a cross-round identity.
                        for candidate, votes in r["candidate_votes"].items():
                            candidate_votes[candidate] += votes
                    aggregates.append(
                        {
                            "contest_id": contest["contest_id"],
                            "totals": values,
                            "turnout": values["attending_voters"] / values["eligible_electors"]
                            if values["eligible_electors"]
                            else None,
                            "candidate_valid_votes": dict(candidate_votes),
                            "whole_principals": len(rows),
                        }
                    )
            output.append(
                {
                    "population_id": pid,
                    "first_contest_id": a["contest_id"],
                    "second_contest_id": b["contest_id"],
                    "availability": "comparable" if usable else "incomparable_or_incomplete",
                    "rounds": aggregates if usable else None,
                    "turnout_difference": aggregates[1]["turnout"] - aggregates[0]["turnout"]
                    if usable and all(r["turnout"] is not None for r in aggregates)
                    else None,
                    "electorate_difference": aggregates[1]["totals"]["eligible_electors"]
                    - aggregates[0]["totals"]["eligible_electors"]
                    if usable
                    else None,
                    "harmonization_evidence": ev,
                    "candidate_identity_mapping": "not_inferred_contest_scoped_ids",
                    "individual_transfer_inference": "unavailable",
                }
            )
    if not output:
        output.append(
            {
                "population_id": "unavailable",
                "first_contest_id": "unavailable",
                "second_contest_id": "unavailable",
                "availability": "missing_explicit_harmonization_or_first_round",
                "rounds": None,
            }
        )
    return output


def derive_electoral(data: Tables) -> tuple[Tables, JSON]:
    # Validate before any selection or aggregation can hide conflicting semantics.
    validate_electoral(data, {})
    canonical = _canonical(data)
    reconciliation = _reconcile(data)
    section_results, unanimous = _section_marts(data, canonical, reconciliation)
    generated = {
        "canonical_result": canonical,
        "result_reconciliation": reconciliation,
        "hierarchy_reconciliation": _hierarchy(data, canonical),
        "section_results": section_results,
        "unanimous_results": unanimous,
        "result_timing": _timing(data),
        "round_comparison": _rounds(data, section_results),
    }
    schema = {
        **MART_SCHEMAS,
        "canonical_result": {
            "key": SCHEMA["canonical_result"]["primary_key"],
            "columns": {k: v["type"] for k, v in SCHEMA["canonical_result"]["fields"].items()},
        },
    }
    return generated, schema
