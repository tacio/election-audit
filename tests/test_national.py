"""Disk-backed national census, bounded structural output and explicit failures."""

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq

from election_audit.national import (
    LIMITS,
    VERSION,
    freeze_census,
    guard,
    preflight,
    process_object,
    read_config,
    resume,
    status,
)


@contextmanager
def database(path):
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


class NationalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.raw = self.base / "raw"
        self.raw.mkdir()
        self.store = self.base / "store"
        self.scratch = self.base / "scratch"
        self.manifest = self.raw / "manifest.sqlite"
        with database(self.manifest) as db:
            db.executescript("""
                CREATE TABLE files(url TEXT PRIMARY KEY,path TEXT,sha256 TEXT,bytes INTEGER,fetched_at TEXT,etag TEXT,last_modified TEXT);
                CREATE TABLE sections(run TEXT,uf TEXT,municipality TEXT,zone TEXT,section TEXT,status TEXT,metadata TEXT,details TEXT);
            """)
        self.spec = {
            "round": 2,
            "root": str(self.raw),
            "manifest": str(self.manifest),
            "ufs": ["ac"],
        }
        self.config = {"version": VERSION, "sources": [self.spec]}
        self.prefix = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/"
        self.save(
            self.prefix + "config/ac/ac-p003221-cs.json",
            json.dumps({"f": "o", "cdp": "3221", "abr": []}).encode(),
        )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(
                "logd.dat",
                "25/10/2026 08:00:00\tINFO\t123\tVOTA\tEleitor foi habilitado\ttoken\n".encode(
                    "latin-1"
                ),
            )
        self.log = self.save(
            self.prefix + "dados/ac/01007/0001/0001/pkg/a-log.jez", archive.getvalue()
        )

    def save(self, url, body):
        h = hashlib.sha256(body).hexdigest()
        path = self.raw / "objects" / h
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(body)
        with database(self.manifest) as db:
            db.execute(
                "INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                (
                    url,
                    str(path.relative_to(self.raw)),
                    h,
                    len(body),
                    "2026-10-30T00:00:00Z",
                    None,
                    None,
                ),
            )
        return {
            "url": url,
            "path": str(path.relative_to(self.raw)),
            "sha256": h,
            "bytes": len(body),
            "source_root": str(self.raw),
        }

    def test_round_mismatch_rejected_before_freezing(self):
        self.spec["round"] = 1
        with self.assertRaisesRegex(ValueError, "another round"):
            preflight(self.config, self.store, self.scratch, reserve_bytes=0)
        self.assertFalse(self.store.exists())

    def test_config_has_explicit_sources_and_known_ufs(self):
        path = self.base / "config.json"
        path.write_text(json.dumps(self.config))
        self.assertEqual(read_config(path)["sources"][0]["round"], 2)
        self.spec["ufs"] = ["xx"]
        path.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            read_config(path)

    def test_resume_content_dedup_and_no_source_writes(self):
        self.save(
            self.prefix + "dados/ac/01007/0001/0002/pkg/b-log.jez",
            (self.raw / self.log["path"]).read_bytes(),
        )
        before = self.manifest.read_bytes()
        with patch("election_audit.national.guard"):
            a = resume(self.config, self.store, self.scratch, reserve_bytes=0, max_objects=3)
            b = resume(self.config, self.store, self.scratch, reserve_bytes=0, max_objects=3)
        self.assertEqual(a, b)
        self.assertEqual(a["structural_objects"], 1)
        self.assertEqual(a["events"], 1)
        self.assertFalse(a["full_pipeline_complete"])
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(len(list((self.store / "objects").glob("*/*"))), 2)
        event_file = next((self.store / "structural").glob("*/*/events.parquet"))
        event = json.loads(pq.read_table(event_file)["payload"][0].as_py())
        self.assertNotIn("token", json.dumps(event))
        self.assertIn("record_locator", event)

    def test_changed_original_never_publishes_structural_success(self):
        (self.raw / self.log["path"]).write_bytes(b"corrupt")
        with patch("election_audit.national.guard"):
            with self.assertRaisesRegex(ValueError, "Original changed"):
                resume(self.config, self.store, self.scratch, reserve_bytes=0, max_objects=3)
        self.assertEqual(list((self.store / "structural").glob("*/*/artifact.json")), [])

    def test_metadata_tampering_and_unsafe_output_rejected(self):
        with patch("election_audit.national.guard"):
            p = freeze_census(self.config, self.store, self.scratch, reserve_bytes=0)
        (p / "census.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "checksum"):
            freeze_census(self.config, self.store, self.scratch, reserve_bytes=0)
        with self.assertRaisesRegex(ValueError, "outside raw"):
            freeze_census(self.config, self.raw / "derived", self.scratch, reserve_bytes=0)

    def test_capacity_failure_no_complete_artifacts(self):
        with patch("election_audit.national.guard", side_effect=OSError("Capacity reserve")):
            with self.assertRaises(OSError):
                resume(self.config, self.store, self.scratch, reserve_bytes=0, max_objects=3)
        self.assertEqual(list(self.store.glob("censuses/*/census.json")), [])

    def test_census_streams_above_old_row_limit_and_retains_history(self):
        with database(self.manifest) as db:
            db.executemany(
                "INSERT INTO sections VALUES (?,?,?,?,?,?,?,?)",
                (
                    (str(i), "ac", "01007", "0001", str(i), "missing", "{}", None)
                    for i in range(100_001)
                ),
            )
        with patch("election_audit.national.guard"):
            p = freeze_census(self.config, self.store, self.scratch, reserve_bytes=0)
        with database(p / "census.sqlite") as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM section_observation").fetchone()[0], 100_001
            )

    def test_unbounded_run_requires_explicit_reviewed_output_budget(self):
        with self.assertRaisesRegex(ValueError, "explicit output budget"):
            resume(self.config, self.store, self.scratch)
        self.assertFalse(self.store.exists())

    def test_output_budget_exhaustion_never_publishes_success(self):
        with patch("election_audit.national.guard"):
            with self.assertRaisesRegex(OSError, "output budget exhausted"):
                resume(self.config, self.store, self.scratch, output_budget_bytes=1)
        self.assertEqual(list((self.store / "structural").glob("*/*/artifact.json")), [])
        self.assertEqual(list(self.scratch.glob("national-object-*")), [])

    def test_shared_scratch_budget_and_cleanup(self):
        with patch("election_audit.national.guard"), patch.dict(LIMITS, {"spill_bytes": 100}):
            with self.assertRaisesRegex(OSError, "scratch budget exceeded"):
                resume(self.config, self.store, self.scratch, max_objects=1)
        self.assertEqual(list((self.store / "structural").glob("*/*/artifact.json")), [])
        self.assertEqual(list(self.scratch.glob("national-object-*")), [])

    def test_invalid_hash_rejected_before_content_path_creation(self):
        bad = {**self.log, "sha256": "../" + "x" * 61}
        with self.assertRaisesRegex(ValueError, "Invalid file metadata"):
            process_object(bad, self.store, self.scratch)
        self.assertFalse(self.store.exists())

    def test_scoped_status_excludes_unrelated_shared_content(self):
        with patch("election_audit.national.guard"):
            result = resume(self.config, self.store, self.scratch, max_objects=1)
            other_body = io.BytesIO()
            with zipfile.ZipFile(other_body, "w") as z:
                z.writestr("logd.dat", b"bad line\n")
            other = self.save(
                self.prefix + "dados/ac/01007/0001/0003/pkg/c-log.jez", other_body.getvalue()
            )
            process_object(other, self.store, self.scratch)
        from election_audit.source_inventory import digest

        scoped = status(self.store, config_id=digest(self.config))
        self.assertEqual(scoped["structural_objects"], result["structural_objects"])
        self.assertEqual(status(self.store)["structural_objects"], 2)
        from contextlib import redirect_stdout

        from election_audit.national import national_main

        config_path = self.base / "scope.json"
        config_path.write_text(json.dumps(self.config))
        with redirect_stdout(io.StringIO()) as output:
            national_main(["status", "--store", str(self.store), "--config", str(config_path)])
        self.assertEqual(json.loads(output.getvalue())["structural_objects"], 1)

    def test_reuse_checks_frozen_original_and_symlink(self):
        with patch("election_audit.national.guard"):
            resume(self.config, self.store, self.scratch, max_objects=1)
        event = next((self.store / "structural").glob("*/*/events.parquet"))
        saved = self.base / "saved-events.parquet"
        event.replace(saved)
        event.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, "Unsafe artifact path"):
            process_object(self.log, self.store, self.scratch)
        event.unlink()
        saved.replace(event)
        original = self.store / "objects" / self.log["sha256"][:2] / self.log["sha256"]
        original.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "Frozen original corrupt"):
            process_object(self.log, self.store, self.scratch)

    def test_concurrent_census_and_run_lock_fail_without_duplicate_work(self):
        from election_audit.national import _lock

        with _lock(self.store, "national"):
            with self.assertRaises(BlockingIOError):
                resume(self.config, self.store, self.scratch, max_objects=1)
        self.assertEqual(list(self.store.glob("censuses/*/census.json")), [])

    def test_hdd_reserve_floor_survives_smaller_requested_reserve(self):
        from collections import namedtuple

        disk = namedtuple("disk", "total used free")
        with patch(
            "election_audit.national.shutil.disk_usage", return_value=disk(100, 0, 19 * 1024**3)
        ):
            with self.assertRaisesRegex(OSError, "Capacity reserve"):
                guard(self.base, self.scratch, reserve_bytes=0)

    def test_census_reuse_checks_frozen_metadata_bytes(self):
        with patch("election_audit.national.guard"):
            census = freeze_census(self.config, self.store, self.scratch)
        with database(census / "census.sqlite") as db:
            sha = db.execute(
                "SELECT sha256 FROM file_observation WHERE url LIKE '%-cs.json'"
            ).fetchone()[0]
        (self.store / "objects" / sha[:2] / sha).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "Frozen metadata original corrupt"):
            freeze_census(self.config, self.store, self.scratch)

    def test_new_bounded_parser_preserves_existing_event_identity(self):
        from election_audit.archive_parsing import parse_object

        old, _ = parse_object(
            self.raw / self.log["path"],
            self.base / "old-parser",
            expected_sha256=self.log["sha256"],
        )
        expected = [json.loads(line) for line in (old / "events.jsonl").read_text().splitlines()]
        with patch("election_audit.national.guard"):
            artifact = process_object(self.log, self.store, self.scratch)
        actual = [
            json.loads(row)
            for row in pq.read_table(artifact / "events.parquet")["payload"].to_pylist()
        ]
        self.assertEqual(actual, expected)

    def test_wide_rows_flush_before_row_count_limit(self):
        from election_audit.national import _compact_jsonl

        source = self.base / "wide.jsonl"
        wide = json.dumps({"value": "x" * (5 * 1024**2)}) + "\n"
        source.write_text(wide * 3)
        output = self.base / "wide.parquet"
        self.assertEqual(_compact_jsonl(source, output, batch_rows=2048), 3)
        self.assertEqual(pq.ParquetFile(output).num_row_groups, 2)

    def test_explicit_sections_freeze_only_selected_versions_and_histories(self):
        self.save(
            self.prefix + "dados/ac/01007/0001/0002/pkg/b-log.jez",
            (self.raw / self.log["path"]).read_bytes(),
        )
        config_path = self.base / "selected.json"
        self.spec["section_keys"] = [["ac", "01007", "0001", "0001"]]
        config_path.write_text(json.dumps(self.config))
        selected = read_config(config_path)
        with patch("election_audit.national.guard"):
            census = freeze_census(selected, self.store, self.scratch)
        with database(census / "census.sqlite") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM file_observation").fetchone()[0], 2)
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM file_observation WHERE url LIKE '%/0002/%'"
                ).fetchone()[0],
                0,
            )
        self.spec["section_keys"] = []
        config_path.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            read_config(config_path)

    def test_info_counts_do_not_hide_errors_after_former_issue_cap(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "logd.dat",
                b"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message\ttoken\n" * 12000
                + b"bad shape\n" * 12000,
            )
        row = self.save(self.prefix + "dados/ac/01007/0001/0003/pkg/c-log.jez", archive.getvalue())
        with patch("election_audit.national.guard"):
            artifact = process_object(row, self.store, self.scratch)
        from election_audit.national import _read_json

        doc = _read_json(artifact / "artifact.json")
        self.assertEqual(doc["counts"], {"events": 12000, "issues": 12000})
        self.assertEqual(doc["parser"]["counts"]["issues_seen"], 24000)
        self.assertEqual(doc["parser"]["counts"]["issues_aggregated"], 12000)
        self.assertEqual(doc["parser"]["status"], "partial")
        issues = [
            json.loads(p) for p in pq.read_table(artifact / "issues.parquet")["payload"].to_pylist()
        ]
        self.assertEqual(len(issues), 12000)
        self.assertEqual(issues[-1]["record_locator"]["line_start"], 24000)
        self.assertTrue(all(r["issue_code"] == "malformed_columns" for r in issues))

    def test_only_unknown_info_is_structurally_complete_but_not_scientifically_eligible(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "logd.dat",
                b"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message\ttoken\n" * 11000,
            )
        row = self.save(self.prefix + "dados/ac/01007/0001/0004/pkg/d-log.jez", archive.getvalue())
        with patch("election_audit.national.guard"):
            artifact = process_object(row, self.store, self.scratch)
        from election_audit.national import _read_json

        doc = _read_json(artifact / "artifact.json")
        self.assertEqual(doc["parser"]["status"], "complete")
        self.assertEqual(doc["parser"]["diagnostics"][0]["count"], 11000)
        self.assertEqual(doc["scientific_eligibility"], "unavailable_structural_only")
        self.assertEqual(doc["counts"], {"events": 11000, "issues": 0})

    def test_published_uppercase_official_phase_is_normalized_without_rewriting_bytes(self):
        row = self.save(
            self.prefix + "dados/ac/01007/0001/0001/p003221-ac-m01007-z0001-s0001-aux.json",
            b'{"f":"O","st":"Totalizada","hashes":[]}',
        )
        with patch("election_audit.national.guard"):
            freeze_census(self.config, self.store, self.scratch)
        frozen = self.store / "objects" / row["sha256"][:2] / row["sha256"]
        self.assertEqual(frozen.read_bytes(), b'{"f":"O","st":"Totalizada","hashes":[]}')


if __name__ == "__main__":
    unittest.main()
