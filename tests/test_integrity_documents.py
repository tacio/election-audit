import contextlib
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from election_audit import integrity_documents as docs


def record(url, body, *, status=200, kind="application/pdf"):
    return {
        "uf": "sp",
        "title": url.rsplit("/", 1)[-1],
        "url": url,
        "status": status,
        "type": kind,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "last_modified": "Tue, 27 Oct 2026 21:07:20 GMT",
    }


class IntegrityDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()

    def write_records(self, court, records):
        body = {"uf": court, "collected_at": "2026-11-04T16:00:00Z", "records": records}
        (self.downloads / f"ea-integrity-manifest-{court}.json").write_text(json.dumps(body))

    def test_files_are_matched_by_hash_not_name_and_stored_read_only(self):
        ata, lista = b"%PDF ata do teste", b"<html>urnas</html>"
        (self.downloads / "Ata (1).pdf").write_bytes(ata)  # renamed by the browser
        (self.downloads / "x.html").write_bytes(lista)
        (self.downloads / "unrelated.pdf").write_bytes(b"other")
        self.write_records(
            "sp",
            [
                record("https://www.tre-sp.jus.br/a/ata", ata),
                record("https://www.tre-sp.jus.br/a/lista", lista, kind="text/html"),
                record("https://www.tre-sp.jus.br/a/gone", b"x" * 9, status=404),
            ],
        )
        result = docs.ingest(self.downloads, self.root / "out")
        self.assertEqual(result["courts"], {"sp": {"filed": 2, "not-served": 1}})
        with contextlib.closing(sqlite3.connect(self.root / "out" / "manifest.sqlite")) as db:
            rows = db.execute("SELECT path, sha256 FROM documents WHERE outcome='filed'").fetchall()
        for path, digest in rows:
            stored = self.root / "out" / path
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), digest)
            self.assertEqual(stored.stat().st_mode & 0o222, 0)
        self.assertTrue((self.root / "out" / "records" / "ea-integrity-manifest-sp.json").exists())
        with self.assertRaises(FileExistsError):
            docs.ingest(self.downloads, self.root / "out")

    def test_a_served_document_without_its_bytes_is_missing_not_dropped(self):
        self.write_records("df", [record("https://www.tre-df.jus.br/ata", b"never saved")])
        (self.downloads / "same-size.pdf").write_bytes(b"other bytes")  # same length
        result = docs.ingest(self.downloads, self.root / "out")
        self.assertEqual(result["documents"], {"missing": 1})

    def test_record_files_must_name_a_court(self):
        (self.downloads / "ea-integrity-manifest-x.json").write_text(json.dumps({"records": []}))
        with self.assertRaisesRegex(ValueError, "no court"):
            docs.ingest(self.downloads, self.root / "out")


if __name__ == "__main__":
    unittest.main()
