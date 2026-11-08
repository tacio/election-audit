"""Certified staging copies every object exactly, resumes safely and fails closed."""

import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from election_audit import source_staging as staging


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class StagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source = base / "source"
        self.bodies = {}
        rows = []
        for index in range(12):
            body = f"object {index}\n".encode() * (index + 1)
            object_sha = hashlib.sha256(body).hexdigest()
            suffix = ".json" if index % 3 == 0 else ".jez"
            relative = f"objects/{object_sha[:2]}/{object_sha}{suffix}"
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            self.bodies[relative] = body
            rows.append((f"https://example.invalid/{index}", relative, object_sha, len(body)))
        # A second URL for the same object must not be copied twice.
        rows.append(("https://example.invalid/alias", *rows[0][1:]))
        self.manifest = base / "manifest-r2.sqlite"
        with contextlib.closing(sqlite3.connect(self.manifest)) as db:
            db.execute("CREATE TABLE files(url TEXT PRIMARY KEY, path, sha256, bytes)")
            db.executemany("INSERT INTO files VALUES(?,?,?,?)", rows)
            db.commit()
        self.certificate = base / "certificate-r2.json"
        self.certificate.write_text(
            json.dumps(
                {
                    "round": 2,
                    "root": str(self.source),
                    "manifest_sha256": digest(self.manifest),
                    "objects": len(self.bodies),
                    "bytes": sum(len(b) for b in self.bodies.values()),
                }
            )
        )
        self.destination = base / "stage" / "turno-2"

    def copy(self, **options):
        return staging.stage(
            self.certificate, self.manifest, self.destination, floor_gib=0, **options
        )

    def test_copy_is_exact_read_only_and_certified(self) -> None:
        for order in ("path", "inode"):
            with self.subTest(order=order):
                result = self.copy(order=order)
                for relative, body in self.bodies.items():
                    target = self.destination / relative
                    self.assertEqual(target.read_bytes(), body)
                    self.assertEqual(os.stat(target).st_mode & 0o777, 0o444)
                self.assertEqual(result["objects"], len(self.bodies))
                self.assertEqual(
                    digest(self.destination / "manifest.sqlite"), digest(self.manifest)
                )
                written = json.loads((self.destination / "staging-certificate.json").read_text())
                self.assertEqual(written["manifest_sha256"], digest(self.manifest))
                self.assertFalse(written["semantic_inspection"])
                self.assertEqual(
                    json.loads((self.destination / "staging-status.json").read_text())["stage"],
                    "finished",
                )
                self.destination = self.destination.with_name(self.destination.name + "-b")

    def test_existing_destination_is_refused_without_resume(self) -> None:
        self.destination.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.copy()

    def test_wrong_manifest_and_unreconciled_certificate_fail_closed(self) -> None:
        certificate = json.loads(self.certificate.read_text())
        certificate["manifest_sha256"] = "0" * 64
        self.certificate.write_text(json.dumps(certificate))
        with self.assertRaisesRegex(ValueError, "certificate digest"):
            self.copy()
        certificate["manifest_sha256"] = digest(self.manifest)
        certificate["objects"] += 1
        self.certificate.write_text(json.dumps(certificate))
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.copy()

    def test_corrupt_source_body_stops_the_copy(self) -> None:
        relative = sorted(self.bodies)[3]
        path = self.source / relative
        path.write_bytes(b"X" * len(self.bodies[relative]))
        with self.assertRaisesRegex(ValueError, "Source digest mismatch"):
            self.copy(order="path")
        status = json.loads((self.destination / "staging-status.json").read_text())
        self.assertEqual(status["stage"], "FAILED_STOPPED")
        self.assertFalse((self.destination / "staging-certificate.json").exists())

    def test_interrupted_copy_resumes_without_recopying_synced_objects(self) -> None:
        original = staging.read_verified
        calls = []

        def failing(root, relative, *args, **kwargs):
            calls.append(relative)
            if len(calls) == 7:
                raise KeyboardInterrupt
            return original(root, relative, *args, **kwargs)

        with (
            patch.object(staging, "BATCH_OBJECTS", 3),
            patch.object(staging, "read_verified", failing),
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.copy(order="path")
        with contextlib.closing(sqlite3.connect(self.destination / "staging-ledger.sqlite")) as db:
            committed = {row[0] for row in db.execute("SELECT path FROM staged")}
        self.assertEqual(len(committed), 6)
        with self.assertRaises(FileExistsError):
            self.copy(order="path")
        with self.assertRaisesRegex(ValueError, "binding"):
            self.copy(order="inode", resume=True)
        seen = []

        def recording(root, relative, *args, **kwargs):
            seen.append(relative)
            return original(root, relative, *args, **kwargs)

        with patch.object(staging, "read_verified", recording):
            result = self.copy(order="path", resume=True)
        self.assertFalse(committed & set(seen))
        self.assertEqual(result["objects"], len(self.bodies))

    def test_destination_tampering_is_detected(self) -> None:
        self.copy(order="path")
        rows = staging.manifest_objects(self.manifest)
        target = self.destination / rows[0][0]
        os.chmod(target, 0o644)
        target.write_bytes(b"Y" * rows[0][2])
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            staging.verify_destination(self.destination, rows)
        target.write_bytes(self.bodies[rows[0][0]])
        extra = self.destination / "objects" / "zz" / "extra.jez"
        extra.parent.mkdir()
        extra.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            staging.verify_destination(self.destination, rows)

    def test_benchmark_reads_disjoint_windows_and_refuses_existing_output(self) -> None:
        output = Path(self.temp.name) / "bench" / "results.json"
        report = staging.benchmark(
            self.certificate, self.manifest, output, window=3, orders=("url", "path", "inode")
        )
        starts = [r["window_start"] for r in report["results"]]
        self.assertEqual(len(set(starts)), 3)
        self.assertTrue(all(r["objects"] == 3 for r in report["results"]))
        with self.assertRaises(FileExistsError):
            staging.benchmark(self.certificate, self.manifest, output, window=3)

    def test_physical_order_when_fiemap_is_supported(self) -> None:
        rows = staging.manifest_objects(self.manifest)
        try:
            ordered = staging.order_rows(self.source, rows, "physical")
        except OSError as exc:
            self.skipTest(f"FIEMAP unavailable here: {exc}")
        self.assertEqual(sorted(ordered), sorted(rows))


if __name__ == "__main__":
    unittest.main()
