import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import download_tse_logs as dl


def jez(content):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("logd.dat", content)
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body)), "ETag": '"test"'}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.collector = dl.Collector(self.root, 50, 0, 10)
        self.addCleanup(self.collector.db().close)
        self.directory = f"{dl.BASE}/ele2026/arquivo-urna/3221/dados/ac/01120/0001/0001"
        self.aux_url = self.directory + "/p003221-ac-m01120-z0001-s0001-aux.json"
        self.aux = {
            "f": "o",
            "st": "Totalizada",
            "hashes": [
                {
                    "hash": "aaa",
                    "st": "Totalizado",
                    "arq": [
                        {"tp": "log", "nm": "official-log.jez"},
                        {"tp": "bu", "nm": "official-bu.dat"},
                    ],
                },
                {
                    "hash": "bbb",
                    "st": "Rejeitado",
                    "arq": [{"tp": "log", "nm": "replacement-log.jez"}],
                },
            ],
        }
        self.item = ("ac", "01120", "0001", "0001", {"ns": "0001", "da": "26/10/2026"})

    def test_original_bytes_multiple_versions_and_resume(self):
        bodies = {
            self.aux_url: json.dumps(self.aux).encode(),
            self.directory + "/aaa/official-log.jez": jez(b"first"),
            self.directory + "/bbb/replacement-log.jez": jez(b"replacement"),
        }
        calls = []

        def open_response(request, timeout):
            calls.append(request.full_url)
            return Response(bodies[request.full_url])

        with patch.object(dl, "urlopen", side_effect=open_response):
            self.assertEqual(self.collector.section(self.item, "3221", "run1"), "downloaded")
            self.assertEqual(self.collector.section(self.item, "3221", "run2"), "downloaded")
            # A damaged local object must be fetched again, despite its manifest row.
            relative = (
                self.collector.db()
                .execute(
                    "SELECT path FROM files WHERE url=?",
                    (self.directory + "/aaa/official-log.jez",),
                )
                .fetchone()[0]
            )
            (self.root / relative).write_bytes(b"damaged")
            self.collector.section(self.item, "3221", "run3")
        self.assertEqual(calls.count(self.aux_url), 3)
        self.assertEqual(calls.count(self.directory + "/aaa/official-log.jez"), 2)
        self.assertEqual(calls.count(self.directory + "/bbb/replacement-log.jez"), 1)
        rows = self.collector.db().execute("SELECT url,path,sha256,bytes FROM files").fetchall()
        for url, path, digest, size in rows:
            self.assertEqual((self.root / path).read_bytes(), bodies[url])
            self.assertEqual(digest, hashlib.sha256(bodies[url]).hexdigest())
            self.assertEqual(size, len(bodies[url]))
        statuses = (
            self.collector.db()
            .execute("SELECT package_status FROM logs WHERE run='run1'")
            .fetchall()
        )
        self.assertEqual(set(statuses), {("Totalizado",), ("Rejeitado",)})

    def test_aggregates_and_unpublished_are_reported_without_requests(self):
        with patch.object(dl, "urlopen") as request:
            aggregated = (*self.item[:4], {"ns": "0002", "nsp": "0001"})
            unpublished = (*self.item[:3], "0003", {"ns": "0003"})
            self.assertEqual(self.collector.section(aggregated, "3221", "r"), "aggregated")
            self.assertEqual(self.collector.section(unpublished, "3221", "r"), "aux_not_published")
            request.assert_not_called()

    def test_missing_only_skips_section_requests_and_carries_provenance(self):
        bodies = {
            self.aux_url: json.dumps(self.aux).encode(),
            self.directory + "/aaa/official-log.jez": jez(b"first"),
            self.directory + "/bbb/replacement-log.jez": jez(b"replacement"),
        }
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ):
            self.collector.section(self.item, "3221", "run1")
        with patch.object(dl, "urlopen") as request:
            self.assertEqual(
                self.collector.section(self.item, "3221", "run2", missing_only=True), "downloaded"
            )
            request.assert_not_called()
        self.assertEqual(self.collector.reused_sections, 1)
        self.assertEqual(
            self.collector.db().execute("SELECT COUNT(*) FROM logs WHERE run='run2'").fetchone()[0],
            2,
        )
        self.assertEqual(
            self.collector.db()
            .execute("SELECT status FROM sections WHERE run='run2'")
            .fetchone()[0],
            "downloaded",
        )

    def test_missing_only_repairs_deleted_or_corrupt_logs(self):
        bodies = {
            self.aux_url: json.dumps(self.aux).encode(),
            self.directory + "/aaa/official-log.jez": jez(b"first"),
            self.directory + "/bbb/replacement-log.jez": jez(b"replacement"),
        }
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ):
            self.collector.section(self.item, "3221", "run1")
        url = self.directory + "/aaa/official-log.jez"
        relative = (
            self.collector.db().execute("SELECT path FROM files WHERE url=?", (url,)).fetchone()[0]
        )
        for run, corrupt in (("run2", True), ("run3", False)):
            if corrupt:
                (self.root / relative).write_bytes(b"damaged")
            else:
                (self.root / relative).unlink()
            calls = []

            def open_response(request, timeout):
                calls.append(request.full_url)
                return Response(bodies[request.full_url])

            with patch.object(dl, "urlopen", side_effect=open_response):
                self.collector.section(self.item, "3221", run, missing_only=True)
            self.assertEqual(calls, [self.aux_url, url])
            self.assertEqual((self.root / relative).read_bytes(), bodies[url])

    def test_changed_metadata_and_failed_sections_are_revisited(self):
        bodies = {
            self.aux_url: json.dumps(self.aux).encode(),
            self.directory + "/aaa/official-log.jez": jez(b"first"),
            self.directory + "/bbb/replacement-log.jez": jez(b"replacement"),
        }
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ):
            self.collector.section(self.item, "3221", "run1")
        changed = (*self.item[:4], {**self.item[4], "ha": "12:00:00"})
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ) as request:
            self.collector.section(changed, "3221", "run2", missing_only=True)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0].full_url, self.aux_url)
        with self.collector.db():
            self.collector.db().execute("UPDATE sections SET status='error'")
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ) as request:
            self.collector.section(changed, "3221", "run3", missing_only=True)
            self.assertEqual(request.call_count, 1)
        self.assertEqual(self.collector.reused_sections, 0)

    def test_official_phase_accepts_uppercase_and_rejects_simulation(self):
        self.aux["f"] = "O"
        self.assertEqual(len(list(dl.log_urls(self.aux, self.directory))), 2)
        for phase in ("s", "S", "", None):
            self.aux["f"] = phase
            with self.assertRaises(ValueError):
                list(dl.log_urls(self.aux, self.directory))
        index = {
            "f": "O",
            "cdp": "3221",
            "abr": [
                {"cd": "ac", "mu": [{"cd": "1120", "zon": [{"cd": "1", "sec": [{"ns": "2"}]}]}]}
            ],
        }
        self.assertEqual(len(list(dl.sections(index, "ac", "3221"))), 1)

    def test_cancelled_tasks_do_not_hide_original_failure(self):
        invalid = {**self.aux, "f": "s"}
        with patch.object(dl, "urlopen", return_value=Response(json.dumps(invalid).encode())):
            with self.assertRaisesRegex(RuntimeError, "Auxiliary file is not official"):
                self.collector.section(self.item, "3221", "run1")
        with patch.object(dl, "urlopen") as request:
            self.assertEqual(
                self.collector.section((*self.item[:3], "0002", self.item[4]), "3221", "run1"),
                "cancelled",
            )
            request.assert_not_called()
        self.assertIn("Auxiliary file is not official", self.collector.stop_reason)
        self.assertEqual(
            self.collector.db()
            .execute("SELECT COUNT(*) FROM sections WHERE status='error'")
            .fetchone()[0],
            1,
        )

    def test_invalid_zip_never_committed(self):
        with patch.object(dl, "urlopen", return_value=Response(b"<html>oops</html>")):
            with self.assertRaises(zipfile.BadZipFile):
                self.collector.fetch(self.directory + "/aaa/official-log.jez")
        self.assertEqual(self.collector.db().execute("SELECT COUNT(*) FROM files").fetchone()[0], 0)

    def test_throttle_stops_without_retry(self):
        error = dl.HTTPError(self.aux_url, 429, "too many requests", {}, None)
        with patch.object(dl, "urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                self.collector.fetch(self.aux_url, metadata=True)
            self.assertEqual(request.call_count, 1)
        self.assertTrue(self.collector.stop.is_set())

    def test_disk_reserve_prevents_commit(self):
        self.collector.reserve = 10**30
        with patch.object(dl, "urlopen", return_value=Response(b"{}")):
            with self.assertRaisesRegex(OSError, "Disk reserve"):
                self.collector.fetch(self.aux_url, metadata=True)
        self.assertEqual(self.collector.db().execute("SELECT COUNT(*) FROM files").fetchone()[0], 0)

    def test_selection_and_padding(self):
        config = {
            "pl": [
                {
                    "c": "ele2026",
                    "cd": "3221",
                    "dt": "25/10/2026",
                    "e": [{"cd": "6258", "t": "2", "tp": "8", "abr": [{"cp": [{"cd": "1"}]}]}],
                }
            ]
        }
        self.assertEqual(dl.runoff(config), ("3221", "6258"))
        config["pl"][0]["dt"] = "04/10/2026"
        with self.assertRaises(ValueError):
            dl.runoff(config)
        index = {
            "f": "o",
            "cdp": "3221",
            "abr": [
                {"cd": "ac", "mu": [{"cd": "1120", "zon": [{"cd": "1", "sec": [{"ns": "2"}]}]}]}
            ],
        }
        self.assertEqual(
            list(dl.sections(index, "ac", "3221"))[0][:4], ("ac", "01120", "0001", "0002")
        )
        with self.assertRaises(ValueError):
            list(dl.sections(index, "ac", "3220"))

    def test_rate_wait_does_not_hold_file_storage_lock(self):
        waiting = threading.Event()
        release = threading.Event()
        self.collector.next_request = time.monotonic() + 10

        def wait_for_release(delay):
            waiting.set()
            if not release.wait(2):
                raise AssertionError("Rate wait did not get released")
            return False

        with (
            patch.object(self.collector.stop, "wait", side_effect=wait_for_release),
            patch.object(dl, "urlopen", return_value=Response(b"{}")),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            future = pool.submit(self.collector.json, self.aux_url)
            try:
                self.assertTrue(waiting.wait(2))
                acquired = self.collector.lock.acquire(timeout=0.5)
                self.assertTrue(acquired, "Rate wait blocked storage/state updates")
                if acquired:
                    self.collector.lock.release()
            finally:
                release.set()
            self.assertEqual(future.result(timeout=2), {})

    def test_rate_budget_is_shared_by_workers(self):
        class FakeClock:
            value = 0.0

            def monotonic(self):
                return self.value

            def wait(self, delay):
                # Called under the rate lock, so clock updates are serialized.
                self.value += delay
                return False

        clock = FakeClock()
        self.collector.next_request = 0
        # Every request must pass the same limiter, irrespective of thread.
        with (
            patch.object(dl.time, "monotonic", side_effect=clock.monotonic),
            patch.object(self.collector.stop, "wait", side_effect=clock.wait),
            patch.object(dl, "urlopen", side_effect=lambda req, timeout: Response(b"{}")),
            ThreadPoolExecutor(max_workers=4) as pool,
        ):
            results = list(
                pool.map(self.collector.json, [f"{self.aux_url}?n={i}" for i in range(8)])
            )
        self.assertEqual(results, [{}] * 8)
        self.assertAlmostEqual(clock.value, 7 / 50)

    def test_parallel_section_manifest_and_missing_only_resume(self):
        items = [
            (*self.item[:3], f"{i:04d}", {"ns": f"{i:04d}", "da": "26/10/2026"})
            for i in range(1, 7)
        ]

        def open_response(request, timeout):
            if request.full_url.endswith("-aux.json"):
                return Response(json.dumps(self.aux).encode())
            return Response(jez(b"original log bytes"))

        with patch.object(dl, "urlopen", side_effect=open_response):
            statuses = list(
                dl.bounded_parallel_map(
                    lambda item: self.collector.section(item, "3221", "parallel1"),
                    items,
                    3,
                    self.collector.stop,
                )
            )
        self.assertEqual(statuses, ["downloaded"] * 6)
        self.assertFalse(self.collector.stop.is_set())
        self.assertEqual(
            self.collector.db()
            .execute("SELECT COUNT(*) FROM logs WHERE run='parallel1'")
            .fetchone()[0],
            12,
        )
        with patch.object(dl, "urlopen") as request:
            statuses = list(
                dl.bounded_parallel_map(
                    lambda item: self.collector.section(
                        item, "3221", "parallel2", missing_only=True
                    ),
                    items,
                    3,
                    self.collector.stop,
                )
            )
            request.assert_not_called()
        self.assertEqual(statuses, ["downloaded"] * 6)
        self.assertEqual(self.collector.reused_sections, 6)
        self.assertEqual(
            self.collector.db()
            .execute("SELECT COUNT(*) FROM logs WHERE run='parallel2'")
            .fetchone()[0],
            12,
        )

    def test_32_workers_share_one_connection_with_short_busy_timeout(self):
        self.collector.db().execute("PRAGMA busy_timeout=1")
        barrier = threading.Barrier(32)

        def worker(index):
            barrier.wait(timeout=5)
            connection_id = id(self.collector.db())
            for iteration in range(10):
                run = f"stress-{index}-{iteration}"
                with self.collector.transaction() as db:
                    db.execute("INSERT INTO runs VALUES (?,?,NULL,?)", (run, run, "running"))
                self.assertEqual(
                    self.collector.query("SELECT status FROM runs WHERE id=?", (run,), one=True),
                    ("running",),
                )
            return connection_id

        with ThreadPoolExecutor(max_workers=32) as pool:
            ids = list(pool.map(worker, range(32)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.collector.query("SELECT COUNT(*) FROM runs", one=True)[0], 320)

    def test_failed_manifest_transaction_rolls_back_all_rows(self):
        with self.assertRaisesRegex(ValueError, "interrupted update"):
            with self.collector.transaction() as db:
                db.execute("INSERT INTO runs VALUES ('atomic','now',NULL,'running')")
                raise ValueError("interrupted update")
        self.assertIsNone(self.collector.query("SELECT id FROM runs WHERE id='atomic'", one=True))
        with self.collector.transaction() as db:
            db.execute("INSERT INTO runs VALUES ('next','now',NULL,'finished')")
        self.assertEqual(
            self.collector.query("SELECT status FROM runs WHERE id='next'", one=True), ("finished",)
        )

    def test_cli_blocks_duplicate_downloader_before_opening_database(self):
        arguments = ["download_tse_logs.py", "--output", str(self.root)]
        with (
            dl.output_lock(self.root),
            patch.object(sys, "argv", arguments),
            patch.object(dl, "Collector") as collector,
            redirect_stderr(io.StringIO()) as errors,
        ):
            with self.assertRaises(SystemExit) as result:
                dl.main()
            self.assertEqual(result.exception.code, 2)
            self.assertIn("Another downloader", errors.getvalue())
            collector.assert_not_called()
        # The persistent lock file must not prevent a later process from resuming.
        with dl.output_lock(self.root):
            self.assertTrue((self.root / ".download.lock").exists())

    def test_cli_completes_with_parallel_downloads_and_closes_manifest(self):
        config = {
            "pl": [
                {
                    "c": "ele2026",
                    "cd": "3221",
                    "dt": "25/10/2026",
                    "e": [{"cd": "6258", "t": "2", "tp": "8", "abr": [{"cp": [{"cd": "1"}]}]}],
                }
            ]
        }
        index = {
            "f": "o",
            "cdp": "3221",
            "abr": [
                {
                    "cd": "ac",
                    "mu": [
                        {
                            "cd": "1120",
                            "zon": [
                                {
                                    "cd": "1",
                                    "sec": [
                                        {"ns": str(i), "da": "26/10/2026"} for i in range(1, 5)
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        def open_response(request, timeout):
            if request.full_url.endswith("ele-c.json"):
                return Response(json.dumps(config).encode())
            if request.full_url.endswith("-cs.json"):
                return Response(json.dumps(index).encode())
            if request.full_url.endswith("-aux.json"):
                return Response(json.dumps(self.aux).encode())
            return Response(jez(b"test log"))

        arguments = [
            "download_tse_logs.py",
            "--output",
            str(self.root),
            "--ufs",
            "ac",
            "--workers",
            "32",
            "--rps",
            "50",
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch.object(dl, "urlopen", side_effect=open_response),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(dl.main(), 0)
        report = json.loads((self.root / "coverage.json").read_text())
        self.assertEqual(report["status"], "finished")
        self.assertEqual(report["sections"], {"downloaded": 4})
        self.assertEqual(report["saved_log_versions"], 8)
        self.assertFalse(report["national_coverage"])
        with dl.output_lock(self.root):
            pass

        # A complete state must produce no section requests on the next run.
        def config_only(request, timeout):
            if request.full_url.endswith("ele-c.json"):
                return Response(json.dumps(config).encode())
            if request.full_url.endswith("-cs.json"):
                return Response(json.dumps(index).encode())
            raise AssertionError("Completed state made a section request")

        external = self.root / "ssd" / "manifest.sqlite"
        with (
            patch.object(sys, "argv", arguments + ["--missing-only", "--manifest", str(external)]),
            patch.object(dl, "urlopen", side_effect=config_only),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(dl.main(), 0)
        report = json.loads((self.root / "coverage.json").read_text())
        self.assertIn("SKIPPED", output.getvalue())
        self.assertIn("already saved=4", output.getvalue())
        self.assertEqual(report["reused_sections"], 4)
        self.assertEqual(report["sections"], {"downloaded": 4})
        self.assertEqual(report["saved_log_versions"], 8)
        self.assertEqual(report["activity"].get("new_logs", 0), 0)
        self.assertEqual(report["activity"]["requests"], 2)
        self.assertEqual(report["states"]["ac"]["processed"], 0)
        self.assertEqual(dl.manifest_path(self.root), external.resolve())
        # A later resume follows the marker even if --manifest is omitted.
        with (
            patch.object(sys, "argv", arguments + ["--missing-only"]),
            patch.object(dl, "urlopen", side_effect=config_only),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(dl.main(), 0)
        report = json.loads((self.root / "coverage.json").read_text())
        self.assertEqual(report["manifest"], str(external.resolve()))
        self.assertEqual(report["reused_sections"], 4)

    def seed_section_for_bulk_resume(self):
        bodies = {
            self.aux_url: json.dumps(self.aux).encode(),
            self.directory + "/aaa/official-log.jez": jez(b"first"),
            self.directory + "/bbb/replacement-log.jez": jez(b"replacement"),
        }
        with patch.object(
            dl, "urlopen", side_effect=lambda req, timeout: Response(bodies[req.full_url])
        ):
            self.collector.section(self.item, "3221", "001-seed")
        return bodies

    def test_bulk_resume_uses_one_commit_without_reading_saved_contents(self):
        self.seed_section_for_bulk_resume()
        aggregate = (*self.item[:3], "0002", {"ns": "0002", "nsp": "0001"})
        statements = []
        self.collector.db().set_trace_callback(statements.append)
        try:
            with (
                patch.object(
                    Path, "read_bytes", side_effect=AssertionError("Read an already-validated file")
                ),
                patch.object(dl, "urlopen") as network,
            ):
                pending, skipped = self.collector.prepare_resume(
                    [self.item, aggregate], "002-resume"
                )
                network.assert_not_called()
        finally:
            self.collector.db().set_trace_callback(None)
        self.assertEqual(pending, [])
        self.assertEqual(skipped, {"downloaded": 1, "aggregated": 1})
        self.assertEqual(sum(s == "BEGIN IMMEDIATE" for s in statements), 1)
        self.assertEqual(sum(s == "COMMIT" for s in statements), 1)
        self.assertEqual(
            self.collector.query("SELECT COUNT(*) FROM logs WHERE run='002-resume'", one=True)[0], 2
        )

    def test_bulk_resume_detects_missing_and_resized_files(self):
        bodies = self.seed_section_for_bulk_resume()
        url = self.directory + "/aaa/official-log.jez"
        path = (
            self.root
            / self.collector.query("SELECT path FROM files WHERE url=?", (url,), one=True)[0]
        )
        for missing in (False, True):
            with self.subTest(missing=missing):
                if missing:
                    path.unlink()
                else:
                    path.write_bytes(b"short")
                pending, skipped = self.collector.prepare_resume([self.item], f"resume-{missing}")
                self.assertEqual(pending, [self.item])
                self.assertEqual(skipped, {})
                path.write_bytes(bodies[url])

    def test_bulk_strict_resume_detects_same_size_corruption(self):
        self.seed_section_for_bulk_resume()
        url = self.directory + "/aaa/official-log.jez"
        path = (
            self.root
            / self.collector.query("SELECT path FROM files WHERE url=?", (url,), one=True)[0]
        )
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        pending, skipped = self.collector.prepare_resume([self.item], "002-quick")
        self.assertEqual(pending, [])
        self.assertEqual(skipped["downloaded"], 1)
        pending, skipped = self.collector.prepare_resume(
            [self.item], "003-strict", verify_existing=True
        )
        self.assertEqual(pending, [self.item])
        self.assertEqual(skipped, {})

    def test_bulk_resume_revisits_changed_and_incomplete_sections(self):
        self.seed_section_for_bulk_resume()
        changed = (*self.item[:4], {**self.item[4], "ha": "15:00:00"})
        pending, _ = self.collector.prepare_resume([changed], "002-changed")
        self.assertEqual(pending, [changed])
        with self.collector.transaction() as db:
            db.execute("DELETE FROM logs WHERE filename='replacement-log.jez'")
        pending, _ = self.collector.prepare_resume([self.item], "003-incomplete")
        self.assertEqual(pending, [self.item])

    def test_external_manifest_copy_includes_committed_wal_and_preserves_source(self):
        with self.collector.transaction() as db:
            db.execute("INSERT INTO runs VALUES ('before-copy','now',NULL,'finished')")
        self.assertTrue((self.root / "manifest.sqlite-wal").exists())
        external = self.root / "ssd" / "separate.sqlite"
        with dl.output_lock(self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(dl.configure_manifest(self.root, external), external.resolve())
        self.assertTrue((self.root / "manifest.sqlite").exists())
        self.assertEqual(dl.manifest_path(self.root), external.resolve())
        with sqlite3.connect(external) as db:
            self.assertEqual(
                db.execute("SELECT status FROM runs WHERE id='before-copy'").fetchone(),
                ("finished",),
            )
            db.execute("INSERT INTO runs VALUES ('external-only','later',NULL,'finished')")
        self.assertIsNone(
            self.collector.query("SELECT id FROM runs WHERE id='external-only'", one=True)
        )
        self.assertEqual(dl.configure_manifest(self.root, external), external.resolve())

    def test_external_manifest_refuses_to_overwrite_existing_target(self):
        target = self.root / "existing.sqlite"
        target.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            dl.configure_manifest(self.root, target)
        self.assertEqual(target.read_bytes(), b"do not overwrite")
        self.assertFalse((self.root / "manifest-location.json").exists())

    def test_missing_external_manifest_does_not_silently_start_fresh(self):
        target = self.root / "missing.sqlite"
        (self.root / "manifest-location.json").write_text(
            json.dumps({"version": 1, "path": str(target)})
        )
        with self.assertRaisesRegex(ValueError, "External manifest unavailable"):
            dl.manifest_path(self.root)
        self.assertFalse(target.exists())


class ParallelSchedulingTests(unittest.TestCase):
    def test_slow_task_does_not_prevent_new_work(self):
        gate = threading.Event()
        released = []

        def task(index):
            if index == 0:
                released.append(gate.wait(2))
            elif index == 6:
                gate.set()
            return index

        result = list(dl.bounded_parallel_map(task, range(10), 2, threading.Event()))
        self.assertTrue(released[0], "Later work stalled behind the first task")
        self.assertEqual(sorted(result), list(range(10)))

    def test_failure_stops_scheduling_and_preserves_reason(self):
        stop = threading.Event()
        consumed = []

        def items():
            for index in range(100):
                consumed.append(index)
                yield index

        def task(index):
            if index == 0:
                raise ValueError("original failure")
            return index

        with self.assertRaisesRegex(ValueError, "original failure"):
            list(dl.bounded_parallel_map(task, items(), 1, stop))
        self.assertTrue(stop.is_set())
        self.assertLessEqual(len(consumed), 2)

    def test_consumer_interrupt_stops_and_cancels_queued_work(self):
        stop = threading.Event()

        def task(index):
            if index >= 2:
                stop.wait(2)
            return index

        results = dl.bounded_parallel_map(task, range(100), 2, stop)
        next(results)
        results.close()
        self.assertTrue(stop.is_set())


if __name__ == "__main__":
    unittest.main()
