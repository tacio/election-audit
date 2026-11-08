"""Acquire and summarize Sistema de Apuração (SA) logs for contingency-counted sections.

Sections counted with the SA contingency system publish ``-logsa.jez`` instead of an
urn ``-log.jez``. The per-section collector only follows urn logs, so this module
reads the certified staging's frozen auxiliary files, fetches every listed SA log
from the same official host into a new content-addressed root, and optionally
checks each file byte for byte against the matching member of a verified bulk
archive. ``summarize`` turns the logs into one row per section: SA logs record
counting attempts, not voting, so the urn vote-cycle rules do not apply.

An SA urn can count many sections, and each section's published file is a snapshot
of that urn's growing log. Attempts are attributed to a section only when the log
prints that section's municipality, zone and section number; otherwise the row
says so and its attempt fields stay null.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.types import JSON, Argv, Row

VERSION = "sa-logs-v1"
SUMMARY_VERSION = "sa-log-summary-v1"
ALLOWED_PREFIX = "https://resultados.tse.jus.br/oficial/"
USER_AGENT = "election-audit/0.1 (+research; SA log acquisition)"
AUX = re.compile(
    r"^(https://resultados\.tse\.jus\.br/oficial/ele\d{4}/arquivo-urna/(\d+)/dados/"
    r"([a-z]{2})/(\d+)/(\d+)/(\d+))/[^/]+-aux\.json$"
)
NAME = re.compile(r"^[A-Za-z0-9._-]+-logsa\.jez$")
SCHEMA = """
CREATE TABLE binding(value TEXT NOT NULL);
CREATE TABLE files(
  url TEXT PRIMARY KEY, round INTEGER NOT NULL, uf TEXT NOT NULL,
  municipality TEXT NOT NULL, zone TEXT NOT NULL, section TEXT NOT NULL,
  aux_url TEXT NOT NULL, aux_sha256 TEXT NOT NULL, package_hash TEXT NOT NULL,
  package_status TEXT, filename TEXT NOT NULL, path TEXT NOT NULL,
  sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, fetched_at TEXT NOT NULL,
  etag TEXT, last_modified TEXT, bulk_archive TEXT, bulk_archive_sha256 TEXT,
  bulk_check TEXT NOT NULL);
"""


# --------------------------------------------------------------------------- listing


def listed_sa_logs(staged_root: str | Path, round_number: int) -> Iterator[JSON]:
    """Yield every SA log the frozen auxiliary files of a certified staging list."""
    staged_root = Path(staged_root)
    pleito = election_for_round(round_number).pleito_code
    uri = (staged_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        rows = db.execute(
            "SELECT url, path, sha256 FROM files WHERE url LIKE '%-aux.json' ORDER BY url"
        ).fetchall()
    for aux_url, path, aux_sha in rows:
        match = AUX.match(aux_url)
        if not match or match.group(2) != pleito:
            raise ValueError(f"Auxiliary file outside round {round_number}: {aux_url}")
        aux = json.loads((staged_root / path).read_bytes())
        if str(aux.get("f", "")).lower() != "o":
            raise ValueError(f"Auxiliary file is not official: {aux_url}")
        for group in aux.get("hashes", []):
            for entry in group.get("arq", []):
                name = entry.get("nm", "")
                if entry.get("tp", "").lower() != "logsa" and not name.endswith("-logsa.jez"):
                    continue
                if not NAME.match(name) or not group.get("hash"):
                    raise ValueError(f"Invalid SA log entry in {aux_url}")
                yield {
                    "url": f"{match.group(1)}/{quote(group['hash'], safe='')}/{name}",
                    "round": round_number,
                    "uf": match.group(3),
                    "municipality": match.group(4),
                    "zone": match.group(5),
                    "section": match.group(6),
                    "aux_url": aux_url,
                    "aux_sha256": aux_sha,
                    "package_hash": group["hash"],
                    "package_status": group.get("st"),
                    "filename": name,
                }


# --------------------------------------------------------------------------- fetch


def _get(url: str, timeout: float = 60, attempts: int = 3) -> tuple[bytes, str | None, str | None]:
    if not url.startswith(ALLOWED_PREFIX):
        raise ValueError(f"Host outside the allow list: {url}")
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) != len(body):
                    raise ValueError(f"Short download: {url}")
                return body, response.headers.get("ETag"), response.headers.get("Last-Modified")
        except urllib.error.URLError, TimeoutError, ConnectionError:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def check_jez(body: bytes) -> None:
    """A JEZ is a ZIP whose CRCs verify and which holds ``logd.dat``."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if archive.testzip() is not None or "logd.dat" not in archive.namelist():
            raise ValueError("Not a valid SA log container")


def _store(output: Path, body: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(body).hexdigest()
    relative = Path("objects") / digest[:2] / f"{digest}.jez"
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


def _bulk_index(bulk_root: str | Path | None, round_number: int) -> dict[str, tuple[Path, str]]:
    """Map each UF to its verified bulk archive for this round."""
    if bulk_root is None:
        return {}
    bulk_root = Path(bulk_root)
    uri = (bulk_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        rows = db.execute("SELECT path, sha256 FROM files WHERE status='complete'").fetchall()
    index = {}
    suffix = re.compile(rf"_{round_number}t_([A-Z]{{2}})\.zip$")
    for path, digest in rows:
        match = suffix.search(path)
        if match:
            if match.group(1).lower() in index:
                raise ValueError(f"Two bulk archives for one UF: {path}")
            index[match.group(1).lower()] = (bulk_root / path, digest)
    return index


def fetch(
    staged_root: str | Path,
    round_number: int,
    output: str | Path,
    *,
    bulk_root: str | Path | None = None,
    delay: float = 0.5,
    get: Callable[[str], tuple[bytes, str | None, str | None]] = _get,
) -> JSON:
    """Fetch every listed SA log into a new root and cross-check the bulk archive."""
    staged_root, output = Path(staged_root), Path(output)
    certificate = json.loads((staged_root / "staging-certificate.json").read_bytes())
    if certificate.get("round") != round_number:
        raise ValueError("Staged root belongs to another round")
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    entries = list(listed_sa_logs(staged_root, round_number))
    bulk = _bulk_index(bulk_root, round_number)
    output.mkdir(parents=True)
    binding = {
        "version": VERSION,
        "round": round_number,
        "staged_root": str(staged_root.resolve()),
        "staging_certificate_sha256": sha(staged_root / "staging-certificate.json"),
        "manifest_sha256": certificate["manifest_sha256"],
        "bulk_root": str(Path(bulk_root).resolve()) if bulk_root else None,
    }
    checks = Counter()
    with contextlib.closing(sqlite3.connect(output / "manifest.sqlite")) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO binding VALUES(?)", (json.dumps(binding, sort_keys=True),))
        for index, entry in enumerate(entries):
            if index:
                time.sleep(delay)
            body, etag, last_modified = get(entry["url"])
            check_jez(body)
            digest, relative = _store(output, body)
            archive, archive_sha, check = None, None, "not-requested"
            if bulk_root is not None:
                check = "archive-missing"
                if entry["uf"] in bulk:
                    archive, archive_sha = bulk[entry["uf"]]
                    with zipfile.ZipFile(archive) as bundle:
                        if entry["filename"] in bundle.namelist():
                            member = hashlib.sha256(bundle.read(entry["filename"])).hexdigest()
                            check = "match" if member == digest else "mismatch"
                        else:
                            check = "member-missing"
                    archive = archive.name
            checks[check] += 1
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry["url"],
                    round_number,
                    entry["uf"],
                    entry["municipality"],
                    entry["zone"],
                    entry["section"],
                    entry["aux_url"],
                    entry["aux_sha256"],
                    entry["package_hash"],
                    entry["package_status"],
                    entry["filename"],
                    relative,
                    digest,
                    len(body),
                    datetime.now().astimezone().isoformat(),
                    etag,
                    last_modified,
                    archive,
                    archive_sha,
                    check,
                ),
            )
            db.commit()
    result = {
        "round": round_number,
        "listed": len(entries),
        "fetched": len(entries),
        "bulk_checks": dict(sorted(checks.items())),
    }
    atomic(output / "status.json", {"stage": "finished", **result})
    bad = {k: v for k, v in checks.items() if k not in ("match", "not-requested")}
    if bad:
        raise ValueError(f"SA logs disagree with the bulk archives: {bad}")
    return result


# --------------------------------------------------------------------------- summarize


def _time(stamp: str) -> str:
    return datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S").isoformat()


def parse_sa_log(body: bytes) -> JSON:
    """Split an SA log into counting attempts; only fixed vocabulary leaves this function."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        text = archive.read("logd.dat").decode("latin-1")
    lines = [line.split("\t") for line in text.splitlines()]
    rows = [r for r in lines if len(r) >= 5]
    attempts, selected = [], None
    current: JSON | None = None
    fields = {"Município": "municipality", "Zona Eleitoral": "zone", "Seção Eleitoral": "section"}
    contingency = any(r[4] == "Modo de carga da UE - Urna de contingência" for r in rows)
    for stamp, _level, _device, app, message, *_ in rows:
        if app != "SA":
            continue
        if message.startswith("Tipo de apuração selecionada ("):
            selected = message[len("Tipo de apuração selecionada (") : -1]
        elif message == "Identificação (município, zona e seção) confirmada":
            current = {
                "start": _time(stamp),
                "date": stamp[:10],
                "type": selected,
                "identity": {},
                "outcome": "open",
            }
            attempts.append(current)
        elif current is None:
            continue
        elif message.startswith(("Município: ", "Zona Eleitoral: ", "Seção Eleitoral: ")):
            key, value = message.split(": ", 1)
            current["identity"][fields[key]] = value.strip()
        elif message.startswith("Motivo da apuração: "):
            current["reason"] = message.split(": ", 1)[1]
        elif message.startswith("Início da digitação de BU") and "cargo" not in message:
            current.setdefault("bu_typing_start", _time(stamp))
        elif message.startswith("Término da digitação de BU") and "cargo" not in message:
            current["bu_typing_end"] = _time(stamp)
        elif message.startswith("Apuração iniciada"):
            current.setdefault("counting_start", _time(stamp))
        elif message.startswith("Apuração encerrada"):
            current["counting_end"] = _time(stamp)
        elif message == "Apuração cancelada":
            current["outcome"] = "cancelled"
            current = None
        elif message == "Gerando arquivo de resultado [busa.dat] + [Término]":
            current["busa_generated"] = _time(stamp)
            current["outcome"] = "completed"
            current = None
    times = [_time(r[0]) for r in rows]
    return {
        "lines": len(lines),
        "first_time": min(times) if times else None,
        "last_time": max(times) if times else None,
        "contingency_urn": contingency,
        "attempts": attempts,
    }


SUMMARY_SCHEMA = pa.schema(
    [
        ("round", pa.int8()),
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("sha256", pa.string()),
        ("bytes", pa.int64()),
        ("lines", pa.int32()),
        ("first_time", pa.string()),
        ("last_time", pa.string()),
        ("contingency_urn", pa.bool_()),
        ("file_attempts", pa.int32()),
        ("file_attempts_completed", pa.int32()),
        ("file_attempts_cancelled", pa.int32()),
        ("file_sections_completed", pa.int32()),
        ("file_round_attempts", pa.int32()),
        ("attribution", pa.string()),
        ("section_attempts", pa.int32()),
        ("section_attempts_cancelled", pa.int32()),
        ("section_attempts_completed", pa.int32()),
        ("counting_type", pa.string()),
        ("reason", pa.string()),
        ("attempt_start", pa.string()),
        ("bu_typing_start", pa.string()),
        ("bu_typing_end", pa.string()),
        ("counting_start", pa.string()),
        ("counting_end", pa.string()),
        ("busa_generated", pa.string()),
    ]
)


def summarize_row(row: Row, body: bytes) -> Row:
    parsed = parse_sa_log(body)
    attempts = parsed["attempts"]
    election_date = datetime.fromisoformat(election_for_round(row["round"]).election_date)
    day = election_date.strftime("%d/%m/%Y")
    key = (row["municipality"], row["zone"], row["section"])
    in_round = [a for a in attempts if a["date"] == day]

    def identity(attempt: JSON) -> tuple[str, ...]:
        found = attempt["identity"]
        return tuple(found.get(k, "").lstrip("0") for k in ("municipality", "zone", "section"))

    mine = [a for a in in_round if identity(a) == tuple(v.lstrip("0") for v in key)]
    completed = [a for a in mine if a["outcome"] == "completed"]
    final = completed[-1] if completed else None
    finished = {identity(a) for a in attempts if a["outcome"] == "completed"}
    return {
        "round": row["round"],
        "uf": row["uf"],
        "municipality": row["municipality"],
        "zone": row["zone"],
        "section": row["section"],
        "sha256": row["sha256"],
        "bytes": row["bytes"],
        "lines": parsed["lines"],
        "first_time": parsed["first_time"],
        "last_time": parsed["last_time"],
        "contingency_urn": parsed["contingency_urn"],
        "file_attempts": len(attempts),
        "file_attempts_completed": sum(a["outcome"] == "completed" for a in attempts),
        "file_attempts_cancelled": sum(a["outcome"] == "cancelled" for a in attempts),
        "file_sections_completed": len(finished),
        "file_round_attempts": len(in_round),
        "attribution": "identity-match" if final else "no-completed-matching-attempt",
        "section_attempts": len(mine),
        "section_attempts_cancelled": sum(a["outcome"] == "cancelled" for a in mine),
        "section_attempts_completed": len(completed),
        "counting_type": final["type"] if final else None,
        "reason": final.get("reason") if final else None,
        "attempt_start": final["start"] if final else None,
        "bu_typing_start": final.get("bu_typing_start") if final else None,
        "bu_typing_end": final.get("bu_typing_end") if final else None,
        "counting_start": final.get("counting_start") if final else None,
        "counting_end": final.get("counting_end") if final else None,
        "busa_generated": final.get("busa_generated") if final else None,
    }


def load_exclusions(path: str | Path) -> tuple[set[tuple[str, ...]], str]:
    value = json.loads(Path(path).read_bytes())
    return {tuple(key) for key in value["section_keys"]}, sha(path)


def summarize(
    inputs: Iterable[str | Path], output: str | Path, exclusions_path: str | Path
) -> JSON:
    """One row per fetched SA log, across one or more fetch roots.

    Protected sections are skipped before their logs are read.
    """
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    exclusions, exclusions_sha = load_exclusions(exclusions_path)
    rows, sources, excluded = [], [], Counter()
    for root in inputs:
        root = Path(root)
        uri = (root / "manifest.sqlite").resolve().as_uri() + "?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
            db.row_factory = sqlite3.Row
            records = [dict(r) for r in db.execute("SELECT * FROM files ORDER BY url")]
        sources.append(
            {"root": str(root.resolve()), "manifest_sha256": sha(root / "manifest.sqlite")}
        )
        for record in records:
            key = (record["uf"], record["municipality"], record["zone"], record["section"])
            if key in exclusions:
                excluded[record["round"]] += 1
                continue
            body = (root / record["path"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != record["sha256"]:
                raise ValueError(f"Stored SA log differs from the manifest: {record['path']}")
            rows.append(summarize_row(record, body))
    rows.sort(key=lambda r: (r["round"], r["uf"], r["municipality"], r["zone"], r["section"]))
    output.mkdir(parents=True)
    table = pa.Table.from_pylist(rows, schema=SUMMARY_SCHEMA)
    pq.write_table(table, output / "sa_sections.parquet", compression="zstd")
    counts = Counter((r["round"], r["attribution"]) for r in rows)
    manifest = {
        "version": SUMMARY_VERSION,
        "sources": sources,
        "exclusions_sha256": exclusions_sha,
        "excluded": {f"round {k}": v for k, v in sorted(excluded.items())},
        "rows": len(rows),
        "attribution": {f"round {k[0]}: {k[1]}": v for k, v in sorted(counts.items())},
        "sa_sections_sha256": sha(output / "sa_sections.parquet"),
        "clock": "urn clock, local time as logged; not corrected",
    }
    atomic(output / "manifest.json", manifest)
    return manifest


# --------------------------------------------------------------------------- CLI


def sa_logs_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit sa-logs",
        description="Fetch and summarize contingency-counting (SA) logs of certified rounds.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch", help="Fetch every SA log listed by a certified staging.")
    get.add_argument("--staged-root", required=True, help="Certified staged round root.")
    get.add_argument("--round", type=int, choices=(1, 2), required=True)
    get.add_argument("--output", required=True, help="New output directory.")
    get.add_argument("--bulk-root", help="Verified bulk-download root to cross-check against.")
    get.add_argument("--delay", type=float, default=0.5, help="Seconds between requests.")
    summary = commands.add_parser("summarize", help="One row per SA log and section.")
    summary.add_argument("--input", action="append", required=True, help="An sa-logs fetch root.")
    summary.add_argument("--output", required=True, help="New output directory.")
    summary.add_argument("--exclusions", required=True, help="Protected/stress exclusions JSON.")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        result = fetch(
            args.staged_root,
            args.round,
            args.output,
            bulk_root=args.bulk_root,
            delay=args.delay,
        )
    else:
        result = summarize(args.input, args.output, args.exclusions)
    print(json.dumps(result, sort_keys=True))
    return 0
