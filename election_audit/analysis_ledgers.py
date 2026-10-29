"""Append-only protocol, exploration, access, investigation and conditional scenarios."""

from __future__ import annotations

import math

from election_audit.electoral_results import _anchor
from election_audit.publication import PublicationError
from election_audit.source_inventory import canonical, digest
from scripts.audit_statistics import (
    maximum_switch_margin_change,
    nonnegative_count,
    removal_contribution_bounds,
)

VERSION = "analysis-ledger-v1"
DIMENSIONS = {"outcome", "subgroup", "window", "scale", "model_variant", "historical_comparison"}
FIELDS = {
    "protocol": {"state", "family", "question", "partition_id"},
    "analysis_run": {"protocol_id", "snapshot_ids", "source_configuration", "model_config_ids"},
    "analysis_snapshot": {"exploration_ids", "status", "all_explorations_recorded"},
    "exploration": DIMENSIONS | {"protocol_id", "family_status", "result", "null_result"},
    "model_config": {"estimator", "hyperparameters", "seed", "fitted"},
    "calibration": {
        "partition_id",
        "unit_population",
        "n_cal",
        "assumptions",
        "exchangeability",
        "score_config_id",
    },
    "score": {"unit_key", "score", "score_config_id", "calibration_id", "interpretation"},
    "test_access": {"partition_id", "purpose", "inspection", "protocol_id"},
    "investigation": {
        "unit_keys",
        "score_ids",
        "alternative_explanations",
        "corroboration",
        "candidate_blinded",
        "conclusion",
    },
    "impact": {
        "target",
        "mechanism",
        "affected_population",
        "overlap_handling",
        "population_evidence",
        "final_margin",
        "margin_assumptions",
    },
}
SCHEMAS = {
    "analysis_ledger": {
        "key": ["record_id"],
        "columns": {"record_id": "text", "record_kind": "text", "analysis_run_id": "text"},
    },
    "impact_scenario": {"key": ["record_id"], "columns": {"record_id": "text"}},
    "test_partition_status": {
        "key": ["partition_id", "stable_location_id"],
        "columns": {"partition_id": "text", "stable_location_id": "text", "access_state": "text"},
    },
}


def conditional_impact(payload):
    """Explicit conditional arithmetic. Overlapping populations are never summed."""
    unavailable = {
        "availability": "unavailable",
        "margin_change_bounds": None,
        "corrected_margin_bounds": None,
        "candidate_attribution": "unavailable_anonymous_ballots",
        "national_inference": "unavailable",
    }
    mechanism = payload["mechanism"]
    if mechanism not in {"removal_exact", "removal_at_most", "switching_cap"}:
        raise PublicationError("Unsupported conditional impact mechanism")
    population = payload["affected_population"]
    if not isinstance(population, list) or not population:
        return {**unavailable, "reason": "missing_affected_population"}
    keys = [r.get("principal_section_id") for r in population]
    if (
        len(keys) != len(set(keys))
        or None in keys
        or payload["overlap_handling"]
        not in {"disjoint_principals", "corroborated_union_per_principal"}
    ):
        return {
            **unavailable,
            "reason": "overlap_requires_deduplicated_union_or_disjoint_population",
        }
    if not _anchor(payload["population_evidence"]):
        return {**unavailable, "reason": "missing_population_evidence"}
    margin = payload["final_margin"]
    if (
        margin is None
        or not isinstance(payload["margin_assumptions"], str)
        or not payload["margin_assumptions"]
    ):
        return {**unavailable, "reason": "missing_coherent_final_margin_assumption"}
    nonnegative_count(margin, "final_margin")
    lower, upper, affected = 0, 0, 0
    for row in population:
        if (
            set(row)
            != {"principal_section_id", "a", "b", "other", "cap", "cap_unit", "cap_evidence"}
            or row["cap_unit"] != "completed_presidential_ballots"
            or not _anchor(row["cap_evidence"])
        ):
            return {**unavailable, "reason": "caps_require_completed_ballots_and_evidence"}
        for field in ("a", "b", "other", "cap"):
            nonnegative_count(row[field], field)
        if row["cap"] > row["a"] + row["b"] + row["other"]:
            raise PublicationError("Affected cap exceeds reconciled population ballots")
        affected += row["cap"]
        if mechanism == "switching_cap":
            lo, hi = 0, maximum_switch_margin_change(row["a"], row["cap"])
        else:
            lo, hi = removal_contribution_bounds(
                row["a"], row["b"], row["other"], row["cap"], at_most=mechanism == "removal_at_most"
            )
        lower += lo
        upper += hi
    return {
        "availability": "conditional_arithmetic_only",
        "mechanism": mechanism,
        "affected_cap": affected,
        "margin_change_bounds": [lower, upper],
        "corrected_margin_bounds": [margin - upper, margin - lower],
        "strict_win_switch_threshold": margin // 2 + 1,
        "strict_win_one_vote_threshold": margin + 1,
        "margin_status": "explicit_assumption_not_verified_national_margin",
        "counts_status": "explicit_conditional_counts_not_independently_corroborated",
        "candidate_attribution": "unavailable_anonymous_ballots",
        "national_inference": "unavailable",
        "assumptions": payload["margin_assumptions"],
    }


def validate_records(inherited, incoming, *, partition_ids, snapshot_ids):
    """Immutable IDs and explicit references; input order never controls validity."""
    if not isinstance(incoming, list):
        raise PublicationError("Analysis records must be a list")
    records = {r["record_id"]: r for r in inherited}
    new = {}
    for record in incoming:
        if not isinstance(record, dict) or set(record) != {
            "record_id",
            "version",
            "record_kind",
            "analysis_run_id",
            "created_at",
            "references",
            "payload",
        }:
            raise PublicationError("Analysis record requires exact versioned envelope")
        kind = record["record_kind"]
        if (
            record["version"] != VERSION
            or kind not in FIELDS
            or not isinstance(record["record_id"], str)
            or not record["record_id"]
        ):
            raise PublicationError("Invalid immutable analysis record identity/kind")
        from election_audit.analysis import _instant

        _instant(record["created_at"])
        if (
            not isinstance(record["references"], list)
            or any(not isinstance(r, str) for r in record["references"])
            or len(set(record["references"])) != len(record["references"])
        ):
            raise PublicationError("References require unique immutable record IDs")
        if not isinstance(record["payload"], dict) or set(record["payload"]) != FIELDS[kind]:
            raise PublicationError(f"Invalid {kind} payload fields")
        previous = records.get(record["record_id"], new.get(record["record_id"]))
        if previous is not None and canonical(previous) != canonical(record):
            raise PublicationError("Conflicting immutable analysis record; use a new version ID")
        if previous is None:
            new[record["record_id"]] = record
    records.update(new)
    for record in new.values():
        kind, p = record["record_kind"], record["payload"]
        if any(r not in records or r == record["record_id"] for r in record["references"]):
            raise PublicationError("Missing/self analysis record reference")
        run = record["analysis_run_id"]
        if kind not in {"protocol", "analysis_run", "model_config"}:
            if run not in records or records[run]["record_kind"] != "analysis_run":
                raise PublicationError("Analysis record requires an existing analysis_run")
        elif run is not None:
            raise PublicationError("Protocol/run/model config envelope run ID must be null")

        def reference(identifier, expected):
            if identifier not in records or records[identifier]["record_kind"] != expected:
                raise PublicationError(f"Missing {expected} reference")
            return records[identifier]

        if kind == "protocol":
            if (
                p["state"] not in {"frozen", "exploratory"}
                or not isinstance(p["family"], list)
                or not p["family"]
                or any(
                    not isinstance(case, dict) or set(case) != DIMENSIONS for case in p["family"]
                )
            ):
                raise PublicationError(
                    "Protocol freezes every outcome/subgroup/window/scale/model/history dimension"
                )
            if p["partition_id"] not in partition_ids or not p["question"]:
                raise PublicationError("Protocol requires exact partition population and question")
            if len({digest(case) for case in p["family"]}) != len(p["family"]):
                raise PublicationError("Duplicate protocol family member")
        elif kind == "analysis_run":
            protocol = reference(p["protocol_id"], "protocol")
            if (
                not isinstance(p["snapshot_ids"], list)
                or not p["snapshot_ids"]
                or not set(p["snapshot_ids"]) <= snapshot_ids
                or not isinstance(p["source_configuration"], dict)
            ):
                raise PublicationError(
                    "Analysis run requires pinned snapshots and source configuration"
                )
            for identifier in p["model_config_ids"]:
                reference(identifier, "model_config")
            if _instant(record["created_at"]) < _instant(protocol["created_at"]):
                raise PublicationError("Analysis run predates protocol")
        elif kind == "model_config":
            if (
                p["fitted"] is not False
                or not p["estimator"]
                or not isinstance(p["hyperparameters"], dict)
            ):
                raise PublicationError("Foundation records configurations only; no fitted models")
        elif kind == "analysis_snapshot":
            if (
                p["status"] not in {"draft", "complete"}
                or p["all_explorations_recorded"] is not True
                or not isinstance(p["exploration_ids"], list)
                or len(set(p["exploration_ids"])) != len(p["exploration_ids"])
            ):
                raise PublicationError(
                    "Analysis snapshot requires explicit complete exploration history"
                )
            explorations = [
                reference(identifier, "exploration") for identifier in p["exploration_ids"]
            ]
            if any(r["analysis_run_id"] != run for r in explorations):
                raise PublicationError("Analysis snapshot references another run")
            if p["status"] == "complete":
                actual = {
                    r["record_id"]
                    for r in records.values()
                    if r["record_kind"] == "exploration" and r["analysis_run_id"] == run
                }
                if set(p["exploration_ids"]) != actual:
                    raise PublicationError("Complete analysis snapshot omits explored/null results")
                protocol = reference(records[run]["payload"]["protocol_id"], "protocol")
                observed = [{k: r["payload"][k] for k in DIMENSIONS} for r in explorations]
                if any(member not in observed for member in protocol["payload"]["family"]):
                    raise PublicationError(
                        "Complete analysis snapshot omits a registered family member/null result"
                    )
        elif kind in {"exploration", "test_access"}:
            protocol = reference(p["protocol_id"], "protocol")
            if records[run]["payload"]["protocol_id"] != p["protocol_id"]:
                raise PublicationError("Record protocol differs from its analysis run")
            if kind == "exploration":
                member = {key: p[key] for key in DIMENSIONS}
                if (
                    p["family_status"] not in {"frozen", "exploratory"}
                    or type(p["null_result"]) is not bool
                ):
                    raise PublicationError("Explorations retain family status and null results")
                if p["family_status"] == "frozen" and (
                    protocol["payload"]["state"] != "frozen"
                    or member not in protocol["payload"]["family"]
                ):
                    raise PublicationError("Exploration is outside frozen family; mark exploratory")
            elif (
                p["partition_id"] not in partition_ids
                or p["partition_id"] != protocol["payload"]["partition_id"]
                or p["inspection"] is not True
                or not p["purpose"]
            ):
                raise PublicationError(
                    "Test inspection requires matching partition/protocol and purpose"
                )
        elif kind == "calibration":
            reference(p["score_config_id"], "model_config")
            if (
                p["partition_id"] not in partition_ids
                or not isinstance(p["unit_population"], list)
                or len(set(p["unit_population"])) != len(p["unit_population"])
                or p["n_cal"] != len(p["unit_population"])
                or p["exchangeability"]
                not in {"unassessed", "unsupported", "assumed_not_validated"}
                or not p["assumptions"]
            ):
                raise PublicationError(
                    "Calibration requires exact population/count and explicit unvalidated assumptions"
                )
        elif kind == "score":
            reference(p["score_config_id"], "model_config")
            calibration = reference(p["calibration_id"], "calibration")
            if (
                calibration["payload"]["score_config_id"] != p["score_config_id"]
                or type(p["score"]) not in (int, float)
                or not math.isfinite(p["score"])
                or p["interpretation"] != "descriptive_only"
            ):
                raise PublicationError(
                    "Scores must be finite descriptive values with matching source configuration"
                )
        elif kind == "investigation":
            for identifier in p["score_ids"]:
                reference(identifier, "score")
            if (
                not p["unit_keys"]
                or not isinstance(p["alternative_explanations"], list)
                or not p["alternative_explanations"]
                or not isinstance(p["corroboration"], list)
                or type(p["candidate_blinded"]) is not bool
                or p["conclusion"]
                not in {"unresolved", "benign_explanation", "requires_independent_review"}
            ):
                raise PublicationError(
                    "Investigation requires alternatives/corroboration; automated fraud conclusions forbidden"
                )
        elif kind == "impact":
            conditional_impact(p)

    # Generic references must be acyclic, regardless of incoming ordering.
    def visit(identifier, chain):
        if identifier in chain:
            raise PublicationError("Cyclic analysis record references")
        for ref in records[identifier]["references"]:
            visit(ref, chain | {identifier})

    for identifier in new:
        visit(identifier, set())
    return sorted(new.values(), key=lambda r: r["record_id"]), records


def access_status(assignments, records):
    inspections = [r for r in records.values() if r["record_kind"] == "test_access"]
    accessed = {}
    for record in inspections:
        partition = record["payload"]["partition_id"]
        for row in assignments:
            if (
                row["partition_id"] == partition
                and row["partition_name"] == "test"
                and row["stable_location_id"]
            ):
                accessed.setdefault(row["stable_location_id"], []).append(record["record_id"])
    return [
        {
            "partition_id": partition,
            "stable_location_id": stable,
            "access_state": "development_inspected" if stable in accessed else "untouched",
            "inspection_record_ids": sorted(set(accessed.get(stable, []))),
            "future_analysis_eligible_holdout": stable not in accessed,
        }
        for partition, stable in sorted(
            {
                (r["partition_id"], r["stable_location_id"])
                for r in assignments
                if r["partition_name"] == "test" and r["stable_location_id"]
            }
        )
    ]
