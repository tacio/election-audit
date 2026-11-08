"""Portable exports, integrity checks, filtering and remote equivalence."""

import http.server
import json
import tempfile
import threading
import unittest
from functools import partial
from pathlib import Path
from typing import Any

from election_audit.dashboard_data import AuditDataset, publish_dataset


class DashboardDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = publish_dataset(
            {
                "coverage": iter(
                    [
                        {"uf": "ac", "round": 2, "value": 0, "readiness": "ready"},
                        {"uf": "al", "round": 1, "value": None, "readiness": "unknown"},
                    ]
                )
            },
            self.root / "export",
            release_id="fixture",
            access_state="development_only",
        )

    def test_local_filters_pagination_zero_unknown_and_csv(self) -> None:
        d = AuditDataset.open(self.manifest)
        self.assertEqual(d.options("coverage", "round"), ["1", "2"])
        self.assertEqual(d.page("coverage", filters={"uf": "ac"})["rows"][0]["value"], 0)
        self.assertIsNone(d.page("coverage", offset=1)["rows"][0]["value"])
        self.assertEqual(d.page("coverage", limit=1)["total"], 2)
        csv, metadata = d.csv("coverage", filters={"uf": "ac"})
        self.assertIn("ac", csv)
        self.assertEqual(metadata["release_id"], "fixture")
        cases: tuple[dict[str, Any], ...] = (
            {"limit": 10001},
            {"offset": -1},
            {"filters": {"SQL": "unsafe"}},
        )
        for kwargs in cases:
            with self.assertRaises(ValueError):
                d.page("coverage", **kwargs)

    def test_integrity_and_path_escape(self) -> None:
        d = AuditDataset.open(self.manifest)
        path = self.manifest.parent / "coverage.parquet"
        path.write_bytes(path.read_bytes() + b"bad")
        with self.assertRaisesRegex(ValueError, "checksum"):
            d.page("coverage")
        for path in ("../escape", "https://elsewhere/a", "%2e%2e/escape", "/absolute"):
            body = json.loads(self.manifest.read_text())
            body["tables"]["coverage"]["path"] = path
            self.manifest.write_text(json.dumps(body))
            with self.assertRaises(ValueError):
                AuditDataset.open(self.manifest)

    def test_http_matches_local_and_cache_bound(self) -> None:
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHandler, directory=self.manifest.parent)
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/dataset.json"
        with self.assertRaises(ValueError):
            AuditDataset.open(url)
        remote = AuditDataset.open(url, allow_http=True, cache=self.root / "cache")
        self.assertEqual(remote.page("coverage"), AuditDataset.open(self.manifest).page("coverage"))
        tiny = AuditDataset.open(url, allow_http=True, cache=self.root / "tiny", cache_bytes=1)
        with self.assertRaisesRegex(ValueError, "budget"):
            tiny.page("coverage")

    def test_publication_is_new_directory_only(self) -> None:
        with self.assertRaises(FileExistsError):
            publish_dataset(
                {}, self.manifest.parent, release_id="bad", access_state="development_only"
            )
        with self.assertRaises(ValueError):
            publish_dataset({}, self.root / "bad", release_id="bad", access_state="untouched")

    def test_no_notebook_data_paths_or_duplicate_definitions(self) -> None:
        import ast

        for path in Path("election_audit/notebooks").glob("0*.py"):
            text = path.read_text()
            ast.parse(text)
            self.assertNotIn("/media/", text)
            self.assertNotIn("/tmp/", text)
            self.assertIn("ELECTION_AUDIT_DATASET", text)
