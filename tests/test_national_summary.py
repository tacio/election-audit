"""Fused parse/reference equivalence, forensic replay, and desktop resource limits."""

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from election_audit.archive_parsing import ParseConfig
from election_audit.national import _parse_bounded
from election_audit.national_resources import cpu_allocation, policy
from election_audit.national_summary import (
    SummaryBudgetExceeded,
    SummaryParser,
    replay_lines,
    summarize,
)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("ELECTION_AUDIT_RELOCATION", None)
        os.environ.pop("ELECTION_AUDIT_RELOCATION_SHA256", None)

    def source(self, lines, *, nested=False):
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("logd.dat", b"".join(lines))
        if nested:
            outer = io.BytesIO()
            with zipfile.ZipFile(outer, "w") as z:
                z.writestr("nested.zip", body.getvalue())
            body = outer
        raw = body.getvalue()
        h = hashlib.sha256(raw).hexdigest()
        path = Path("objects") / h[:2] / (h + ".jez")
        target = self.root / "raw" / path
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        return {
            "source_root": str(self.root / "raw"),
            "path": str(path),
            "sha256": h,
            "bytes": len(raw),
            "url": "https://example.test/source.jez",
        }

    def line(self, time="08:00:00", app="VOTA", message="Unknown", device="123", level="INFO"):
        return f"25/10/2026 {time}\t{level}\t{device}\t{app}\t{message}\tprivate-token\n".encode(
            "latin-1"
        )

    def test_fused_reference_counts_diagnostics_and_every_replayed_field(self):
        lines = [
            self.line(),
            self.line(message="Eleitor foi habilitado"),
            self.line(time="07:59:00", app="OTHER", level="WARN"),
            b"broken\n",
            self.line(time="99:00:00"),
            self.line(device="bad"),
            self.line(message="O voto do eleitor foi computado"),
            self.line(message="Solicitação de dado pessoal do eleitor para habilitação manual"),
        ]
        row = self.source(lines, nested=True)
        reference = self.root / "reference"
        reference.mkdir()
        doc = _parse_bounded(Path(row["source_root"]) / row["path"], reference, row["sha256"])
        actual = summarize(row, self.scratch, block_lines=3)
        self.assertEqual(actual["counts"], doc["counts"])
        self.assertEqual(actual["status"], "partial")
        self.assertEqual(
            {(a, b): n for a, b, n in actual["diagnostics"]},
            {(d["issue_code"], d["severity"]): d["count"] for d in doc["diagnostics"]},
        )
        expected = [
            json.loads(line) for line in (reference / "events.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual(list(replay_lines(row, self.scratch, 0, 1, len(lines))), expected)
        self.assertEqual(actual["members"][0][10], 1)
        self.assertEqual(actual["readiness"]["official_sessions"], "unavailable")
        self.assertNotIn("private-token", json.dumps(actual))
        self.assertEqual(actual["errors"][0][-1], hashlib.sha256(lines[3]).hexdigest())

    def test_unknown_blocks_reproduce_physical_bytes_without_an_event_table(self):
        lines = [self.line() for _ in range(1200)]
        row = self.source(lines)
        doc = summarize(row, self.scratch)
        self.assertEqual(doc["counts"]["events"], 1200)
        self.assertEqual(doc["counts"]["issues_aggregated"], 1200)
        self.assertEqual(len(doc["anchors"]), 1)
        self.assertEqual(len(doc["blocks"]), 3)
        for block in doc["blocks"]:
            self.assertEqual(
                block[3], hashlib.sha256(b"".join(lines[block[1] - 1 : block[2]])).hexdigest()
            )
        events = list(replay_lines(row, self.scratch, 0, 513, 514))
        self.assertEqual([r["record_locator"]["line_start"] for r in events], [513, 514])
        self.assertTrue(
            all(r["source_line_sha256"] == hashlib.sha256(lines[0]).hexdigest() for r in events)
        )

    def test_evidence_limit_fails_instead_of_silent_truncation(self):
        row = self.source([self.line(message="Eleitor foi habilitado") for _ in range(100)])
        with self.assertRaises(SummaryBudgetExceeded):
            summarize(row, self.scratch, output_limit=1024)

    def test_corrupt_source_never_publishes_summaries(self):
        row = self.source([self.line()])
        target = Path(row["source_root"]) / row["path"]
        target.write_bytes(b"x" * row["bytes"])
        with self.assertRaisesRegex(ValueError, "hash/length"):
            summarize(row, self.scratch)

    def test_cpu_and_worker_budgets_cannot_exceed_half_available_capacity(self):
        with patch("os.sched_getaffinity", return_value=set(range(12))):
            cpus = cpu_allocation()
            self.assertLessEqual(len(cpus["allowed_cpus"]), 6)
            self.assertLessEqual(cpus["cpu_quota_percent"], 600)
            resources = policy(workers=2, batch=16, prefetch=1)
            self.assertEqual(resources["queue_limit"], 3)
            self.assertLessEqual(
                resources["workers"] * resources["worker_address_space_bytes"]
                + resources["parent_allowance_bytes"],
                4 * 1024**3,
            )
            with self.assertRaises(ValueError):
                policy(workers=100)
            with self.assertRaises(ValueError):
                cpu_allocation(1)
        with patch("os.sched_getaffinity", return_value={0}):
            with self.assertRaises(ValueError):
                cpu_allocation()

    def test_line_limit_does_not_mislabel_a_prefix_hash_as_full_line_evidence(self):
        parser = SummaryParser("a" * 64, self.scratch)
        parser.config = ParseConfig(max_lines=1, max_line_bytes=8)
        parser.lines(io.BytesIO(b"x\n" + b"y" * 100 + b"\n"), [])
        limit = next(e for e in parser.errors if e[0] == "line_count_limit")
        self.assertIsNone(limit[-1])
        self.assertTrue(parser.incomplete)


if __name__ == "__main__":
    unittest.main()
