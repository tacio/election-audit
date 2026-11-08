"""Normalized fixtures are not real TSE BU acceptance evidence."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from election_audit.electoral_imports import read_import
from election_audit.publication import SCHEMA, PublicationError


def row(name: str, **values: Any) -> dict[str, Any]:
    result = {key: values.get(key) for key in SCHEMA[name]["fields"]}
    result["field_states"] = {key: "unknown" for key, value in result.items() if value is None}
    return result


def bundle_at(root: Path, tables: dict[str, list[dict[str, Any]]]) -> Path:
    sources = []
    for name, rows in tables.items():
        data = "".join(json.dumps(r) + "\n" for r in rows).encode()
        (root / f"{name}.jsonl").write_bytes(data)
        sources.append(
            {
                "path": f"{name}.jsonl",
                "sha256": hashlib.sha256(data).hexdigest(),
                "table": name,
                "format": "jsonl",
                "encoding": "utf-8",
                "official_url": "fixture://normalized-only/" + name,
                "observed_at": "2026-10-29T00:00:00+00:00",
                "schema_evidence": ["fixture contract, no official header verified"],
            }
        )
    path = root / "bundle.json"
    path.write_text(
        json.dumps(
            {
                "adapter": "electoral-normalized-v1",
                "verification_status": "normalized_only",
                "sources": sources,
            }
        )
    )
    return path


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_originals_lineage_retransmission_and_explicit_verification(self) -> None:
        choice = row(
            "vote_choice", vote_choice_id="c", contest_id="p", choice_code="x", choice_kind="blank"
        )
        path = bundle_at(self.root, {"vote_choice": [choice, choice]})
        imported = read_import(path)
        self.assertEqual(imported["tables"]["vote_choice"], [choice])
        self.assertEqual(len(imported["tables"]["record_lineage"]), 2)
        self.assertEqual(imported["verification_status"], "normalized_only")
        self.assertEqual(
            next(iter(imported["originals"].values())),
            (self.root / "vote_choice.jsonl").read_bytes(),
        )

    def test_schema_categories_types_hash_encoding_and_naive_timestamp_rejected(self) -> None:
        for change in ({"choice_kind": "invented"}, {"choice_code": 99}):
            choice = row(
                "vote_choice",
                vote_choice_id="c",
                contest_id="p",
                choice_code="x",
                choice_kind="blank",
            )
            choice.update(change)
            with self.assertRaises(PublicationError):
                read_import(bundle_at(self.root, {"vote_choice": [choice]}))
        result = row(
            "result_version",
            result_version_id="v",
            principal_section_id="s",
            contest_id="p",
            generated_at="2026-10-25T17:00:00",
            result_status="totalized",
        )
        with self.assertRaises(PublicationError):
            read_import(bundle_at(self.root, {"result_version": [result]}))
        path = bundle_at(self.root, {})
        doc = json.loads(path.read_text())
        doc["verification_status"] = "official_verified"
        path.write_text(json.dumps(doc))
        with self.assertRaises(PublicationError):
            read_import(path)

    def test_exact_csv_header_and_utf8_only(self) -> None:
        path = bundle_at(self.root, {"vote_choice_count": []})
        doc = json.loads(path.read_text())
        spec = doc["sources"][0]
        spec["format"] = "csv"
        raw = b"result_version_id;vote_choice_id;vote_count;field_states\nv;c;1;{}\n"
        (self.root / spec["path"]).write_bytes(raw)
        spec["sha256"] = hashlib.sha256(raw).hexdigest()
        path.write_text(json.dumps(doc))
        self.assertEqual(read_import(path)["tables"]["vote_choice_count"][0]["vote_count"], 1)
        raw = raw.replace(b"vote_count;", b"votes;")
        (self.root / spec["path"]).write_bytes(raw)
        spec["sha256"] = hashlib.sha256(raw).hexdigest()
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(PublicationError, "header"):
            read_import(path)
        spec["encoding"] = "latin-1"
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(PublicationError, "encoding"):
            read_import(path)

    def test_conflicting_immutable_rows_and_duplicate_json_key(self) -> None:
        rows = [
            row("vote_choice_count", result_version_id="v", vote_choice_id="c", vote_count=n)
            for n in (1, 2)
        ]
        with self.assertRaisesRegex(PublicationError, "immutable"):
            read_import(bundle_at(self.root, {"vote_choice_count": rows}))
        path = self.root / "bundle.json"
        path.write_text('{"adapter":"a","adapter":"b"}')
        with self.assertRaisesRegex(PublicationError, "Duplicate"):
            read_import(path)
