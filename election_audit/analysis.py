"""Versioned analysis foundations. Arithmetic is descriptive; no models are fitted."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb

from election_audit.archive_parsing import _read_checked
from election_audit.publication import PublicationError, ResourceConfig, open_release
from election_audit.source_inventory import canonical, digest
from election_audit.types import JSON, Argv, Row, one

VERSION = "audit-analysis-v1"
REGISTRY_VERSION = "audit-features-v1"
SPECIFICATIONS = {
    "operational_adjusted": {"device_logistics": "adjustment", "baseline": "first_round_required"},
    "mechanism": {"device_logistics": "possible_mechanism", "baseline": "first_round_required"},
    "no_first_round": {"device_logistics": "adjustment", "baseline": "current_cycle_only"},
    "history_assisted": {
        "device_logistics": "adjustment",
        "baseline": "comparable_history_required",
    },
}
COMPONENTS = {
    "population_coverage": ["coverage_status"],
    "session_summary": ["completed_cycles"],
    "cycle_duration_gap": ["duration_gap_distribution"],
    "processing_event_availability": ["lifecycle_availability"],
    "late_voting": ["after17_share"],
    "section_results": ["canonical_result_status"],
    "unanimous_results": ["strict_all_ballot_unanimity"],
    "result_timing": ["named_endpoint_intervals"],
    "round_comparison": ["harmonized_round_vector"],
    "audit_features": ["registry_coverage"],
    "turnout_target": ["turnout"],
    "candidate_share_target": ["candidate_a_share", "candidate_b_share"],
    "blank_null_targets": ["blank_share", "null_share"],
    "peer_covariates": ["electorate", "first_round_vector", "geography", "history", "pre_election"],
    "device_logistics": ["model_version_logistics"],
    "integrity": ["accounting_hierarchy_rdv_signatures"],
    "conditional_unusualness": ["held_out_scores"],
    "multiplicity": ["frozen_family_valid_pvalues"],
    "validation_investigation": ["independent_validation"],
    "conditional_margin_bounds": ["conditional_impact"],
    "counterfactual_excess": ["conditional_counterfactual"],
}
BLOCKERS = {
    "population_coverage": "unknown_location_model_support_strata; inspect operational_coverage",
    "session_summary": "principal_session_deduplication_and_semantic_review_required",
    "cycle_duration_gap": "prespecified_statistic_exposure_clock_and_contest_count_review_required",
    "processing_event_availability": "publisher_lifecycle_population_and_semantics_required",
    "late_voting": "principal_deduplication_and_clock_review_required; inspect late_voting",
    "section_results": "canonical_reconciled_result_required",
    "unanimous_results": "complete_positive_all_ballot_result_required; inspect unanimous_results",
    "result_timing": "named_endpoint_and_clock_review_required; inspect result_timing",
    "round_comparison": "reviewed_first_round_population_and_composition_required",
    "audit_features": "scientific_eligibility_is_feature_specific",
    "peer_covariates": "explicit_comparable_pre_election_first_round_history_imports_required",
    "device_logistics": "verified_device_version_and_pre_election_logistics_exposure_required",
    "integrity": "national_final_population_rdv_signature_and_independent_records_unavailable",
    "conditional_unusualness": "no_fitted_model_calibration_exchangeability_or_power_validation",
    "multiplicity": "no_valid_null_pvalues_frozen_test_family_or_assessed_exchangeability",
    "validation_investigation": "independent_corroboration_and_simulation_validation_required",
    "conditional_margin_bounds": "final_margin_and_corroborated_disjoint_mechanism_population_required",
    "counterfactual_excess": "no_fitted_baseline_or_identified_counterfactual",
}
SOURCE_TABLES = {
    "turnout_target": ["section_results", "section_contest_totals"],
    "candidate_share_target": ["section_results", "vote_choice_count", "vote_choice", "candidacy"],
    "blank_null_targets": ["section_results", "section_contest_totals", "vote_choice_count"],
    "peer_covariates": ["section_results", "round_comparison", "location", "section"],
    "device_logistics": ["voting_session", "event_evidence"],
    "integrity": ["result_reconciliation", "hierarchy_reconciliation"],
}
SCHEMAS = {
    "audit_feature_registry": {
        "key": ["registry_version", "feature_id"],
        "columns": {"registry_version": "text", "feature_id": "text"},
    },
    "audit_features": {
        "key": ["analysis_id", "unit_key", "feature_id", "component", "specification_version"],
        "columns": {
            "analysis_id": "text",
            "unit_key": "text",
            "feature_id": "text",
            "component": "text",
            "specification_version": "text",
            "value": "number",
            "numerator": "number",
            "denominator": "number",
            "readiness_state": "text",
        },
    },
}


def registry() -> list[JSON]:
    """All 21 contracts retain their normative dependency and exclusion definitions."""
    contract = json.loads(
        files("election_audit.resources").joinpath("contracts/features.json").read_text()
    )
    return [
        {
            **item,
            "registry_version": REGISTRY_VERSION,
            "feature_id": item["id"],
            "components": COMPONENTS[item["id"]],
            "source_tables": SOURCE_TABLES.get(item["id"], [item["mart"]]),
            "specifications": SPECIFICATIONS,
            "temporal_rule": "as_of_cutoff; unknown observation date prevents predictive eligibility",
            "unit": "proportion"
            if item["id"] in {"turnout_target", "candidate_share_target", "blank_null_targets"}
            else "component_specific",
            "blocker": BLOCKERS.get(
                item["id"], "canonical_counts_positive_denominator_and_fixed_design_required"
            ),
        }
        for item in contract["features"]
    ]


def _instant(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PublicationError("Analysis cutoff requires an offset-aware ISO instant") from exc
    if instant.utcoffset() is None:
        raise PublicationError("Analysis cutoff requires an offset-aware ISO instant")
    return instant


def read_analysis(bundle: str | Path, config: ResourceConfig) -> JSON:
    raw = Path(bundle).read_bytes()
    if len(raw) > 8 * 1024**2:
        raise PublicationError("Analysis configuration exceeds 8 MiB bound")
    from election_audit.electoral_imports import strict_json

    spec = strict_json(raw)
    if not isinstance(spec, dict) or set(spec) - {
        "version",
        "cutoff_at",
        "candidate_a",
        "candidate_b",
        "partition",
        "records",
    }:
        raise PublicationError("Unknown analysis configuration field")
    if spec.get("version") != VERSION:
        raise PublicationError("Unsupported analysis version")
    _instant(spec.get("cutoff_at"))
    if (
        not isinstance(spec.get("records", []), list)
        or len(spec.get("records", [])) > config.max_events
    ):
        raise PublicationError("Bounded analysis record limit exceeded")
    if bool(spec.get("candidate_a")) != bool(spec.get("candidate_b")) or (
        spec.get("candidate_a") and spec["candidate_a"] == spec["candidate_b"]
    ):
        raise PublicationError("Fix distinct candidate A/B identifiers together")
    if any(
        name in spec and (not isinstance(spec[name], str) or not spec[name])
        for name in ("candidate_a", "candidate_b")
    ):
        raise PublicationError("Candidate identifiers must be nonempty official scoped strings")
    sha = hashlib.sha256(raw).hexdigest()
    from election_audit.analysis_ledgers import SCHEMAS as LEDGER_SCHEMAS
    from election_audit.analysis_partitions import SCHEMAS as PARTITION_SCHEMAS

    schema_sha = digest(
        {"registry": registry(), "schemas": {**SCHEMAS, **LEDGER_SCHEMAS, **PARTITION_SCHEMAS}}
    )
    return {
        "analysis": spec,
        "tables": {},
        "bundle_sha256": sha,
        "identity": {"adapter": VERSION, "configuration_sha256": sha},
        "normalized_schema_sha256": schema_sha,
        "source_discovery": {"status": "analysis_foundation_normalized_only"},
        "real_bu_validation": "unavailable_verified_official_adapter_outstanding",
        "verification_status": "normalized_only",
        "originals": {sha: raw},
    }


def _rows(connection: duckdb.DuckDBPyConnection, sql: str, batch_rows: int) -> Iterator[Any]:
    cursor = connection.execute(sql)
    while batch := cursor.fetchmany(batch_rows):
        yield from batch


def _measure(feature: str, component: Row, result: Row, spec: JSON) -> tuple[Any, Any, str | None]:
    totals = result.get("totals", {})
    a, b = spec.get("candidate_a"), spec.get("candidate_b")
    if result.get("availability") != "available":
        return None, None, "missing_or_unreconciled_canonical_result"
    if feature == "turnout_target":
        return totals.get("attending_voters"), totals.get("eligible_electors"), None
    if feature == "blank_null_targets":
        return (
            totals.get("blank_votes" if component == "blank_share" else "null_votes"),
            totals.get("total_presidential_ballots"),
            None,
        )
    if feature == "candidate_share_target":
        votes = result.get("candidate_votes", {})
        if not a or a not in votes or b not in votes or set(votes) != {a, b}:
            return None, None, "fixed_A_B_and_exact_candidate_set_required"
        return votes[a if component == "candidate_a_share" else b], votes[a] + votes[b], None
    if feature == "peer_covariates" and component == "electorate":
        return totals.get("eligible_electors"), None, None
    return None, None, BLOCKERS.get(feature, "missing_input")


def feature_rows(parent: Path, document: JSON, spec: JSON, config: ResourceConfig) -> Iterator[Row]:
    """Stream the long ledger; never materialize parent operational events/cycles."""
    names = document.get("combined_tables", document["tables"])
    result_sql = "r.payload" if "section_results" in names else "NULL"
    join = (
        "LEFT JOIN section_results r ON r.snapshot_id=c.snapshot_id AND r.principal_section_id=c.principal_section_id"
        if "section_results" in names
        else ""
    )
    units = "SELECT snapshot_id,principal_section_id FROM section_composition WHERE member_section_id=principal_section_id"
    if "operational_coverage" in names:
        units += " UNION SELECT snapshot_id,section_id AS principal_section_id FROM operational_coverage WHERE json_extract_string(payload,'$.principal_section_id') IS NULL"
    sql = f"SELECT c.snapshot_id,c.principal_section_id,{result_sql} FROM ({units}) c {join} ORDER BY c.snapshot_id,c.principal_section_id"
    analysis_id = digest(spec)
    from election_audit.derivatives import release_layers

    official_snapshots = set()
    for layer_path, layer in release_layers(parent, document):
        if layer.get("verification_status") == "official_layout_verified":
            evidence = _read_checked(layer_path, "import.json")["source_discovery"]
            official_snapshots.add(evidence["real_validation"]["snapshot_id"])
    with open_release(parent, _verified_document=document, config=config) as db:
        for snapshot, principal, payload in _rows(db, sql, config.batch_rows):
            result = json.loads(payload) if payload else {}
            official_layout = snapshot in official_snapshots
            source_key = {
                "snapshot_id": snapshot,
                "principal_section_id": principal,
                "contest_id": result.get("contest_id"),
                "result_version_id": result.get("result_version_id"),
            }
            unit_key = digest(source_key)
            for definition in registry():
                feature = definition["feature_id"]
                for component in definition["components"]:
                    numerator, denominator, reason = _measure(feature, component, result, spec)
                    if numerator is not None and (
                        denominator is None and component != "electorate"
                    ):
                        reason = "missing_denominator"
                    if denominator is not None and denominator <= 0:
                        reason = "zero_denominator"
                    value = (
                        numerator / denominator
                        if not reason and denominator
                        else numerator
                        if not reason
                        else None
                    )
                    if value is None and reason is None:
                        reason = "missing_input"
                    for variant, settings in SPECIFICATIONS.items():
                        yield {
                            "analysis_id": analysis_id,
                            "snapshot_id": snapshot,
                            "unit_key": unit_key,
                            "feature_id": feature,
                            "component": component,
                            "specification_version": f"{REGISTRY_VERSION}:{variant}",
                            "value": value,
                            "unit": "electors" if component == "electorate" else definition["unit"],
                            "numerator": numerator,
                            "denominator": denominator,
                            "computational_state": "available"
                            if value is not None
                            else "unavailable",
                            "readiness_state": "partial" if value is not None else "unavailable",
                            "unavailable_reason": reason,
                            "details": {
                                "definition": definition["definition"],
                                "required_inputs": definition["requires"],
                                "denominator_definition": definition["denominator"],
                                "unavailable_when": definition["unavailable_when"],
                            },
                            "scientific_eligible": False,
                            "quality_indicators": [
                                "official_layout_verified"
                                if official_layout
                                else "normalized_only",
                                "final_BU_reconciliation_unavailable"
                                if official_layout
                                else "real_BU_validation_unavailable",
                                "partial_national",
                                "temporal_source_availability_unverified",
                            ],
                            "scientific_blockers": [
                                "official_status_and_complete_choices_unverified"
                                if official_layout
                                else "source_schema_not_officially_verified",
                                "no_fitted_model",
                                "no_assessed_exchangeability",
                                "no_coherent_final_national_margin",
                            ],
                            "cutoff_at": spec["cutoff_at"],
                            "source_available_at": None,
                            "temporal_availability": "unknown_prevents_predictive_eligibility",
                            "analytical_role": definition["analytical_role"],
                            "specification_role": settings["device_logistics"]
                            if feature == "device_logistics"
                            else definition["analytical_role"],
                            "baseline_requirement": settings["baseline"],
                            "automatic_control": False,
                            "lineage_keys": {
                                "parent_release_id": parent.name,
                                "tables": definition["source_tables"],
                                **source_key,
                            },
                            "transformation_version": REGISTRY_VERSION,
                        }


def derive_analysis(
    parent: Path, document: JSON, spec: JSON, config: ResourceConfig
) -> tuple[dict[str, Any], JSON]:
    from election_audit.analysis_ledgers import (
        SCHEMAS as LEDGER_SCHEMAS,
    )
    from election_audit.analysis_ledgers import (
        access_status,
        conditional_impact,
        validate_records,
    )
    from election_audit.analysis_partitions import SCHEMAS as PARTITION_SCHEMAS

    result: dict[str, Any] = {
        "audit_feature_registry": registry(),
        "audit_features": feature_rows(parent, document, spec, config),
    }
    schemas = {**SCHEMAS, **PARTITION_SCHEMAS, **LEDGER_SCHEMAS}
    names = document.get("combined_tables", document["tables"])
    inherited = {}
    with open_release(parent, _verified_document=document, config=config) as db:
        retained = 0
        for name in ("partition_plan", "location_partition", "analysis_ledger"):
            rows = (
                db.execute(f'SELECT payload FROM "{name}"').fetchmany(config.max_events + 1)
                if name in names
                else []
            )
            retained += len(rows)
            if retained > config.max_events:
                raise PublicationError("Bounded inherited analysis context limit exceeded")
            inherited[name] = [json.loads(row[0]) for row in rows]
        source_hashes = {
            row[0]
            for row in db.execute("SELECT object_sha256 FROM source_object").fetchmany(
                config.max_events + 1
            )
        }
        if len(source_hashes) > config.max_events:
            raise PublicationError("Bounded analysis evidence catalogue limit exceeded")
        validate_evidence(spec, source_hashes)
        snapshots = {
            row[0]
            for row in db.execute("SELECT snapshot_id FROM snapshot").fetchmany(
                config.max_events + 1
            )
        }
        if len(snapshots) > config.max_events:
            raise PublicationError("Bounded analysis snapshot catalogue limit exceeded")
        if spec.get("partition") is not None:
            from election_audit.analysis_partitions import partition_tables

            plans, assignments = partition_tables(db, spec["partition"], config.max_events)
        else:
            plans, assignments = [], []
    for name, rows in (("partition_plan", plans), ("location_partition", assignments)):
        keys = schemas[name]["key"]
        old = {tuple(row[k] for k in keys): row for row in inherited[name]}
        fresh = []
        for row in rows:
            key = tuple(row[k] for k in keys)
            if key in old and canonical(old[key]) != canonical(row):
                raise PublicationError("Conflicting immutable partition assignment")
            if key not in old:
                fresh.append(row)
        result[name] = fresh
    all_plans = inherited["partition_plan"] + result["partition_plan"]
    all_assignments = inherited["location_partition"] + result["location_partition"]
    fresh_records, records = validate_records(
        inherited["analysis_ledger"],
        spec.get("records", []),
        partition_ids={p["partition_id"] for p in all_plans},
        snapshot_ids=snapshots,
    )
    if len(all_assignments) + len(all_plans) + len(records) > config.max_events:
        raise PublicationError("Bounded combined analysis context limit exceeded")
    validate_populations(all_assignments, records, fresh_records)
    with open_release(parent, _verified_document=document, config=config) as db:
        for record in fresh_records:
            if record["record_kind"] == "impact":
                validate_impact_target(db, record["payload"], names)
    result["analysis_ledger"] = fresh_records
    result["impact_scenario"] = [
        {"record_id": r["record_id"], **conditional_impact(r["payload"])}
        for r in fresh_records
        if r["record_kind"] == "impact"
    ]
    result["test_partition_status"] = access_status(all_assignments, records)
    return result, schemas


def validate_evidence(value: Any, source_hashes: set[str]) -> None:
    """Publication resolves anchors to preserved bytes; review truth remains asserted."""
    from election_audit.electoral_results import _anchor

    if isinstance(value, dict):
        if _anchor(value) and value["object_sha256"] not in source_hashes:
            raise PublicationError(
                "Analysis evidence anchor does not resolve to a frozen source object"
            )
        for item in value.values():
            validate_evidence(item, source_hashes)
    elif isinstance(value, list):
        for item in value:
            validate_evidence(item, source_hashes)


def validate_impact_target(db: duckdb.DuckDBPyConnection, payload: JSON, names: set[str]) -> None:
    target = payload["target"]
    if (
        not isinstance(target, dict)
        or set(target) != {"snapshot_id", "election_id", "contest_id", "candidate_a", "candidate_b"}
        or any(not isinstance(v, str) or not v for v in target.values())
        or target["candidate_a"] == target["candidate_b"]
    ):
        raise PublicationError(
            "Impact requires one exact snapshot/election/contest and distinct candidate IDs"
        )
    if "section_results" not in names:
        raise PublicationError("Impact requires a normalized reconciled electoral parent")
    for row in payload["affected_population"]:
        rows = db.execute(
            "SELECT r.payload,s.election_id FROM section_results r JOIN section s ON s.section_id=r.principal_section_id WHERE r.snapshot_id=? AND r.contest_id=? AND r.principal_section_id=?",
            [target["snapshot_id"], target["contest_id"], row["principal_section_id"]],
        ).fetchmany(2)
        if len(rows) != 1 or rows[0][1] != target["election_id"]:
            raise PublicationError(
                "Impact population crosses target election/contest or is unresolved"
            )
        result = json.loads(rows[0][0])
        votes = result.get("candidate_votes", {})
        a, b = target["candidate_a"], target["candidate_b"]
        if result.get("availability") != "available" or a not in votes or b not in votes:
            raise PublicationError(
                "Impact candidate counts require reconciled explicit candidate IDs"
            )
        expected = (
            votes[a],
            votes[b],
            result["totals"]["total_presidential_ballots"] - votes[a] - votes[b],
        )
        if (row["a"], row["b"], row["other"]) != expected:
            raise PublicationError(
                "Impact counts differ from the pinned normalized canonical population"
            )


def validate_populations(
    assignments: list[Row], records: dict[str, Row], fresh: Iterable[Row]
) -> None:
    from election_audit.analysis_ledgers import access_status

    units = {r["stable_location_id"] for r in assignments if r["eligible"]}
    principals = {r["principal_section_id"] for r in assignments}
    prior = {
        key: record for key, record in records.items() if key not in {r["record_id"] for r in fresh}
    }
    accessed = {
        r["stable_location_id"]
        for r in access_status(assignments, prior)
        if r["access_state"] == "development_inspected"
    }
    untouched = {
        r["stable_location_id"]
        for r in access_status(assignments, records)
        if r["access_state"] == "untouched"
    }
    test_principals = {
        r["principal_section_id"] for r in assignments if r["stable_location_id"] in untouched
    }
    for record in fresh:
        p, kind = record["payload"], record["record_kind"]
        if kind == "protocol" and p["state"] == "frozen":
            tests = {
                r["stable_location_id"]
                for r in assignments
                if r["partition_id"] == p["partition_id"] and r["partition_name"] == "test"
            }
            if tests & accessed:
                raise PublicationError(
                    "Inspected test population is development data; future protocol must be exploratory or use a fresh untouched population"
                )
        if kind == "calibration":
            eligible = {
                r["stable_location_id"]
                for r in assignments
                if r["partition_id"] == p["partition_id"]
                and r["partition_name"] == "calibration"
                and r["eligible"]
            }
            if not set(p["unit_population"]) <= eligible:
                raise PublicationError(
                    "Calibration population contains unknown or non-calibration locations"
                )
        if kind == "score" and p["unit_key"] not in units | principals:
            raise PublicationError("Score unit is outside exact linked population")
        if kind == "score" and p["unit_key"] in untouched | test_principals:
            raise PublicationError("Test score inspection requires an immutable test_access record")
        if kind == "investigation" and not set(p["unit_keys"]) <= units | principals:
            raise PublicationError("Investigation unit is outside exact population")
        if kind == "investigation" and set(p["unit_keys"]) & (untouched | test_principals):
            raise PublicationError("Test investigation requires an immutable test_access record")
        if kind == "impact" and any(
            r.get("principal_section_id") not in principals for r in p["affected_population"]
        ):
            raise PublicationError(
                "Conditional impact population is outside pinned principal population"
            )


def _logical(rows: Iterable[Any]) -> JSON:
    count, total = 0, 0
    for row in rows:
        count += 1
        total = (total + int.from_bytes(hashlib.sha256(canonical(row)).digest(), "big")) % (
            1 << 256
        )
    return {
        "rows": count,
        "logical_sha256": hashlib.sha256(f"{count}:{total}".encode()).hexdigest(),
    }


def validate_analysis(path: Path, document: JSON, connection: duckdb.DuckDBPyConnection) -> None:
    spec = _read_checked(path, "import.json")["analysis"]
    pin = document["identity"]["adapter"]["configuration_sha256"]
    checked = read_analysis(
        path / "originals" / pin, ResourceConfig(**document["settings_applied"])
    )
    if (
        checked["analysis"] != spec
        or checked["normalized_schema_sha256"] != document["identity"]["normalized_schema_sha256"]
    ):
        raise PublicationError("Analysis configuration/schema pin mismatch")
    generated, _ = derive_analysis(
        Path(document["_parent_path"]),
        document["_parent_document"],
        spec,
        ResourceConfig(**document["settings_applied"]),
    )
    for name, rows in generated.items():
        expected = _logical(rows)
        if name in {"partition_plan", "location_partition", "analysis_ledger", "impact_scenario"}:
            from election_audit.derivatives import release_layers

            number = len(list(release_layers(path, document))) - 1
            actual = _logical(
                json.loads(row[0])
                for row in _rows(
                    connection, f'SELECT payload FROM parent_{number}.main."local_{name}"', 2048
                )
            )
        else:
            actual = document["combined_tables"][name]
        if any(actual[k] != v for k, v in expected.items()):
            raise PublicationError(f"Analysis derivation mismatch: {name}")


def protect_test_query(connection: duckdb.DuckDBPyConnection, document: JSON, sql: str) -> None:
    """Require an immutable inspection record before exposing any untouched test outcomes."""
    import re

    import duckdb

    if "test_partition_status" not in document.get("combined_tables", {}):
        return
    untouched = one(
        connection.execute(
            "SELECT count(*) FROM test_partition_status WHERE access_state='untouched'"
        ).fetchone()
    )[0]
    if untouched:
        safe = {
            "audit_feature_registry",
            "partition_plan",
            "location_partition",
            "analysis_ledger",
            "test_partition_status",
            "training_features",
        }
        # Parse against an empty catalogue: resolving existing views would expand
        # safe metadata into their attached physical layer names. Dynamic table
        # functions are unavailable while outcomes remain untouched.
        surface = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S)
        dynamic = re.search(r'\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?(?:[\w".]*)\s*\(', surface, re.I)
        if dynamic or duckdb.get_table_names(sql, qualified=True) - safe:
            raise PublicationError(
                "Untouched test outcomes are reserved. Query training_features or publish a test_access record before inspection; inspected locations become development data for future analyses"
            )


def publish_analysis(
    parent: str | Path,
    bundle: str | Path,
    store: str | Path,
    *,
    config: ResourceConfig | None = None,
) -> Path:
    from election_audit.derivatives import publish_derivative

    return publish_derivative(parent, bundle, store, config=config, _analysis=True)


def analysis_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    for key, default in ResourceConfig().__dict__.items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        result = publish_analysis(
            args.parent,
            args.bundle,
            args.store,
            config=ResourceConfig(**{k: getattr(args, k) for k in ResourceConfig().__dict__}),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(result)
    return 0
