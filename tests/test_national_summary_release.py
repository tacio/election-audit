"""Compact typed Parquet publication, unknowns, integrity and quota idempotence."""

import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

import pyarrow.parquet as pq


class SummaryReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        from tests.test_national_parallel import ParallelTests

        self.helper = ParallelTests("test_documented_cli_prepare_and_bounded_frozen_run")
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.out, self.spec = self.helper.setup_job("analytical", 1)
        self.helper.execute(self.out)
        self.release = self.helper.fixture.root / "release"

    def export(self, check=True):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.out / "run_frozen.py"),
                "export",
                "--output",
                str(self.release),
                "--target-mib",
                "1",
            ],
            check=check,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_few_typed_files_portable_reads_unknowns_and_idempotent_budget(self) -> None:
        # Analytical publication and queries need no original body or per-source
        # checkpoint reads after the producer's committed group verification.
        shutil.rmtree(self.helper.copied)
        result = self.export()
        manifest = json.loads(result.stdout)
        self.assertEqual(len(manifest["files"]), 5)
        self.assertTrue(manifest["no_event_lake"])
        self.assertFalse(manifest["full_national_complete"])
        summaries = pq.read_table(self.release / "source_summaries").to_pylist()
        self.assertEqual(len(summaries), 2)
        self.assertEqual(sum(r["observed_events"] for r in summaries), 2)
        self.assertTrue(
            all(
                len(r["object_sha256"]) == 32
                and r["feature_readiness"] == "unavailable_structural_only"
                for r in summaries
            )
        )
        witnesses = pq.read_table(self.release / "source_witnesses").to_pylist()
        self.assertEqual(len(witnesses), 3)
        self.assertEqual(
            next(r for r in witnesses if r["section"] == "0003")["summary_state"],
            "deferred_protected_or_stress",
        )
        with sqlite3.connect(Path(self.spec["store"]) / "work.sqlite") as db:
            before = db.execute("SELECT value FROM metadata WHERE key='released_bytes'").fetchone()[
                0
            ]
        self.export()
        with sqlite3.connect(Path(self.spec["store"]) / "work.sqlite") as db:
            self.assertEqual(
                db.execute("SELECT value FROM metadata WHERE key='released_bytes'").fetchone()[0],
                before,
            )

    def test_existing_parquet_corruption_is_never_overwritten(self) -> None:
        self.export()
        part = next((self.release / "source_summaries").glob("*.parquet"))
        part.write_bytes(b"corrupted")
        result = self.export(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr)
        self.assertEqual(part.read_bytes(), b"corrupted")

    def test_metadata_only_scope_needs_no_legacy_event_work_ledger(self) -> None:
        # Existing scope metadata is sufficient on fresh hardware; completed old
        # event artifacts are optional references, never a setup prerequisite.
        for path in self.helper.fixture.store.glob("work.sqlite*"):
            path.unlink()
        out, spec = self.helper.setup_job("metadata-only", 1)
        self.helper.execute(out)
        from election_audit.national_parallel import status

        self.assertEqual(status(out)["completed"], 2)

    def test_run_can_finalize_automatically_after_worker_shutdown(self) -> None:
        out, spec = self.helper.setup_job("auto-finalize", 1)
        destination = self.helper.fixture.root / "auto-analysis"
        result = self.helper.execute(out, "--analysis-output", str(destination))
        manifest = json.loads((destination / "manifest.json").read_text())
        self.assertEqual(manifest["completed_source_objects"], 2)
        self.assertTrue(manifest["complete_requested_scope"])
        self.assertIn("analytical_release", result.stdout)


if __name__ == "__main__":
    unittest.main()
