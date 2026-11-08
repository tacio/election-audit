"""Frozen inputs and coverage use isolated tiny acquisition fixtures only."""

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from election_audit.contracts import validate_rows
from election_audit.coverage import build_population
from election_audit.snapshots import (
    SnapshotError,
    create_snapshot,
    inspect_snapshot,
    publish_snapshot,
    snapshot_tables,
)
from election_audit.source_inventory import (
    BASE,
    aux_url,
    index_url,
    inventory_sources,
    read_manifest,
)


class SourceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "raw"
        self.root.mkdir()
        self.manifest = Path(self.temporary.name) / "ssd.sqlite"
        (self.root / "manifest-location.json").write_text(
            json.dumps({"version": 1, "path": str(self.manifest)})
        )
        self.db = sqlite3.connect(self.manifest)
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE files(url TEXT PRIMARY KEY,path TEXT,sha256 TEXT,bytes INTEGER,
                               fetched_at TEXT,etag TEXT,last_modified TEXT);
            CREATE TABLE runs(id TEXT PRIMARY KEY,started_at TEXT,finished_at TEXT,status TEXT);
            CREATE TABLE sections(run TEXT,uf TEXT,municipality TEXT,zone TEXT,section TEXT,
                                  status TEXT,metadata TEXT,details TEXT,
                                  PRIMARY KEY(run,uf,municipality,zone,section));
            CREATE TABLE logs(run TEXT,uf TEXT,municipality TEXT,zone TEXT,section TEXT,
                              url TEXT,package_status TEXT,package_hash TEXT,filename TEXT,
                              PRIMARY KEY(run,url));
        """)
        self.run = "2026-10-28T10:00:00+00:00"
        self.db.execute("INSERT INTO runs VALUES (?,?,NULL,'running')", (self.run, self.run))
        self.db.commit()
        self.key = ("ac", "01120", "0001", "0001")
        self.log_url = f"{BASE}/ele2026/arquivo-urna/3221/dados/ac/01120/0001/0001/pkg/a-log.dat"

    def save(self, url, body):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        sha = hashlib.sha256(body).hexdigest()
        relative = f"objects/{sha[:2]}/{sha}"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.db.execute(
            "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,NULL,NULL)",
            (url, relative, sha, len(body), self.run),
        )
        self.db.commit()
        return path

    def record_section(self, code="0001", status="downloaded", metadata=None, run=None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?,?,NULL)",
            (
                run or self.run,
                *self.key[:3],
                code,
                status,
                json.dumps({"ns": code, "da": "date"} if metadata is None else metadata),
            ),
        )
        self.db.commit()

    def advertise(self, url=None, run=None, code="0001") -> None:
        self.db.execute(
            "INSERT INTO logs VALUES (?,?,?,?,?,?,?,?,?)",
            (run or self.run, *self.key[:3], code, url or self.log_url, "1", "pkg", "a-log.dat"),
        )
        self.db.commit()

    def save_index(self, entries):
        return self.save(
            index_url("ac"),
            {
                "f": "o",
                "cdp": "3221",
                "abr": [
                    {"cd": "ac", "mu": [{"cd": "01120", "zon": [{"cd": "0001", "sec": entries}]}]}
                ],
            },
        )


class InventoryTests(SourceFixture):
    def test_marker_wal_current_observation_and_unknown_history(self) -> None:
        self.record_section()
        self.advertise()
        self.save(self.log_url, b"original")
        self.save(aux_url(self.key), {"f": "o"})
        inventory = inventory_sources(self.root, ["ac"])
        self.assertEqual(inventory["manifest_locator"], str(self.manifest))
        self.assertTrue(Path(str(self.manifest) + "-wal").exists())
        self.assertEqual(inventory["manifest_rows"]["runs"][0]["status"], "running")
        self.assertEqual(len(inventory["source_object"]), 2)
        self.assertEqual(
            inventory["historical_advertisements"][0]["mapping_state"], "historical_mapping_unknown"
        )
        self.assertIsNone(inventory["historical_advertisements"][0]["object_sha256"])
        for table in ("source_object", "source_observation"):
            self.assertEqual(validate_rows(table, inventory[table]), [])

    def test_read_view_spans_tables_when_writer_commits(self) -> None:
        self.record_section(status="error")

        def writer_commit() -> str:
            self.db.execute("UPDATE runs SET status='finished'")
            self.db.execute("UPDATE sections SET status='downloaded'")
            self.db.commit()
            return "2026-10-29T00:00:00+00:00"

        with patch("election_audit.source_inventory.utc_now", side_effect=writer_commit):
            view = read_manifest(self.root, ["ac"])
        self.assertEqual(view["manifest_rows"]["runs"][0]["status"], "running")
        self.assertEqual(view["manifest_rows"]["sections"][0]["status"], "error")
        self.assertEqual(self.db.execute("SELECT status FROM runs").fetchone()[0], "finished")

    def test_missing_corrupt_and_unsafe_objects_retained(self) -> None:
        self.advertise()
        path = self.save(self.log_url, b"original")
        path.write_bytes(b"corrupt!")
        inventory = inventory_sources(self.root, ["ac"])
        self.assertEqual(inventory["object_checks"][0]["state"], "digest_or_size_mismatch")
        self.assertEqual(inventory["source_object"], [])
        path.unlink()
        self.assertEqual(
            inventory_sources(self.root, ["ac"])["object_checks"][0]["state"], "missing_object"
        )
        self.db.execute("UPDATE files SET path='../outside'")
        self.db.commit()
        self.assertEqual(
            inventory_sources(self.root, ["ac"])["object_checks"][0]["state"],
            "unsafe_storage_locator",
        )

    def test_selection_validation_and_no_manifest_creation(self) -> None:
        with self.assertRaises(ValueError):
            read_manifest(self.root, ["xx"])
        (self.root / "manifest-location.json").unlink()
        with self.assertRaises(sqlite3.OperationalError):
            read_manifest(self.root, ["ac"])
        self.assertFalse((self.root / "manifest.sqlite").exists())

    def test_latest_url_bytes_never_assigned_to_original_run(self) -> None:
        self.record_section()
        self.advertise()
        self.save(self.log_url, b"old")
        first = inventory_sources(self.root, ["ac"])
        self.save(self.log_url, b"new")
        second = inventory_sources(self.root, ["ac"])
        self.assertNotEqual(first["source_object"], second["source_object"])
        self.assertIsNone(first["historical_advertisements"][0]["object_sha256"])
        self.assertIsNone(second["historical_advertisements"][0]["object_sha256"])


class PopulationTests(SourceFixture):
    def population(self, **kwargs):
        return build_population(inventory_sources(self.root, ["ac"], **kwargs))

    def test_expected_members_and_unique_principals_never_multiply(self) -> None:
        self.save_index(
            [
                {"ns": "0001", "da": "date"},
                {"ns": "0002", "nsp": "0001"},
                {"ns": "0003", "da": "date"},
                {"ns": "0004", "da": "date"},
                {"ns": "0005"},
            ]
        )
        self.record_section()
        self.record_section("0004", "error")
        self.advertise()
        self.save(self.log_url, b"log")
        self.save(
            aux_url(self.key),
            {
                "f": "o",
                "hashes": [{"hash": "pkg", "st": "1", "arq": [{"nm": "a-log.dat", "tp": "log"}]}],
            },
        )
        population = self.population()
        summary = population["coverage_summary"]
        self.assertEqual(summary["expected_members"], 5)
        self.assertEqual(summary["expected_unique_principals"], 4)
        self.assertEqual(summary["acquired_unique_principals"], 1)
        self.assertEqual(
            summary["member_accounting"],
            {"acquired": 1, "aggregated": 1, "failed": 1, "missing": 1, "not_published": 1},
        )
        self.assertEqual(summary["national_status"], "partial_national")
        self.assertIsNone(summary["national_expected_members"])
        self.assertEqual(summary["unfinished_runs"], [self.run])
        for table, rows in population["tables"].items():
            self.assertEqual(validate_rows(table, rows), [], table)
        self.assertEqual(
            population["tables"]["package_observation"][0]["package_status"], "unknown"
        )

    def test_missing_index_retains_observed_members_but_unknown_expected(self) -> None:
        self.record_section()
        population = self.population()
        self.assertIsNone(population["coverage_summary"]["expected_members"])
        self.assertIsNone(population["coverage_summary"]["expected_unique_principals"])
        self.assertEqual(len(population["tables"]["coverage_ledger"]), 1)
        self.assertEqual(population["section_evidence"][0]["acquisition_state"], "unresolved")

    def test_current_file_without_run_or_index_still_has_coverage_row(self) -> None:
        self.save(self.log_url, b"unrecorded active download")
        population = self.population()
        self.assertEqual(len(population["tables"]["coverage_ledger"]), 1)
        self.assertEqual(population["coverage_summary"]["observed_only_sections"], 1)
        self.assertIsNone(population["coverage_summary"]["expected_members"])

    def test_exact_package_status_mapping_is_versioned_and_raw_preserved(self) -> None:
        self.save_index([{"ns": "0001", "da": "date"}])
        for status, normalized in (
            ("Totalizado", "totalized"),
            ("totalizado", "unknown"),
            ("1", "unknown"),
            ("future", "unknown"),
        ):
            self.save(
                aux_url(self.key),
                {
                    "f": "O",
                    "hashes": [
                        {"hash": "pkg", "st": status, "arq": [{"nm": "a-log.dat", "tp": "log"}]}
                    ],
                },
            )
            population = self.population()
            row = population["tables"]["package_observation"][0]
            self.assertEqual(row["package_status_raw"], status)
            self.assertEqual(row["package_status"], normalized)

    def test_ambiguous_composition_and_unseen_principal_are_unresolved(self) -> None:
        self.save_index(
            [
                {"ns": "0001", "nsp": "0002"},
                {"ns": "0002", "nsp": "0001"},
                {"ns": "0003", "nsp": "0009"},
                {"ns": "0004"},
                {"ns": "0004", "nsp": "0003"},
            ]
        )
        population = self.population()
        self.assertIsNone(population["coverage_summary"]["expected_members"])
        self.assertIsNone(population["coverage_summary"]["expected_unique_principals"])
        self.assertEqual(population["coverage_summary"]["unresolved_composition_sections"], 4)
        self.assertEqual(population["tables"]["section_composition"], [])
        self.assertEqual(len(population["tables"]["coverage_ledger"]), 4)

    def test_partial_interrupted_and_finished_runs_do_not_prove_coverage(self) -> None:
        self.save_index([{"ns": "0001", "da": "date"}, {"ns": "0002", "da": "date"}])
        self.record_section()
        self.advertise()
        for status in ("running", "interrupted", "finished"):
            with self.subTest(status=status):
                self.db.execute(
                    "UPDATE runs SET status=?,finished_at=?",
                    (status, None if status == "running" else self.run),
                )
                self.db.commit()
                population = self.population()
                self.assertEqual(
                    population["coverage_summary"]["member_accounting"], {"missing": 2}
                )
                self.assertFalse(population["coverage_summary"]["run_status_is_coverage_proof"])

    def test_explicit_section_selection_bounds_bytes_preserves_index_denominator(self) -> None:
        self.save_index([{"ns": "0001", "da": "date"}, {"ns": "0002", "da": "date"}])
        self.record_section()
        self.record_section("0002")
        self.advertise()
        self.save(self.log_url, b"selected")
        other = self.log_url.replace("/0001/pkg/", "/0002/pkg/")
        self.advertise(other, code="0002")
        self.save(other, b"unselected")
        inventory = inventory_sources(self.root, ["ac"], section_keys=[self.key])
        self.assertEqual(len(inventory["manifest_rows"]["logs"]), 1)
        self.assertNotIn(other, [row["url"] for row in inventory["object_checks"]])
        population = build_population(inventory)
        self.assertEqual(population["coverage_summary"]["expected_members"], 2)
        self.assertEqual(
            population["coverage_summary"]["member_accounting"], {"acquired": 1, "not_selected": 1}
        )
        self.assertEqual(len(population["tables"]["coverage_ledger"]), 2)

    def test_additional_ufs_can_enter_explicit_subsequent_snapshot(self) -> None:
        inventory = inventory_sources(self.root, ["sp", "zz"])
        population = build_population(inventory)
        self.assertEqual(population["coverage_summary"]["declared_ufs"], ["sp", "zz"])
        self.assertIsNone(population["coverage_summary"]["expected_members"])

    def test_missing_advertised_asset_and_corrupt_metadata_stay_visible(self) -> None:
        self.save_index([{"ns": "0001", "da": "date"}])
        path = self.save(
            aux_url(self.key),
            {
                "f": "o",
                "hashes": [{"hash": "pkg", "st": "1", "arq": [{"nm": "a-log.dat", "tp": "log"}]}],
            },
        )
        population = self.population()
        self.assertEqual(len(population["tables"]["package_asset"]), 1)
        self.assertEqual(population["coverage_summary"]["member_accounting"], {"missing": 1})
        # An advertisement with absent bytes is missing, even if the aux is verified.
        self.assertEqual(
            population["tables"]["source_observation"][-1]["observation_status"], "missing"
        )
        path.write_bytes(b"bad")
        population = self.population()
        self.assertEqual(population["tables"]["package_asset"], [])
        self.assertNotEqual(population["section_evidence"][0]["auxiliary_state"], "verified")


class SnapshotTests(SourceFixture):
    def setUp(self) -> None:
        super().setUp()
        self.store = Path(self.temporary.name) / "snapshots"
        self.save_index([{"ns": "0001", "da": "date"}, {"ns": "0002", "nsp": "0001"}])
        self.record_section()
        self.advertise()
        self.raw_log = self.save(self.log_url, b"original")

    def captured(self):
        inventory = inventory_sources(self.root, ["ac"])
        return inventory, build_population(inventory)

    def test_atomic_self_contained_snapshot_and_idempotent_publication(self) -> None:
        inventory, population = self.captured()
        path = publish_snapshot(inventory, population, self.store)
        document = inspect_snapshot(path, verify_objects=True)
        self.assertEqual(document["snapshot"]["inventory_sha256"], path.name)
        for table, rows in snapshot_tables(document).items():
            self.assertEqual(validate_rows(table, rows), [], table)
        before = (path / "snapshot.json").read_bytes()
        self.assertEqual(publish_snapshot(inventory, population, self.store), path)
        self.assertEqual((path / "snapshot.json").read_bytes(), before)
        self.assertEqual(len(list(self.store.glob("[0-9a-f]*"))), 1)
        self.assertEqual(list(self.store.glob(".snapshot-building-*")), [])

    def test_later_download_and_raw_deletion_cannot_change_snapshot(self) -> None:
        path = create_snapshot(self.root, self.store, ["ac"])
        before = inspect_snapshot(path, verify_objects=True)
        self.save(self.log_url, b"changed!")
        self.raw_log.unlink()
        self.db.execute("UPDATE runs SET status='finished',finished_at=?", (self.run,))
        self.db.commit()
        after = inspect_snapshot(path, verify_objects=True)
        self.assertEqual(before, after)
        second = create_snapshot(self.root, self.store, ["ac"])
        self.assertNotEqual(path, second)
        self.assertEqual(
            inspect_snapshot(second)["payload"]["coverage_summary"]["member_accounting"],
            {"acquired": 1, "aggregated": 1},
        )

    def test_changed_source_aborts_before_publication_and_retry_is_safe(self) -> None:
        inventory, population = self.captured()
        self.raw_log.write_bytes(b"changed!")
        with self.assertRaises(SnapshotError):
            publish_snapshot(inventory, population, self.store)
        self.assertEqual(list(self.store.glob("[0-9a-f]*")), [])
        self.assertEqual(list(self.store.glob(".snapshot-building-*")), [])
        self.raw_log.write_bytes(b"original")
        path = publish_snapshot(inventory, population, self.store)
        inspect_snapshot(path, verify_objects=True)

    def test_abandoned_staging_and_interruption_never_look_complete(self) -> None:
        self.store.mkdir()
        abandoned = self.store / ".snapshot-building-abandoned"
        abandoned.mkdir()
        (abandoned / "partial").write_bytes(b"partial")
        inventory, population = self.captured()
        with patch("election_audit.snapshots._copy_verified", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                publish_snapshot(inventory, population, self.store)
        self.assertEqual(list(self.store.glob("[0-9a-f]*")), [])
        path = publish_snapshot(inventory, population, self.store)
        inspect_snapshot(path, verify_objects=True)
        self.assertTrue(abandoned.exists())

    def test_snapshot_damage_is_detected_and_never_overwritten(self) -> None:
        inventory, population = self.captured()
        path = publish_snapshot(inventory, population, self.store)
        document = inspect_snapshot(path)
        obj = document["payload"]["tables"]["source_object"][0]
        frozen = path / obj["storage_locator"]
        frozen.write_bytes(b"x" * obj["byte_length"])
        with self.assertRaises(SnapshotError):
            inspect_snapshot(path, verify_objects=True)
        with self.assertRaises(SnapshotError):
            publish_snapshot(inventory, population, self.store)
        frozen.unlink()
        with self.assertRaises(SnapshotError):
            inspect_snapshot(path)
        (path / "snapshot.json").write_bytes(b"{}")
        with self.assertRaisesRegex(SnapshotError, "checksum"):
            inspect_snapshot(path)

    def test_inspection_uses_frozen_schema_and_detects_payload_tampering(self) -> None:
        path = create_snapshot(self.root, self.store, ["ac"])
        with patch(
            "election_audit.snapshots.load_contract",
            side_effect=AssertionError("live schema accessed"),
        ):
            document = inspect_snapshot(path)
        document["payload"]["coverage_summary"]["expected_members"] = 999
        encoded = json.dumps(document).encode()
        (path / "snapshot.json").write_bytes(encoded)
        (path / "snapshot.sha256").write_text(hashlib.sha256(encoded).hexdigest())
        with self.assertRaisesRegex(SnapshotError, "identity/inventory"):
            inspect_snapshot(path)

    def test_missing_objects_and_failed_attempts_can_be_frozen_honestly(self) -> None:
        self.raw_log.unlink()
        self.record_section(status="error")
        path = create_snapshot(self.root, self.store, ["ac"])
        document = inspect_snapshot(path, verify_objects=True)
        self.assertEqual(
            document["payload"]["coverage_summary"]["member_accounting"],
            {"aggregated": 1, "failed": 1},
        )
        self.assertEqual(
            document["payload"]["inventory"]["object_checks"][0]["state"]
            in ("verified", "missing_object"),
            True,
        )
        self.assertTrue(
            any(
                row["state"] == "missing_object"
                for row in document["payload"]["inventory"]["object_checks"]
            )
        )

    def test_reserve_and_raw_root_protection(self) -> None:
        inventory, population = self.captured()
        with self.assertRaises(SnapshotError):
            publish_snapshot(inventory, population, self.root / "snapshots")
        with self.assertRaisesRegex(SnapshotError, "Insufficient space"):
            publish_snapshot(inventory, population, self.store, reserve_bytes=10**30)
        self.assertEqual(list(self.store.glob("[0-9a-f]*")), [])

    def test_new_cli_recipes_are_usable_and_legacy_inspect_remains(self) -> None:
        from election_audit.cli import main

        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(
                main(
                    [
                        "snapshot",
                        "--source",
                        str(self.root),
                        "--store",
                        str(self.store),
                        "--ufs",
                        "ac",
                        "--section",
                        "/".join(self.key),
                        "--reserve-gib",
                        "0",
                    ]
                ),
                0,
            )
        path = Path(output.getvalue().strip())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["snapshot-inspect", str(path), "--verify-objects"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["coverage"]["expected_members"], 2)
        self.assertTrue(report["objects_rehashed"])


if __name__ == "__main__":
    unittest.main()
