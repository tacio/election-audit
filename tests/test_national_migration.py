"""Transfer identity, durable blind-copy acceptance and strict cache relocation."""

import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from election_audit import national_migration as migration
from election_audit import national_relocation as relocation
from election_audit.national_overnight import checked_copy, verify_checkpoint
from election_audit.national_storage import process_compact_original, resolve_original
from election_audit.national_workload import _reuse


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.old = self.root / "old"
        self.new = self.root / "new"
        self.old.mkdir()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(
                "logd.dat", b"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message\ttoken\n"
            )
        body = archive.getvalue()
        object_sha = hashlib.sha256(body).hexdigest()
        relative = f"objects/{object_sha[:2]}/{object_sha}.jez"
        source = self.old / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(body)
        shutil.copytree(self.old, self.new)
        self.row = {
            "source_root": str(self.old),
            "sha256": object_sha,
            "path": relative,
            "bytes": len(body),
            "url": "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/go/o-log.jez",
        }
        self.manifest = self.root / "source.sqlite"
        with sqlite3.connect(self.manifest) as db:
            db.executescript(
                "CREATE TABLE runs(id,started_at,finished_at,status);"
                "CREATE TABLE files(url,path,sha256,bytes);"
                "CREATE TABLE sections(run,status);CREATE TABLE logs(run,package_status);"
            )
            db.execute("INSERT INTO runs VALUES('r','2026','2027','finished')")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?)",
                tuple(self.row[k] for k in ("url", "path", "sha256", "bytes")),
            )
            db.execute("INSERT INTO sections VALUES('r','unknown')")
        self.item = {
            "round": 2,
            "pleito": "3221",
            "manifest": str(self.manifest),
            "old_root": str(self.old),
            "new_root": str(self.new),
            "mount": "/",
        }
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("ELECTION_AUDIT_RELOCATION", None)
        os.environ.pop("ELECTION_AUDIT_RELOCATION_SHA256", None)
        self.addCleanup(self.reset_cache)

    def reset_cache(self):
        if relocation._CACHE:
            for _, db in set(relocation._CACHE[1].values()):
                db.close()
        relocation._CACHE = None

    def accept(self):
        certificate = migration.verify_round(self.item, self.state, lambda *a: None, lambda: None)
        registry = self.state / "relocation.json"
        migration.atomic(
            registry, {"version": "verified-source-relocation-v1", "certificates": [certificate]}
        )
        relocation.configure(registry, migration.sha(registry))
        return certificate, registry

    def test_receiver_survives_sender_and_pid_reuse_is_not_alive(self):
        expected = [
            {"pid": 1, "start": 10, "argv": ["rsync"]},
            {"pid": 2, "start": 20, "argv": ["rsync"]},
        ]
        calls = {
            1: iter([None, None]),
            2: iter(
                [
                    {"pid": 2, "start": 20, "argv": ["rsync"], "state": "S", "exit_status": None},
                    None,
                ]
            ),
        }
        reports = []
        with (
            patch.object(migration, "process", side_effect=lambda p: next(calls[p])),
            patch.object(migration, "writers"),
            patch.object(migration.time, "sleep"),
        ):
            result = migration.wait_transfers(
                {"transfers": expected, "rounds": [self.item]}, lambda s, d: reports.append(d)
            )
        self.assertEqual(reports[0]["alive"], [2])
        self.assertIsNone(result["1"]["observed_exit_code"])
        self.assertFalse(migration.transfer_alive(expected[0], {"start": 99, "state": "S"}))

    def test_observed_transfer_failure_stops(self):
        with patch.object(
            migration,
            "process",
            return_value={"start": 10, "state": "Z", "argv": [], "exit_status": 23 << 8},
        ):
            with self.assertRaisesRegex(RuntimeError, "23"):
                migration.wait_transfers(
                    {"transfers": [{"pid": 1, "start": 10}], "rounds": [self.item]}, lambda *a: None
                )

    def test_unexpected_transfer_rejected_even_with_no_open_output(self):
        proc = {
            "pid": os.getpid() + 100,
            "state": "S",
            "argv": ["rsync", "-a", "somewhere", str(self.new) + "/"],
        }
        with patch.object(migration, "processes", return_value=iter([proc])):
            with self.assertRaisesRegex(RuntimeError, "Unexpected transfer"):
                migration.writers([self.new])

    def test_worker_guard_distinguishes_unrelated_test_from_relevant_source(self):
        launcher = self.root / "test-job/run_frozen.py"
        launcher.parent.mkdir()
        spec = launcher.parent / "workload.json"
        migration.atomic(spec, {"source": {"root": str(self.root / "unrelated-test-source")}})
        proc = {"pid": 99999999, "state": "S", "argv": ["python", str(launcher), "run"]}
        with patch.object(migration, "processes", return_value=iter([proc])):
            migration.writers([self.new])
        migration.atomic(spec, {"source": {"root": str(self.new)}})
        with patch.object(migration, "processes", return_value=iter([proc])):
            with self.assertRaisesRegex(RuntimeError, "Existing structural worker"):
                migration.writers([self.new])

    def test_blind_acceptance_preserves_unknowns_and_resume_rejects_mutation(self):
        cert, _ = self.accept()
        self.assertEqual(cert["identity"]["section_status_counts"], {"unknown": 1})
        self.assertFalse(cert["semantic_inspection"])
        self.assertFalse(cert["identity"]["national_coverage_complete"])
        self.assertEqual(cert["objects"], 1)
        # Same bytes with a new inode must not reuse a stale verification ledger.
        target = self.new / self.row["path"]
        replacement = target.with_suffix(".new")
        replacement.write_bytes(target.read_bytes())
        replacement.replace(target)
        with self.assertRaisesRegex(ValueError, "Previously verified copy changed"):
            migration.verify_round(self.item, self.state, lambda *a: None, lambda: None)

    def test_missing_corrupt_symlink_and_traversal_fail(self):
        target = self.new / self.row["path"]
        target.write_bytes(b"x" * self.row["bytes"])
        with self.assertRaisesRegex(ValueError, "digest"):
            migration.verify_file(self.new, self.row["path"], self.row["sha256"], self.row["bytes"])
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            migration.verify_file(self.new, self.row["path"], self.row["sha256"], self.row["bytes"])
        target.symlink_to(self.old / self.row["path"])
        with self.assertRaisesRegex(ValueError, "Symlink"):
            migration.verify_file(self.new, self.row["path"], self.row["sha256"], self.row["bytes"])
        with self.assertRaises(ValueError):
            migration.relative_object("../outside", self.row["sha256"])

    def test_mixed_round_and_unfinished_manifest_fail(self):
        with sqlite3.connect(self.manifest) as db:
            db.execute("UPDATE files SET url=replace(url,'3221','3220')")
            with self.assertRaisesRegex(ValueError, "another election round"):
                migration.manifest_identity(db, "3221")
            db.execute("UPDATE runs SET status='running'")
            with self.assertRaisesRegex(ValueError, "not finished"):
                migration.manifest_identity(db, "3221")

    def test_original_old_path_absent_cache_reuse_keeps_checkpoint_bytes(self):
        store, scratch = self.root / "store", self.root / "scratch"
        with patch("election_audit.national.guard"):
            artifact = process_compact_original(
                self.row, store, scratch, output_budget_bytes=8 * 1024**2
            )
        checkpoint_before = (artifact / "checkpoint.json").read_bytes()
        self.accept()
        self.old.rename(self.root / "old-hidden")
        new_row = {**self.row, "source_root": str(self.new)}
        doc = json.loads(checkpoint_before)
        self.assertEqual(resolve_original(doc["original_reference"]), self.new / self.row["path"])
        self.assertEqual(_reuse(new_row, [store]), artifact)
        with patch("election_audit.national.guard"):
            self.assertEqual(
                process_compact_original(new_row, store, scratch, output_budget_bytes=8 * 1024**2),
                artifact,
            )
        self.assertEqual((artifact / "checkpoint.json").read_bytes(), checkpoint_before)
        self.assertEqual(verify_checkpoint(artifact, self.row)["counts"]["events"], 1)
        copy = self.root / "copied/compact" / artifact.name[:2] / artifact.name
        self.assertEqual(checked_copy(artifact, copy), copy)
        self.assertEqual(verify_checkpoint(copy, self.row)["counts"]["events"], 1)

    def test_no_old_fallback_unknown_root_or_ledger_pin(self):
        _, registry = self.accept()
        with self.assertRaisesRegex(ValueError, "not in the pinned"):
            relocation.relocated_root(
                self.root / "other", self.row["path"], self.row["sha256"], self.row["bytes"]
            )
        self.reset_cache()
        with sqlite3.connect(self.state / "verification-r2.sqlite") as db:
            db.execute("UPDATE verified SET size=size+1")
        with self.assertRaisesRegex(ValueError, "ledger changed"):
            relocation.relocated_root(
                self.old, self.row["path"], self.row["sha256"], self.row["bytes"]
            )
        registry.write_text("{}")
        with self.assertRaisesRegex(ValueError, "registry"):
            relocation.configure(registry, "0" * 64)

    def test_failed_continuation_propagates_and_bad_gate_never_runs(self):
        gate = self.root / "gate.json"
        script = self.root / "child.py"
        script.write_text("raise SystemExit(9)\n")
        migration.atomic(
            gate, {"files": {str(script): "0" * 64}, "command": ["python", str(script)]}
        )
        plan = self.root / "plan.json"
        migration.atomic(
            plan,
            {
                "state": str(self.state),
                "rounds": [self.item],
                "transfers": [],
                "ready_gate": str(gate),
                "quiescence_seconds": 0,
            },
        )
        with patch.object(migration, "writers"), patch.object(migration.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "pin mismatch"):
                migration.execute(plan)
            run.assert_not_called()
        migration.atomic(
            gate,
            {"files": {str(script): migration.sha(script)}, "command": ["python", str(script)]},
        )
        with (
            patch.object(migration, "writers"),
            patch.object(
                migration.subprocess, "run", return_value=subprocess.CompletedProcess([], 9)
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "exit code 9"):
                migration.execute(plan)
        self.assertEqual(
            json.loads((self.state / "status.json").read_text())["stage"], "FAILED_STOPPED"
        )

    def test_continuation_wires_new_job_reuse_and_protected_scope(self):
        from election_audit import national_overnight as overnight
        from election_audit.national import _read_json, _write_json
        from tests.test_national_workload import WorkloadExecutionTests

        fixture = WorkloadExecutionTests(
            "test_protected_missing_body_never_opened_and_bounded_resume"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        old_spec = fixture.configure()
        fixture.execute(max_objects=1)
        copied = fixture.root / "copied-raw"
        shutil.copytree(fixture.raw, copied)
        with sqlite3.connect(self.manifest) as db:
            db.execute("DELETE FROM files")
            db.executemany(
                "INSERT INTO files VALUES(?,?,?,?)",
                (tuple(r[k] for k in ("url", "path", "sha256", "bytes")) for r in fixture.rows),
            )
        self.item.update(old_root=str(fixture.raw), new_root=str(copied))
        self.accept()
        fixture.raw.rename(fixture.root / "offline-raw")
        with sqlite3.connect(fixture.store / "work.sqlite") as db:
            object_sha, artifact = db.execute(
                "SELECT sha256,artifact FROM work WHERE status='complete'"
            ).fetchone()
        comparison = fixture.root / "comparison.json"
        _write_json(
            comparison,
            {
                "sample_id": "registered-development",
                "records": [{"source_sha256": object_sha, "artifact": artifact}],
            },
        )
        config = {
            "workspace": str(fixture.root / "overnight"),
            "migration_state": str(self.state),
            "migration_plan": str(self.root / "migration-plan.json"),
            "anchor": "/",
            "old_workload": str(fixture.config),
            "safe_comparison": str(comparison),
            "tuning_comparison": str(comparison),
            "sample": str(fixture.root / "sample"),
            "cache_store": str(fixture.root / "cache"),
            "initial_store": str(fixture.store),
            "production_store": str(fixture.root / "new-production"),
            "new_profile": str(fixture.root / "new-profile"),
            "scratch": str(fixture.scratch),
            "tuning_store": str(fixture.root / "tuning-store"),
        }
        migration.atomic(config["migration_plan"], {"rounds": [self.item]})
        config_path = fixture.root / "overnight-config.json"
        migration.atomic(config_path, config)

        def prepare_tuning(sample, report, directory, *args, **kwargs):
            directory.mkdir()
            _write_json(directory / "recommended.json", _read_json(fixture.reco))

        def run_tranche(command, **kwargs):
            from election_audit.national_workload import run

            return run(Path(config["workspace"]) / "production", max_objects=25)

        with (
            patch.object(overnight, "writers"),
            patch.object(
                overnight.shutil,
                "disk_usage",
                return_value=shutil._ntuple_diskusage(2**41, 0, 2**41),
            ),
            patch.object(overnight.tuning, "prepare", side_effect=prepare_tuning),
            patch.object(overnight.tuning, "run"),
            patch.object(overnight.subprocess, "run", side_effect=run_tranche),
            patch.object(overnight.subprocess, "Popen") as child,
            patch("election_audit.national_workload.configure_production"),
            patch("election_audit.national.guard"),
        ):
            child.return_value.pid = 999999
            child.return_value.wait.return_value = 0
            overnight.execute(config_path)
        workspace = Path(config["workspace"])
        spec = _read_json(workspace / "production/workload.json")
        self.assertNotEqual(spec["job_id"], old_spec["job_id"])
        self.assertEqual(spec["source"]["root"], str(copied))
        self.assertEqual(spec["source_growth_budget_bytes"], 0)
        self.assertEqual(spec["scope"]["excluded_observations"], 1)
        acceptance = json.loads((workspace / "resume-acceptance.json").read_text())
        self.assertEqual(acceptance["counters"]["completed"], 2)
        self.assertEqual(acceptance["counters"]["reused_external"], 1)
        self.assertEqual(
            json.loads((workspace / "continuation-status.json").read_text())["stage"],
            "production_scope_finished",
        )


if __name__ == "__main__":
    unittest.main()
