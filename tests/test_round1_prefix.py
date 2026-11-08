"""I6 prefix re-read: round-1 blocks of runoff logs verified line by line."""

import contextlib
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from test_semantic_pass import CYCLES, TOKEN, VOTER, jez, log_body

from election_audit import round1_prefix as rp
from election_audit import semantic_pass as sp
from election_audit.integrity_checks import LOG_SECTION_SCHEMA, round1_statuses
from election_audit.national_migration import sha

PROTECTED = ("ac", "01015", "0002", "0101")
OPEN, INSERTED, DELETED, REPLACED, CLOSED = (
    ("ac", "01023", "0001", f"000{i}") for i in range(1, 6)
)


def lines(messages, device, *, date="04/10/2026", hour=18, app="VOTA"):
    return "".join(
        f"{date} {hour:02d}:{i // 60:02d}:{i % 60:02d}\tINFO\t{device}\t{app}\t{m}\t{TOKEN}\n"
        for i, m in enumerate(messages)
    ).encode("latin-1")


def split(body):
    return body.splitlines(keepends=True)


def urn_bodies(device):
    """Round-1 log, later round-1 lines, runoff lines and a new round-1 block of one urn."""
    return (
        log_body(CYCLES, round_number=1, date="04/10/2026", device=device),
        lines(["Aplicação encerrada", f"Mesário {VOTER} saiu"], device),
        log_body(CYCLES[:4], round_number=2, date="25/10/2026", device=device),
        lines(
            ["Iniciando aplicação - ELEIÇÃO OFICIAL PRIMEIRO TURNO - 1º turno"],
            device,
            hour=19,
            app="GAP",
        ),
    )


def staged(root, round_number, bodies) -> None:
    pleito = 3220 if round_number == 1 else 3221
    rows, logs = [], []
    for key, body in bodies.items():
        digest = hashlib.sha256(body).hexdigest()
        relative = f"objects/{digest[:2]}/{digest}.jez"
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(body)
        url = (
            f"https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/{pleito}/dados/"
            f"{'/'.join(key)}/hash/o0{pleito}-log.jez"
        )
        rows.append((url, relative, digest, len(body)))
        logs.append((url, "Totalizado"))
    with contextlib.closing(sqlite3.connect(root / "manifest.sqlite")) as db:
        db.execute("CREATE TABLE files(url,path,sha256,bytes)")
        db.execute("CREATE TABLE logs(url,package_status)")
        db.executemany("INSERT INTO files VALUES(?,?,?,?)", rows)
        db.executemany("INSERT INTO logs VALUES(?,?)", logs)
        db.commit()
    (root / "staging-certificate.json").write_text(
        json.dumps({"round": round_number, "manifest_sha256": "m" * 64})
    )


class DescribeTests(unittest.TestCase):
    @staticmethod
    def records(names):
        return [(n, f"2026-10-04T08:00:{i:02d}", "VOTA", n) for i, n in enumerate(names)]

    def test_insertion_deletion_and_replacement(self) -> None:
        a = self.records("abcdef")
        k, realigned, kind, detail = rp.describe(a, self.records("abXYcdefgh"))
        self.assertEqual((k, realigned, kind), (2, 4, "insertion_in_runoff"))
        self.assertEqual(detail["runoff"]["lines"], 2)
        self.assertEqual(detail["round1"]["lines"], 0)
        self.assertEqual(detail["runoff_tail_lines"], 2)
        k, realigned, kind, detail = rp.describe(a, self.records("abefgh"))
        self.assertEqual((k, realigned, kind), (2, 2, "deletion_in_runoff"))
        self.assertEqual(detail["round1"]["lines"], 2)
        self.assertEqual(detail["runoff_tail_lines"], 2)
        k, realigned, kind, detail = rp.describe(a, self.records("abXdef"))
        self.assertEqual((k, realigned, kind), (2, 3, "replacement"))
        self.assertEqual((detail["round1"]["lines"], detail["runoff"]["lines"]), (1, 1))


class PrefixPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        keys = (PROTECTED, OPEN, INSERTED, DELETED, REPLACED, CLOSED)
        urn = {key: urn_bodies(f"1000000{i}") for i, key in enumerate(keys)}
        first = {key: jez(urn[key][0]) for key in keys}
        # A closed round-1 block: a later restart opens another round-1 block in both logs.
        first[CLOSED] = jez(urn[CLOSED][0] + urn[CLOSED][3])
        r1 = {key: split(urn[key][0]) for key in keys}
        middle = len(r1[OPEN]) // 2
        malformed = b"not a log line\n"

        def body(key, block):
            return jez(b"".join(block) + urn[key][2])

        runoff = {
            PROTECTED: body(PROTECTED, [urn[PROTECTED][0], urn[PROTECTED][1]]),
            OPEN: body(OPEN, [urn[OPEN][0], malformed, urn[OPEN][1]]),
            INSERTED: body(
                INSERTED, [*r1[INSERTED][:middle], urn[INSERTED][1], *r1[INSERTED][middle:]]
            ),
            DELETED: body(
                DELETED, [*r1[DELETED][:middle], *r1[DELETED][middle + 1 :], urn[DELETED][1]]
            ),
            REPLACED: body(
                REPLACED,
                [
                    *r1[REPLACED][:middle],
                    r1[REPLACED][middle].replace(b"INFO", b"WARN"),
                    *r1[REPLACED][middle + 1 :],
                ],
            ),
            # The closed block grows in the runoff log before the restart.
            CLOSED: body(CLOSED, [urn[CLOSED][0], urn[CLOSED][1], urn[CLOSED][3]]),
        }
        self.middle, self.block_lines = middle, len(r1[OPEN])
        exclusions = base / "exclusions.json"
        exclusions.write_text(json.dumps({"section_keys": [list(PROTECTED)]}))
        self.semantic = {}
        for round_number, bodies in ((1, first), (2, runoff)):
            root = base / f"turno-{round_number}"
            staged(root, round_number, bodies)
            self.semantic[round_number] = base / f"semantic-{round_number}"
            sp.run_pass(
                root, round_number, self.semantic[round_number], exclusions_path=exclusions,
                workers=1,
            )  # fmt: skip
        # A minimal round-2 logs release bound to both semantic passes.
        statuses = round1_statuses(self.semantic[2] / "release", self.semantic[1] / "release")
        self.logs = base / "logs"
        release = self.logs / "release"
        release.mkdir(parents=True)
        rows = [
            {
                **dict(zip(("uf", "municipality", "zone", "section"), key, strict=True)),
                "log": "semantic" if key != PROTECTED else "protected_or_unavailable",
                "i6": statuses.get(key) if key != PROTECTED else None,
            }
            for key in runoff
        ]
        pq.write_table(
            pa.Table.from_pylist(rows, schema=LOG_SECTION_SCHEMA), release / "sections.parquet"
        )
        (release / "manifest.json").write_text(
            json.dumps(
                {
                    "round": 2,
                    "semantic_manifest_sha256": sha(self.semantic[2] / "release" / "manifest.json"),
                    "semantic_round1_manifest_sha256": sha(
                        self.semantic[1] / "release" / "manifest.json"
                    ),
                    "files": {"sections.parquet": {"sha256": sha(release / "sections.parquet")}},
                }
            )
        )
        self.output = base / "prefix"
        self.statuses = statuses

    def run_prefix(self, **options):
        return rp.run_prefix(
            self.logs, self.semantic[2], self.semantic[1], self.output, workers=1, **options
        )

    def test_prefixes_are_verified_and_differences_described(self) -> None:
        self.assertEqual(self.statuses[OPEN], "open_prefix_unverified")
        self.assertEqual(self.statuses[CLOSED], "differs+equal")
        result = self.run_prefix(chunk_objects=2)
        release = self.output / "release"
        sections = {
            (r["uf"], r["municipality"], r["zone"], r["section"]): r
            for r in pq.read_table(release / "sections.parquet").to_pylist()
        }
        self.assertEqual(sections[OPEN]["i6"], "equal_open_prefix_equal")
        self.assertEqual(sections[OPEN]["blocks_prefix_open"], 1)
        self.assertIsNone(sections[PROTECTED]["i6"])
        self.assertIn("prefix_closed", sections[CLOSED]["i6"].split("+"))
        self.assertEqual(sections[CLOSED]["blocks_prefix_closed"], 1)
        pairs = {
            (p["uf"], p["municipality"], p["zone"], p["section"]): p
            for p in pq.read_table(release / "pairs.parquet").to_pylist()
            if p["status"] == "differs"
        }
        self.assertEqual(pairs[INSERTED]["diff_kind"], "insertion_in_runoff")
        self.assertEqual(pairs[DELETED]["diff_kind"], "deletion_in_runoff")
        self.assertEqual(pairs[REPLACED]["diff_kind"], "replacement")
        self.assertEqual(pairs[INSERTED]["common_prefix"], self.middle)
        self.assertEqual(pairs[INSERTED]["realigned_lines"], self.block_lines - self.middle)
        self.assertEqual(pairs[REPLACED]["realigned_lines"], self.block_lines - self.middle - 1)
        self.assertEqual(result["summary"]["pair_status"].get("realignment_failed"), None)
        self.assertEqual(result["summary"]["object_errors"], 0)
        exported = b"".join(p.read_bytes() for p in release.iterdir())
        self.assertNotIn(TOKEN.encode(), exported)
        self.assertNotIn(VOTER.encode(), exported)
        with self.assertRaises(FileExistsError):
            self.run_prefix(chunk_objects=2)
        again = self.run_prefix(chunk_objects=2, resume=True)
        self.assertEqual(again["files"], result["files"])

    def test_tampered_staging_object_is_an_object_error(self) -> None:
        objects = pq.read_table(self.semantic[2] / "release" / "objects.parquet").to_pylist()
        target = next(o for o in objects if json.loads(o["witnesses_json"])[0] == list(OPEN))
        path = Path(self.temp.name) / "turno-2" / target["path"]
        path.write_bytes(path.read_bytes() + b"x")
        result = self.run_prefix()
        self.assertEqual(result["summary"]["object_errors"], 1)
        self.assertEqual(result["summary"]["pair_status"]["realignment_failed"], 1)


if __name__ == "__main__":
    unittest.main()
