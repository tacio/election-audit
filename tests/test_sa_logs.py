import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from election_audit import sa_logs

BASE = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/dados"
OPERATOR = "151116550256"


def line(stamp, app, message) -> str:
    return f"{stamp}\tINFO\t02254078\t{app}\t{message}\t0123456789ABCDEF"


def attempt(day, clock, municipality, zone, section, *, kind, reason="Outros", cancel=False):
    rows = [
        line(f"{day} {clock}:00", "SA", f"Tipo de apuração selecionada ({kind})"),
        line(f"{day} {clock}:01", "SA", "Identificação (município, zona e seção) confirmada"),
        line(f"{day} {clock}:01", "SA", f"Município: {municipality}"),
        line(f"{day} {clock}:01", "SA", f"Zona Eleitoral: {zone}"),
        line(f"{day} {clock}:01", "SA", f"Seção Eleitoral: {section}"),
    ]
    if cancel:
        return rows + [line(f"{day} {clock}:02", "SA", "Apuração cancelada")]
    return rows + [
        line(f"{day} {clock}:03", "SA", f"Motivo da apuração: {reason}"),
        line(f"{day} {clock}:04", "SA", "Início da digitação de BU"),
        line(f"{day} {clock}:04", "SA", "Início da digitação de BU para o cargo [Pres.]"),
        line(f"{day} {clock}:05", "SA", "Término da digitação de BU para o cargo [Pres.]"),
        line(f"{day} {clock}:05", "SA", "Término da digitação de BU"),
        line(f"{day} {clock}:06", "SA", "Apuração iniciada majoritária federal"),
        line(f"{day} {clock}:07", "SA", "Apuração encerrada majoritária federal"),
        line(f"{day} {clock}:08", "SA", "Gerando arquivo de resultado [busa.dat] + [Início]"),
        line(f"{day} {clock}:09", "SA", "Gerando arquivo de resultado [busa.dat] + [Término]"),
    ]


def jez(rows):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("logd.dat", ("\n".join(rows) + "\n").encode("latin-1"))
    return stream.getvalue()


PREAMBLE = [
    line("04/10/2026 20:33:05", "GAP", "Modo de carga da UE - Urna de contingência"),
    line("04/10/2026 20:33:14", "GAP", f"MR gerada pelo usuário: {OPERATOR}"),
]
# MG: a cancelled attempt, an abandoned selection, then a completed retry.
MG = jez(
    PREAMBLE
    + attempt("04/10/2026", "20:39", "41238", "0039", "0168", kind="DIGITAÇÃO", cancel=True)
    + [line("04/10/2026 20:48:03", "SA", "Tipo de apuração selecionada (RECEPÇÃO)")]
    + attempt(
        "04/10/2026",
        "20:48",
        "41238",
        "0039",
        "0168",
        kind="DIGITAÇÃO",
        reason="Urna encerrada com eleitores na fila",
    )
)
# ZZ: a shared SA urn; this section's file also holds another section's attempt.
ZZ = jez(
    attempt("04/10/2026", "17:10", "29300", "0001", "0006", kind="DIGITAÇÃO DE BUEx")
    + attempt("04/10/2026", "17:20", "29254", "0001", "0001", kind="DIGITAÇÃO DE BUEx")
)
# A file whose log never names its own section.
ORPHAN = jez(attempt("04/10/2026", "18:00", "29300", "0001", "0006", kind="DIGITAÇÃO DE BUEx"))


class SaLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bodies = {}
        self.staged = self.stage(
            {
                ("mg", "41238", "0039", "0168"): ("o03220mg4123800390168-logsa.jez", MG),
                ("zz", "29254", "0001", "0001"): ("o03220zz2925400010001-logsa.jez", ZZ),
                ("zz", "29999", "0001", "0002"): ("o03220zz2999900010002-logsa.jez", ORPHAN),
                ("ac", "01007", "0009", "0001"): None,  # an urn-log section
            }
        )
        self.bulk = self.bulk_root()

    def stage(self, sections):
        staged = self.root / "staged"
        (staged / "objects").mkdir(parents=True)
        files = []
        for (uf, mun, zone, section), sa in sections.items():
            group = {"hash": f"h{mun}{section}", "st": "Totalizado", "arq": []}
            if sa:
                name, body = sa
                group["arq"] = [{"nm": name, "tp": "logsa"}, {"nm": "x-busa.dat", "tp": "busa"}]
                url = f"{BASE}/{uf}/{mun}/{zone}/{section}/{group['hash']}/{name}"
                self.bodies[url] = body
            else:
                group["arq"] = [{"nm": "x-log.jez", "tp": "log"}]
            aux = json.dumps({"f": "o", "st": "Totalizada", "hashes": [group]}).encode()
            digest = hashlib.sha256(aux).hexdigest()
            (staged / "objects" / f"{digest}.json").write_bytes(aux)
            aux_url = f"{BASE}/{uf}/{mun}/{zone}/{section}/p003220-{uf}-m{mun}-z{zone}-s{section}-aux.json"
            files.append((aux_url, f"objects/{digest}.json", digest))
        with contextlib.closing(sqlite3.connect(staged / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(url TEXT, path TEXT, sha256 TEXT)")
            db.executemany("INSERT INTO files VALUES(?,?,?)", files)
            db.commit()
        (staged / "staging-certificate.json").write_text(
            json.dumps({"round": 1, "manifest_sha256": "m" * 64})
        )
        return staged

    def bulk_root(self, *, tamper=None):
        bulk = self.root / ("bulk-tampered" if tamper else "bulk")
        (bulk / "files").mkdir(parents=True)
        rows = []
        by_uf = {}
        for url, body in self.bodies.items():
            uf = url.split("/dados/")[1][:2]
            name = url.rsplit("/", 1)[1]
            by_uf.setdefault(uf, []).append((name, b"tampered" + body if name == tamper else body))
        for uf, members in by_uf.items():
            path = bulk / "files" / f"bu_imgbu_logjez_rdv_vscmr_2026_1t_{uf.upper()}.zip"
            with zipfile.ZipFile(path, "w") as archive:
                for name, body in members:
                    archive.writestr(name, body)
            rows.append((f"files/{path.name}", hashlib.sha256(path.read_bytes()).hexdigest()))
        with contextlib.closing(sqlite3.connect(bulk / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path TEXT, sha256 TEXT, status TEXT)")
            db.executemany("INSERT INTO files VALUES(?,?,'complete')", rows)
            db.commit()
        return bulk

    def get(self, url):
        return self.bodies[url], '"e"', "Sun, 04 Oct 2026 23:00:00 GMT"

    def fetch(self, name="fetch", **options):
        return sa_logs.fetch(self.staged, 1, self.root / name, delay=0, get=self.get, **options)

    def test_fetch_lists_only_sa_logs_stores_them_and_matches_the_bulk_archive(self) -> None:
        result = self.fetch(bulk_root=self.bulk)
        self.assertEqual(result["listed"], 3)
        self.assertEqual(result["bulk_checks"], {"match": 3})
        out = self.root / "fetch"
        with contextlib.closing(sqlite3.connect(out / "manifest.sqlite")) as db:
            rows = db.execute("SELECT uf, path, sha256, bulk_check FROM files").fetchall()
        for uf, path, digest, check in rows:
            stored = out / path
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), digest)
            self.assertEqual(stored.stat().st_mode & 0o222, 0)
            self.assertEqual(check, "match")
        with self.assertRaises(FileExistsError):
            self.fetch(bulk_root=self.bulk)

    def test_a_bulk_mismatch_is_recorded_and_fails_the_run(self) -> None:
        tampered = self.bulk_root(tamper="o03220zz2925400010001-logsa.jez")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.fetch(bulk_root=tampered)
        with contextlib.closing(sqlite3.connect(self.root / "fetch" / "manifest.sqlite")) as db:
            checks = dict(db.execute("SELECT section, bulk_check FROM files").fetchall())
        self.assertEqual(checks["0001"], "mismatch")

    def test_hosts_outside_the_allow_list_and_broken_containers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "allow list"):
            sa_logs._get("https://example.invalid/x-logsa.jez")
        with self.assertRaises(zipfile.BadZipFile):
            sa_logs.check_jez(b"not a zip")

    def test_summary_attributes_attempts_by_printed_identity_only(self) -> None:
        self.fetch()
        exclusions = self.root / "exclusions.json"
        exclusions.write_text(json.dumps({"section_keys": []}))
        manifest = sa_logs.summarize([self.root / "fetch"], self.root / "summary", exclusions)
        rows = {
            r["section"]: r
            for r in pq.read_table(self.root / "summary" / "sa_sections.parquet").to_pylist()
        }
        mg = rows["0168"]
        self.assertEqual(mg["attribution"], "identity-match")
        self.assertEqual((mg["section_attempts"], mg["section_attempts_cancelled"]), (2, 1))
        self.assertEqual(mg["counting_type"], "DIGITAÇÃO")  # not the abandoned selection
        self.assertEqual(mg["reason"], "Urna encerrada com eleitores na fila")
        self.assertTrue(mg["contingency_urn"])
        self.assertEqual(mg["busa_generated"], "2026-10-04T20:48:09")
        zz = rows["0001"]
        self.assertEqual(zz["attribution"], "identity-match")
        self.assertEqual((zz["file_sections_completed"], zz["section_attempts"]), (2, 1))
        self.assertEqual(zz["attempt_start"], "2026-10-04T17:20:01")
        orphan = rows["0002"]
        self.assertEqual(orphan["attribution"], "no-completed-matching-attempt")
        self.assertIsNone(orphan["counting_type"])
        self.assertEqual(manifest["rows"], 3)
        written = (self.root / "summary" / "sa_sections.parquet").read_bytes()
        self.assertNotIn(OPERATOR.encode(), written)

    def test_protected_sections_are_skipped_before_reading(self) -> None:
        self.fetch()
        stored = self.root / "fetch" / "objects"
        protected = ["zz", "29254", "0001", "0001"]
        exclusions = self.root / "exclusions.json"
        exclusions.write_text(json.dumps({"section_keys": [protected]}))
        with contextlib.closing(sqlite3.connect(self.root / "fetch" / "manifest.sqlite")) as db:
            path = db.execute("SELECT path FROM files WHERE section='0001'").fetchone()[0]
        (self.root / "fetch" / path).chmod(0o644)
        (self.root / "fetch" / path).write_bytes(b"unreadable if read")
        manifest = sa_logs.summarize([self.root / "fetch"], self.root / "summary", exclusions)
        self.assertEqual((manifest["rows"], manifest["excluded"]), (2, {"round 1": 1}))
        self.assertTrue(stored.exists())

    def test_attempts_on_another_round_date_are_not_attributed(self) -> None:
        late = jez(attempt("25/10/2026", "17:00", "41238", "0039", "0168", kind="X"))
        row = {
            "round": 1,
            "uf": "mg",
            "municipality": "41238",
            "zone": "0039",
            "section": "0168",
            "sha256": "s",
            "bytes": len(late),
        }
        summary = sa_logs.summarize_row(row, late)
        self.assertEqual(summary["file_round_attempts"], 0)
        self.assertEqual(summary["attribution"], "no-completed-matching-attempt")


if __name__ == "__main__":
    unittest.main()
