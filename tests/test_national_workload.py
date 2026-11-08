"""National scopes exclude protected content before access and resume in bounded rows."""

import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from election_audit.national import _read_json, _write_json
from election_audit.national_storage import process_compact_original
from election_audit.national_tuning import VERSION as TUNING_VERSION
from election_audit.national_tuning import code_pins, limits
from election_audit.national_workload import (
    _requirements,
    initialise,
    iter_observations,
    preflight,
    prepare,
    run,
    status,
)
from election_audit.source_inventory import canonical, hash_file


class WorkloadExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.rows = []
        for section in ("0001", "0002", "0003"):
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(
                    "logd.dat",
                    f"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message {section}\ttoken\n".encode(),
                )
            body = archive.getvalue()
            sha = hashlib.sha256(body).hexdigest()
            source = self.raw / "objects" / sha[:2] / (sha + ".jez")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(body)
            self.rows.append(
                {
                    "uf": "go",
                    "municipality": "01007",
                    "zone": "0001",
                    "section": section,
                    "url": f"https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/go/01007/0001/{section}/package/o-log.jez",
                    "path": str(source.relative_to(self.raw)),
                    "sha256": sha,
                    "bytes": len(body),
                }
            )
        self._profile()
        self.excluded = self.root / "excluded.json"
        _write_json(
            self.excluded,
            {
                "version": "structural-sample-exclusions-v1",
                "round": 2,
                "section_keys": [["go", "01007", "0001", "0003"]],
            },
        )
        self.reco = self.root / "recommended.json"
        _write_json(
            self.reco,
            {
                "version": TUNING_VERSION,
                "code": code_pins(),
                "workers": 1,
                "event_batch_rows": 2,
                "resources": limits(
                    hdd_reserve_bytes=0, ssd_reserve_bytes=0, scratch_bytes=1024**3
                ),
            },
        )
        self.config = self.root / "config"
        self.store = self.root / "store"
        self.scratch = self.root / "scratch"

    def _profile(self) -> None:
        path = self.profile / "profile.sqlite"
        if path.exists():
            path.unlink()
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE sources(uf TEXT,municipality TEXT,zone TEXT,section TEXT,url TEXT PRIMARY KEY,path TEXT,sha256 TEXT,bytes INTEGER)"
            )
            db.executemany(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                (tuple(r.values()) for r in self.rows),
            )
            db.commit()
        doc = self.profile / "profile.json"
        if doc.exists():
            doc.unlink()
            Path(str(doc) + ".sha256").unlink()
        _write_json(
            doc,
            {
                "source": {
                    "round": 2,
                    "root": str(self.raw),
                    "manifest": str(self.root / "original.sqlite"),
                    "ufs": ["go"],
                },
                "source_run": {"id": "finished-input", "status": "finished"},
                "source_rows_sha256": hashlib.sha256(canonical(self.rows)).hexdigest(),
                "files": {
                    "profile.sqlite": dict(zip(("sha256", "bytes"), hash_file(path), strict=True))
                },
            },
        )

    def configure(self, reuse_stores=()):
        return prepare(
            self.profile,
            self.excluded,
            self.reco,
            self.config,
            self.store,
            self.scratch,
            output_budget_bytes=16 * 1024**2,
            future_budget_bytes=0,
            reuse_stores=reuse_stores,
        )

    def execute(self, **kwargs):
        with (
            patch("election_audit.national_workload.configure_production"),
            patch("election_audit.national.guard"),
        ):
            return run(self.config, **kwargs)

    def test_protected_missing_body_never_opened_and_bounded_resume(self) -> None:
        spec = self.configure()
        (self.raw / self.rows[2]["path"]).unlink()
        first = self.execute(max_objects=1)
        self.assertEqual(first["counters"]["completed"], 1)
        final = self.execute()
        self.assertEqual(final["state"], "eligible_scope_complete")
        self.assertEqual(final["counters"]["completed"], 2)
        self.assertEqual(final["scope"]["excluded_observations"], 1)
        before = final["counters"]
        again = self.execute()
        self.assertEqual(again["counters"], before)
        self.assertEqual(again["objects_this_attempt"], 0)
        self.assertFalse((self.store / "objects").exists())
        self.assertEqual(spec["scope"]["source_observations"], 3)

    def test_observation_reader_preserves_unknowns_and_protected_coverage(self) -> None:
        self.configure()
        self.execute(max_objects=1)
        rows = list(iter_observations(self.config))
        self.assertEqual(len(rows), 3)
        protected = next(r for r in rows if r["section"] == "0003")
        self.assertEqual(protected["work_state"], "deferred_protected_or_stress")
        self.assertIsNone(protected["events"])
        self.assertIsNone(protected["artifact"])
        pending = next(r for r in rows if r["work_state"] == "pending")
        self.assertIsNone(pending["events"])
        self.assertEqual(sum(r["events"] or 0 for r in rows), 1)
        self.assertTrue(
            all(r["scientific_eligibility"] == "unavailable_structural_only" for r in rows)
        )

    def test_identical_content_alias_of_protected_section_is_excluded(self) -> None:
        alias = {
            **self.rows[2],
            "section": "0004",
            "url": self.rows[2]["url"].replace("0003", "0004"),
        }
        self.rows.append(alias)
        self._profile()
        spec = self.configure()
        (self.raw / self.rows[2]["path"]).unlink()
        final = self.execute()
        self.assertEqual(spec["scope"]["excluded_observations"], 2)
        self.assertEqual(final["counters"]["completed"], 2)

    def test_reuses_only_verified_explicit_external_checkpoint(self) -> None:
        old = self.root / "old-store"
        with patch("election_audit.national.guard"):
            artifact = process_compact_original(
                {**self.rows[0], "source_root": str(self.raw)},
                old,
                self.scratch,
                output_budget_bytes=8 * 1024**2,
                batch_rows=2,
            )
        self.configure(reuse_stores=[old])
        result = self.execute()
        self.assertEqual(result["counters"]["reused_external"], 1)
        with closing(sqlite3.connect(self.store / "work.sqlite")) as db:
            row = db.execute(
                "SELECT artifact,allocated_bytes FROM work WHERE sha256=?",
                (self.rows[0]["sha256"],),
            ).fetchone()
        self.assertEqual(row, (str(artifact), 0))
        self.assertFalse((self.store / "objects").exists())

    def test_failure_is_durable_and_explicit_retry_preserves_attempts(self) -> None:
        self.configure()
        source = self.raw / self.rows[0]["path"]
        original = source.read_bytes()
        source.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.execute()
        self.assertEqual(status(self.config)["counters"]["failed"], 1)
        source.write_bytes(original)
        result = self.execute(retry_failed=True)
        self.assertEqual(result["state"], "eligible_scope_complete")
        with closing(sqlite3.connect(self.store / "work.sqlite")) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM attempts WHERE state='failed'").fetchone()[0], 1
            )

    def test_corrupt_scope_and_changed_exclusions_fail_before_processing(self) -> None:
        self.configure()
        scope = initialise(self.config)
        (scope / "observations.sqlite").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            self.execute()
        self.excluded.write_text("{}")
        with self.assertRaisesRegex(ValueError, "registry changed"):
            preflight(self.config)

    def test_capacity_and_unmounted_volume_stop_before_store_creation(self) -> None:
        self.configure()
        with patch("election_audit.national_workload.shutil.disk_usage") as usage:
            usage.return_value.free = 1
            with self.assertRaisesRegex(OSError, "capacity allowance"):
                preflight(self.config)
        self.assertFalse(self.store.exists())
        with patch("pathlib.Path.is_mount", return_value=False):
            with self.assertRaisesRegex(OSError, "not mounted"):
                preflight(self.config)

    def test_malformed_protected_geography_is_rejected_before_source_access(self) -> None:
        self.excluded.unlink()
        Path(str(self.excluded) + ".sha256").unlink()
        _write_json(
            self.excluded,
            {
                "version": "structural-sample-exclusions-v1",
                "round": 2,
                "section_keys": [["GO", "01007", "0001", "0003"]],
            },
        )
        with self.assertRaisesRegex(ValueError, "exclusion geography"):
            self.configure()
        self.assertFalse(self.store.exists())

    def test_shared_volume_reservations_are_added_once_with_largest_floor(self) -> None:
        spec = {
            "resources": {
                "hdd_reserve_bytes": 2,
                "ssd_reserve_bytes": 10,
                "scratch_budget_bytes": 8,
            },
            "output_budget_bytes": 100,
            "future_derived_budget_bytes": 40,
            "source_growth_budget_bytes": 30,
        }
        self.assertEqual(
            _requirements(spec, 0, {"store": 1, "source": 1, "scratch": 1}),
            {"store": 188, "source": 188, "scratch": 188},
        )
        self.assertEqual(
            _requirements(spec, 0, {"store": 1, "source": 2, "scratch": 2}),
            {"store": 142, "source": 48, "scratch": 48},
        )
        self.assertEqual(
            _requirements(spec, 20, {"store": 1, "source": 2, "scratch": 3}),
            {"store": 122, "source": 32, "scratch": 18},
        )

    def test_frozen_launcher_status_and_tampered_runtime_fail_closed(self) -> None:
        self.configure()
        spec = _read_json(self.config / "workload.json")
        self.assertIn("scripts/download_tse_logs.py", spec["runtime_files"])
        self.assertIn("uv.lock", spec["runtime_files"])
        origin = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import sys;sys.path.insert(0,sys.argv[1]);import scripts.download_tse_logs as module;print(module.__file__)",
                str(self.config / "runtime"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(origin.returncode, 0, origin.stderr)
        self.assertEqual(
            Path(origin.stdout.strip()), self.config / "runtime/scripts/download_tse_logs.py"
        )
        child = subprocess.run(
            [sys.executable, "-B", str(self.config / "run_frozen.py"), "status"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn('"state": "not_started"', child.stdout)
        (self.raw / self.rows[2]["path"]).unlink()
        child = subprocess.run(
            [sys.executable, "-B", str(self.config / "run_frozen.py"), "run", "--max-objects", "1"],
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn('"objects_this_attempt": 1', child.stdout)
        with closing(sqlite3.connect(self.store / "work.sqlite")) as db:
            artifact = Path(
                db.execute("SELECT artifact FROM work WHERE status='complete'").fetchone()[0]
            )
        checkpoint = _read_json(artifact / "checkpoint.json")
        self.assertEqual(checkpoint["resources"]["aggregate_memory_budget_bytes"], 4 * 1024**3)
        self.assertEqual(checkpoint["resources"]["event_batch_rows"], 2)
        target = self.config / "runtime/election_audit/national_storage.py"
        target.write_text(target.read_text() + "\n# changed\n")
        child = subprocess.run(
            [sys.executable, "-B", str(self.config / "run_frozen.py"), "status"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("Frozen runtime changed", child.stderr)
