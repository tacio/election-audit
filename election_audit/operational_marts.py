"""Operational diagnostics with explicit populations, clocks and lifecycle unknowns."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from election_audit.types import JSON, Row

MART_VERSION = "operational-marts-v1"
BRASILIA = ZoneInfo("America/Sao_Paulo")
LIFECYCLE_KINDS = ("receipt", "processing", "generation", "publication", "observation")


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        raise ValueError("Normalized clock requires explicit UTC offset")
    return instant.astimezone(UTC)


def _known_instant(value: str) -> datetime:
    """``_instant`` of a value already checked to be present."""
    instant = _instant(value)
    if instant is None:
        raise ValueError("Normalized clock missing")
    return instant


def coverage_rows(
    context: JSON, selected_objects: Iterable[str], parsed_sections: Iterable[str] = ()
) -> Iterator[Row]:
    """Preserve every frozen expected section; absence is never an observed zero."""
    tables = context["context_tables"]
    ledger = {r["section_id"]: r for r in tables.get("coverage_ledger", [])}
    composition = {
        r["member_section_id"]: r["principal_section_id"]
        for r in tables.get("section_composition", [])
    }
    membership = {r["section_id"]: r.get("membership") for r in context.get("section_evidence", [])}
    selected = set(selected_objects)
    parsed_sections = set(parsed_sections)
    for section in tables["section"]:
        sid = section["section_id"]
        original = ledger.get(sid)
        yield {
            "snapshot_id": context["snapshot_id"],
            "section_id": sid,
            "uf": section["uf"],
            "principal_section_id": composition.get(sid),
            "expected_population_status": "frozen_index"
            if membership.get(sid) == "expected_index"
            else "unknown",
            "installation_state": original["installation_state"] if original else "unknown",
            "log_availability": original["log_availability"] if original else "unknown",
            "bu_availability": original["bu_availability"] if original else "unknown",
            "source_parse_state": original["parse_state"] if original else "not_attempted",
            "operational_parse_state": "observed_selected_session"
            if sid in parsed_sections
            else "unavailable",
            "reconciliation_state": "unavailable",
            "exclusion_reason": original.get("exclusion_reason") if original else None,
            "selected_content_objects": len(selected),
            "national_status": "partial_national",
            "candidate_support_stratum": None,
            "candidate_support_state": "electoral_inputs_unavailable",
            "location_stratum": "unknown",
            "model_stratum": "unknown",
            "version_stratum": "unknown",
        }


def processing_availability_rows(context: JSON, events: Iterable[Row] = ()) -> Iterator[Row]:
    """Package/type denominators, preserving event multiplicity without fact joins.

    Optional lifecycle rows must already be authoritative contract events. Client
    observation time is reported solely for the observation kind. No HTTP header,
    download timestamp or omitted event establishes a publisher lifecycle time.
    """
    events = list(events)
    observations = {
        r["observation_id"]: r for r in context["context_tables"].get("source_observation", [])
    }
    assets = context["context_tables"].get("package_asset", [])
    for package in context["context_tables"]["source_package"]:
        pid = package["package_id"]
        witness_ids = {
            a["asset_observation_id"]
            for a in assets
            if a["package_id"] == pid and a.get("asset_observation_id")
        }
        for kind in LIFECYCLE_KINDS:
            relevant = [e for e in events if e.get("package_id") == pid and e["event_kind"] == kind]
            supported = [
                e
                for e in relevant
                if e.get("event_at")
                and e["availability_state"] == "observed"
                and e["confidence"] == "verified"
            ]
            original_observations = (
                [observations[oid] for oid in sorted(witness_ids) if oid in observations]
                if kind == "observation"
                else []
            )
            times = [e["event_at"] for e in supported] + [
                o["observed_at"] for o in original_observations
            ]
            yield {
                "snapshot_id": context["snapshot_id"],
                "package_id": pid,
                "principal_section_id": next(
                    (
                        r["principal_section_id"]
                        for r in context["context_tables"].get("section_composition", [])
                        if r["member_section_id"] == package["section_id"]
                    ),
                    None,
                ),
                "event_kind": kind,
                "expected_package_denominator": 1,
                "expected_population_status": "frozen_advertised_packages_results_unknown",
                "observed_event_count": len(relevant) + len(original_observations),
                "normalized_event_count": len(times),
                "availability_state": "observed"
                if times
                else "unresolved"
                if relevant
                else "missing_source",
                "first_event_at": min(times, key=_known_instant) if times else None,
                "last_event_at": max(times, key=_known_instant) if times else None,
                "source_event_ids": [e["processing_event_id"] for e in relevant],
                "observation_ids": [o["observation_id"] for o in original_observations],
                "latency_seconds": None,
                "latency_state": "independent_lifecycle_intervals_unavailable",
            }


def late_session_row(
    session: Row,
    summary: Row,
    cycles: list[Row],
    events: list[Row],
    section: Row,
    election: Row,
    *,
    clock_bounds: JSON | None = None,
    cross_shard_overlap: bool = False,
) -> Row:
    """Strict Brasilia completion boundary, separate open state and bounded sensitivity.

    Bounds are explicit normalized UTC [lower, upper] instants keyed by event_id;
    bounded clocks without supplied bounds remain unclassifiable. Overseas needs
    a separately validated convention and is never assigned a domestic cutoff.
    """
    sid = session["session_id"]
    by_id = {e["event_id"]: e for e in events}
    completed = [c for c in cycles if c["completion_state"] == "completed"]
    blockers = list(summary.get("blockers", []))
    if session["target_selection_state"] != "selected":
        blockers.append("official_context_unresolved")
    if cross_shard_overlap:
        blockers.append("cross_shard_overlap_unresolved")
    overseas = str(section.get("uf", "")).upper() == "ZZ"
    domestic = bool(section.get("uf")) and not overseas
    if overseas:
        blockers.append("overseas_convention_unvalidated")
    if not domestic:
        blockers.append("domestic_context_unavailable")
    date = election.get("election_date")
    cutoff = (
        datetime.fromisoformat(date + "T17:00:00").replace(tzinfo=BRASILIA).astimezone(UTC)
        if date
        else None
    )
    if not cutoff:
        blockers.append("target_date_unavailable")
    classifiable, after, unknown, lower_count, upper_count = 0, 0, 0, 0, 0
    last = None
    for cycle in completed:
        end = by_id.get(cycle.get("end_event_id"), {})
        instant = _instant(end.get("normalized_at"))
        if instant and (last is None or instant > last):
            last = instant
        if not domestic or not cutoff:
            unknown += 1
            continue
        bounds = (clock_bounds or {}).get(end.get("event_id"))
        if end.get("clock_confidence") == "verified" and instant:
            bounds = (instant.isoformat(), instant.isoformat())
        if not bounds:
            unknown += 1
            upper_count += 1
            continue
        lower, upper = map(_instant, bounds)
        if not lower or not upper or lower > upper:
            raise ValueError("Invalid explicit clock bounds")
        # Target-date membership must also be supported by the interval.
        if (
            lower.astimezone(BRASILIA).date().isoformat() != date
            or upper.astimezone(BRASILIA).date().isoformat() != date
        ):
            unknown += 1
            upper_count += 1
            continue
        definite, possible = lower > cutoff, upper > cutoff
        lower_count += definite
        upper_count += possible
        if definite == possible:
            classifiable += 1
            after += definite
        else:
            unknown += 1
    opening = [by_id.get(key, {}) for key in summary.get("opening_event_ids", [])]
    closing = [by_id.get(key, {}) for key in summary.get("closing_event_ids", [])]
    remaining_open = None
    if (
        domestic
        and cutoff
        and not blockers
        and summary.get("exposure_readiness") == "ready"
        and len(opening) == len(closing) == 1
        and all(
            e.get("clock_confidence") == "verified" and e.get("normalized_at")
            for e in opening + closing
        )
    ):
        remaining_open = (
            _known_instant(opening[0]["normalized_at"])
            <= cutoff
            < _known_instant(closing[0]["normalized_at"])
        )
    eligible = not blockers
    return {
        "session_id": sid,
        "principal_section_id": session.get("principal_section_id"),
        "snapshot_id": session["snapshot_id"],
        "convention": "overseas_unavailable"
        if overseas
        else "domestic_brasilia"
        if domestic
        else "unknown",
        "cutoff_at": cutoff.isoformat() if cutoff and domestic else None,
        "observed_completed_cycles": len(completed),
        "classifiable_completed_cycles": classifiable if eligible else None,
        "observed_classifiable_completed_cycles": classifiable,
        "unknown_completion_clock_cycles": unknown,
        "completed_cycles_after17": after if eligible else None,
        "observed_completed_cycles_after17": after,
        "after17_share": after / classifiable if eligible and classifiable else None,
        "remaining_open_at17": remaining_open,
        "remaining_open_state": "evidenced_interval"
        if remaining_open is not None
        else "unavailable",
        "clock_sensitivity_after17_lower": lower_count if domestic and cutoff else None,
        "clock_sensitivity_after17_upper": upper_count if domestic and cutoff else None,
        "last_observed_completion_at": last.isoformat() if last else None,
        "readiness": "unavailable" if blockers else "partial" if unknown else "ready",
        "blockers": sorted(set(blockers)),
        "counts_are_reconstructed_cycles_not_reconciled_votes": True,
    }


def materialize_marts(
    connection: duckdb.DuckDBPyConnection,
    context: JSON,
    selected_objects: Iterable[str],
    shards: Iterable[Path],
    *,
    cross_shard_overlap: bool = False,
) -> list[str]:
    """One bounded shard at a time; no package/member/lineage fact multiplication."""
    from collections import defaultdict

    from election_audit.archive_parsing import _rows
    from election_audit.publication import _batches, _create, _insert

    for name in ("operational_coverage", "processing_event_availability", "late_voting"):
        _create(connection, name)
    selected_sections = {
        r[0]
        for r in connection.execute(
            "SELECT DISTINCT principal_section_id FROM voting_session WHERE target_selection_state='selected'"
        ).fetchall()
    }
    for batch in _batches(coverage_rows(context, selected_objects, selected_sections), 2048):
        _insert(connection, "operational_coverage", batch)
    for batch in _batches(processing_availability_rows(context), 2048):
        _insert(connection, "processing_event_availability", batch)
    sections = {r["section_id"]: r for r in context["context_tables"]["section"]}
    elections = {r["election_id"]: r for r in context["context_tables"]["election"]}
    shards = list(shards)
    # Only a section whose sessions come from more than one shard can be split between them;
    # the others keep their measures (xr1-20261109-P6-08).
    spanning: set[str] = set()
    if cross_shard_overlap:
        seen: dict[str, Path] = {}
        for shard in shards:
            for session in _rows(shard / "voting_session.jsonl"):
                principal = session.get("principal_section_id")
                if seen.setdefault(principal, shard) != shard:
                    spanning.add(principal)
    for shard in shards:
        events, cycles = defaultdict(list), defaultdict(list)
        for row in _rows(shard / "selected_event.jsonl"):
            events[row["session_id"]].append(row)
        for row in _rows(shard / "anonymous_cycle.jsonl"):
            cycles[row["session_id"]].append(row)
        summaries = {row["session_id"]: row for row in _rows(shard / "session_summaries.jsonl")}
        for session in _rows(shard / "voting_session.jsonl"):
            sid = session["session_id"]
            section = sections.get(session.get("principal_section_id"), {})
            row = late_session_row(
                session,
                summaries[sid],
                cycles[sid],
                events[sid],
                section,
                elections.get(section.get("election_id"), {}),
                cross_shard_overlap=session.get("principal_section_id") in spanning,
            )
            _insert(connection, "late_voting", [row])
    return ["operational_coverage", "processing_event_availability", "late_voting"]
