"""Tiny synthetic archives only; no real corpus reads or electoral vote inference."""

import hashlib
import io
import json
import struct
import tempfile
import unittest
import warnings
import zipfile
from collections.abc import Iterable
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_snapshots import SourceFixture

from election_audit.archive_parsing import (
    ParseConfig,
    ParseError,
    inspect_artifact,
    inspect_parse,
    iter_event_witnesses,
    iter_lineage,
    iter_parsing_issues,
    parse_object,
    parse_snapshot,
)
from election_audit.contracts import validate_rows
from election_audit.snapshots import create_snapshot
from election_audit.source_inventory import aux_url


def log_line(
    message: str = "O voto do eleitor foi computado",
    timestamp: str = "25/10/2026 08:00:00",
    app: str = "VOTA",
) -> bytes:
    return f"{timestamp}\tINFO\t1234\t{app}\t{message}\tSECRET-TOKEN\n".encode("latin-1")


def archive_bytes(members: Iterable[tuple[str, bytes]]) -> bytes:
    body = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in members:
                archive.writestr(name, content)
    return body.getvalue()


def rows(path: Path, name: str) -> list[Any]:
    return [json.loads(line) for line in (path / name).read_bytes().splitlines()]


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "input.jez"
        self.store = self.root / "derived"

    def parse(
        self,
        members: Iterable[tuple[str, bytes]] | None = None,
        *,
        body: bytes | None = None,
        config: ParseConfig | None = None,
    ) -> tuple[Path, list[Any], list[Any]]:
        self.source.write_bytes(body if body is not None else archive_bytes(members))
        path, hit = parse_object(self.source, self.store, config=config)
        return path, rows(path, "events.jsonl"), rows(path, "issues.jsonl")

    def codes(self, issues: Iterable[dict[str, Any]]) -> set[str]:
        return {row["issue_code"] for row in issues}

    def test_nested_duplicate_occurrences_order_and_no_path_extraction(self) -> None:
        nested = archive_bytes([("logd.dat", log_line()), ("logd.dat", log_line())])
        path, events, issues = self.parse(
            [
                ("../../escape.zip", nested),
                ("../../escape.zip", nested),
                ("dir\\LOGD.DAT", log_line()),
            ]
        )
        self.assertEqual(len(events), 5)
        self.assertEqual(issues, [])
        self.assertEqual(len({row["event_id"] for row in events}), 5)
        locators = [row["record_locator"]["archive_segments"] for row in events]
        self.assertEqual([row[0]["occurrence"] for row in locators], [0, 0, 1, 1, 0])
        self.assertEqual([row[1]["occurrence"] for row in locators[:4]], [0, 1, 0, 1])
        self.assertEqual(locators[-1][0]["member_name"], "dir\\LOGD.DAT")
        self.assertFalse((self.root / "escape.zip").exists())
        self.assertEqual(inspect_artifact(path)["counts"]["verified_members"], 7)

    def test_crc_corruption_never_emits_events_from_invalid_member(self) -> None:
        body = bytearray(archive_bytes([("logd.dat", log_line()), ("other", b"data")]))
        position = body.index(b"O voto")
        body[position] ^= 1
        _, events, issues = self.parse(body=bytes(body))
        self.assertEqual(events, [])
        self.assertIn("member_integrity_error", self.codes(issues))
        self.assertIn("missing_log_member", self.codes(issues))

    def test_all_members_crc_checked_even_when_not_logs(self) -> None:
        body = bytearray(archive_bytes([("logd.dat", log_line()), ("other", b"other-body")]))
        body[body.index(b"other-body")] ^= 1
        path, events, issues = self.parse(body=bytes(body))
        self.assertEqual(len(events), 1)
        self.assertIn("member_integrity_error", self.codes(issues))
        self.assertEqual(inspect_artifact(path)["status"], "partial")

    def test_missing_log_and_invalid_zip_are_explicit(self) -> None:
        _, events, issues = self.parse([("readme", b"hello")])
        self.assertFalse(events)
        self.assertEqual(self.codes(issues), {"missing_log_member"})
        _, _, issues = self.parse(body=b"not an archive")
        self.assertEqual(self.codes(issues), {"invalid_archive", "missing_log_member"})

    def test_archive_member_expansion_depth_and_directory_guards(self) -> None:
        nested = archive_bytes([("next.jez", archive_bytes([("logd.dat", log_line())]))])
        cases = [
            (
                [("logd.dat", log_line())],
                replace(ParseConfig(), max_archive_bytes=10),
                "archive_size_limit",
            ),
            (
                [("logd.dat", log_line())],
                replace(ParseConfig(), max_member_bytes=10),
                "member_size_limit",
            ),
            (
                [("logd.dat", log_line())],
                replace(ParseConfig(), max_total_bytes=10),
                "expanded_size_limit",
            ),
            ([("next.zip", nested)], replace(ParseConfig(), max_depth=1), "archive_depth_limit"),
            (
                [("a", b""), ("logd.dat", b"")],
                replace(ParseConfig(), max_members=1),
                "member_count_limit",
            ),
            (
                [("logd.dat", log_line())],
                replace(ParseConfig(), max_directory_bytes=10),
                "directory_size_limit",
            ),
        ]
        for members, config, code in cases:
            with self.subTest(code=code):
                path, _, issues = self.parse(members, config=config)
                self.assertIn(code, self.codes(issues))
                self.assertEqual(inspect_artifact(path)["status"], "partial")

    def test_lying_eocd_count_cannot_bypass_member_guard(self) -> None:
        body = bytearray(archive_bytes([("a", b""), ("b", b"")]))
        end = body.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", body, end + 8, 1, 1)
        _, _, issues = self.parse(body=bytes(body), config=replace(ParseConfig(), max_members=1))
        self.assertIn("member_count_limit", self.codes(issues))

    def test_oversized_line_drains_without_splitting_then_keeps_original_line(self) -> None:
        content = b"SENSITIVE-ID" * 30 + b"\n" + log_line()
        _, events, issues = self.parse(
            [("logd.dat", content)], config=replace(ParseConfig(), max_line_bytes=120)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["record_locator"]["line_start"], 2)
        self.assertEqual(issues[0]["issue_code"], "line_size_limit")
        self.assertNotIn("SENSITIVE", json.dumps(issues))

    def test_malformed_unknown_sensitive_and_mixed_contexts_remain_honest(self) -> None:
        content = (
            log_line(timestamp="04/10/2026 08:00:00")
            + log_line()
            + log_line()
            + log_line("Solicitação de dado pessoal do eleitor para habilitação manual")
            + log_line("Eleitor foi habilitado")
            + log_line("CPF=12345678900 mesario SECRET")
            + log_line(app="SETUP")
            + b"malformed SECRET\n"
            + log_line(timestamp="99/10/2026 08:00:00")
        )
        path, events, issues = self.parse([("first-round-name/logd.dat", content)])
        self.assertEqual(len(events), 7)
        self.assertEqual(len({row["event_id"] for row in events}), 7)
        self.assertEqual([row["source_sequence"] for row in events], list(range(1, 8)))
        self.assertEqual(events[0]["device_timestamp_raw"], "04/10/2026 08:00:00")
        self.assertEqual(events[1]["device_timestamp_raw"], events[2]["device_timestamp_raw"])
        self.assertEqual(events[3]["event_kind"], "manual_request_message")
        self.assertEqual(events[4]["event_kind"], "authorization_message")
        self.assertEqual(events[5]["event_kind"], "unknown")
        self.assertEqual(events[6]["application"], "SETUP")
        self.assertTrue(all(row["selection_state"] == "context_unresolved" for row in events))
        selected = (path / "events.jsonl").read_text() + (path / "issues.jsonl").read_text()
        for secret in ("SECRET", "12345678900", "mesario", "CPF"):
            self.assertNotIn(secret, selected)
        self.assertEqual(
            self.codes(issues),
            {"unsupported_message_class", "malformed_columns", "invalid_timestamp"},
        )
        self.assertEqual(issues[-1]["record_locator"]["line_start"], 9)
        self.assertIsNone(events[0]["record_locator"]["byte_start"])

    def test_unknown_exact_line_fingerprints_distinguish_content_and_line_endings(self) -> None:
        first = log_line("unsupported class one")
        second = log_line("unsupported class two")
        third = first.rstrip(b"\n") + b"\r\n"
        _, events, _ = self.parse([("logd.dat", first + second + third)])
        self.assertEqual([event["event_kind"] for event in events], ["unknown"] * 3)
        self.assertEqual(
            [event["source_line_sha256"] for event in events],
            [hashlib.sha256(line).hexdigest() for line in (first, second, third)],
        )
        self.assertEqual(len({event["source_line_sha256"] for event in events}), 3)

    def test_line_and_diagnostic_limits_are_visible_and_bounded(self) -> None:
        path, events, issues = self.parse(
            [("logd.dat", b"bad\n" * 20 + log_line())],
            config=replace(ParseConfig(), max_issues=2, max_lines=5),
        )
        self.assertEqual(events, [])
        self.assertEqual(len(issues), 3)
        self.assertEqual(issues[-1]["issue_code"], "diagnostic_limit")
        metadata = inspect_artifact(path)
        self.assertEqual(metadata["status"], "partial")
        self.assertEqual(metadata["counts"]["issues_seen"], 6)

    def test_cache_key_config_hits_damage_and_interrupted_restart(self) -> None:
        self.source.write_bytes(archive_bytes([("logd.dat", log_line())]))
        path, hit = parse_object(self.source, self.store)
        self.assertFalse(hit)
        with patch(
            "election_audit.archive_parsing._Parser.archive", side_effect=AssertionError("reparsed")
        ):
            self.assertEqual(parse_object(self.source, self.store), (path, True))
        second, hit = parse_object(
            self.source, self.store, config=replace(ParseConfig(), max_issues=1)
        )
        self.assertNotEqual(path, second)
        (path / "events.jsonl").write_bytes(b"corrupt\n")
        rebuilt, hit = parse_object(self.source, self.store)
        self.assertEqual(rebuilt, path)
        self.assertFalse(hit)
        self.assertEqual(len(list((self.store / "cache").glob(".corrupt-*"))), 1)
        inspect_artifact(path)
        abandoned = self.store / "cache" / ".parse-building-abandoned"
        abandoned.mkdir()
        config = replace(ParseConfig(), max_issues=3)
        with patch("election_audit.archive_parsing._Parser.archive", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                parse_object(self.source, self.store, config=config)
        self.assertEqual(list((self.store / "cache").glob(".parse-building-*")), [abandoned])
        recovered, hit = parse_object(self.source, self.store, config=config)
        inspect_artifact(recovered)
        self.assertFalse(hit)

    def test_mutating_input_is_never_published_and_invalid_limits_rejected(self) -> None:
        self.source.write_bytes(archive_bytes([("logd.dat", log_line())]))
        actual_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaises(ParseError):
            parse_object(self.source, self.store, expected_sha256="0" * 64)
        with patch(
            "election_audit.archive_parsing.hash_file", side_effect=[(actual_sha, 1), ("0" * 64, 1)]
        ):
            with self.assertRaisesRegex(ParseError, "changed"):
                parse_object(self.source, self.store)
        self.assertEqual(list((self.store / "cache").glob("[0-9a-f]*")), [])
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                ParseConfig(max_depth=value)


class ParseSnapshotTests(SourceFixture):
    def setUp(self) -> None:
        super().setUp()
        self.store = Path(self.temporary.name) / "derived"

    def frozen(self) -> Path:
        self.save_index([{"ns": "0001", "da": "date"}, {"ns": "0002", "da": "date"}])
        self.record_section()
        self.save(self.log_url, archive_bytes([("logd.dat", log_line() + b"malformed SECRET\n")]))
        self.save(
            aux_url(self.key),
            {
                "f": "o",
                "hashes": [
                    {"hash": "pkg", "st": "Totalizado", "arq": [{"nm": "a-log.dat", "tp": "log"}]},
                    {"hash": "pkg2", "st": "future", "arq": [{"nm": "b-log.dat", "tp": "log"}]},
                ],
            },
        )
        second_url = self.log_url.replace("/pkg/a-log.dat", "/pkg2/b-log.dat")
        self.save(second_url, archive_bytes([("logd.dat", log_line() + b"malformed SECRET\n")]))
        return create_snapshot(self.root, Path(self.temporary.name) / "snapshots", ["ac"])

    def test_same_content_multiple_packages_observations_and_snapshots_parse_once(self) -> None:
        snapshot = self.frozen()
        publication = parse_snapshot(snapshot, self.store)
        document = inspect_parse(publication)
        self.assertEqual(len(document["artifacts"]), 1)
        self.assertEqual(len(document["associations"]), 2)
        witnesses = list(iter_event_witnesses(publication))
        self.assertEqual(len(witnesses), 2)
        self.assertEqual(len({row["event_id"] for row in witnesses}), 1)
        self.assertEqual(len({row["witness_event_id"] for row in witnesses}), 2)
        self.assertEqual(
            {row["package_assets"][0]["filename"] for row in witnesses}, {"a-log.dat", "b-log.dat"}
        )
        self.assertEqual(validate_rows("record_lineage", list(iter_lineage(publication))), [])
        self.assertEqual(validate_rows("parsing_issue", list(iter_parsing_issues(publication))), [])
        with patch(
            "election_audit.archive_parsing._Parser.archive", side_effect=AssertionError("reparsed")
        ):
            self.assertEqual(parse_snapshot(snapshot, self.store), publication)
            other = create_snapshot(self.root, Path(self.temporary.name) / "snapshots", ["ac"])
            second = parse_snapshot(other, self.store)
        self.assertNotEqual(publication, second)
        self.assertEqual(len(list(iter_event_witnesses(second))), 2)
        self.assertEqual(
            inspect_parse(publication)["coverage_summary"]["national_status"], "partial_national"
        )

    def test_only_frozen_objects_and_no_output_inside_source(self) -> None:
        snapshot = self.frozen()
        for path in (self.root / "objects").rglob("*"):
            if path.is_file():
                path.unlink()
        publication = parse_snapshot(snapshot / "snapshot.json", self.store)
        self.assertEqual(len(list(iter_event_witnesses(publication))), 2)
        from election_audit.cli import main

        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["parse", str(snapshot), "--store", str(self.store)]), 0)
        self.assertEqual(Path(output.getvalue().strip()), publication)
        for unsafe in (snapshot / "derived", self.root / "derived"):
            with self.assertRaises(ParseError):
                parse_snapshot(snapshot, unsafe)
            self.assertFalse(unsafe.exists())

    def test_missing_asset_retains_association_without_false_parse_success(self) -> None:
        self.record_section()
        self.advertise()
        self.save(
            aux_url(self.key),
            {
                "f": "o",
                "hashes": [
                    {"hash": "pkg", "st": "Totalizado", "arq": [{"nm": "a-log.dat", "tp": "log"}]},
                ],
            },
        )
        snapshot = create_snapshot(self.root, Path(self.temporary.name) / "snapshots", ["ac"])
        publication = parse_snapshot(snapshot, self.store)
        document = inspect_parse(publication)
        self.assertEqual(document["artifacts"], [])
        self.assertTrue(document["associations"])
        self.assertTrue(document["historical_advertisements"])
        self.assertTrue(
            all(row["observation"]["object_sha256"] is None for row in document["associations"])
        )
        self.assertEqual(list(iter_event_witnesses(publication)), [])


if __name__ == "__main__":
    unittest.main()
