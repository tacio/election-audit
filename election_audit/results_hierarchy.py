"""Acquire the official hierarchical presidential results (EA20) for a 2026 round.

TSE publishes one unified result file (``-u.json``) per scope: Brazil, each UF and
ZZ (abroad), and each municipality, plus a progress file (``-ab.json``) per country
and UF and the municipality configuration (``-cm.json``) that lists every scope.
``fetch`` reads the configuration, fetches every listed file from the official host
into a new content-addressed root, checks that each file is official and names the
expected election, round and scope, and records the generation stamp, ETag and
Last-Modified of each body.

These files are republished after court-ordered retotalizations, so a fetch is a
dated snapshot, not a final value. Each row keeps the file's own generation stamp
(``dg``/``hg``/``idg``) so later checks can tell which publication they compare.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.sa_logs import _get

VERSION = "results-hierarchy-v1"
BASE = "https://resultados.tse.jus.br/oficial/ele2026"
OFFICE = "0001"  # Presidente
SCHEMA = """
CREATE TABLE binding(value TEXT NOT NULL);
CREATE TABLE files(
  url TEXT PRIMARY KEY, kind TEXT NOT NULL, scope_type TEXT NOT NULL,
  uf TEXT, municipality TEXT, path TEXT NOT NULL, sha256 TEXT NOT NULL,
  bytes INTEGER NOT NULL, fetched_at TEXT NOT NULL, etag TEXT, last_modified TEXT,
  generated_date TEXT, generated_time TEXT, generation_id TEXT,
  totalization_final TEXT, visible TEXT, sections_total INTEGER,
  sections_totalized INTEGER);
"""


def _urls(round_number):
    election = election_for_round(round_number).election_code
    code = f"e{int(election):06d}"
    return election, f"{BASE}/{election}", code


def config_url(round_number) -> str:
    _, root, code = _urls(round_number)
    return f"{root}/config/mun-{code}-cm.json"


def planned(config, round_number):
    """Every file the configuration implies, in a stable order."""
    election, root, code = _urls(round_number)
    if str(config.get("f", "")).lower() != "o":
        raise ValueError("Municipality configuration is not official")
    yield {
        "kind": "unified",
        "scope_type": "br",
        "uf": "br",
        "municipality": None,
        "url": f"{root}/dados/br/br-c{OFFICE}-{code}-u.json",
    }
    yield {
        "kind": "progress",
        "scope_type": "br",
        "uf": "br",
        "municipality": None,
        "url": f"{root}/dados/br/br-{code}-ab.json",
    }
    seen = set()
    for scope in config["abr"]:
        uf = scope["cd"].lower()
        if len(uf) != 2 or not uf.isalpha() or uf in seen:
            raise ValueError(f"Invalid UF in configuration: {scope['cd']!r}")
        seen.add(uf)
        yield {
            "kind": "unified",
            "scope_type": "uf",
            "uf": uf,
            "municipality": None,
            "url": f"{root}/dados/{uf}/{uf}-c{OFFICE}-{code}-u.json",
        }
        yield {
            "kind": "progress",
            "scope_type": "uf",
            "uf": uf,
            "municipality": None,
            "url": f"{root}/dados/{uf}/{uf}-{code}-ab.json",
        }
        for municipality in scope["mu"]:
            number = municipality["cd"]
            if len(number) != 5 or not number.isdigit():
                raise ValueError(f"Invalid municipality code: {number!r}")
            yield {
                "kind": "unified",
                "scope_type": "mun",
                "uf": uf,
                "municipality": number,
                "url": f"{root}/dados/{uf}/{uf}{number}-c{OFFICE}-{code}-u.json",
            }


def check(entry, value, round_number) -> None:
    """Reject a body that is not official or names another election, round or scope."""
    election = election_for_round(round_number).election_code
    if str(value.get("f", "")).lower() != "o":
        raise ValueError(f"Not an official file: {entry['url']}")
    if (str(value.get("ele")), str(value.get("t"))) != (election, str(round_number)):
        raise ValueError(f"Wrong election or round: {entry['url']}")
    if entry["kind"] == "unified":
        expected = entry["municipality"] or entry["uf"]
        if (value.get("tpabr"), str(value.get("cdabr")).lower()) != (
            {"mun": "mu"}.get(entry["scope_type"], entry["scope_type"]),  # unified files say "mu"
            expected,
        ):
            raise ValueError(f"Wrong scope: {entry['url']}")
        if not any(c.get("cd") == str(int(OFFICE)) for c in value.get("carg", [])):
            raise ValueError(f"Presidential office missing: {entry['url']}")


def _store(output, body):
    digest = hashlib.sha256(body).hexdigest()
    relative = Path("objects") / digest[:2] / f"{digest}.json"
    target = output / relative
    if target.exists():
        if sha(target) != digest:
            raise ValueError(f"Stored object differs from its address: {relative}")
        return digest, str(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    with temporary.open("wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o444)
    os.replace(temporary, target)
    return digest, str(relative)


def _number(value):
    return int(value) if value not in (None, "") else None


def _row(entry, value, digest, relative, size, etag, last_modified):
    sections = value.get("s") if entry["kind"] == "unified" else None
    return (
        entry["url"],
        entry["kind"],
        entry["scope_type"],
        entry["uf"],
        entry["municipality"],
        relative,
        digest,
        size,
        datetime.now().astimezone().isoformat(),
        etag,
        last_modified,
        value.get("dg"),
        value.get("hg"),
        value.get("idg"),
        value.get("tf"),
        value.get("dv"),
        _number(sections.get("ts")) if sections else None,
        _number(sections.get("st")) if sections else None,
    )


def fetch(round_number, output, *, delay=0.2, resume=False, get=_get):
    """Fetch the whole presidential EA20 hierarchy of one round into a new root."""
    output = Path(output)
    binding = {"version": VERSION, "round": round_number, "office": OFFICE}
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new: {output}")
    output.mkdir(parents=True, exist_ok=resume)
    db_path = output / "manifest.sqlite"
    fresh = not db_path.exists()
    with contextlib.closing(sqlite3.connect(db_path)) as db:
        if fresh:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO binding VALUES(?)", (json.dumps(binding, sort_keys=True),))
            db.commit()
        elif json.loads(db.execute("SELECT value FROM binding").fetchone()[0]) != binding:
            raise ValueError("Output belongs to another round or version")
        done = {url for (url,) in db.execute("SELECT url FROM files")}
        entry = {
            "kind": "config",
            "scope_type": "config",
            "uf": None,
            "municipality": None,
            "url": config_url(round_number),
        }
        row = db.execute("SELECT path FROM files WHERE url=?", (entry["url"],)).fetchone()
        if row:
            config_body = (output / row[0]).read_bytes()
        else:
            config_body, etag, last_modified = get(entry["url"])
            config = json.loads(config_body)
            digest, relative = _store(output, config_body)
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _row(entry, config, digest, relative, len(config_body), etag, last_modified),
            )
            db.commit()
        entries = list(planned(json.loads(config_body), round_number))
        for index, entry in enumerate(e for e in entries if e["url"] not in done):
            if index:
                time.sleep(delay)
            body, etag, last_modified = get(entry["url"])
            value = json.loads(body)
            check(entry, value, round_number)
            digest, relative = _store(output, body)
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _row(entry, value, digest, relative, len(body), etag, last_modified),
            )
            db.commit()
        counts = Counter(
            (kind, scope)
            for kind, scope in db.execute("SELECT kind, scope_type FROM files WHERE kind!='config'")
        )
        not_final = db.execute(
            "SELECT count(*) FROM files WHERE kind='unified' AND totalization_final!='s'"
        ).fetchone()[0]
        stamps = sorted(
            datetime.strptime(f"{day} {clock}", "%d/%m/%Y %H:%M:%S").isoformat()
            for day, clock in db.execute(
                "SELECT generated_date, generated_time FROM files WHERE kind!='config'"
            )
        )
        stamps = (stamps[0], stamps[-1]) if stamps else (None, None)
    if sum(counts.values()) != len(entries):
        raise ValueError("Fetched files do not match the configuration")
    result = {
        "round": round_number,
        "planned": len(entries),
        "files": {f"{k} {s}": v for (k, s), v in sorted(counts.items())},
        "unified_not_final": not_final,
        "generated_range": list(stamps),
        "config_sha256": hashlib.sha256(config_body).hexdigest(),
    }
    atomic(output / "status.json", {"stage": "finished", **result})
    return result


def results_hierarchy_main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit results-hierarchy",
        description="Fetch the official hierarchical presidential results (EA20) of a round.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch", help="Fetch BR, UF/ZZ and municipal result files.")
    get.add_argument("--round", type=int, choices=(1, 2), required=True)
    get.add_argument("--output", required=True, help="New output directory.")
    get.add_argument("--delay", type=float, default=0.2, help="Seconds between requests.")
    get.add_argument("--resume", action="store_true", help="Continue an interrupted fetch.")
    args = parser.parse_args(argv)
    result = fetch(args.round, args.output, delay=args.delay, resume=args.resume)
    print(json.dumps(result, sort_keys=True))
    return 0
