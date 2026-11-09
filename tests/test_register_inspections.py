"""Inspection registration of sections seen in integrity outputs (xr1 P7-11)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.register_inspections import register


class RegisterInspectionTests(unittest.TestCase):
    def test_each_seen_section_registers_its_polling_place_once_per_source(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            table = root / "sections.parquet"
            pq.write_table(
                pa.Table.from_pylist(
                    [
                        {
                            "uf": "ac",
                            "municipality": "01007",
                            "zone": "0001",
                            "section": "0010",
                            "location_key": "place-a",
                        },
                        {
                            "uf": "ac",
                            "municipality": "01007",
                            "zone": "0001",
                            "section": "0011",
                            "location_key": "place-a",
                        },
                    ]
                ),
                table,
            )
            seen = root / "discrepancies.jsonl"
            rows = [
                {
                    "check": "I5",
                    "uf": "ac",
                    "municipality": "01007",
                    "zone": "0001",
                    "section": "0010",
                },
                {
                    "check": "I7",
                    "uf": "ac",
                    "municipality": "01007",
                    "zone": "0001",
                    "section": "0011",
                },
                {"check": "I4", "uf": "ac", "municipality": "01007", "level": "municipality"},
                {
                    "check": "G1",
                    "uf": "am",
                    "municipality": "02003",
                    "zone": "0005",
                    "section": "0001",
                },
            ]
            seen.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            registry = root / "registry.sqlite"
            result = register(registry, [seen], [table], "phase20b_disagreeing_rows")
            self.assertEqual(result, {"sections": 3, "entries": 2, "unplaced": 1})
            with sqlite3.connect(registry) as db:
                ids = sorted(r[0] for r in db.execute("SELECT stable_location_id FROM inspection"))
                evidence = json.loads(db.execute("SELECT evidence FROM inspection").fetchone()[0])
            self.assertEqual(ids, ["location:place-a", "section:am:02003:0005:0001"])
            self.assertTrue(
                evidence["record_locator"].endswith("#line1")
                or "#line4" in evidence["record_locator"]
            )
            self.assertEqual(
                register(registry, [seen], [table], "phase20b_disagreeing_rows")["entries"], 2
            )


if __name__ == "__main__":
    unittest.main()
