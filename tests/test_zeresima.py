"""Phase 20b zerésima rules over semantic-pass markers."""

import json
import unittest
from typing import Any

from election_audit.zeresima import section_rules

DAY = "2026-10-25"


def marker(kind: str, line: int, *, before: int = 0, **extra: Any) -> dict[str, Any]:
    row = {
        "object_sha256": "o",
        "stream_ordinal": 0,
        "segment_ordinal": 1,
        "device_id": "d1",
        "kind": kind,
        "line": line,
        "reading": f"{DAY}T07:00:00",
        "completions_before": before,
        "block_start": "b1",
        "rank": 1,
    }
    return row | extra


def session(device: str = "d1", completed: int = 10, **extra: Any) -> dict[str, Any]:
    row = {
        "object_sha256": "o",
        "stream_ordinal": 0,
        "segment_ordinal": 1,
        "device_id": device,
        "cycles_completed_biometric": completed,
        "cycles_completed_manual": 0,
        "cycles_completed_unknown": 0,
    }
    return row | extra


class ZeresimaRuleTests(unittest.TestCase):
    def failed(self, row: dict[str, Any]) -> list[str]:
        return json.loads(row["failed_json"])

    def test_an_ordinary_section_passes(self) -> None:
        row = section_rules([marker("zeresima_start", 5), marker("ready", 9)], [session()], DAY)
        self.assertEqual(self.failed(row), [])
        self.assertEqual((row["zeresimas"], row["votes_before_first"]), (1, 0))

    def test_memory_copies_count_once(self) -> None:
        copy: dict[str, Any] = {"object_sha256": "o2"}
        markers = [marker("zeresima_start", 5), marker("zeresima_start", 5, **copy)]
        markers += [marker("ready", 3), marker("ready", 3, **copy)]
        row = section_rules(markers, [session()], DAY)
        self.assertEqual(row["zeresimas"], 1)
        self.assertEqual(row["ready_before_zeresima"], 1)
        self.assertEqual(self.failed(row), ["Z5"])

    def test_each_rule_fails_on_its_own_case(self) -> None:
        self.assertEqual(self.failed(section_rules([], [session()], DAY)), ["Z1"])
        late = section_rules([marker("zeresima_start", 50, before=3)], [session()], DAY)
        self.assertEqual((self.failed(late), late["votes_before_first"]), (["Z2"], 3))
        earlier_block = section_rules(
            [marker("zeresima_start", 50, segment_ordinal=2)], [session(completed=4)], DAY
        )
        self.assertEqual(earlier_block["votes_before_first"], 4)
        off_day = section_rules(
            [marker("zeresima_start", 5, reading="2026-10-24T17:00:00")], [session()], DAY
        )
        self.assertEqual(self.failed(off_day), ["Z3"])
        two = [marker("zeresima_start", 5), marker("zeresima_start", 8, rank=2)]
        self.assertEqual(self.failed(section_rules(two, [session()], DAY)), ["Z4"])

    def test_a_contingency_urn_without_its_own_zeresima_is_counted_not_failed(self) -> None:
        markers = [marker("zeresima_start", 5)]
        sessions = [session(completed=3), session("d2", completed=7, stream_ordinal=1)]
        row = section_rules(markers, sessions, DAY)
        self.assertEqual(self.failed(row), [])
        self.assertEqual(
            (row["devices_with_votes"], row["devices_with_votes_without_zeresima"]), (2, 1)
        )


if __name__ == "__main__":
    unittest.main()
