"""Bulk acquisition records catalogs, resumes by range and refuses unsafe states."""

import contextlib
import hashlib
import http.server
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from election_audit import bulk_acquisition as bulk


def archive(text: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("a.bu", text * 50)
        z.writestr("b.logjez", text[::-1] * 50)
    return stream.getvalue()


class Server:
    """Range- and If-Range-aware fake of the TSE CKAN API and CDN."""

    def __init__(self) -> None:
        self.files = {"x_1t_AC.zip": archive("ac"), "x_1t_AL.zip": archive("al")}
        self.etags = {name: '"v1"' for name in self.files}
        self.cut = None  # (name, bytes) to truncate a GET once
        self.stale = set()  # names whose unqueried HEAD omits Content-Length
        self.stale_head = set()  # names whose unqueried HEAD reports an older ETag
        self.stale_get = {}  # name -> older body served on unqueried GETs
        self.requests = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _file(self) -> str:
                return self.path.split("?", 1)[0].rsplit("/", 1)[-1]

            def do_HEAD(self) -> None:
                name = self._file()
                busted = "?" in self.path
                self.send_response(200)
                stale = name in outer.stale and not busted
                if not name.endswith(".sha512") and not stale:
                    self.send_header("Content-Length", str(len(outer.files[name])))
                etag = outer.etags[name]
                if not busted and name in outer.stale_head:
                    etag = '"old"'  # an earlier version cached for HEAD only
                self.send_header("ETag", etag)
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            def do_GET(self) -> None:
                outer.requests.append((self.path, self.headers.get("Range")))
                if self.path.startswith("/api/"):
                    dataset = self.path.split("id=", 1)[1]
                    body = json.dumps(
                        {
                            "success": True,
                            "result": {
                                "resources": [
                                    {"id": n, "name": n, "url": f"{outer.base}/cdn/{n}"}
                                    for n in sorted(outer.files)
                                ]
                                + [{"id": "csv", "url": f"{outer.base}/cdn/{dataset}.csv"}]
                            },
                        }
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                name = self._file()
                body = outer.files[name]
                start = 0
                ranged = self.headers.get("Range")
                if ranged and self.headers.get("If-Range") == outer.etags[name]:
                    start = int(ranged.split("=")[1].rstrip("-"))
                    self.send_response(206)
                else:
                    self.send_response(200)
                payload = body[start:]
                self.send_header("Content-Length", str(len(payload)))
                stale = outer.stale_get.get(name)
                if stale and "?" not in self.path:
                    payload = stale  # an older cached copy of the same size
                    self.send_header("ETag", '"old"')
                else:
                    self.send_header("ETag", outer.etags[name])
                self.end_headers()
                if outer.cut and outer.cut[0] == name:
                    payload = payload[: outer.cut[1]]
                    outer.cut = None
                    self.wfile.write(payload)
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                self.wfile.write(payload)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class BulkAcquisitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = Server()
        self.addCleanup(self.server.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "bulk"

    def run_acquire(self, **options: Any) -> dict[str, Any]:
        return bulk.acquire(
            ["demo-dataset"],
            self.output,
            api=self.server.base + "/api/package_show?id=",
            allowed_prefixes=(self.server.base + "/cdn/",),
            reserve_gib=0,
            **options,
        )

    def rows(self) -> list[Any]:
        uri = (self.output / "manifest.sqlite").as_uri() + "?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
            return db.execute(
                "SELECT name,status,sha256,bytes,zip_members FROM files"
                " WHERE name NOT LIKE '%.sha512'"
            ).fetchall()

    def test_downloads_are_exact_read_only_and_catalogued(self) -> None:
        result = self.run_acquire()
        self.assertEqual(result["complete_files"], 2)
        for name, status, digest, size, members in self.rows():
            body = self.server.files[name]
            self.assertEqual(
                (status, digest, size, members),
                ("complete", hashlib.sha256(body).hexdigest(), len(body), 2),
            )
            path = self.output / "files" / name
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o444)
        catalogs = list((self.output / "catalog").iterdir())
        self.assertEqual(len(catalogs), 1)
        self.assertEqual(bulk.verify(self.output)["verified_files"], 2)
        self.assertEqual(json.loads((self.output / "status.json").read_text())["stage"], "finished")

    def test_existing_output_is_refused_and_resume_skips_complete_files(self) -> None:
        self.run_acquire()
        with self.assertRaises(FileExistsError):
            self.run_acquire()
        before = len(self.server.requests)
        self.run_acquire(resume=True)
        downloads = [p for p, _ in self.server.requests[before:] if "/cdn/" in p]
        self.assertEqual(downloads, [])

    def test_interrupted_download_resumes_with_a_range(self) -> None:
        self.server.cut = ("x_1t_AC.zip", 100)
        with self.assertRaises(Exception):
            self.run_acquire()
        partial = self.output / "files" / "x_1t_AC.zip.part"
        self.assertEqual(partial.stat().st_size, 100)
        self.run_acquire(resume=True)
        self.assertIn(("/cdn/x_1t_AC.zip", "bytes=100-"), self.server.requests)
        self.assertEqual(
            (self.output / "files" / "x_1t_AC.zip").read_bytes(), self.server.files["x_1t_AC.zip"]
        )

    def test_changed_server_object_restarts_instead_of_splicing(self) -> None:
        self.server.cut = ("x_1t_AC.zip", 100)
        with self.assertRaises(Exception):
            self.run_acquire()
        self.server.files["x_1t_AC.zip"] = archive("changed")
        self.server.etags["x_1t_AC.zip"] = '"v2"'
        self.run_acquire(resume=True)
        self.assertEqual(
            (self.output / "files" / "x_1t_AC.zip").read_bytes(), self.server.files["x_1t_AC.zip"]
        )

    def test_hosts_outside_the_allow_list_and_non_zips_fail_closed(self) -> None:
        resources = [{"url": "https://evil.example/x.zip"}]
        with self.assertRaisesRegex(ValueError, "outside"):
            bulk.select_resources(resources, r"\.zip$")
        resources = [{"url": "https://cdn.tse.jus.br/estatistica/sead/eleicoes/../x.zip"}]
        with self.assertRaisesRegex(ValueError, "file name|outside"):
            bulk.select_resources(resources, r"\.zip$", ("https://cdn.tse.jus.br/",))

    def test_not_a_zip_is_not_accepted(self) -> None:
        self.server.files["x_1t_AL.zip"] = b"not a zip"
        with self.assertRaises(zipfile.BadZipFile):
            self.run_acquire()
        self.assertFalse((self.output / "files" / "x_1t_AL.zip").exists())

    def test_published_sha512_companions_are_fetched_and_reconciled(self) -> None:
        body = self.server.files["x_1t_AC.zip"]
        published = hashlib.sha512(body).hexdigest().upper().encode() + b"  x_1t_AC.zip\n"
        self.server.files["x_1t_AC.zip.sha512"] = published
        self.server.etags["x_1t_AC.zip.sha512"] = '"s1"'
        result = self.run_acquire()
        self.assertEqual(result["published_sha512"], {"match": 1, "not_published": 1})
        self.assertEqual(result["complete_files"], 3)

    def test_published_sha512_mismatch_fails_the_run(self) -> None:
        self.server.files["x_1t_AC.zip.sha512"] = b"0" * 128 + b"\n"
        self.server.etags["x_1t_AC.zip.sha512"] = '"s1"'
        with self.assertRaisesRegex(ValueError, "published SHA-512"):
            self.run_acquire()
        uri = (self.output / "manifest.sqlite").as_uri() + "?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
            state = db.execute(
                "SELECT published_sha512 FROM files WHERE name='x_1t_AC.zip'"
            ).fetchone()[0]
        self.assertEqual(state, "mismatch")

    def test_unsized_archives_are_refused_but_unsized_checksums_are_capped(self) -> None:
        with self.assertRaisesRegex(ValueError, "length"):
            bulk.download_one(
                "http://unused.invalid/x.zip",
                Path(self.temp.name) / "x.zip",
                {"bytes": None, "etag": None, "ranges": False},
                reserve=0,
            )
        self.server.files["x_1t_AC.zip.sha512"] = b"0" * (bulk.UNSIZED_LIMIT + 1)
        self.server.etags["x_1t_AC.zip.sha512"] = '"s1"'
        with self.assertRaisesRegex(ValueError, "more bytes"):
            self.run_acquire()

    def test_stale_cdn_copy_without_length_is_revalidated_once(self) -> None:
        self.server.stale.add("x_1t_AL.zip")
        result = self.run_acquire()
        self.assertEqual(result["complete_files"], 2)
        body = self.server.files["x_1t_AL.zip"]
        self.assertIn(
            ("x_1t_AL.zip", "complete", hashlib.sha256(body).hexdigest()),
            [row[:3] for row in self.rows()],
        )

    def test_stale_cdn_head_from_an_earlier_version_is_bypassed(self) -> None:
        self.server.stale_head.add("x_1t_AL.zip")
        self.run_acquire()
        uri = (self.output / "manifest.sqlite").as_uri() + "?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
            etag = db.execute("SELECT etag FROM files WHERE name='x_1t_AL.zip'").fetchone()
        self.assertEqual(etag, ('"v1"',))

    def test_stale_cdn_copy_on_get_is_refetched_from_the_current_version(self) -> None:
        old = archive("zz")
        self.server.stale_get["x_1t_AC.zip"] = old
        self.run_acquire()
        body = self.server.files["x_1t_AC.zip"]
        stored = (self.output / "files" / "x_1t_AC.zip").read_bytes()
        self.assertEqual(stored, body)
        self.assertNotEqual(stored, old)

    def test_tampered_archive_fails_verification(self) -> None:
        self.run_acquire()
        path = self.output / "files" / "x_1t_AC.zip"
        os.chmod(path, 0o644)
        path.write_bytes(b"X" * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, "does not match"):
            bulk.verify(self.output)

    def test_insufficient_space_stops_before_downloading(self) -> None:
        with patch.object(bulk, "_free", return_value=10):
            with self.assertRaisesRegex(RuntimeError, "free space"):
                self.run_acquire()
        self.assertFalse(list((self.output / "files").iterdir()))


if __name__ == "__main__":
    unittest.main()
