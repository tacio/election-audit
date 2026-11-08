"""File election-day integrity test documents collected from regional court (TRE) sites.

TSE does not publish the integrity test (Teste de Integridade) results as open data;
each TRE posts its own minutes, urn-selection lists and notices, in its own layout,
and the sites refuse scripted requests. Documents are therefore collected in a
browser: for every document the page fetches the bytes, records the URL, HTTP status,
media type, size, SHA-256 and Last-Modified in a per-court record file
(``ea-integrity-manifest-<court>.json``) and saves the bytes.

``ingest`` reads those record files and the saved files from one directory, matches
each served record to a saved file by SHA-256 (browsers rename downloads, so names
are not trusted), and copies every match into a new content-addressed, read-only
root. A served record without a matching file stays in the manifest as ``missing``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from election_audit.national_migration import atomic, sha

VERSION = "integrity-documents-v1"
RECORDS = "ea-integrity-manifest-*.json"
EXTENSIONS = {"application/pdf": ".pdf", "text/html": ".html"}
SCHEMA = """
CREATE TABLE record_files(name TEXT PRIMARY KEY, court TEXT NOT NULL, sha256 TEXT NOT NULL,
  collected_at TEXT, listing_page TEXT, path TEXT NOT NULL);
CREATE TABLE documents(
  court TEXT NOT NULL, title TEXT, url TEXT NOT NULL, status INTEGER, media_type TEXT,
  bytes INTEGER, sha256 TEXT, last_modified TEXT, note TEXT, record_file TEXT NOT NULL,
  outcome TEXT NOT NULL, path TEXT, PRIMARY KEY(court, url));
"""


def _store(output, source, digest, media_type):
    relative = Path("objects") / digest[:2] / f"{digest}{EXTENSIONS.get(media_type, '.bin')}"
    target = output / relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
    if sha(target) != digest:
        raise ValueError(f"Stored document differs from its address: {relative}")
    return str(relative)


def _court(name, value):
    court = str(value.get("uf", "")).lower()
    if len(court) != 2 or not court.isalpha():
        raise ValueError(f"Record file names no court: {name}")
    return court


def ingest(downloads, output):
    """Match browser records to saved files by SHA-256 and file them in a new root."""
    downloads, output = Path(downloads), Path(output)
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    record_paths = sorted(downloads.glob(RECORDS))
    if not record_paths:
        raise ValueError(f"No record files in {downloads}")
    records = []
    for path in record_paths:
        value = json.loads(path.read_bytes())
        court = _court(path.name, value)
        for record in value["records"]:
            records.append((path, court, value, record))
    wanted = {r["bytes"] for *_, r in records if r.get("status") == 200 and r.get("sha256")}
    found = {}
    for candidate in sorted(downloads.iterdir()):
        if candidate.is_file() and not candidate.is_symlink():
            if candidate.stat().st_size in wanted:
                found.setdefault(sha(candidate), candidate)
    output.mkdir(parents=True)
    outcomes = defaultdict(Counter)
    with contextlib.closing(sqlite3.connect(output / "manifest.sqlite")) as db:
        db.executescript(SCHEMA)
        for path in record_paths:
            value = json.loads(path.read_bytes())
            kept = Path("records") / path.name
            (output / "records").mkdir(exist_ok=True)
            shutil.copyfile(path, output / kept)
            os.chmod(output / kept, 0o444)
            db.execute(
                "INSERT INTO record_files VALUES(?,?,?,?,?,?)",
                (
                    path.name,
                    _court(path.name, value),
                    sha(path),
                    value.get("collected_at"),
                    value.get("listing_page"),
                    str(kept),
                ),
            )
        for path, court, _value, record in records:
            stored, outcome = None, "not-served"
            if record.get("status") == 200:
                source = found.get(record.get("sha256"))
                outcome = "missing"
                if source is not None:
                    stored = _store(output, source, record["sha256"], record.get("type"))
                    outcome = "filed"
            outcomes[court][outcome] += 1
            db.execute(
                "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    court,
                    record.get("title"),
                    record["url"],
                    record.get("status"),
                    record.get("type"),
                    record.get("bytes"),
                    record.get("sha256"),
                    record.get("last_modified"),
                    record.get("note"),
                    path.name,
                    outcome,
                    stored,
                ),
            )
        db.commit()
    totals = Counter()
    for counts in outcomes.values():
        totals.update(counts)
    result = {
        "version": VERSION,
        "courts": {court: dict(sorted(c.items())) for court, c in sorted(outcomes.items())},
        "documents": dict(sorted(totals.items())),
        "record_files": len(record_paths),
    }
    atomic(output / "status.json", {"stage": "finished", **result})
    return result


def integrity_documents_main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit integrity-docs",
        description="File browser-collected TRE integrity test documents by SHA-256.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    put = commands.add_parser("ingest", help="Match records to saved files and file them.")
    put.add_argument("--downloads", required=True, help="Directory with records and files.")
    put.add_argument("--output", required=True, help="New output directory.")
    args = parser.parse_args(argv)
    print(json.dumps(ingest(args.downloads, args.output), sort_keys=True))
    return 0
