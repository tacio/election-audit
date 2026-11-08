"""Lossless compact events preserve all logical IDs, line hashes and locators."""

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.archive_parsing import PARSER_VERSION, ParseConfig
from election_audit.national import _read_json, _write_json
from election_audit.national_storage import iter_compact, write_compact
from election_audit.source_inventory import identity


class CompactEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "compact"
        self.sha = "a" * 64
        self.config = ParseConfig().__dict__

    def rows(self, n=41):
        for i in range(n):
            locator = {
                "archive_segments": [
                    {"member_name": "histórico.zip", "member_index": 0, "occurrence": 0},
                    {"member_name": "logd.dat", "member_index": i // 20, "occurrence": i // 20},
                ],
                "line_start": i * 2 + 1,
                "line_end": i * 2 + 1,
                "byte_start": None,
                "byte_end": None,
            }
            yield {
                "event_id": identity(
                    "structural-event", [self.sha, locator, PARSER_VERSION, self.config]
                ),
                "object_sha256": self.sha,
                "record_locator": locator,
                "source_sequence": i * 2 + 1,
                "source_line_sha256": hashlib.sha256(str(i).encode()).hexdigest(),
                "device_timestamp_raw": "25/10/2026 08:00:00",
                "device_id_raw": "123",
                "application": "VOTA",
                "level": "INFO",
                "event_kind": "unknown" if i % 2 else "authorization_message",
                "selection_state": "context_unresolved",
                "parser_version": PARSER_VERSION,
            }

    def write(self, rows):
        return write_compact(
            rows,
            self.directory,
            object_sha256=self.sha,
            parser_version=PARSER_VERSION,
            config=self.config,
            batch_rows=3,
        )

    def test_exact_roundtrip_binary_hashes_member_templates_and_batches(self) -> None:
        original = list(self.rows())
        self.write(iter(original))
        self.assertEqual(list(iter_compact(self.directory, batch_rows=5)), original)
        schema = pq.read_schema(self.directory / "events.parquet")
        self.assertEqual(schema.field("source_line_sha256").type, pa.binary(32))
        self.assertNotIn("event_id", schema.names)
        self.assertNotIn("object_sha256", schema.names)
        doc = _read_json(self.directory / "compact.json")
        self.assertEqual(len(doc["members"]), 3)
        self.assertEqual(doc["count"], 41)

    def test_no_silent_extra_field_or_invalid_event_identity(self) -> None:
        row = next(self.rows())
        row["unexpected"] = "must not disappear"
        with self.assertRaises(ValueError):
            self.write([row])
        self.assertFalse((self.directory / "compact.json").exists())

    def test_inconsistent_event_id_rejected(self) -> None:
        row = next(self.rows())
        row["event_id"] = "changed"
        with self.assertRaisesRegex(ValueError, "identity"):
            self.write([row])

    def test_corrupt_compact_bytes_fail_before_reading_events(self) -> None:
        self.write(self.rows())
        (self.directory / "events.parquet").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "integrity"):
            list(iter_compact(self.directory))

    def test_logical_stream_digest_protects_context_reconstruction(self) -> None:
        self.write(self.rows())
        doc = _read_json(self.directory / "compact.json")
        doc["object_sha256"] = "b" * 64
        (self.directory / "compact.json").unlink()
        (self.directory / "compact.json.sha256").unlink()
        _write_json(self.directory / "compact.json", doc)
        with self.assertRaisesRegex(ValueError, "logical event digest"):
            list(iter_compact(self.directory))

    def test_empty_events_are_not_invented(self) -> None:
        self.write([])
        self.assertEqual(list(iter_compact(self.directory)), [])

    def test_registered_cas_compact_producer_preserves_original_and_full_events(self) -> None:
        from election_audit.archive_parsing import parse_object
        from election_audit.national_storage import process_compact_original, registered_original
        from election_audit.source_inventory import hash_file

        root = Path(self.temp.name) / "raw"
        root.mkdir()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(
                "logd.dat", b"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message\ttoken\n"
            )
        body = archive.getvalue()
        sha = hashlib.sha256(body).hexdigest()
        source = root / "objects" / sha[:2] / (sha + ".jez")
        source.parent.mkdir(parents=True)
        source.write_bytes(body)
        row = {
            "sha256": sha,
            "bytes": len(body),
            "source_root": str(root),
            "path": str(source.relative_to(root)),
            "url": "https://resultados.tse.jus.br/official-example-log.jez",
        }
        original = registered_original(row)
        self.assertFalse(original["self_contained"])
        before = hash_file(source)
        old, _ = parse_object(source, Path(self.temp.name) / "old-parser")
        import json

        expected = [json.loads(line) for line in (old / "events.jsonl").read_text().splitlines()]
        store = Path(self.temp.name) / "store"
        scratch = Path(self.temp.name) / "scratch"
        with patch("election_audit.national.guard"):
            target = process_compact_original(row, store, scratch, output_budget_bytes=8 * 1024**2)
            self.assertEqual(
                process_compact_original(row, store, scratch, output_budget_bytes=8 * 1024**2),
                target,
            )
        self.assertEqual(list(iter_compact(target / "events")), expected)
        self.assertEqual(hash_file(source), before)
        self.assertFalse((store / "objects").exists())
        self.assertEqual(
            _read_json(target / "checkpoint.json")["parser"]["diagnostics"][0]["count"], 1
        )
        source.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            process_compact_original(row, store, scratch, output_budget_bytes=8 * 1024**2)

    def test_registered_original_rejects_non_cas_namespace(self) -> None:
        from election_audit.national_storage import registered_original

        with self.assertRaisesRegex(ValueError, "content-addressed namespace"):
            registered_original(
                {
                    "source_root": self.temp.name,
                    "path": "ordinary.dat",
                    "sha256": "a" * 64,
                    "bytes": 1,
                    "url": "official-example",
                }
            )
