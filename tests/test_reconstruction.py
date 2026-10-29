"""Synthetic operational sequences; no raw acquisition or real voter data."""

import copy
import hashlib
import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_archive_parsing import archive_bytes, log_line
from test_snapshots import SourceFixture

from election_audit.archive_parsing import FrozenParseReader, iter_event_witnesses, parse_snapshot
from election_audit.cli import main
from election_audit.contracts import validate_rows
from election_audit.reconstruction import (
    EVIDENCE_VERSION,
    ReconstructionError,
    elapsed_seconds,
    inspect_reconstruction,
    iter_reconstruction_rows,
    load_reconstruction_context,
    normalize_clocks,
    reconstruct_cycles,
    reconstruct_parse,
    reconstruct_sessions,
    summarize_operations,
)
from election_audit.snapshots import create_snapshot
from election_audit.source_inventory import identity


def event(
    line,
    kind="authorization_message",
    *,
    member="logd.dat",
    source="a",
    time="08:00:00",
    date="25/10/2026",
    device="1234",
    physical=None,
    observation="obs",
    package="pkg",
):
    sha = hashlib.sha256(source.encode()).hexdigest()
    raw = physical or f"{date} {time}\tINFO\t{device}\tVOTA\t{kind}\t\n"
    return {
        "event_id": identity("fixture", [sha, member, line]),
        "object_sha256": sha,
        "record_locator": {
            "archive_segments": [{"member_name": member, "occurrence": 0, "directory_index": 0}],
            "line_start": line,
            "line_end": line,
            "byte_start": None,
            "byte_end": None,
        },
        "source_sequence": line,
        "source_line_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "device_timestamp_raw": f"{date} {time}",
        "device_id_raw": device,
        "application": "VOTA",
        "event_kind": kind,
        "observation_id": observation,
        "package_assets": [{"package_id": package}],
    }


def document():
    return {
        "snapshot_id": "snap",
        "context_tables": {
            "section": [{"section_id": "section", "election_id": "runoff"}],
            "election": [{"election_id": "runoff", "election_date": "2026-10-25"}],
        },
    }


def claim(events, **values):
    return {
        "rule_id": "fixture-reviewed-v1",
        "review_state": "reviewed",
        "evidence": [
            {"event_id": e["event_id"], "source_line_sha256": e["source_line_sha256"]}
            for e in events
        ],
        **values,
    }


def evidence(**values):
    return {"version": EVIDENCE_VERSION, **values}


def official(events, **values):
    return claim(
        events,
        event_ids=[e["event_id"] for e in events],
        session_kind="official_vota",
        principal_section_id="section",
        election_id="runoff",
        **values,
    )


class SessionTests(unittest.TestCase):
    def test_identical_content_packages_do_not_multiply_sessions_events(self):
        first = event(1)
        second = {**first, "observation_id": "obs2", "package_assets": [{"package_id": "pkg2"}]}
        result = reconstruct_sessions(document(), [first, second])
        self.assertEqual(len(result["tables"]["voting_session"]), 1)
        self.assertEqual(len(result["tables"]["selected_event"]), 1)
        self.assertEqual(len(result["tables"]["session_package"]), 2)
        self.assertEqual(len(result["tables"]["record_lineage"]), 6)
        self.assertFalse(result["tables"]["selected_event"][0]["selected"])
        self.assertEqual(result["tables"]["physical_device"], [])

    def test_replacement_devices_and_source_order_mixed_round(self):
        first = [event(1, date="04/10/2026"), event(2, time="08:01:00")]
        replacement = [event(3, device="5678"), event(4, device="5678", time="08:00:30")]
        rules = evidence(
            segments=[
                official(first, serial="1234", end_reason="replacement"),
                official(replacement, serial="5678", start_reason="replacement"),
            ]
        )
        result = reconstruct_sessions(document(), first + replacement, evidence=rules)
        self.assertEqual(len(result["tables"]["voting_session"]), 2)
        self.assertEqual(len(result["tables"]["physical_device"]), 2)
        self.assertEqual(
            [e["selected"] for e in result["tables"]["selected_event"]], [False, True, True, True]
        )
        self.assertEqual(
            [e["event_id"] for e in result["tables"]["selected_event"]],
            [e["event_id"] for e in first + replacement],
        )

    def test_copy_requires_exact_bytes_and_keeps_duplicate_lineage(self):
        first = [event(1), event(2, "completion_message", time="08:01:00")]
        copied = [event(1, source="b"), event(2, "completion_message", source="b", time="08:01:00")]
        rule = claim(
            first + copied,
            canonical_event_ids=[e["event_id"] for e in first],
            copied_event_ids=[e["event_id"] for e in copied],
        )
        result = reconstruct_sessions(document(), first + copied, evidence=evidence(copies=[rule]))
        self.assertEqual(len(result["tables"]["selected_event"]), 2)
        self.assertEqual(len(result["tables"]["voting_session"]), 1)
        self.assertEqual(
            sum(row["lineage_role"] == "duplicate" for row in result["tables"]["record_lineage"]), 6
        )
        reconstruct_cycles(result)
        self.assertEqual(len(result["tables"]["anonymous_cycle"]), 1)
        self.assertEqual(result["tables"]["anonymous_cycle"][0]["completion_state"], "completed")
        changed = copy.deepcopy(copied)
        changed[1]["source_line_sha256"] = "0" * 64
        rule = claim(
            first + changed,
            canonical_event_ids=[e["event_id"] for e in first],
            copied_event_ids=[e["event_id"] for e in changed],
        )
        with self.assertRaises(ReconstructionError):
            reconstruct_sessions(document(), first + changed, evidence=evidence(copies=[rule]))

    def test_repeated_same_second_preserved_and_ambiguous_overlap_visible(self):
        repeated = [event(1), event(2)]
        other = event(1, source="b")
        result = reconstruct_sessions(document(), repeated + [other])
        self.assertEqual(len(result["tables"]["selected_event"]), 3)
        self.assertEqual(len(result["tables"]["voting_session"]), 2)
        self.assertTrue(
            all(
                row["uncertainty"]["possible_copied_history"]
                for row in result["tables"]["voting_session"]
            )
        )

    def test_unverified_claim_does_not_select_and_bad_anchor_rejected(self):
        source = [event(1)]
        rule = official(source)
        rule["review_state"] = "unverified"
        result = reconstruct_sessions(document(), source, evidence=evidence(segments=[rule]))
        self.assertEqual(result["tables"]["voting_session"][0]["session_kind"], "unresolved")
        rule["evidence"][0]["source_line_sha256"] = "0" * 64
        with self.assertRaises(ReconstructionError):
            reconstruct_sessions(document(), source, evidence=evidence(segments=[rule]))

    def test_candidate_date_device_boundaries_limits_and_contracts(self):
        source = [event(1), event(2, date="04/10/2026"), event(3, date="04/10/2026", device=None)]
        result = reconstruct_sessions(document(), source)
        self.assertEqual(len(result["tables"]["voting_session"]), 3)
        for name, rows in result["tables"].items():
            self.assertEqual(validate_rows(name, rows), [], name)
        with self.assertRaises(ReconstructionError):
            reconstruct_sessions(document(), source, max_events=2)


class CycleTests(unittest.TestCase):
    def cycles(self, source, rules=None):
        return reconstruct_cycles(
            reconstruct_sessions(document(), source, evidence=evidence(semantics=rules or []))
        )

    def semantic(self, source, kind):
        return claim([source], event_id=source["event_id"], kind=kind)

    def test_baseline_and_repeated_authorizations_completion_orphans(self):
        source = [
            event(1),
            event(2),
            event(3, "completion_message"),
            event(4, "completion_message"),
        ]
        result = self.cycles(source)
        cycles = result["tables"]["anonymous_cycle"]
        self.assertEqual(
            [row["completion_state"] for row in cycles], ["unresolved", "completed", "unresolved"]
        )
        self.assertEqual(cycles[1]["authorization_mode"], "unresolved")
        self.assertIsNone(cycles[2]["start_event_id"])
        self.assertEqual(validate_rows("anonymous_cycle", cycles), [])

    def test_manual_request_completion_is_not_completed_manual_vote(self):
        source = [event(1, "manual_request_message"), event(2, "completion_message")]
        cycles = self.cycles(source)["tables"]["anonymous_cycle"]
        self.assertEqual(cycles[0]["completion_state"], "unresolved")
        self.assertEqual(cycles[0]["authorization_mode"], "unresolved")

    def test_request_then_authorization_still_unknown_method(self):
        source = [event(1, "manual_request_message"), event(2), event(3, "completion_message")]
        cycles = self.cycles(source)["tables"]["anonymous_cycle"]
        self.assertEqual(cycles[0]["completion_state"], "completed")
        self.assertEqual(cycles[0]["authorization_mode"], "unresolved")

    def test_manual_cancel_abandonment_full_and_partial_suspensions(self):
        kinds = [
            "manual_request_message",
            "unknown",
            "authorization_message",
            "unknown",
            "authorization_message",
            "unknown",
            "unknown",
            "completion_message",
            "authorization_message",
            "unknown",
        ]
        source = [event(i + 1, kind) for i, kind in enumerate(kinds)]
        rules = [
            self.semantic(source[index], kind)
            for index, kind in [
                (1, "cancellation"),
                (3, "suspension_full"),
                (5, "suspension_partial"),
                (6, "resumption"),
                (9, "abandonment"),
            ]
        ]
        cycles = self.cycles(source, rules)["tables"]["anonymous_cycle"]
        self.assertEqual(
            [c["completion_state"] for c in cycles],
            ["cancelled", "suspended", "completed", "cancelled"],
        )
        self.assertEqual(cycles[2]["uncertainty"]["suspension_kind"], "partial")

    def test_only_explicit_method_and_success_make_completed_manual_cycle(self):
        source = [event(1, "manual_request_message"), event(2), event(3, "completion_message")]
        cycles = self.cycles(source, [self.semantic(source[1], "authorization_manual")])["tables"][
            "anonymous_cycle"
        ]
        self.assertEqual(
            (cycles[0]["completion_state"], cycles[0]["authorization_mode"]),
            ("completed", "manual"),
        )
        self.assertNotIn("candidate", str(cycles))

    def test_unknown_and_incomplete_history_not_silently_completed(self):
        source = [event(1), event(2, "unknown"), event(3, "completion_message"), event(4)]
        cycles = self.cycles(source)["tables"]["anonymous_cycle"]
        self.assertEqual([c["completion_state"] for c in cycles], ["unresolved", "unresolved"])
        self.assertIn("unsupported_intervening_event", cycles[0]["uncertainty"]["reasons"])


def clock_rule(source, **values):
    return claim(
        source,
        event_ids=[e["event_id"] for e in source],
        section_id="section",
        election_id="runoff",
        continuity="verified",
        **values,
    )


def timed_bundle(source, *, clock=None, semantics=None):
    rules = evidence(segments=[official(source)], clocks=clock or [], semantics=semantics or [])
    bundle = reconstruct_cycles(reconstruct_sessions(document(), source, evidence=rules))
    return normalize_clocks(bundle, document())


class ClockTests(unittest.TestCase):
    def test_unknown_timezone_stays_unknown_but_explicit_local_continuity_works(self):
        source = [event(1), event(2, "completion_message", time="08:01:00")]
        bundle = timed_bundle(source)
        self.assertEqual(
            elapsed_seconds(bundle, [e["event_id"] for e in source]),
            (None, "continuity_unresolved"),
        )
        bundle = timed_bundle(source, clock=[clock_rule(source, timezone=None)])
        rows = bundle["tables"]["selected_event"]
        self.assertTrue(all(row["normalized_at"] is None for row in rows))
        self.assertEqual(elapsed_seconds(bundle, [e["event_id"] for e in source])[0], 60)

    def test_explicit_zone_correction_and_geography(self):
        source = [event(1), event(2, "completion_message", time="08:01:00")]
        bundle = timed_bundle(
            source,
            clock=[clock_rule(source, timezone="America/Rio_Branco", clock_adjustment_seconds=30)],
        )
        row = bundle["tables"]["selected_event"][0]
        self.assertEqual(row["normalized_at"], "2026-10-25T13:00:30+00:00")
        self.assertEqual((row["offset_seconds"], row["clock_adjustment_seconds"]), (-18000, 30))
        self.assertEqual(validate_rows("selected_event", bundle["tables"]["selected_event"]), [])
        bad = clock_rule(source, timezone="UTC")
        bad["section_id"] = "unknown-municipality"
        with self.assertRaises(ReconstructionError):
            timed_bundle(source, clock=[bad])

    def test_reversal_and_rule_change_invalidate_duration(self):
        source = [event(1, time="08:01:00"), event(2, "completion_message", time="08:00:00")]
        bundle = timed_bundle(source, clock=[clock_rule(source, timezone=None)])
        self.assertEqual(
            elapsed_seconds(bundle, [e["event_id"] for e in source]), (None, "clock_reversal")
        )
        self.assertEqual(
            len(bundle["clock_reversals"][bundle["tables"]["voting_session"][0]["session_id"]]), 1
        )
        a, b = (
            clock_rule(source[:1], timezone="UTC"),
            clock_rule(source[1:], timezone="UTC", clock_adjustment_seconds=120),
        )
        b["rule_id"] = "clock-correction-v2"
        bundle = timed_bundle(source, clock=[a, b])
        self.assertEqual(
            elapsed_seconds(bundle, [e["event_id"] for e in source])[1],
            "clock_rule_change_or_unknown_continuity",
        )

    def test_overseas_explicit_zone_and_dst_ambiguity(self):
        source = [
            event(1, date="01/11/2026", time="01:10:00"),
            event(2, "completion_message", date="01/11/2026", time="01:11:00"),
        ]
        bundle = timed_bundle(source, clock=[clock_rule(source, timezone="America/New_York")])
        self.assertTrue(
            all(row["normalized_at"] is None for row in bundle["tables"]["selected_event"])
        )
        self.assertEqual(
            elapsed_seconds(bundle, [e["event_id"] for e in source])[1], "ambiguous_local_time"
        )


class SummaryTests(unittest.TestCase):
    def test_durations_gaps_and_method_denominators(self):
        source = [
            event(1),
            event(2, "completion_message", time="08:01:00"),
            event(3, time="08:02:00"),
            event(4, "completion_message", time="08:03:00"),
        ]
        result = summarize_operations(
            timed_bundle(
                source,
                clock=[clock_rule(source, timezone=None)],
                semantics=[
                    claim([source[2]], event_id=source[2]["event_id"], kind="authorization_manual")
                ],
            )
        )
        summary = result["session_summaries"][0]
        self.assertEqual(summary["eligible_completed_cycles"], 2)
        self.assertEqual(summary["duration_seconds"], [60, 60])
        self.assertEqual(summary["gap_seconds"], [60])
        self.assertEqual(
            (
                summary["completed_method_known_denominator"],
                summary["completed_method_unknown"],
                summary["known_completed_manual_cycles"],
            ),
            (1, 1, 1),
        )
        self.assertIsNone(summary["completed_manual_cycles"])
        self.assertIsNone(summary["exposure_seconds"])
        self.assertIsNone(summary["known_attempt_failure_rate"])

    def test_exposure_requires_boundaries_and_resolved_interruptions(self):
        kinds = [
            "unknown",
            "authorization_message",
            "completion_message",
            "unknown",
            "unknown",
            "unknown",
        ]
        source = [event(i + 1, kind, time=f"08:0{i}:00") for i, kind in enumerate(kinds)]
        semantics = [
            claim([source[i]], event_id=source[i]["event_id"], kind=kind)
            for i, kind in [
                (0, "session_opening"),
                (3, "suspension_full"),
                (4, "resumption"),
                (5, "session_closing"),
            ]
        ]
        result = summarize_operations(
            timed_bundle(source, clock=[clock_rule(source, timezone="UTC")], semantics=semantics)
        )
        summary = result["session_summaries"][0]
        self.assertEqual(summary["observed_span_seconds"], 300)
        self.assertEqual(summary["exposure_seconds"], 240)
        self.assertEqual(summary["interruption_seconds"], [60])

    def test_unknown_clocks_incomplete_and_partial_suspension_denominators(self):
        source = [
            event(1),
            event(2, "unknown", time="08:01:00"),
            event(3, "unknown", time="08:02:00"),
            event(4, "completion_message", time="08:03:00"),
        ]
        semantics = [
            claim([source[i]], event_id=source[i]["event_id"], kind=kind)
            for i, kind in [(1, "suspension_partial"), (2, "resumption")]
        ]
        result = summarize_operations(
            timed_bundle(source, clock=[clock_rule(source, timezone=None)], semantics=semantics)
        )
        self.assertEqual(result["tables"]["anonymous_cycle"][0]["completion_state"], "completed")
        self.assertEqual(
            result["tables"]["anonymous_cycle"][0]["uncertainty"]["duration_state"],
            "interrupted_cycle",
        )
        self.assertEqual(result["session_summaries"][0]["duration_eligible_denominator"], 0)


class PublicationTests(SourceFixture):
    def frozen_parse(self):
        self.record_section()
        self.advertise()
        self.save_index([{"ns": "0001"}])
        self.save(
            self.log_url,
            archive_bytes(
                [
                    (
                        "logd.dat",
                        log_line("Eleitor foi habilitado")
                        + log_line(timestamp="25/10/2026 08:01:00"),
                    )
                ]
            ),
        )
        base = Path(self.temporary.name)
        snapshot = create_snapshot(self.root, base / "snapshots", ["ac"])
        parsed = parse_snapshot(snapshot, base / "parsed")
        return base, snapshot, parsed

    def test_standalone_immutable_restart_safe_cli_and_contract_rows(self):
        base, snapshot, parsed = self.frozen_parse()
        path = reconstruct_parse(parsed, base / "operations")
        self.assertEqual(path, reconstruct_parse(parsed, base / "operations"))
        self.assertEqual(len(list(iter_reconstruction_rows(path, "anonymous_cycle"))), 1)
        for name in ("voting_session", "selected_event", "anonymous_cycle", "record_lineage"):
            self.assertEqual(validate_rows(name, list(iter_reconstruction_rows(path, name))), [])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(["reconstruct", str(parsed), "--store", str(base / "operations")]), 0
            )
        self.assertEqual(output.getvalue().strip(), str(path))
        shutil.rmtree(snapshot)
        shutil.rmtree(parsed.parent.parent)
        self.assertEqual(inspect_reconstruction(path)["input_parse_id"], parsed.name)
        self.assertEqual(
            load_reconstruction_context(path)["snapshot_id"],
            inspect_reconstruction(path)["snapshot_id"],
        )

    def test_shared_context_once_relocation_and_reused_parse_reader(self):
        base, _, parsed = self.frozen_parse()
        reader = FrozenParseReader(parsed)
        first = reconstruct_parse(parsed, base / "operations", reader=reader)
        with patch(
            "election_audit.reconstruction._publish_context",
            side_effect=AssertionError("must reuse context"),
        ):
            second = reconstruct_parse(parsed, base / "operations", max_events=100, reader=reader)
        self.assertNotEqual(first, second)
        self.assertNotIn("input_parse", inspect_reconstruction(first))
        self.assertEqual(len(list((base / "operations" / "contexts").glob("[0-9a-f]*"))), 1)
        moved = base / "relocated"
        shutil.move(base / "operations", moved)
        self.assertEqual(
            load_reconstruction_context(moved / "reconstructions" / first.name)["snapshot_id"],
            reader.document["snapshot_id"],
        )

    def test_shard_filter_and_corruption_rejected(self):
        base, _, parsed = self.frozen_parse()
        content = list(iter_event_witnesses(parsed))[0]["object_sha256"]
        path = reconstruct_parse(parsed, base / "operations", object_sha256=[content])
        self.assertEqual(inspect_reconstruction(path)["object_sha256"], [content])
        self.assertEqual(len(list(iter_event_witnesses(parsed, object_sha256=[]))), 0)
        (path / "selected_event.jsonl").write_text("broken")
        with self.assertRaises(ReconstructionError):
            inspect_reconstruction(path)

    def test_interruption_does_not_publish_partial_and_raw_store_rejected(self):
        base, snapshot, parsed = self.frozen_parse()
        with patch(
            "election_audit.reconstruction._write_checked",
            side_effect=OSError("fixture interruption"),
        ):
            with self.assertRaises(OSError):
                reconstruct_parse(parsed, base / "operations")
        self.assertEqual(list((base / "operations" / "reconstructions").glob("[0-9a-f]*")), [])
        path = reconstruct_parse(parsed, base / "operations")
        self.assertTrue(path.is_dir())
        with self.assertRaises(ReconstructionError):
            reconstruct_parse(parsed, self.root / "bad-output")
        with self.assertRaises(ReconstructionError):
            reconstruct_parse(parsed, snapshot / "bad-output")
