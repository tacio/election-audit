"""Metadata-only workload samples, immutable selection and explicit inspection history."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from election_audit.national import _read_json
from election_audit.national_benchmark import profile_source, select_sample


class WorkloadTests(unittest.TestCase):
    def test_deterministic_size_bands_tail_and_inspection_before_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "source.sqlite"
            with closing(sqlite3.connect(manifest)) as db:
                db.executescript(
                    "CREATE TABLE files(url TEXT,path TEXT,sha256 TEXT,bytes INTEGER); CREATE TABLE runs(id TEXT,status TEXT); INSERT INTO runs VALUES ('observed','finished');"
                )
                for uf in ["ac", "zz"]:
                    db.executemany(
                        "INSERT INTO files VALUES (?,?,?,?)",
                        (
                            (
                                f"https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/{uf}/01007/0001/{i:04d}/package/a-log.jez",
                                f"objects/{i:064x}",
                                f"{i:064x}",
                                i * 100,
                            )
                            for i in range(1, 17)
                        ),
                    )
                db.commit()
            spec = {
                "round": 2,
                "root": str(root / "raw"),
                "manifest": str(manifest),
                "ufs": ["ac", "zz"],
            }
            with patch("election_audit.national_benchmark.guard"):
                profile = profile_source(spec, root / "profile", root / "scratch")
            first = select_sample(profile, root / "first", per_band=1)
            second = select_sample(profile, root / "second", per_band=1)
            self.assertEqual(first["sample_id"], second["sample_id"])
            self.assertEqual(len(first["units"]), 10)
            self.assertEqual(first["regions"], {"north": 5, "overseas": 5})
            self.assertTrue(all("size_band" in u for u in first["units"]))
            self.assertTrue(
                _read_json(root / "first/inspection.json")["before_log_outcome_inspection"]
            )
            self.assertFalse((root / "raw").exists())
            doc = _read_json(profile / "profile.json")
            self.assertEqual(doc["source_rows"], 32)
            self.assertEqual(len(doc["strata"]), 8)
            with self.assertRaises(ValueError):
                select_sample(profile, root / "zero", per_band=0)
            from election_audit.national import _write_json

            excluded = {
                "version": "structural-sample-exclusions-v1",
                "round": 2,
                "section_keys": [["ac", "01007", "0001", "0001"], ["ac", "01007", "0001", "0016"]],
            }
            _write_json(root / "excluded.json", excluded)
            protected = select_sample(
                profile, root / "protected", per_band=1, exclusions=root / "excluded.json"
            )
            keys = {tuple(k) for k in protected["config"]["sources"][0]["section_keys"]}
            self.assertTrue(all(tuple(k) not in keys for k in excluded["section_keys"]))
            self.assertEqual(len(protected["units"]), 10)
            self.assertEqual(protected["exclusions"]["section_count"], 2)
