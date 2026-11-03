"""Real processes: protected scope, deterministic shards, publication recovery."""

import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

from election_audit import national_parallel as parallel
from election_audit.national_resources import policy
from election_audit.national_workload import prepare as prepare_legacy


class ParallelTests(unittest.TestCase):
    def setUp(self):
        from tests.test_national_migration import MigrationTests
        from tests.test_national_workload import WorkloadExecutionTests

        self.fixture = WorkloadExecutionTests(
            "test_protected_missing_body_never_opened_and_bounded_resume"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.migration = MigrationTests("test_observed_transfer_failure_stops")
        self.migration.setUp()
        self.addCleanup(self.migration.doCleanups)
        copied = self.fixture.root / "copied-raw"
        shutil.copytree(self.fixture.raw, copied)
        with sqlite3.connect(self.migration.manifest) as db:
            db.execute("DELETE FROM files")
            db.executemany(
                "INSERT INTO files VALUES(?,?,?,?)",
                (
                    tuple(r[k] for k in ("url", "path", "sha256", "bytes"))
                    for r in self.fixture.rows
                ),
            )
        self.migration.item.update(old_root=str(self.fixture.raw), new_root=str(copied))
        _, registry = self.migration.accept()
        prepare_legacy(
            self.fixture.profile,
            self.fixture.excluded,
            self.fixture.reco,
            self.fixture.config,
            self.fixture.store,
            self.fixture.scratch,
            output_budget_bytes=16 * 1024**2,
            future_budget_bytes=0,
            relocation_registry=registry,
        )
        self.fixture.execute()
        self.fixture.raw.rename(self.fixture.root / "old-offline")
        # Protected original may be unavailable: no semantic/cache read is allowed.
        self.copied = copied

    def setup_job(self, name, workers):
        resources = policy(workers=workers, batch=1, prefetch=0)
        resources.update(
            hdd_reserve_bytes=0,
            ssd_reserve_bytes=0,
            scratch_budget_bytes=1024**3,
            future_budget_bytes=0,
            output_budget_bytes=32 * 1024**2,
        )
        out = self.fixture.root / name
        spec = parallel.prepare(
            self.fixture.config, out, self.fixture.root / (name + "-store"), resources=resources
        )
        return out, spec

    def execute(self, out, *args, check=True):
        return subprocess.run(
            [sys.executable, "-B", str(out / "run_frozen.py"), "run", *args],
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )

    def logical(self, spec):
        rows = {}
        for path in sorted((Path(spec["store"]) / "shards").glob("*/*/summary.sqlite")):
            with sqlite3.connect(path) as db:
                for table in ("objects", "members", "blocks", "anchors", "errors"):
                    rows.setdefault(table, []).extend(db.execute("SELECT * FROM " + table))
        return {k: sorted(v) for k, v in rows.items()}

    def test_real_worker_counts_protected_exclusion_and_logical_determinism(self):
        first, spec1 = self.setup_job("one", 1)
        second, spec2 = self.setup_job("two", 2)
        # A missing protected source proves scheduler filtering precedes body access.
        (self.copied / self.fixture.rows[2]["path"]).unlink()
        self.execute(first)
        self.execute(second)
        self.assertEqual(parallel.status(first)["completed"], 2)
        self.assertEqual(self.logical(spec1), self.logical(spec2))
        before = self.logical(spec1)
        self.execute(first)
        self.assertEqual(before, self.logical(spec1))
        with sqlite3.connect(Path(spec1["store"]) / "work.sqlite") as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM work WHERE legacy_ref IS NOT NULL").fetchone()[0],
                2,
            )

    def test_published_unledgered_group_recovers_without_reparse(self):
        out, spec = self.setup_job("recover", 1)
        self.execute(out)
        with sqlite3.connect(Path(spec["store"]) / "work.sqlite") as db:
            group = db.execute("SELECT * FROM groups LIMIT 1").fetchone()
            marker = Path(spec["store"]) / "shards" / group[0][:2] / group[0] / "shard.json"
            doc = json.loads(marker.read_text())
            db.execute("DELETE FROM groups WHERE id=?", (group[0],))
            for sha in doc["objects"]:
                db.execute("UPDATE work SET status='running',shard=NULL WHERE sha=?", (sha,))
            for key, amount in [("completed", group[1]), ("events", group[2]), ("bytes", group[3])]:
                db.execute(
                    "UPDATE metadata SET value=CAST(value AS INTEGER)-? WHERE key=?", (amount, key)
                )
        before = self.logical(spec)
        self.execute(out)
        self.assertEqual(parallel.status(out)["completed"], 2)
        self.assertEqual(before, self.logical(spec))

    def test_changed_source_stops_without_published_group(self):
        out, spec = self.setup_job("corrupt", 2)
        target = self.copied / self.fixture.rows[0]["path"]
        target.write_bytes(b"x" * target.stat().st_size)
        result = self.execute(out, check=False)
        self.assertNotEqual(result.returncode, 0)
        for marker in (Path(spec["store"]) / "shards").glob("*/*/shard.json"):
            self.assertNotIn(
                self.fixture.rows[0]["sha256"], json.loads(marker.read_text())["objects"]
            )
        self.assertEqual(parallel.status(out)["failures"], 1)

    def test_benchmark_cannot_select_protected_alias(self):
        with self.assertRaisesRegex(ValueError, "Protected"):
            parallel.prepare(
                self.fixture.config,
                self.fixture.root / "forbidden",
                self.fixture.root / "forbidden-store",
                selection=[self.fixture.rows[2]["sha256"]],
            )

    def test_cancellation_is_fail_fast_and_preserves_unpublished_group(self):
        out, spec = self.setup_job("cancel", 1)
        pool = Mock()
        pool._processes = {}
        pool.submit.side_effect = lambda *a: Future()

        def cancel(pending, **kwargs):
            parallel._STOP = True
            return set(), set(pending)

        with (
            patch.object(parallel, "apply"),
            patch.object(parallel, "ProcessPoolExecutor", return_value=pool),
            patch.object(parallel, "wait", side_effect=cancel),
        ):
            with self.assertRaises(InterruptedError):
                parallel.run(out)
        self.assertFalse(list((Path(spec["store"]) / "shards").glob("*/*/shard.json")))
        self.assertEqual(json.loads((out / "progress.json").read_text())["run_state"], "cancelled")
        self.execute(out)
        self.assertEqual(parallel.status(out)["completed"], 2)

    def test_export_verifies_shard_and_retains_all_witness_unknowns(self):
        from election_audit.national_summary_tools import iter_source_observations, iter_table

        out, spec = self.setup_job("readers", 1)
        self.execute(out)
        self.assertEqual(len(list(iter_table(out))), 2)
        observations = list(iter_source_observations(out))
        protected = next(r for r in observations if r["section"] == "0003")
        self.assertEqual(protected["object_work_status"], "deferred_protected_or_stress")
        self.assertIsNone(protected["summary_shard"])
        data = next((Path(spec["store"]) / "shards").glob("*/*/summary.sqlite"))
        with data.open("r+b") as stream:
            stream.seek(100)
            stream.write(b"broken")
        with self.assertRaisesRegex(ValueError, "checksum"):
            list(iter_table(out))

    def test_documented_cli_prepare_and_bounded_frozen_run(self):
        out = self.fixture.root / "cli-config"
        store = self.fixture.root / "cli-store"
        command = [
            sys.executable,
            "-B",
            "-m",
            "election_audit.national_parallel",
            "prepare",
            "--scope-workload",
            str(self.fixture.config),
            "--output",
            str(out),
            "--store",
            str(store),
            "--memory-gib",
            "4",
            "--cpu-fraction",
            "0.5",
            "--workers",
            "2",
            "--batch-objects",
            "32",
            "--prefetch",
            "1",
            "--hdd-reserve-gib",
            "0",
            "--ssd-reserve-gib",
            "0",
            "--scratch-gib",
            "1",
            "--output-gib",
            "0.03125",
            "--future-gib",
            "0",
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        self.execute(out, "--max-objects", "1")
        self.assertEqual(parallel.status(out)["completed"], 1)
        result = subprocess.run(
            [sys.executable, "-B", str(out / "run_frozen.py"), "status"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout)["completed"], 1)


if __name__ == "__main__":
    unittest.main()
