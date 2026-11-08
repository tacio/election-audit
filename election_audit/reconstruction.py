"""Conservative operational reconstruction from verified frozen parse publications.

Structural observations are automatic; official context and new semantics need a
reviewed, versioned evidence input. Neither assertions nor hashes verify signatures.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from election_audit.archive_parsing import (
    FrozenParseReader,
    _read_checked,
    _rows,
    _write_checked,
)
from election_audit.contracts import validate_rows
from election_audit.snapshots import _fsync_directory
from election_audit.source_inventory import canonical, digest, hash_file, identity

VERSION = "operational-v1"
EVIDENCE_VERSION = "operational-evidence-v1"
TABLES = (
    "physical_device",
    "software_configuration",
    "voting_session",
    "session_package",
    "selected_event",
    "anonymous_cycle",
    "record_lineage",
    "parsing_issue",
)


class ReconstructionError(ValueError):
    """Invalid evidence or reconstruction input; no successful artifact emitted."""


def _row(**values):
    return {**values, "field_states": {key: "unresolved" for key, v in values.items() if v is None}}


def _reading(event):
    raw = event.get("device_timestamp_raw")
    return datetime.strptime(raw, "%d/%m/%Y %H:%M:%S") if raw else None


def _stream(event):
    return canonical([event["object_sha256"], event["record_locator"]["archive_segments"]])


def _claim(claim, events):
    """Validate exact source anchors; a review remains a supplied human assertion."""
    if claim.get("review_state") not in {"reviewed", "unverified"}:
        raise ReconstructionError("Every claim needs reviewed/unverified review_state")
    rule = claim.get("rule_id", "")
    if (
        not isinstance(rule, str)
        or not rule
        or len(rule) > 120
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
            for c in rule
        )
    ):
        raise ReconstructionError("Use a bounded non-sensitive versioned rule_id")
    anchors = claim.get("evidence", [])
    if not anchors:
        raise ReconstructionError("Claims require original event/hash anchors")
    for anchor in anchors:
        if set(anchor) != {"event_id", "source_line_sha256"}:
            raise ReconstructionError("Evidence must contain only event_id/source_line_sha256")
        if (
            events.get(anchor["event_id"], {}).get("source_line_sha256")
            != anchor["source_line_sha256"]
        ):
            raise ReconstructionError("Evidence event/hash mismatch")
    return claim["review_state"] == "reviewed"


def _contiguous(ids, events) -> None:
    if not ids or len(set(ids)) != len(ids) or any(key not in events for key in ids):
        raise ReconstructionError("Empty, duplicate or unknown event interval")
    group = [events[key] for key in ids]
    if len({_stream(event) for event in group}) != 1:
        raise ReconstructionError("Intervals must stay in one original member occurrence")
    lines = [event["record_locator"]["line_start"] for event in group]
    if lines != list(range(lines[0], lines[0] + len(lines))):
        raise ReconstructionError("Interval must contain every consecutive physical source line")


def reconstruct_sessions(document, witnesses, *, evidence=None, max_events=1_000_000):
    """Build candidate sessions once per content occurrence; retain every witness.

    Explicit segments replace candidate boundaries only for reviewed claims. A
    copied block is removed only after exact consecutive physical-line hashes
    match a reviewed rule. Unknown devices receive no shared physical identity.
    """
    evidence = evidence or {"version": EVIDENCE_VERSION}
    if evidence.get("version") != EVIDENCE_VERSION or set(evidence) - {
        "version",
        "segments",
        "copies",
        "semantics",
        "clocks",
    }:
        raise ReconstructionError("Unsupported evidence format/fields")
    if type(max_events) is not int or max_events < 1:
        raise ReconstructionError("max_events must be positive")
    events, originals, witness_count = {}, defaultdict(list), 0
    for witness in witnesses:
        key = witness["event_id"]
        events.setdefault(key, witness)
        originals[key].append(witness)
        witness_count += 1
        if len(events) > max_events or witness_count > max_events * 10:
            raise ReconstructionError("Reconstruction event/witness bound exceeded")
    aliases, copy_rules = {}, {}
    for copy in evidence.get("copies", []):
        if set(copy) - {
            "canonical_event_ids",
            "copied_event_ids",
            "rule_id",
            "review_state",
            "evidence",
        }:
            raise ReconstructionError("Unknown copy fields")
        reviewed = _claim(copy, events)
        left, right = copy["canonical_event_ids"], copy["copied_event_ids"]
        _contiguous(left, events)
        _contiguous(right, events)
        if len(left) != len(right) or len(left) < 2 or set(left) & set(right):
            raise ReconstructionError(
                "Copy requires distinct equal intervals of at least two lines"
            )
        if [events[k]["source_line_sha256"] for k in left] != [
            events[k]["source_line_sha256"] for k in right
        ]:
            raise ReconstructionError("Copied block is not exact physical-line byte evidence")
        if reviewed:
            for target, duplicate in zip(left, right, strict=True):
                if duplicate in aliases or target in aliases or target in aliases.values():
                    raise ReconstructionError(
                        "Copy chains/overlapping copy decisions are unsupported"
                    )
                aliases[duplicate], copy_rules[duplicate] = target, copy["rule_id"]
    # Keep original witnesses attached to the surviving operational occurrence.
    for duplicate, target in aliases.items():
        originals[target].extend(originals[duplicate])
    surviving = {key: event for key, event in events.items() if key not in aliases}
    segments, assigned = [], set()
    for segment in evidence.get("segments", []):
        if set(segment) - {
            "event_ids",
            "rule_id",
            "review_state",
            "evidence",
            "session_kind",
            "principal_section_id",
            "election_id",
            "serial",
            "software_version",
            "software_build",
            "start_reason",
            "end_reason",
            "distinct_history",
        }:
            raise ReconstructionError("Unknown session evidence fields")
        reviewed = _claim(segment, events)
        ids = segment["event_ids"]
        _contiguous(ids, surviving)
        if not {anchor["event_id"] for anchor in segment["evidence"]} <= set(ids):
            raise ReconstructionError("Session evidence must anchor its own interval")
        if "distinct_history" in segment and type(segment["distinct_history"]) is not bool:
            raise ReconstructionError("distinct_history must be an explicit boolean review")
        if not reviewed:
            continue
        if assigned & set(ids):
            raise ReconstructionError("Overlapping session segment assignments")
        if len({surviving[key].get("device_id_raw") for key in ids}) != 1:
            raise ReconstructionError("A physical session cannot cross observed device changes")
        if segment.get("session_kind", "unresolved") not in {
            "official_vota",
            "setup",
            "training",
            "other",
            "unresolved",
        }:
            raise ReconstructionError("Unknown session kind")
        for field in ("start_reason", "end_reason"):
            if segment.get(field, "unknown") not in {
                "unknown",
                "opening",
                "closing",
                "restart",
                "replacement",
                "truncated",
            }:
                raise ReconstructionError("Unknown session boundary reason")
        assigned.update(ids)
        segments.append((ids, segment))
    # Source order, never timestamp order. Device/date changes create conservative
    # candidate boundaries, not proof of an official session or hardware identity.
    streams = defaultdict(list)
    for event in surviving.values():
        streams[_stream(event)].append(event)
    for stream in sorted(streams):
        chunk, prior = [], None
        for event in sorted(streams[stream], key=lambda row: row["source_sequence"]):
            reading = _reading(event)
            context = (event.get("device_id_raw"), reading.date() if reading else None)
            if chunk and (context != prior or event["event_id"] in assigned):
                segments.append((chunk, {}))
                chunk = []
            if event["event_id"] not in assigned:
                chunk.append(event["event_id"])
            prior = context
        if chunk:
            segments.append((chunk, {}))
    tables = {table: [] for table in TABLES}
    sections = {row["section_id"]: row for row in document["context_tables"].get("section", [])}
    elections = {row["election_id"]: row for row in document["context_tables"].get("election", [])}
    packages_by_id = {
        row["package_id"]: row for row in document["context_tables"].get("source_package", [])
    }
    composition = {
        row["member_section_id"]: row["principal_section_id"]
        for row in document["context_tables"].get("section_composition", [])
    }
    devices, configurations, event_context = {}, {}, {}
    # Repeated hashes across original streams indicate possible histories. They
    # are neither merged nor classified as copies without a reviewed byte rule.
    hashes = defaultdict(set)
    for event in surviving.values():
        hashes[event["source_line_sha256"]].add(_stream(event))
    for ids, segment in sorted(
        segments,
        key=lambda pair: (_stream(events[pair[0][0]]), events[pair[0][0]]["source_sequence"]),
    ):
        sid = identity("operational-session-v1", [document["snapshot_id"], ids, segment])
        principal, election = segment.get("principal_section_id"), segment.get("election_id")
        if principal is not None and principal not in sections:
            raise ReconstructionError("Unknown principal section")
        if election is not None and election not in elections:
            raise ReconstructionError("Unknown election")
        if principal is not None and election != sections[principal]["election_id"]:
            raise ReconstructionError("Session section/election conflict")
        serial = segment.get("serial")
        if serial is not None and (
            not isinstance(serial, str) or not serial.isdecimal() or len(serial) > 32
        ):
            raise ReconstructionError("Serial must be bounded explicit numeric hardware evidence")
        did = identity("physical-device-v1", [serial]) if serial else None
        if did:
            devices[did] = _row(
                device_id=did, serial_raw=serial, hardware_model=None, identity_state="verified"
            )
        version, build = segment.get("software_version"), segment.get("software_build")
        for value in (version, build):
            if value is not None and (
                not isinstance(value, str)
                or len(value) > 80
                or not value.replace(".", "").replace("-", "").isalnum()
            ):
                raise ReconstructionError("Software identity must be a bounded version/build")
        cid = identity("software-configuration-v1", [version, build]) if version or build else None
        if cid:
            configurations[cid] = _row(
                configuration_id=cid,
                version_raw=version,
                build_raw=build,
                configuration_raw={"rule_id": segment["rule_id"]},
            )
        overlap = any(len(hashes[events[key]["source_line_sha256"]]) > 1 for key in ids)
        uncertainty = {
            "candidate_only": not bool(segment),
            "source_device_readings": sorted(
                {events[key].get("device_id_raw") for key in ids}, key=str
            ),
            "rule_id": segment.get("rule_id"),
            "start_reason": segment.get("start_reason", "unknown"),
            "end_reason": segment.get("end_reason", "unknown"),
            "possible_copied_history": overlap and segment.get("distinct_history") is not True,
            "official_context_is_reviewed_assertion": bool(segment),
        }
        kind = segment.get("session_kind", "unresolved")
        selected = kind == "official_vota" and principal is not None and election is not None
        advertised_sections = {
            packages_by_id[asset["package_id"]]["section_id"]
            for key in ids
            for witness in originals[key]
            for asset in witness.get("package_assets", [])
            if asset["package_id"] in packages_by_id
        }
        package_conflict = principal is not None and any(
            composition.get(section, section) != principal for section in advertised_sections
        )
        uncertainty["advertised_section_conflict"] = package_conflict
        selected = selected and not package_conflict
        packages, states = set(), set()
        for sequence, key in enumerate(ids):
            event = events[key]
            reading = _reading(event)
            reason = "context_unresolved"
            belongs = (
                selected
                and reading is not None
                and reading.date().isoformat() == elections[election]["election_date"]
            )
            if selected:
                reason = "reviewed_official_context" if belongs else "other_date_or_unknown_clock"
            elif kind in {"setup", "training", "other"}:
                reason = f"excluded_{kind}"
            row = _row(
                event_id=key,
                session_id=sid,
                event_sequence=sequence,
                event_kind=event["event_kind"],
                selected=belongs,
                selection_reason=reason,
                device_time_raw=event.get("device_timestamp_raw"),
                timezone_rule=None,
                offset_seconds=None,
                clock_adjustment_seconds=None,
                normalized_at=None,
                clock_confidence="unresolved",
            )
            tables["selected_event"].append(row)
            states.add(belongs)
            event_context[key] = {"source": event, "witnesses": originals[key], "segment": segment}
            for witness in originals[key]:
                packages.update(asset["package_id"] for asset in witness.get("package_assets", []))
                for asset in witness.get("package_assets", []):
                    tables["record_lineage"].append(
                        _lineage(
                            "session_package",
                            [sid, asset["package_id"]],
                            witness,
                            "duplicate" if witness["event_id"] in aliases else "input",
                        )
                    )
                for table, derived in (("selected_event", key), ("voting_session", sid)):
                    tables["record_lineage"].append(
                        _lineage(
                            table,
                            derived,
                            witness,
                            "duplicate" if witness["event_id"] in aliases else "input",
                        )
                    )
                if did:
                    tables["record_lineage"].append(
                        _lineage("physical_device", did, witness, "input")
                    )
                if cid:
                    tables["record_lineage"].append(
                        _lineage("software_configuration", cid, witness, "input")
                    )
        tables["voting_session"].append(
            _row(
                session_id=sid,
                snapshot_id=document["snapshot_id"],
                principal_section_id=principal,
                device_id=did,
                configuration_id=cid,
                reconstruction_version=VERSION,
                session_kind=kind,
                target_selection_state="selected"
                if states == {True}
                else "excluded"
                if kind in {"setup", "training", "other"}
                else "unresolved",
                uncertainty=uncertainty,
            )
        )
        tables["session_package"].extend(
            {"session_id": sid, "package_id": package} for package in sorted(packages)
        )
    tables["physical_device"] = list(devices.values())
    tables["software_configuration"] = list(configurations.values())
    return {
        "tables": tables,
        "events": event_context,
        "aliases": aliases,
        "copy_rules": copy_rules,
        "evidence": evidence,
        "all_events": events,
    }


def _lineage(table, key, witness, role):
    return {
        "derived_table": table,
        "derived_key": canonical(key if isinstance(key, list) else [key]).decode(),
        "object_sha256": witness["object_sha256"],
        "record_locator": canonical(witness["record_locator"]).decode(),
        "transformation_version": VERSION,
        "observation_id": witness["observation_id"],
        "lineage_role": role,
    }


SEMANTIC_KINDS = {
    "authorization_attempt",
    "authorization_failed",
    "authorization_manual",
    "authorization_biometric",
    "authorization_other",
    "suspension_full",
    "suspension_partial",
    "resumption",
    "cancellation",
    "abandonment",
    "session_opening",
    "session_closing",
    "clock_change",
}


def reconstruct_cycles(bundle):
    """Explicit anonymous state machine; completion requires an active authorization.

    A request alone supplies neither authorization nor method. Repeated starts,
    orphan ends, unresolved intervening messages and partial histories stay rows.
    No event is associated with candidate choices, voter IDs or RDV order.
    """
    tables, context = bundle["tables"], bundle["events"]
    overrides = {}
    for rule in bundle["evidence"].get("semantics", []):
        if set(rule) - {"event_id", "kind", "rule_id", "review_state", "evidence"}:
            raise ReconstructionError("Unknown semantic evidence fields")
        reviewed = _claim(rule, bundle["all_events"])
        key, kind = rule["event_id"], rule["kind"]
        if key not in context or kind not in SEMANTIC_KINDS:
            raise ReconstructionError("Unknown semantic event/kind")
        parsed_kind = context[key]["source"]["event_kind"]
        if parsed_kind != "unknown" and not (
            parsed_kind == "authorization_message"
            and kind in {"authorization_manual", "authorization_biometric", "authorization_other"}
        ):
            raise ReconstructionError(
                "Reviewed semantics cannot contradict a decoded baseline class"
            )
        if key not in {anchor["event_id"] for anchor in rule["evidence"]}:
            raise ReconstructionError("Semantic rule must anchor its own original event")
        if key in overrides:
            raise ReconstructionError("Competing semantic rules")
        if reviewed:
            overrides[key] = rule
    sessions = defaultdict(list)
    for event in tables["selected_event"]:
        rule = overrides.get(event["event_id"])
        if rule:
            event["event_kind"] = rule["kind"]
        sessions[event["session_id"]].append(event)
    details = {}
    for sid, events in sessions.items():
        active, sequence = None, 0

        def begin(event, *, authorized=False, mode="unresolved"):
            return {
                "start": event,
                "events": [event],
                "authorized": authorized,
                "authorization_event_id": event["event_id"] if authorized else None,
                "mode": mode,
                "reasons": [],
                "suspended": False,
                "suspension_kind": None,
                "attempts": int(event["event_kind"] == "authorization_attempt"),
            }

        def finish(state, end=None, reason=None) -> None:
            nonlocal active, sequence
            if reason:
                active["reasons"].append(reason)
            ids = list(dict.fromkeys(e["event_id"] for e in active["events"]))
            cid = identity("anonymous-cycle-v1", [sid, sequence, ids])
            start = active["start"]
            uncertainty = {
                "reasons": active["reasons"],
                "suspension_kind": active["suspension_kind"],
                "authorization_evidenced": active["authorized"],
                "method_evidenced": active["mode"] != "unresolved",
                "selected": all(e["selected"] for e in active["events"]),
                "duration_state": "not_evaluated",
            }
            tables["anonymous_cycle"].append(
                _row(
                    cycle_id=cid,
                    session_id=sid,
                    cycle_sequence=sequence,
                    start_event_id=start["event_id"] if start else None,
                    end_event_id=end["event_id"] if end else None,
                    completion_state=state,
                    authorization_mode=active["mode"],
                    duration_seconds=None,
                    uncertainty=uncertainty,
                )
            )
            details[cid] = {
                "event_ids": ids,
                "attempt_events": active["attempts"],
                "authorization_event_id": active["authorization_event_id"],
                "authorization_evidenced": active["authorized"],
                "suspended": active["suspension_kind"] is not None,
            }
            for key in ids:
                tables["record_lineage"].extend(
                    _lineage(
                        "anonymous_cycle",
                        cid,
                        witness,
                        "duplicate" if witness["event_id"] in bundle["aliases"] else "input",
                    )
                    for witness in context[key]["witnesses"]
                )
            sequence += 1
            active = None

        previous_source_line = None
        for event in events:
            current_line = context[event["event_id"]]["source"]["record_locator"]["line_start"]
            if (
                active
                and previous_source_line is not None
                and current_line != previous_source_line + 1
            ):
                active["reasons"].append("missing_physical_source_lines")
            previous_source_line = current_line
            kind = event["event_kind"]
            if kind in {"session_opening", "session_closing", "clock_change"}:
                if active:
                    active["events"].append(event)
                    finish("unresolved", event, f"{kind}_during_cycle")
                continue
            if kind == "manual_request_message":
                if active is None:
                    active = begin(event)
                else:
                    active["events"].append(event)
                    active["reasons"].append("repeated_or_intervening_manual_request")
            elif kind == "authorization_attempt":
                if active is not None:
                    finish("unresolved", reason="superseded_by_attempt")
                active = begin(event)
            elif kind in {
                "authorization_message",
                "authorization_manual",
                "authorization_biometric",
                "authorization_other",
            }:
                mode = (
                    kind.removeprefix("authorization_")
                    if kind != "authorization_message"
                    else "unresolved"
                )
                if active and active["authorized"]:
                    finish("unresolved", reason="repeated_authorization")
                if active is None:
                    active = begin(event, authorized=True, mode=mode)
                else:
                    active["events"].append(event)
                    active["authorized"], active["mode"] = True, mode
                    active["authorization_event_id"] = event["event_id"]
            elif kind == "completion_message":
                if active is None:
                    active = begin(event)
                    active["start"] = None
                    finish("unresolved", event, "orphan_completion")
                else:
                    active["events"].append(event)
                    if not active["authorized"]:
                        finish("unresolved", event, "completion_without_authorization")
                    elif active["suspended"]:
                        finish("unresolved", event, "completion_while_suspended")
                    elif active["reasons"]:
                        finish("unresolved", event, "ambiguous_transition_history")
                    else:
                        finish("completed", event)
            elif kind in {
                "suspension_full",
                "suspension_partial",
                "cancellation",
                "abandonment",
                "authorization_failed",
            }:
                orphan = active is None
                if orphan:
                    active = begin(event)
                    active["start"] = None
                    active["reasons"].append("orphan_transition")
                else:
                    active["events"].append(event)
                if kind.startswith("suspension_"):
                    active["suspension_kind"] = kind.removeprefix("suspension_")
                    active["suspended"] = True
                if kind == "suspension_partial" and not orphan:
                    continue
                state = "suspended" if kind.startswith("suspension_") else "cancelled"
                finish("unresolved" if orphan else state, event, kind)
            elif kind == "resumption":
                if active and active["suspended"]:
                    active["events"].append(event)
                    active["suspended"] = False
                else:
                    if active:
                        finish("unresolved", reason="unexpected_resumption")
                    active = begin(event)
                    active["start"] = None
                    finish("unresolved", event, "orphan_resumption")
            elif active:
                active["events"].append(event)
                active["reasons"].append("unsupported_intervening_event")
        if active:
            finish(
                "suspended" if active["suspended"] else "unresolved",
                reason="partial_history_at_end",
            )
    bundle["cycle_evidence"], bundle["semantic_rules"] = details, overrides
    return bundle


def normalize_clocks(bundle, document):
    """Apply explicit section/election rules, never UF or early/late heuristics.

    A timezone-free reviewed continuity interval may support local durations.
    IANA ambiguous/nonexistent local readings remain unresolved. Corrections are
    stored independently of offsets and must be explicit in the reviewed rule.
    """
    rows = {row["event_id"]: row for row in bundle["tables"]["selected_event"]}
    sections = {row["section_id"]: row for row in document["context_tables"].get("section", [])}
    clocks = {}
    for rule in bundle["evidence"].get("clocks", []):
        if set(rule) - {
            "event_ids",
            "rule_id",
            "review_state",
            "evidence",
            "section_id",
            "election_id",
            "timezone",
            "clock_adjustment_seconds",
            "continuity",
        }:
            raise ReconstructionError("Unknown clock evidence fields")
        reviewed = _claim(rule, bundle["all_events"])
        ids = rule["event_ids"]
        _contiguous(ids, {key: value["source"] for key, value in bundle["events"].items()})
        if not {anchor["event_id"] for anchor in rule["evidence"]} <= set(ids):
            raise ReconstructionError("Clock evidence must anchor its own interval")
        section = sections.get(rule.get("section_id"))
        if section is None or section["election_id"] != rule.get("election_id"):
            raise ReconstructionError("Clock rule requires exact frozen section/election context")
        if any(
            bundle["events"][key]["segment"].get("principal_section_id") != rule["section_id"]
            for key in ids
        ):
            raise ReconstructionError("Clock geography conflicts with session evidence")
        correction = rule.get("clock_adjustment_seconds", 0)
        if type(correction) is not int or abs(correction) > 86400 * 366:
            raise ReconstructionError("Clock correction must be explicit bounded integer seconds")
        if rule.get("continuity") not in {"verified", "unknown"}:
            raise ReconstructionError("Clock continuity must be verified or unknown")
        zone_name = rule.get("timezone")
        if zone_name is not None and (not isinstance(zone_name, str) or len(zone_name) > 80):
            raise ReconstructionError("Invalid timezone rule")
        try:
            zone = ZoneInfo(zone_name) if zone_name else None
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ReconstructionError("Unknown evidenced IANA timezone") from exc
        for key in ids:
            if key in clocks:
                raise ReconstructionError("Overlapping clock evidence intervals")
            if not reviewed:
                continue
            event = rows[key]
            reading = _reading(bundle["events"][key]["source"])
            adjusted = reading + timedelta(seconds=correction) if reading else None
            event["timezone_rule"] = rule["rule_id"] if zone else None
            event["clock_adjustment_seconds"] = correction
            event["clock_confidence"] = (
                "bounded" if rule["continuity"] == "verified" else "unresolved"
            )
            state = "timezone_unresolved"
            if adjusted and zone:
                local = adjusted.replace(tzinfo=zone)
                alternate = adjusted.replace(tzinfo=zone, fold=1)
                valid = local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == adjusted
                if valid and local.utcoffset() == alternate.utcoffset():
                    event["normalized_at"] = local.astimezone(UTC).isoformat()
                    event["offset_seconds"] = int(local.utcoffset().total_seconds())
                    event["clock_confidence"] = "verified"
                    state = "converted"
                else:
                    state = "ambiguous_or_nonexistent_local_time"
            clocks[key] = {
                "rule_id": rule["rule_id"],
                "continuity": rule["continuity"],
                "interval_id": identity("clock-interval-v1", rule),
                "adjusted": adjusted.isoformat() if adjusted else None,
                "state": state,
                "evidence": rule["evidence"],
            }
            event["field_states"] = {
                field: "unresolved" for field, value in event.items() if value is None
            }
    # Record reversals in original source order even when corrected UTC readings
    # are monotonic. A correction is not hidden by sorting the observations.
    sessions = defaultdict(list)
    for row in rows.values():
        sessions[row["session_id"]].append(row)
    reversals = {}
    for sid, events in sessions.items():
        pairs = []
        for previous, current in zip(events, events[1:]):
            a, b = (
                _reading(bundle["events"][previous["event_id"]]["source"]),
                _reading(bundle["events"][current["event_id"]]["source"]),
            )
            if a and b and b < a:
                pairs.append([previous["event_id"], current["event_id"]])
        reversals[sid] = pairs
        for session in bundle["tables"]["voting_session"]:
            if session["session_id"] == sid:
                session["uncertainty"]["clock_reversals"] = pairs
    bundle["clock_evidence"], bundle["clock_reversals"] = clocks, reversals
    return bundle


def elapsed_seconds(bundle, event_ids):
    """Return elapsed/state only for one reviewed continuous interval and source order."""
    clocks = bundle.get("clock_evidence", {})
    if len(event_ids) < 2 or any(key not in clocks for key in event_ids):
        return None, "continuity_unresolved"
    rules = [clocks[key] for key in event_ids]
    if len({rule["interval_id"] for rule in rules}) != 1 or any(
        rule["continuity"] != "verified" for rule in rules
    ):
        return None, "clock_rule_change_or_unknown_continuity"
    if any(rule["adjusted"] is None for rule in rules):
        return None, "missing_clock"
    if any(rule["state"] == "ambiguous_or_nonexistent_local_time" for rule in rules):
        return None, "ambiguous_local_time"
    readings = [datetime.fromisoformat(rule["adjusted"]) for rule in rules]
    if any(b < a for a, b in zip(readings, readings[1:])):
        return None, "clock_reversal"
    if any(
        bundle["events"][key]["source"]["event_kind"] == "unknown"
        and key not in bundle.get("semantic_rules", {})
        for key in event_ids
    ):
        return None, "unresolved_intervening_event"
    if any(
        bundle.get("semantic_rules", {}).get(key, {}).get("kind") == "clock_change"
        for key in event_ids
    ):
        return None, "clock_change"
    return (readings[-1] - readings[0]).total_seconds(), "local_continuity_verified"


def summarize_operations(bundle):
    """Calculate evidenced durations/gaps and explicit operational denominators.

    Observed diagnostics remain available for unresolved sessions; eligible target
    counts are null when official context or copied-history resolution is missing.
    Exposure additionally needs opening/closing and resolved interruption clocks.
    """
    tables = bundle["tables"]
    by_session, cycles_by_session = defaultdict(list), defaultdict(list)
    for event in tables["selected_event"]:
        by_session[event["session_id"]].append(event)
    for cycle in tables["anonymous_cycle"]:
        cycles_by_session[cycle["session_id"]].append(cycle)
    summaries, gaps, interruptions = [], [], []
    for session in tables["voting_session"]:
        sid = session["session_id"]
        events, cycles = by_session[sid], cycles_by_session[sid]
        positions = {event["event_id"]: index for index, event in enumerate(events)}
        event_ids = [event["event_id"] for event in events]
        blockers = []
        if session["target_selection_state"] != "selected":
            blockers.append("official_target_context_unresolved_or_excluded")
        if session["uncertainty"]["possible_copied_history"]:
            blockers.append("unresolved_cross_stream_overlap")
        unknown_events = sum(event["event_kind"] == "unknown" for event in events)
        if unknown_events:
            blockers.append("unsupported_operational_events")
        if tables["parsing_issue"]:
            blockers.append("structural_parse_issues_in_shard")
        eligible = not blockers
        durations, auth_latencies = [], []
        for cycle in cycles:
            details = bundle["cycle_evidence"][cycle["cycle_id"]]
            auth = details["authorization_event_id"]
            state, duration = "not_completed", None
            if cycle["completion_state"] == "completed" and auth and cycle["end_event_id"]:
                ids = event_ids[positions[auth] : positions[cycle["end_event_id"]] + 1]
                duration, state = elapsed_seconds(bundle, ids)
                if details["suspended"]:
                    duration, state = None, "interrupted_cycle"
            cycle["duration_seconds"] = duration
            cycle["uncertainty"]["duration_state"] = state
            cycle["field_states"] = {
                key: "unresolved" for key, value in cycle.items() if value is None
            }
            if duration is not None and eligible and cycle["uncertainty"]["selected"]:
                durations.append(duration)
            if auth and cycle["start_event_id"] != auth and cycle["start_event_id"]:
                latency, latency_state = elapsed_seconds(
                    bundle, event_ids[positions[cycle["start_event_id"]] : positions[auth] + 1]
                )
                if eligible and latency is not None:
                    auth_latencies.append(latency)
                details["authorization_latency_seconds"] = latency
                details["authorization_latency_state"] = latency_state
        for previous, current in zip(cycles, cycles[1:]):
            a, b = (
                previous["end_event_id"],
                bundle["cycle_evidence"][current["cycle_id"]]["authorization_event_id"],
            )
            seconds, state = None, "adjacent_cycle_ineligible"
            if (
                eligible
                and previous["completion_state"] == current["completion_state"] == "completed"
                and a
                and b
            ):
                seconds, state = elapsed_seconds(bundle, event_ids[positions[a] : positions[b] + 1])
            gaps.append(
                {
                    "session_id": sid,
                    "previous_cycle_id": previous["cycle_id"],
                    "next_cycle_id": current["cycle_id"],
                    "gap_seconds": seconds,
                    "state": state,
                }
            )
        pending, interruption_unknown, interruption_seconds = None, False, []
        for index, event in enumerate(events):
            if event["event_kind"] in {"suspension_full", "suspension_partial"}:
                if pending is not None:
                    interruption_unknown = True
                    interruptions.append(
                        {
                            "session_id": sid,
                            "start_event_id": events[pending]["event_id"],
                            "end_event_id": None,
                            "seconds": None,
                            "state": "superseded_suspension",
                        }
                    )
                pending = index
            elif event["event_kind"] == "resumption":
                if pending is None:
                    interruption_unknown = True
                    interruptions.append(
                        {
                            "session_id": sid,
                            "start_event_id": None,
                            "end_event_id": event["event_id"],
                            "seconds": None,
                            "state": "orphan_resumption",
                        }
                    )
                else:
                    seconds, state = elapsed_seconds(bundle, event_ids[pending : index + 1])
                    interruptions.append(
                        {
                            "session_id": sid,
                            "start_event_id": events[pending]["event_id"],
                            "end_event_id": event["event_id"],
                            "seconds": seconds,
                            "state": state,
                        }
                    )
                    interruption_unknown |= seconds is None
                    if seconds is not None:
                        interruption_seconds.append(seconds)
                    pending = None
        if pending is not None:
            interruption_unknown = True
            interruptions.append(
                {
                    "session_id": sid,
                    "start_event_id": events[pending]["event_id"],
                    "end_event_id": None,
                    "seconds": None,
                    "state": "unclosed_suspension",
                }
            )
        span, span_state = elapsed_seconds(bundle, event_ids)
        openings = [
            event["event_id"] for event in events if event["event_kind"] == "session_opening"
        ]
        closings = [
            event["event_id"] for event in events if event["event_kind"] == "session_closing"
        ]
        complete_boundaries = (
            len(openings) == len(closings) == 1
            and openings[0] == event_ids[0]
            and closings[0] == event_ids[-1]
        )
        exposure = (
            span - sum(interruption_seconds)
            if eligible and complete_boundaries and span is not None and not interruption_unknown
            else None
        )
        completed = [cycle for cycle in cycles if cycle["completion_state"] == "completed"]
        known_method = [cycle for cycle in completed if cycle["authorization_mode"] != "unresolved"]
        manual = sum(cycle["authorization_mode"] == "manual" for cycle in known_method)
        attempts = sum(
            bundle["cycle_evidence"][cycle["cycle_id"]]["attempt_events"] for cycle in cycles
        )
        failed_attempts = sum(
            bundle["cycle_evidence"][cycle["cycle_id"]]["attempt_events"] > 0
            and "authorization_failed" in cycle["uncertainty"]["reasons"]
            for cycle in cycles
        )
        valid_gaps = [
            gap["gap_seconds"]
            for gap in gaps
            if gap["session_id"] == sid and gap["gap_seconds"] is not None
        ]
        summaries.append(
            {
                "session_id": sid,
                "readiness": "partial" if blockers else "ready",
                "blockers": blockers,
                "observed_events": len(events),
                "unknown_events": unknown_events,
                "observed_cycles_by_state": {
                    state: sum(c["completion_state"] == state for c in cycles)
                    for state in ("completed", "suspended", "cancelled", "unresolved")
                },
                "eligible_completed_cycles": len(completed) if eligible else None,
                "completed_method_known_denominator": len(known_method) if eligible else None,
                "completed_method_unknown": len(completed) - len(known_method),
                "known_completed_manual_cycles": manual if eligible else None,
                "completed_manual_cycles": manual
                if eligible and len(known_method) == len(completed)
                else None,
                "manual_share_known_method": manual / len(known_method)
                if eligible and known_method
                else None,
                "manual_request_events": sum(
                    event["event_kind"] == "manual_request_message" for event in events
                ),
                "explicit_attempt_denominator": attempts,
                "known_attempt_failures": failed_attempts,
                "authorization_failure_events": sum(
                    event["event_kind"] == "authorization_failed" for event in events
                ),
                "known_attempt_failure_rate": failed_attempts / attempts if attempts else None,
                "attempt_population_state": "partial_observed_explicit_attempts",
                "duration_readiness": "ready"
                if eligible and len(durations) == len(completed) and completed
                else "partial"
                if durations
                else "unavailable",
                "manual_share_readiness": "ready"
                if eligible and known_method and len(known_method) == len(completed)
                else "partial"
                if eligible and known_method
                else "unavailable",
                "exposure_readiness": "ready" if exposure is not None else "unavailable",
                "duration_eligible_denominator": len(durations),
                "duration_seconds": durations,
                "adjacent_cycle_pair_denominator": max(0, len(cycles) - 1),
                "gap_eligible_denominator": len(valid_gaps),
                "gap_seconds": valid_gaps,
                "authorization_latency_eligible_denominator": len(auth_latencies),
                "authorization_latency_seconds": auth_latencies,
                "observed_span_seconds": span,
                "observed_span_state": span_state,
                "exposure_seconds": exposure,
                "exposure_state": "verified_boundaries_and_continuity"
                if exposure is not None
                else "unknown_boundaries_interruptions_or_clock",
                "completed_per_exposure_second": len(completed) / exposure
                if exposure and eligible
                else None,
                "opening_event_ids": openings,
                "closing_event_ids": closings,
                "interruption_count": sum(
                    event["event_kind"] in {"suspension_full", "suspension_partial"}
                    for event in events
                ),
                "interruption_duration_eligible_denominator": len(interruption_seconds),
                "interruption_seconds": interruption_seconds,
                "restart_boundary_count": int(session["uncertainty"]["start_reason"] == "restart"),
                "replacement_boundary_count": int(
                    session["uncertainty"]["start_reason"] == "replacement"
                ),
            }
        )
    bundle["session_summaries"], bundle["cycle_gaps"], bundle["interruptions"] = (
        summaries,
        gaps,
        interruptions,
    )
    return bundle


ARTIFACT_FORMAT = "election-audit-reconstruction-v1"
EXTRA_TABLES = ("event_evidence", "session_summaries", "cycle_gaps", "interruptions")


def _evidence_rows(bundle):
    for key, source in bundle["all_events"].items():
        target = bundle["aliases"].get(key, key)
        yield {
            "event_id": key,
            "canonical_event_id": target,
            "object_sha256": source["object_sha256"],
            "record_locator": source["record_locator"],
            "source_sequence": source["source_sequence"],
            "source_line_sha256": source["source_line_sha256"],
            "device_id_raw": source.get("device_id_raw"),
            "application": source.get("application"),
            "device_time_raw": source.get("device_timestamp_raw"),
            "parsed_event_kind": source["event_kind"],
            "copy_rule": bundle["copy_rules"].get(key),
            "semantic_rule": bundle.get("semantic_rules", {}).get(key),
            "clock": bundle.get("clock_evidence", {}).get(key),
            "observation_ids": sorted(
                {
                    w["observation_id"]
                    for w in bundle["events"][target]["witnesses"]
                    if w["event_id"] == key
                }
            ),
        }


def reconstruct_parse(
    parse, store, *, evidence=None, object_sha256=None, max_events=1_000_000, reader=None
):
    """Publish one immutable bounded reconstruction shard without raw input access.

    object_sha256 selects a content group (including all its publisher witnesses).
    Include replacement/copied histories in the same group. Independent shards
    retain stable session/cycle IDs but cannot resolve cross-shard overlaps.
    """
    parse, store = Path(parse).resolve(), Path(store).resolve()
    if parse.name == "parse.json":
        parse = parse.parent
    if store.is_relative_to(parse.parent) or store.is_relative_to(parse.parent.parent / "cache"):
        raise ReconstructionError("Reconstruction store must be outside parse publications/cache")
    if any(
        (ancestor / "manifest-location.json").exists()
        or (ancestor / "manifest.sqlite").exists()
        or (ancestor / "snapshot.json").exists()
        for ancestor in (store, *store.parents)
    ):
        raise ReconstructionError("Reconstruction store must be outside acquisition/snapshot roots")
    selected = None if object_sha256 is None else sorted(set(object_sha256))
    if selected == []:
        raise ReconstructionError("Object shard selection cannot be empty")
    reader = reader or FrozenParseReader(parse)
    if reader.path != parse:
        raise ReconstructionError("Reader/input parse mismatch")
    document = reader.document
    selected = (
        selected
        if selected is not None
        else sorted(item["object_sha256"] for item in document["artifacts"])
    )
    witnesses, parsing_issues = reader.group(selected)
    bundle = reconstruct_sessions(
        document,
        witnesses,
        evidence=evidence,
        max_events=max_events,
    )
    reconstruct_cycles(bundle)
    normalize_clocks(bundle, document)
    bundle["tables"]["parsing_issue"] = list(parsing_issues)
    summarize_operations(bundle)
    # Duplicate witnesses of an identical URL/record do not duplicate lineage PKs.
    lineage = bundle["tables"]["record_lineage"]
    bundle["tables"]["record_lineage"] = list({canonical(row): row for row in lineage}.values())
    for name in TABLES:
        errors = validate_rows(name, bundle["tables"][name])
        if errors:
            raise ReconstructionError("; ".join(errors[:10]))
    parent = store / "reconstructions"
    parent.mkdir(parents=True, exist_ok=True)
    if not hasattr(reader, "reconstruction_contexts"):
        reader.reconstruction_contexts = {}
    context = reader.reconstruction_contexts.get(str(store))
    if context is None:
        context = _publish_context(store, parse.name, document)
        reader.reconstruction_contexts[str(store)] = context
    with (parent / ".publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        temporary = Path(tempfile.mkdtemp(prefix=".reconstruction-building-", dir=parent))
        try:
            streams = {
                **bundle["tables"],
                **{name: bundle[name] for name in EXTRA_TABLES if name != "event_evidence"},
                "event_evidence": _evidence_rows(bundle),
            }
            files = {}
            for name, rows in streams.items():
                count = 0
                with (temporary / f"{name}.jsonl").open("xb") as output:
                    for row in rows:
                        output.write(canonical(row) + b"\n")
                        count += 1
                    output.flush()
                    os.fsync(output.fileno())
                sha, length = hash_file(temporary / f"{name}.jsonl")
                files[f"{name}.jsonl"] = {"sha256": sha, "byte_length": length, "rows": count}
            publication = {
                "format_version": ARTIFACT_FORMAT,
                "reconstruction_version": VERSION,
                "input_parse_id": parse.name,
                "snapshot_id": document["snapshot_id"],
                "input_context": {"locator": f"../../contexts/{parse.name}", "sha256": context},
                "evidence": bundle["evidence"],
                "object_sha256": selected,
                "max_events": max_events,
                "overlap_resolution_scope": "selected_object_group_only",
                "counts_are_reconstructed_cycles_not_reconciled_votes": True,
                "files": files,
            }
            target = parent / digest(publication)
            if target.exists():
                if inspect_reconstruction(target) != publication:
                    raise ReconstructionError("Existing reconstruction identity mismatch")
                shutil.rmtree(temporary)
                return target
            _write_checked(temporary, "reconstruction.json", publication)
            _fsync_directory(temporary)
            temporary.rename(target)
            _fsync_directory(parent)
            return target
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise


def inspect_reconstruction(path):
    """Verify standalone immutable metadata and every row file; raw/parses unnecessary."""
    path = Path(path)
    publication = _read_checked(path, "reconstruction.json")
    if publication.get("format_version") != ARTIFACT_FORMAT or digest(publication) != path.name:
        raise ReconstructionError("Invalid reconstruction identity")
    load_reconstruction_context(path, publication=publication)
    expected = {f"{name}.jsonl" for name in (*TABLES, *EXTRA_TABLES)}
    if set(publication.get("files", {})) != expected:
        raise ReconstructionError("Invalid reconstruction row-file manifest")
    for name, spec in publication["files"].items():
        try:
            sha, length = hash_file(path / name)
        except OSError as exc:
            raise ReconstructionError("Missing reconstruction rows") from exc
        if (sha, length) != (spec["sha256"], spec["byte_length"]):
            raise ReconstructionError("Reconstruction rows checksum mismatch")
    return publication


def _publish_context(store, parse_id, document):
    """Persist full population metadata once per store, shared by all shards."""
    parent = store / "contexts"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / parse_id
    with (parent / ".context.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not target.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".context-building-", dir=parent))
            try:
                _write_checked(temporary, "parse.json", document)
                _fsync_directory(temporary)
                temporary.rename(target)
                _fsync_directory(parent)
            except BaseException:
                if temporary.exists():
                    shutil.rmtree(temporary)
                raise
        loaded = _read_checked(target, "parse.json")
        if digest(loaded) != parse_id:
            raise ReconstructionError("Shared context identity mismatch")
        return hash_file(target / "parse.json")[0]


def load_reconstruction_context(path, *, publication=None):
    """Load/check shared full population metadata; relocate the whole store together."""
    path = Path(path)
    publication = publication or _read_checked(path, "reconstruction.json")
    parse_id = publication["input_parse_id"]
    if len(parse_id) != 64 or any(c not in "0123456789abcdef" for c in parse_id):
        raise ReconstructionError("Invalid shared parse identity")
    reference = publication["input_context"]
    if reference["locator"] != f"../../contexts/{parse_id}":
        raise ReconstructionError("Invalid shared context locator")
    context_path = path.parent.parent / "contexts" / parse_id
    document = _read_checked(context_path, "parse.json")
    if (
        digest(document) != parse_id
        or hash_file(context_path / "parse.json")[0] != reference["sha256"]
    ):
        raise ReconstructionError("Shared context digest mismatch")
    return document


def iter_reconstruction_rows(path, table):
    """Stream contract rows or explicit intermediate summaries/evidence after verification."""
    if table not in (*TABLES, *EXTRA_TABLES):
        raise ReconstructionError("Unknown reconstruction table")
    inspect_reconstruction(path)
    yield from _rows(Path(path) / f"{table}.jsonl")


def reconstruction_main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parse", type=Path)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--evidence", type=Path, help="Reviewed/unverified original-event evidence JSON"
    )
    parser.add_argument(
        "--object-sha256", action="append", help="Repeat for a bounded related content group"
    )
    parser.add_argument("--max-events", type=int, default=1_000_000)
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(args.evidence.read_text()) if args.evidence else None
        print(
            reconstruct_parse(
                args.parse,
                args.store,
                evidence=evidence,
                object_sha256=args.object_sha256,
                max_events=args.max_events,
            )
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0
