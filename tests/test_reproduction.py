"""Offline walkthrough, relocation/tampering, and interrupted frozen resume."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from election_audit.pilot import select_pilot
from election_audit.publication import PublicationError, publish_release
from election_audit.release_tools import query_release
from election_audit.reproduction import (
    demo,
    frozen_pipeline,
    reproduce,
    review_bundle,
    verify_bundle,
)
from election_audit.walkthrough import archive
from scripts.check_doc_commands import check_commands


class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.fixture_run = cls.base / "demo"
        cls.descriptor = demo(cls.fixture_run)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_synthetic_numbers_unknowns_null_ledger_and_paired_reports(self):
        stages = self.descriptor["stages"]
        release = self.fixture_run / stages[-1]["locator"]
        self.assertEqual(
            query_release(
                release,
                "SELECT DISTINCT value,numerator,denominator FROM audit_features WHERE feature_id='turnout_target' ORDER BY value NULLS LAST",
            )["rows"],
            [(0.5, 10.0, 20.0), (None, None, None)],
        )
        self.assertEqual(
            query_release(release, "SELECT count(*) FROM analysis_ledger")["rows"], [(5,)]
        )
        self.assertEqual(
            query_release(
                release, "SELECT count(*) FROM anonymous_cycle WHERE completion_state='completed'"
            )["rows"],
            [(2,)],
        )
        self.assertEqual(
            query_release(
                release, "SELECT count(*) FROM anonymous_cycle WHERE completion_state='cancelled'"
            )["rows"],
            [(1,)],
        )
        for kind in ("operational", "electoral", "analysis"):
            for language, marker in (("en", "SYNTHETIC"), ("pt-BR", "SINTÉTICO")):
                self.assertIn(
                    marker,
                    (self.fixture_run / "reports" / kind / f"report.{language}.md").read_text(),
                )
                text = (self.fixture_run / "reports" / kind / f"report.{language}.md").read_text()
                self.assertIn("Document-ID: EA-REPORT-", text)
                self.assertIn(f"Revision: 1 · Language: {language}", text)
        snapshot = json.loads(
            (self.fixture_run / self.descriptor["snapshot"] / "snapshot.json").read_text()
        )
        self.assertEqual(snapshot["payload"]["coverage_summary"]["expected_members"], 3)
        self.assertEqual(snapshot["payload"]["coverage_summary"]["expected_unique_principals"], 2)
        self.assertEqual(archive([("logd.dat", b"x")]), archive([("logd.dat", b"x")]))

    def test_relocated_bundle_offline_replay_and_tamper(self):
        original = review_bundle(self.fixture_run, self.base / "bundle")
        moved = self.base / "relocated" / "review"
        moved.parent.mkdir()
        shutil.move(original, moved)
        self.assertTrue((moved / "source" / "research").is_dir())
        self.assertFalse((moved / "run" / "synthetic-source").exists())
        self.assertFalse((moved / "source" / ".local-state").exists())
        result = reproduce(moved, self.base / "replay")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["stages"]), 4)
        path = moved / "run" / self.descriptor["snapshot"] / "snapshot.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(PublicationError, "inventory/hash"):
            verify_bundle(moved)

    def test_interrupted_publication_then_bounded_resume(self):
        evidence = json.loads((self.fixture_run / "inputs" / "evidence.json").read_text())
        output = self.base / "resume"
        parsed, shards, release, _ = frozen_pipeline(
            self.fixture_run / self.descriptor["snapshot"],
            output,
            evidence=evidence,
            object_groups=self.descriptor["object_groups"],
        )

        def interrupt(stage):
            if stage == "before_release":
                raise InterruptedError("fixture interruption")

        interrupted = self.base / "interrupted"
        with self.assertRaises(InterruptedError):
            publish_release(shards, interrupted, hook=interrupt)
        self.assertFalse((interrupted / "current").exists())
        finished = publish_release(shards, interrupted)
        self.assertEqual(finished.name, release.name)
        parsed_again, _, resumed, _ = frozen_pipeline(
            self.fixture_run / self.descriptor["snapshot"],
            output,
            evidence=evidence,
            object_groups=self.descriptor["object_groups"],
        )
        self.assertEqual((parsed_again, resumed), (parsed, release))

    def test_selection_is_seeded_bounded_and_read_only(self):
        root = self.fixture_run / "synthetic-source"
        before = (root / "manifest.sqlite").read_bytes()
        first = select_pilot(root, sampled_ufs=("ac",))
        second = select_pilot(root, sampled_ufs=("ac",))
        self.assertEqual(first["selected"], second["selected"])
        self.assertEqual(first["selected"][0]["section_key"], ("ac", "01120", "0001", "0001"))
        self.assertEqual(before, (root / "manifest.sqlite").read_bytes())
        self.assertEqual(first["national_status"], "partial_national")

    def test_source_symlink_is_rejected_before_copy(self):
        source = self.base / "unsafe-source"
        (source / "election_audit").mkdir(parents=True)
        (source / "election_audit" / "leak.py").symlink_to("/etc/passwd")
        with self.assertRaisesRegex(PublicationError, "symlinks"):
            review_bundle(self.fixture_run, self.base / "unsafe-bundle", source_root=source)
        self.assertFalse((self.base / "unsafe-bundle").exists())


class DocumentationCommandTests(unittest.TestCase):
    def test_known_flags_sql_and_invalid_examples_without_operation_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "justfile").write_text(
                "download *args:\n    ignored\nquery *args:\n    ignored\n"
            )
            document = root / "README.md"
            document.write_text(
                "```sh\nrtk proxy just download --output /NEVER/CREATE --workers 1\nrtk proxy just query /DOES/NOT/EXIST --sql 'SELECT 1'\n```\n"
            )
            errors, counts = check_commands(root)
            self.assertEqual(errors, [])
            self.assertEqual(counts["help_invocations"], 2)
            document.write_text(
                "```sh\nrtk proxy just query /NEVER/OPEN --invented\n```\n```sql\nSELECT FROM;\n```\n"
            )
            errors, _ = check_commands(root)
            self.assertTrue(any("unknown flag" in error for error in errors))
            self.assertTrue(any("SQL syntax" in error for error in errors))
