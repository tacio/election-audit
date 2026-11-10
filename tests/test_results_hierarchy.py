import contextlib
import hashlib
import json
import sqlite3
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from election_audit import results_hierarchy as rh

ROOT = "https://resultados.tse.jus.br/oficial/ele2026/6258"
CONFIG = {
    "dg": "15/10/2026",
    "hg": "10:00:00",
    "idg": "1",
    "f": "o",
    "abr": [
        {"cd": "ac", "ds": "ACRE", "mu": [{"cd": "01120"}, {"cd": "01570"}]},
        {"cd": "zz", "ds": "EXTERIOR", "mu": [{"cd": "29300"}]},
    ],
}


def unified(scope_type: str, scope: str, *, tf: str | None = "s", **changes: Any) -> bytes:
    value = {
        "ele": "6258",
        "t": "2",
        "f": "o",
        "tpabr": scope_type,
        "cdabr": scope,
        "dg": "25/10/2026",
        "hg": "23:26:56",
        "idg": "42",
        "tf": tf,
        "dv": "s",
        "carg": [{"cd": "1"}],
        "s": {"ts": "10", "st": "10"},
    }
    if tf is None:
        del value["tf"]
    value.update(changes)
    return json.dumps(value).encode()


def progress() -> bytes:
    return json.dumps(
        {"ele": "6258", "t": "2", "f": "o", "dg": "25/10/2026", "hg": "23:26:59", "abr": []}
    ).encode()


def bodies(**overrides: bytes) -> dict[str, bytes]:
    files = {
        f"{ROOT}/config/mun-e006258-cm.json": json.dumps(CONFIG).encode(),
        f"{ROOT}/dados/br/br-c0001-e006258-u.json": unified("br", "br"),
        f"{ROOT}/dados/br/br-e006258-ab.json": progress(),
    }
    for uf, municipalities in (("ac", ["01120", "01570"]), ("zz", ["29300"])):
        files[f"{ROOT}/dados/{uf}/{uf}-c0001-e006258-u.json"] = unified("uf", uf)
        files[f"{ROOT}/dados/{uf}/{uf}-e006258-ab.json"] = progress()
        for number in municipalities:
            files[f"{ROOT}/dados/{uf}/{uf}{number}-c0001-e006258-u.json"] = unified("mu", number)
    files.update(overrides)
    return files


class ResultsHierarchyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def getter(
        self, files: dict[str, bytes], fail_after: int | None = None
    ) -> tuple[Callable[[str], tuple[bytes, str | None, str | None]], list[str]]:
        calls = []

        def get(url: str) -> tuple[bytes, str | None, str | None]:
            if fail_after is not None and len(calls) >= fail_after:
                raise ConnectionError("network down")
            calls.append(url)
            return files[url], '"e"', "Mon, 26 Oct 2026 02:28:26 GMT"

        return get, calls

    def test_fetch_stores_every_scope_read_only_and_records_stamps(self) -> None:
        get, calls = self.getter(bodies())
        out = self.root / "r2"
        result = rh.fetch(2, out, delay=0, get=get)
        self.assertEqual(result["planned"], 9)
        self.assertEqual(
            result["files"],
            {
                "progress br": 1,
                "progress uf": 2,
                "unified br": 1,
                "unified mun": 3,
                "unified uf": 2,
            },
        )
        self.assertEqual(result["unified_not_final"], 0)
        self.assertEqual(len(calls), 10)
        with contextlib.closing(sqlite3.connect(out / "manifest.sqlite")) as db:
            rows = db.execute("SELECT path, sha256, generation_id FROM files").fetchall()
        for path, digest, _ in rows:
            stored = out / path
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), digest)
            self.assertEqual(stored.stat().st_mode & 0o222, 0)
        with self.assertRaises(FileExistsError):
            rh.fetch(2, out, delay=0, get=get)

    def test_an_interrupted_fetch_resumes_without_refetching(self) -> None:
        files = bodies()
        get, _ = self.getter(files, fail_after=4)
        out = self.root / "r2"
        with self.assertRaises(ConnectionError):
            rh.fetch(2, out, delay=0, get=get)
        get, calls = self.getter(files)
        result = rh.fetch(2, out, delay=0, resume=True, get=get)
        self.assertEqual(result["planned"], 9)
        self.assertEqual(len(calls), 6)
        with self.assertRaisesRegex(ValueError, "another round"):
            rh.fetch(1, out, delay=0, resume=True, get=get)

    def test_wrong_scope_round_or_unofficial_files_fail_closed(self) -> None:
        url = f"{ROOT}/dados/ac/ac01570-c0001-e006258-u.json"
        for bad, message in (
            (unified("mu", "01120"), "Wrong scope"),
            (unified("mu", "01570", t="1"), "Wrong election"),
            (unified("mu", "01570", f="s"), "Not an official"),
            (unified("mu", "01570", carg=[{"cd": "3"}]), "Presidential office"),
        ):
            get, _ = self.getter(bodies(**{url: bad}))
            with self.assertRaisesRegex(ValueError, message):
                rh.fetch(2, self.root / message, delay=0, get=get)

    def test_non_final_totalization_is_counted_not_hidden(self) -> None:
        url = f"{ROOT}/dados/zz/zz29300-c0001-e006258-u.json"
        get, _ = self.getter(bodies(**{url: unified("mu", "29300", tf="n")}))
        result = rh.fetch(2, self.root / "r2", delay=0, get=get)
        self.assertEqual(result["unified_not_final"], 1)
        # xr1-20261109-P5-06: a file without tf is unknown, never final
        get, _ = self.getter(bodies(**{url: unified("mu", "29300", tf=None)}))
        result = rh.fetch(2, self.root / "r2-unknown", delay=0, get=get)
        self.assertEqual(result["unified_final_unknown"], 1)

    def test_planned_rejects_malformed_configuration(self) -> None:
        broken = dict(CONFIG, abr=[{"cd": "ac", "mu": [{"cd": "1120"}]}])
        with self.assertRaisesRegex(ValueError, "municipality code"):
            list(rh.planned(broken, 2))
        with self.assertRaisesRegex(ValueError, "not official"):
            list(rh.planned(dict(CONFIG, f="s"), 2))


if __name__ == "__main__":
    unittest.main()
