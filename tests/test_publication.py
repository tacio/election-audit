"""Synthetic immutable release failure and relational acceptance fixtures."""

import fcntl
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import test_reconstruction
import test_snapshots

from election_audit.publication import (
    PublicationError,
    ResourceConfig,
    inspect_release,
    open_release,
    publish_release,
)
from election_audit.reconstruction import reconstruct_parse
from election_audit.types import one


class ReleaseTests(test_snapshots.SourceFixture):
    frozen_parse = test_reconstruction.PublicationTests.frozen_parse

    # Reuse fixture setup, not the reconstruction test methods.
    def release_input(self) -> tuple[Path, Path]:
        base, _, parsed = self.frozen_parse()
        shard = reconstruct_parse(parsed, base / "operations")
        return base, shard

    def test_release_partition_settings_integrity_and_relocation(self) -> None:
        base, shard = self.release_input()
        config = ResourceConfig(duckdb_threads=2, memory_bytes=128 * 1024**2, batch_rows=1)
        path = publish_release([shard], base / "warehouse", config=config)
        self.assertEqual(path, publish_release([shard], base / "warehouse", config=config))
        manifest = inspect_release(path)
        self.assertEqual(manifest["settings_applied"]["duckdb_threads"], 2)
        self.assertTrue(
            all(
                "year=" in p and "round=" in p and "uf=" in p
                for p in manifest["tables"]["selected_event"]["files"]
            )
        )
        moved = base / "moved"
        shutil.move(base / "warehouse", moved)
        with open_release(moved) as db:
            self.assertEqual(
                one(db.execute("SELECT count(*) FROM selected_event").fetchone())[0], 2
            )
            self.assertEqual(one(db.execute("SELECT current_setting('threads')").fetchone())[0], 2)
            self.assertEqual(
                one(db.execute("SELECT current_setting('memory_limit')").fetchone())[0], "128.0 MiB"
            )
        self.assertIsNone(manifest["global_eligible_cycle_total"])

    def test_interruptions_preserve_previous_current_and_resume(self) -> None:
        base, shard = self.release_input()
        store = base / "warehouse"
        first = publish_release([shard], store)
        config = ResourceConfig(duckdb_threads=1)
        for stage in ("shard_written", "before_release", "before_current"):

            def interrupt(current: str) -> None:
                if current == stage:
                    raise OSError("fixture interruption")

            with self.assertRaises(OSError):
                publish_release([shard], store, config=config, hook=interrupt)
            self.assertEqual((store / "current").read_text().strip(), first.name)
            self.assertEqual(
                inspect_release(first)["identity"]["version"], "operational-release-v1"
            )
            # A completed immutable release can survive a pointer update interruption.
            target = store / "releases"
            for path in target.glob("[0-9a-f]*"):
                if path != first and stage != "before_current":
                    shutil.rmtree(path)
        second = publish_release([shard], store, config=config)
        self.assertNotEqual(first, second)
        self.assertEqual((store / "current").read_text().strip(), second.name)

    def test_writer_resource_and_overlap_guards(self) -> None:
        base, shard = self.release_input()
        store = base / "warehouse"
        store.mkdir()
        with (store / ".writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(PublicationError, "writer"):
                publish_release([shard], store)
        with patch("election_audit.publication.shutil.disk_usage") as usage:
            usage.return_value.free = 1
            with self.assertRaisesRegex(PublicationError, "reserve"):
                publish_release([shard], store)
        with self.assertRaises(PublicationError):
            ResourceConfig(parser_workers=0)
        # Distinct shard settings cannot make the same objects disjoint.
        other = reconstruct_parse(
            shard.parent.parent.parent
            / "parsed"
            / "parses"
            / inspect_release(publish_release([shard], store))["identity"]["parse_id"],
            base / "operations",
            max_events=50,
        )
        with self.assertRaisesRegex(PublicationError, "overlap"):
            publish_release([shard, other], store)

    def test_duplicate_and_foreign_key_failures(self) -> None:
        base, shard = self.release_input()
        import json

        import duckdb

        from election_audit.publication import _create, _insert, _validate

        row = json.loads((shard / "selected_event.jsonl").read_text().splitlines()[0])
        with duckdb.connect() as db:
            _create(db, "selected_event")
            _create(db, "voting_session")
            _insert(db, "selected_event", [row, row])
            with self.assertRaisesRegex(PublicationError, "duplicate"):
                _validate(db, ["selected_event", "voting_session"])
            db.execute("DELETE FROM selected_event")
            _insert(db, "selected_event", [row])
            with self.assertRaisesRegex(PublicationError, "foreign key"):
                _validate(db, ["selected_event", "voting_session"])

    def test_corruption_rejected(self) -> None:
        base, shard = self.release_input()
        path = publish_release([shard], base / "warehouse")
        file = path / inspect_release(path)["tables"]["selected_event"]["files"][0]
        file.write_bytes(b"broken")
        with self.assertRaises(PublicationError):
            inspect_release(path)

    def test_parser_independent_keys_run_concurrently_identical_key_runs_once(self) -> None:
        import concurrent.futures
        import threading
        import time

        from test_archive_parsing import archive_bytes, log_line

        from election_audit.archive_parsing import _Parser, parse_object

        base, _shard = self.release_input()
        first, second = base / "first.zip", base / "second.zip"
        first.write_bytes(archive_bytes([("logd.dat", log_line())]))
        second.write_bytes(archive_bytes([("otherlog.dat", log_line())]))
        original = _Parser.archive
        barrier = threading.Barrier(2)
        calls = []

        def independent(parser: Any, source: Any, *args: Any, **kwargs: Any) -> Any:
            # Only outer archives participate in the concurrency assertion.
            if not args and not kwargs:
                calls.append(parser)
                barrier.wait(timeout=5)
            return original(parser, source, *args, **kwargs)

        with patch.object(_Parser, "archive", independent):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(lambda path: parse_object(path, base / "parallel"), [first, second])
                )
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(not hit for _path, hit in results))
        calls.clear()

        def serialized(parser: Any, source: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(parser)
            time.sleep(0.01)
            return original(parser, source, *args, **kwargs)

        with patch.object(_Parser, "archive", serialized):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(lambda path: parse_object(path, base / "same"), [first, first])
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(hit for _path, hit in results), [False, True])
