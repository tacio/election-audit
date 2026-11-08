"""Phase 20b GEDAI check: BU urn loads against the preparation logs."""

import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import gedai

LINES = [
    "Usuário Windows: 99999999999",
    "Transmitida a correspondência de seção: município 01015, zona 0002, seção 0088, "
    "carga 111111111111111111111111, id urna 02263093, mc CB28DF40.",
    "Mídia de carga gerada. NS:CB28DF40 Z:0002 | Seções  (M:01015) 0075 0088",
    "Recebida correspondência de contingência: município 01392, zona 0001, "
    "carga 222222222222222222222222, id urna 02046630, mc ECCE29DD.",
    "Transmitida a correspondência de seção: município 01015, zona 0002, seção 0090, "
    "carga 333333333333333333333333, id urna 02000001, mc 00000001.",
]


def zipped(name: str, body: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr(name, body)
    return stream.getvalue()


def archive(lines: list[str]) -> bytes:
    log = "".join(f"18/09/2026 15:00:00\tINFO\t{m}\tABCDEF\n" for m in lines).encode("latin-1")
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as z:
        z.writestr("gedai-ue-ac-oficial-ZAC001STD25-log.jez", zipped("gedai-ue.log", log))
        z.writestr("gedai-ue-ac-oficial-ZAC001STD25-log.vsc", b"signature")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("leiame.pdf", b"%PDF")
        z.writestr("gedai-ue-ac-03220-oficial-ZAC001STD25-X-Y-log.jez", package.getvalue())
    return stream.getvalue()


def bu(
    section: str, load: str | None, urn: str | None, serial: str | None, **extra: Any
) -> dict[str, Any]:
    row = {
        "uf": "ac",
        "municipality": "01015",
        "zone": "0002",
        "section": section,
        "package": "urn",
        "bu_status": "decoded",
        "urn_serial": urn,
        "load_code": load,
        "flash_serial": serial,
    }
    return row | extra


class GedaiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "gedai"
        (self.root / "files").mkdir(parents=True)
        path = "files/log_gedai_1t_AC_041020261441.zip"
        body = archive(LINES)
        (self.root / path).write_bytes(body)
        with contextlib.closing(sqlite3.connect(self.root / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path, sha256, bytes, status)")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?)",
                (path, hashlib.sha256(body).hexdigest(), len(body), "complete"),
            )
            db.commit()

    def test_correspondences_and_media_are_parsed_without_operator_lines(self) -> None:
        parsed = gedai.parse_archives(self.root, gedai.gedai_archives(self.root))
        key = ("01015", "0002", "0088")
        self.assertEqual(
            parsed["sections"][key], {("111111111111111111111111", "2263093", "CB28DF40", 1)}
        )
        self.assertIn(key, parsed["media"]["CB28DF40"])
        self.assertEqual(
            parsed["contingency"][("222222222222222222222222", "2046630")],
            {("01392", "0001", "ECCE29DD", 1)},
        )
        self.assertNotIn("99999999999", repr(parsed))

    def test_rules_per_section(self) -> None:
        parsed = gedai.parse_archives(self.root, gedai.gedai_archives(self.root))
        ok = gedai.section_rules(bu("0088", "1" * 24, "2263093", "cb28df40"), parsed)
        self.assertEqual((ok["correspondence"], ok["failed_json"]), ("section", "[]"))
        moved = gedai.section_rules(bu("0437", "2" * 24, "2046630", "ECCE29DD"), parsed)
        self.assertEqual(moved["correspondence"], "contingency_other_zone")
        self.assertEqual(moved["failed_json"], "[]")
        absent = gedai.section_rules(bu("0088", "4" * 24, "2263093", "CB28DF40"), parsed)
        self.assertEqual(json.loads(absent["failed_json"]), ["G1"])
        medium = gedai.section_rules(bu("0088", "1" * 24, "2263093", "00000000"), parsed)
        self.assertEqual(json.loads(medium["failed_json"]), ["G2", "G3"])  # no such medium
        uncovered = gedai.section_rules(bu("0090", "3" * 24, "2000001", "00000001"), parsed)
        self.assertEqual(
            (uncovered["load_medium"], json.loads(uncovered["failed_json"])), ("absent", ["G3"])
        )

    def test_pass_writes_a_release_bound_to_its_inputs(self) -> None:
        release = self.base / "sections" / "release"
        release.mkdir(parents=True)
        rows = [bu("0088", "1" * 24, "2263093", "CB28DF40"), bu("0091", None, None, None)]
        pq.write_table(pa.Table.from_pylist(rows), release / "sections.parquet")
        files = {"sections.parquet": {"sha256": gedai.sha(release / "sections.parquet")}}
        (release / "manifest.json").write_text(json.dumps({"round": 1, "files": files}))
        result = gedai.run_gedai(self.base / "sections", [self.root], self.base / "out")
        self.assertEqual(result["summary"]["correspondence"], {"section": 1, "no_bu_load": 1})
        self.assertIn(str(self.root), result["gedai"])
        with self.assertRaises(FileExistsError):
            gedai.run_gedai(self.base / "sections", [self.root], self.base / "out")
        (self.root / "files/log_gedai_1t_AC_041020261441.zip").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            gedai.gedai_archives(self.root)


if __name__ == "__main__":
    unittest.main()
