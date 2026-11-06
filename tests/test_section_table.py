import json
import unittest

from election_audit.section_table import (
    METHODS,
    PROFILE_COLUMNS,
    _chunks,
    _finish,
    _section_row,
    clock_state,
    close_rules,
    harmonize,
    section_operations,
)

CYCLES = [
    f"cycles_{s}_{m}"
    for s in ("completed", "suspended", "cancelled", "unresolved")
    for m in METHODS
]


def session(**values):
    base = {
        "uf": "ac",
        "municipality": "01392",
        "zone": "0009",
        "section": "0070",
        "object_sha256": "a" * 64,
        "stream_ordinal": 0,
        "session_ordinal": 0,
        "segment_ordinal": 1,
        "rank_in_segment": 1,
        "device_id": "02130889",
        "block_start": "b" * 64,
        "block_lines": 100,
        "start_reading": "2026-10-25T06:00:01",
        "end_reading": "2026-10-25T15:05:00",
        "closing_reading": "2026-10-25T15:02:00",
        "reading_backsteps": 0,
        "reading_backstep_max_s": None,
        "orphan_completions": 0,
        "manual_requests": 0,
        "authorization_failures": 0,
        "completed_interrupted": 0,
        "first_completion_reading": "2026-10-25T06:01:00",
        "last_completion_reading": "2026-10-25T14:59:00",
        "completions_by_reading_hour": [0] * 24,
        "completion_gap_max_s": 600,
        "model": "UE2020",
        "software_version": "10.23.0.0 - Praia da Barra do Cahy",
        "clock_adh_before": 0,
        "clock_adh_shift_s_before": 0,
        "clock_tz_shifts_before": 0,
        "clock_tz_shift_s_before": 0,
        "clock_dst_before": 0,
        "configured_close": None,
        **{c: 0 for c in CYCLES},
    }
    base.update(values)
    return base


class CopyTests(unittest.TestCase):
    def test_internal_and_external_copies_count_once(self):
        internal = session(stream_ordinal=0, block_lines=120, cycles_completed_biometric=10)
        external = session(stream_ordinal=1, block_lines=110, cycles_completed_biometric=9)
        ops = section_operations([internal, external])
        self.assertEqual(ops["official_sessions_raw"], 2)
        self.assertEqual(ops["official_sessions"], 1)
        self.assertEqual(ops["copies_removed"], 1)
        self.assertEqual(ops["copy_conflicts"], 0)
        self.assertEqual(ops["completed_biometric"], 10)

    def test_shorter_copy_with_more_completions_is_a_conflict(self):
        longer = session(block_lines=120, cycles_completed_biometric=10)
        shorter = session(stream_ordinal=1, block_lines=110, cycles_completed_biometric=11)
        self.assertEqual(section_operations([longer, shorter])["copy_conflicts"], 1)

    def test_distinct_blocks_and_ranks_add(self):
        first = session(cycles_completed_manual=3)
        restart = session(session_ordinal=1, rank_in_segment=2, cycles_completed_manual=4)
        replacement = session(
            object_sha256="c" * 64,
            device_id="02392288",
            block_start="d" * 64,
            model="UE2022",
            start_reading="2026-10-25T10:00:00",
            cycles_completed_unknown=5,
        )
        ops = section_operations([first, restart, replacement])
        self.assertEqual(ops["official_sessions"], 3)
        self.assertEqual(ops["completed_manual"], 7)
        self.assertEqual(ops["completed_unknown"], 5)
        self.assertEqual(ops["devices"], 2)
        self.assertEqual(ops["log_models"], ["UE2020", "UE2022"])
        self.assertEqual(ops["last_model"], "UE2022")

    def test_unlinked_sessions_are_never_merged(self):
        a = session(block_start=None, cycles_completed_biometric=1)
        b = session(block_start=None, stream_ordinal=1, cycles_completed_biometric=1)
        ops = section_operations([a, b])
        self.assertEqual(ops["official_sessions"], 2)
        self.assertEqual(ops["unlinked_sessions"], 2)


class ClockTests(unittest.TestCase):
    def test_close_rules(self):
        rows = [
            {"uf": "ac", "municipality": "01392", "configured_close": []},
            {"uf": "mt", "municipality": "90670", "configured_close": []},
            {"uf": "sp", "municipality": "71072", "configured_close": []},
            {"uf": "zz", "municipality": "29564", "configured_close": []},
            {"uf": "pe", "municipality": "25810", "configured_close": []},
            {"uf": "am", "municipality": "02550", "configured_close": ["15:00:00"]},
            {"uf": "am", "municipality": "02550", "configured_close": ["15:00:00"]},
            {"uf": "am", "municipality": "02003", "configured_close": ["15:00:00", "16:00:00"]},
            {"uf": "am", "municipality": "02097", "configured_close": []},
        ]
        names = {("pe", "25810"): "FERNANDO DE NORONHA"}
        rules = close_rules(rows, names)
        self.assertEqual(rules[("ac", "01392")], ("law_uf", "15:00:00"))
        self.assertEqual(rules[("mt", "90670")], ("law_uf", "16:00:00"))
        self.assertEqual(rules[("sp", "71072")], ("law_uf", "17:00:00"))
        self.assertEqual(rules[("zz", "29564")], ("abroad", "17:00:00"))
        self.assertEqual(rules[("pe", "25810")], ("law_noronha", "18:00:00"))
        self.assertEqual(rules[("am", "02550")], ("am_configured", "15:00:00"))
        self.assertEqual(rules[("am", "02003")], ("unresolved", None))
        self.assertEqual(rules[("am", "02097")], ("unresolved", None))

    def test_clock_states(self):
        ops = section_operations([session()])
        day = "2026-10-25"
        self.assertEqual(clock_state(None, "15:00:00", day), "no_sessions")
        self.assertEqual(clock_state(ops, None, day), "no_close_rule")
        self.assertEqual(clock_state(ops, "15:00:00", "2026-10-04"), "off_election_date")
        self.assertEqual(clock_state(ops, "15:00:00", day), "ok")
        self.assertEqual(clock_state(ops, "16:00:00", day), "ok")  # no configured close seen
        conflict = section_operations([session(configured_close="16:00:00")])
        self.assertEqual(clock_state(conflict, "15:00:00", day), "close_conflict")
        adjusted = section_operations([session(clock_adh_before=1)])
        self.assertEqual(clock_state(adjusted, "15:00:00", day), "adjusted")
        stepped = section_operations([session(reading_backsteps=1, clock_adh_before=1)])
        self.assertEqual(clock_state(stepped, "15:00:00", day), "backstep")


def row(round_number, section, members, *, ops=None, protected=False, result=True):
    key = ("ac", "01392", "0009", section)
    profile = {("ac", "01392", "0009", m): {c: 1 for c in PROFILE_COLUMNS} for m in members}
    result_row = (
        {"eligible": 10, "attendance": 8, "unparsed_votes": 0, "location": "1554"}
        if result
        else None
    )
    return _section_row(
        key,
        2026,
        round_number,
        "2026-10-25" if round_number == 2 else "2026-10-04",
        result_row,
        None,
        round_number,
        members,
        False,
        profile,
        {"complete"} if ops else None,
        ops,
        protected,
        {},
    )


class RowTests(unittest.TestCase):
    def test_timing_needs_a_resolved_clock_and_counts_after_close(self):
        hours = [0] * 24
        hours[14], hours[15] = 5, 2
        ops = section_operations(
            [
                session(
                    cycles_completed_biometric=6,
                    cycles_completed_manual=1,
                    completions_by_reading_hour=hours,
                )
            ]
        )
        r = row(2, "0070", ["0070"], ops=ops)
        restricted = _finish(r, "law_uf", "15:00:00")
        self.assertEqual(r["clock_state"], "ok")
        self.assertEqual(r["timing_state"], "ready")
        self.assertEqual(restricted["completed"], 7)
        self.assertEqual(restricted["completed_nonbiometric"], 1)
        self.assertEqual(restricted["completed_after_close"], 2)
        unresolved = row(2, "0070", ["0070"], ops=ops)
        restricted = _finish(unresolved, "unresolved", None)
        self.assertEqual(unresolved["timing_state"], "unavailable")
        self.assertEqual(unresolved["timing_reason"], "unresolved_clock")
        self.assertIsNone(restricted["completed_after_close"])
        self.assertEqual(restricted["completed"], 7)

    def test_protected_and_missing_inputs_stay_unavailable(self):
        protected = row(2, "0070", ["0070"], protected=True)
        restricted = _finish(protected, "law_uf", "15:00:00")
        self.assertEqual(protected["log_status"], "protected_until_freeze")
        self.assertEqual(protected["operations_reason"], "outside_scope")
        self.assertIsNone(restricted["completed"])
        missing = row(2, "0071", ["0071"], result=False)
        _finish(missing, "law_uf", "15:00:00")
        self.assertEqual(missing["results_state"], "unavailable")
        self.assertEqual(missing["results_reason"], "missing_input")
        self.assertEqual(missing["log_status"], "no_log")

    def test_recombined_sections_form_one_unit(self):
        rows = [
            row(1, "0070", ["0070", "0071"]),
            row(2, "0070", ["0070"]),
            row(2, "0071", ["0071"]),
        ]
        rows.append(row(1, "0090", ["0090"]))
        rows.append(row(2, "0090", ["0090"]))
        restricted = [_finish(r, "law_uf", "15:00:00") for r in rows]
        units = {json.loads(u["members_json"])[0]: u for u in harmonize(rows, restricted, 2026)}
        self.assertEqual(units["0070"]["kind"], "recombined")
        self.assertEqual((units["0070"]["principals_r1"], units["0070"]["principals_r2"]), (1, 2))
        self.assertTrue(units["0070"]["comparable"])
        self.assertEqual(units["0090"]["kind"], "same_principal")
        self.assertEqual(rows[0]["profile_electors"], 2)
        ids = {r["unit_id"] for r in rows[:3]}
        self.assertEqual(len(ids), 1)
        self.assertEqual({r["unit_id"] for r in restricted[:3]}, ids)

    def test_chunks_hold_whole_municipalities_of_one_uf(self):
        sizes = [
            ("ac", "01", 4),
            ("ac", "02", 4),
            ("ac", "03", 9),
            ("am", "04", 1),
            ("rr", "05", 2),
        ]
        self.assertEqual(
            list(_chunks(sizes, None, 8)),
            [("ac", ["01", "02"]), ("ac", ["03"]), ("am", ["04"]), ("rr", ["05"])],
        )
        self.assertEqual(list(_chunks(sizes, {"am", "rr"}, 8)), [("am", ["04"]), ("rr", ["05"])])


if __name__ == "__main__":
    unittest.main()
