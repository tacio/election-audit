"""Phase 20b hash lists: logged package names against TSE's lists."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import hash_lists as hl


def page(rows: list[tuple[str, ...]]) -> bytes:
    cells = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    text = f"<html><table><tr><th>Arquivo</th><th>SHA512b64</th></tr>{cells}</table></html>"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("path1u.html", text.encode("utf-8"))
        z.writestr("__MACOSX/._path1u.html", b"x")
    return stream.getvalue()


class HashListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.lists = self.base / "lists"
        self.lists.mkdir()
        for model, stem in hl.LISTS.items():
            suffix = model[2:]
            rows = [
                ("ARQUIVOS BASE",),
                ("/bin/avbin.vst", "AAAA"),
                (f"/lib/modules/ue{suffix}/avmodue.vst", "BBBB"),
                ("UF = AC",),
                ("AC - /dsk/fi/estatico/chave/avusrchave.vst", "CCCC"),
            ]
            (self.lists / f"{stem}.zip").write_bytes(page(rows))

    def test_lists_are_read_by_block(self) -> None:
        blocks = hl.read_list(self.lists / "path1u20.zip")
        self.assertEqual(set(blocks), {"ARQUIVOS BASE", "UF = AC"})
        self.assertIn("/dsk/fi/estatico/chave/avusrchave.vst", blocks["UF = AC"])

    def test_each_listing_kind(self) -> None:
        names = {
            m: {p for b in hl.read_list(self.lists / f"{s}.zip").values() for p in b}
            for m, s in hl.LISTS.items()
        }
        cases = {
            "/bin/avbin.vst": "exact",
            "/lib/modules/ue2013/avmodue.vst": "other_model",
            "/lib/modules/ue2020/avmodue2020.vst": "model_suffix",
            "/dsk/fe/estatico/jez/vota_apl.vst": "not_listed",
            "/dsk/fi/estatico/o#ac-ce.vsc": "data_file",
        }
        for path, expected in cases.items():
            self.assertEqual(hl.listing("UE2020", path, names), expected, path)

    def test_pass_counts_failures_and_unlisted_programs(self) -> None:
        release = self.base / "semantic" / "release"
        release.mkdir(parents=True)
        rows = [
            ("UE2020", "GAP", "startup", "/bin/avbin.vst", None, "SUCESSO", 10, 5),
            ("UE2020", "GAP", "startup", "/bin/avbin.vst", None, "ERRO", 1, 1),
            (
                "UE2020",
                "SCUE",
                "aplicação",
                "/dsk/fe/estatico/jez/vota_apl.vst",
                "x",
                "SUCESSO",
                3,
                3,
            ),
        ]
        names = ("model", "application", "stage", "path", "file", "result", "events", "objects")
        table = pa.Table.from_pylist([dict(zip(names, r, strict=True)) for r in rows])
        pq.write_table(table, release / "packages.parquet")
        manifest = {
            "version": "session-aggregates-v5",
            "round": 1,
            "files": {"packages.parquet": {"sha256": hl.sha(release / "packages.parquet")}},
        }
        (release / "manifest.json").write_text(json.dumps(manifest))
        result = hl.run_hash_lists([self.base / "semantic"], self.lists, self.base / "out")
        summary = result["summary"]
        self.assertEqual(summary["program_verification_failures"], {"/bin/avbin.vst:ERRO": 1})
        self.assertEqual(summary["not_listed_programs"], ["/dsk/fe/estatico/jez/vota_apl.vst"])
        self.assertEqual(summary["listed"], {"exact": 1, "not_listed": 1})


if __name__ == "__main__":
    unittest.main()
