"""Resumable, checksummed acquisition of TSE open-data bulk archives.

A dataset is resolved through the TSE CKAN ``package_show`` API. The exact catalog
bytes are kept, and every selected resource is downloaded once into a new root,
resumed with HTTP ranges only while the server's ETag and length are unchanged,
hashed with SHA-256 and SHA-512, checked to open as a ZIP central directory and
made read-only. When the TSE publishes a sibling ``<archive>.sha512`` resource, it is
downloaded too and the archive is reconciled against it; otherwise the recorded
digest proves only that later stages read the bytes this run received. Bodies are
never decoded here.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from election_audit.national_migration import atomic, sha

VERSION = "tse-bulk-acquisition-v1"
CATALOG_API = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id="
ALLOWED_PREFIXES = ("https://cdn.tse.jus.br/estatistica/sead/",)
UNSIZED_LIMIT = 64 * 1024  # only .sha512 companions may omit Content-Length
USER_AGENT = "election-audit/0.1 (+research; bulk open-data acquisition)"
CHUNK = 4 * 1024**2

SCHEMA = """
CREATE TABLE IF NOT EXISTS binding(value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalogs(
  dataset TEXT PRIMARY KEY, url TEXT NOT NULL, path TEXT NOT NULL,
  sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files(
  url TEXT PRIMARY KEY, dataset TEXT NOT NULL, resource_id TEXT, name TEXT,
  catalog_last_modified TEXT, path TEXT NOT NULL, expected_bytes INTEGER,
  etag TEXT, last_modified TEXT, status TEXT NOT NULL,
  sha256 TEXT, bytes INTEGER, zip_members INTEGER, fetched_at TEXT);
"""
# Columns added after the first national runs; added in place on resume.
LATER_COLUMNS = {"sha512": "TEXT", "published_sha512": "TEXT"}


def _now():
    return datetime.now(UTC).isoformat()


def _request(url, *, method="GET", headers=None, timeout=60):
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_catalog(dataset, api=CATALOG_API):
    """Return the raw catalog bytes and the parsed resource list."""
    url = api + dataset
    with _request(url) as response:
        body = response.read()
    value = json.loads(body)
    if not value.get("success"):
        raise ValueError(f"Catalog request failed for {dataset}")
    return url, body, value["result"]["resources"]


def select_resources(resources, include, allowed_prefixes=ALLOWED_PREFIXES):
    """Filter resources by URL regex, refusing hosts outside the allow list."""
    pattern = re.compile(include)
    selected = []
    for resource in resources:
        url = resource["url"]
        if not pattern.search(url):
            continue
        parts = urlsplit(url)
        if (
            not url.startswith(tuple(allowed_prefixes))
            or parts.query
            or parts.fragment
            or any(segment in (".", "..") for segment in parts.path.split("/"))
        ):
            raise ValueError(f"Resource outside the allowed TSE prefixes: {url}")
        name = Path(urlsplit(url).path).name
        if not re.fullmatch(r"[A-Za-z0-9._-]+\.zip(?:\.sha512)?", name):
            raise ValueError(f"Unexpected resource file name: {url}")
        selected.append(resource)
    # Published checksum companions always travel with their archive.
    chosen = {r["url"] for r in selected}
    for resource in resources:
        if resource["url"] not in chosen and resource["url"].endswith(".sha512"):
            if resource["url"][: -len(".sha512")] in chosen:
                selected.extend(select_resources([resource], r"\.sha512$", allowed_prefixes))
    names = [Path(urlsplit(r["url"]).path).name for r in selected]
    if len(set(names)) != len(names):
        raise ValueError("Selected resources share a file name")
    return selected


def head(url):
    # CDN edges cache HEAD and GET separately and can hold copies stored without
    # Content-Length or from an earlier republication. A throwaway query reaches the
    # current version; downloads must then match its ETag and length.
    return _head(_revalidate(url))


def _revalidate(url):
    """Return ``url`` with a throwaway query that bypasses a stale CDN cache entry."""
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}revalidate={time.time_ns()}"


def _head(url):
    with _request(url, method="HEAD") as response:
        return {
            "bytes": (
                int(response.headers["Content-Length"])
                if response.headers.get("Content-Length")
                else None
            ),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "ranges": response.headers.get("Accept-Ranges") == "bytes",
        }


def _free(path):
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def download_one(url, target, expected, *, reserve, progress=None):
    """Download to ``target``.part with ETag-guarded range resume.

    Returns (sha256, sha512, bytes, zip members or None).
    """
    partial = target.with_name(target.name + ".part")
    if expected["bytes"] is None and not target.name.endswith(".sha512"):
        raise ValueError(f"Server did not announce a length: {url}")
    limit = UNSIZED_LIMIT if expected["bytes"] is None else expected["bytes"]
    digest, long_digest = hashlib.sha256(), hashlib.sha512()
    offset = 0
    if partial.exists():
        if not expected["ranges"] or not expected["etag"] or expected["bytes"] is None:
            partial.unlink()
        else:
            with partial.open("rb") as stream:
                for block in iter(lambda: stream.read(CHUNK), b""):
                    digest.update(block)
                    long_digest.update(block)
                    offset += len(block)
            if offset > limit:
                partial.unlink()
                digest, long_digest, offset = hashlib.sha256(), hashlib.sha512(), 0
    headers = {}
    if offset:
        headers = {"Range": f"bytes={offset}-", "If-Range": expected["etag"]}
    response = _request(url, headers=headers, timeout=120)
    if response.headers.get("ETag") and response.headers.get("ETag") != expected["etag"]:
        # An edge can serve an older cached copy on GET while HEAD reached the origin.
        response.close()
        response = _request(_revalidate(url), headers=headers, timeout=120)
    with response:
        if offset and response.status != 206:
            # The object changed (If-Range failed) or ranges were refused: restart.
            digest, long_digest, offset = hashlib.sha256(), hashlib.sha512(), 0
            mode = "wb"
        else:
            mode = "ab" if offset else "wb"
        if response.headers.get("ETag") and response.headers.get("ETag") != expected["etag"]:
            raise ValueError(f"ETag changed during download: {url}")
        with partial.open(mode) as stream:
            last = time.monotonic()
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                stream.write(block)
                digest.update(block)
                long_digest.update(block)
                offset += len(block)
                if offset > limit:
                    raise ValueError(f"Server sent more bytes than announced: {url}")
                if time.monotonic() - last > 10:
                    last = time.monotonic()
                    if _free(target.parent) < reserve:
                        raise RuntimeError("Output free-space reserve breached")
                    if progress:
                        progress(offset)
            stream.flush()
            os.fsync(stream.fileno())
    if expected["bytes"] is not None and offset != expected["bytes"]:
        raise ValueError(f"Short download ({offset} of {expected['bytes']} bytes): {url}")
    if sha(partial) != digest.hexdigest():
        raise ValueError(f"Stored bytes differ from received bytes: {url}")
    members = None
    if target.name.endswith(".zip"):
        with zipfile.ZipFile(partial) as archive:
            members = len(archive.infolist())
    os.chmod(partial, 0o444)
    os.replace(partial, target)
    fd = os.open(target.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return digest.hexdigest(), long_digest.hexdigest(), offset, members


def published_digest(path):
    """The single SHA-512 hex digest in a TSE ``.sha512`` file, or None."""
    text = Path(path).read_bytes()[:4096].decode("ascii", errors="replace")
    found = re.findall(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{128}(?![0-9A-Fa-f])", text)
    return found[0].lower() if len(set(found)) == 1 else None


def reconcile_published(db, output):
    """Record, per archive, whether a published SHA-512 matches the received bytes."""
    rows = db.execute(
        "SELECT url, path, sha512 FROM files WHERE status='complete' AND url NOT LIKE '%.sha512'"
    ).fetchall()
    mismatches = []
    for url, relative, long_sha in rows:
        companion = db.execute(
            "SELECT path FROM files WHERE url=? AND status='complete'", (url + ".sha512",)
        ).fetchone()
        if not companion:
            state = "not_published"
        else:
            if long_sha is None:
                h = hashlib.sha512()
                with (output / relative).open("rb") as stream:
                    for block in iter(lambda: stream.read(CHUNK), b""):
                        h.update(block)
                long_sha = h.hexdigest()
                db.execute("UPDATE files SET sha512=? WHERE url=?", (long_sha, url))
            published = published_digest(output / companion[0])
            state = (
                "unparsed"
                if published is None
                else "match"
                if published == long_sha
                else "mismatch"
            )
            if state != "match":
                mismatches.append((url, state))
        db.execute("UPDATE files SET published_sha512=? WHERE url=?", (state, url))
    db.commit()
    return mismatches


def acquire(
    datasets,
    output,
    *,
    include=r"\.zip$",
    resume=False,
    reserve_gib=20,
    api=CATALOG_API,
    allowed_prefixes=ALLOWED_PREFIXES,
    dry_run=False,
):
    output = Path(output).expanduser().absolute()
    # The host allow list is a safety policy, not part of the acquisition identity.
    binding = {"version": VERSION, "datasets": sorted(datasets), "include": include, "api": api}
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new (or pass --resume): {output}")
    if resume and not (output / "manifest.sqlite").exists():
        raise FileNotFoundError("Nothing to resume at this output")
    output.mkdir(parents=True, exist_ok=resume)
    (output / "catalog").mkdir(exist_ok=True)
    (output / "files").mkdir(exist_ok=True)
    lock = (output / "acquisition.lock").open("a")
    db = sqlite3.connect(output / "manifest.sqlite")
    started = time.time()
    status_path = output / "status.json"

    def report(stage, **extra):
        atomic(
            status_path,
            {
                "stage": stage,
                "pid": os.getpid(),
                "started_unix": started,
                "updated_unix": time.time(),
                **extra,
            },
        )

    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript(SCHEMA)
        present = {row[1] for row in db.execute("PRAGMA table_info(files)")}
        for column, kind in LATER_COLUMNS.items():
            if column not in present:
                db.execute(f"ALTER TABLE files ADD COLUMN {column} {kind}")
        encoded = json.dumps(binding, sort_keys=True)
        previous = db.execute("SELECT value FROM binding").fetchone()
        if previous:
            earlier = json.loads(previous[0])
            earlier.pop("allowed_prefixes", None)
        if previous and earlier != binding:
            raise ValueError("Resume binding differs from the original acquisition")
        if not previous:
            db.execute("INSERT INTO binding VALUES(?)", (encoded,))
            db.commit()
        report("cataloguing")
        planned = []
        for dataset in sorted(datasets):
            url, body, resources = fetch_catalog(dataset, api)
            path = output / "catalog" / f"{dataset}.{hashlib.sha256(body).hexdigest()[:16]}.json"
            if not path.exists():
                path.write_bytes(body)
                os.chmod(path, 0o444)
            known = db.execute("SELECT sha256 FROM catalogs WHERE dataset=?", (dataset,)).fetchone()
            if known and known[0] != hashlib.sha256(body).hexdigest():
                # Keep both catalog versions; resource rows below record what changed.
                report("catalog_changed", dataset=dataset)
            db.execute(
                "INSERT OR REPLACE INTO catalogs VALUES(?,?,?,?,?,?)",
                (
                    dataset,
                    url,
                    str(path.relative_to(output)),
                    hashlib.sha256(body).hexdigest(),
                    len(body),
                    _now(),
                ),
            )
            for resource in select_resources(resources, include, allowed_prefixes):
                planned.append((dataset, resource))
        db.commit()
        rows = []
        for dataset, resource in planned:
            url = resource["url"]
            name = Path(urlsplit(url).path).name
            existing = db.execute(
                "SELECT status,etag,expected_bytes FROM files WHERE url=?", (url,)
            ).fetchone()
            if existing and existing[0] == "complete":
                rows.append((url, None))
                continue
            expected = head(url)
            if existing and (existing[1], existing[2]) != (expected["etag"], expected["bytes"]):
                partial = output / "files" / (name + ".part")
                if partial.exists():
                    partial.unlink()
            db.execute(
                "INSERT INTO files(url,dataset,resource_id,name,catalog_last_modified,path,"
                "expected_bytes,etag,last_modified,status) VALUES(?,?,?,?,?,?,?,?,?,'pending')"
                " ON CONFLICT(url) DO UPDATE SET expected_bytes=excluded.expected_bytes,"
                " etag=excluded.etag, last_modified=excluded.last_modified,"
                " catalog_last_modified=excluded.catalog_last_modified",
                (
                    url,
                    dataset,
                    resource.get("id"),
                    resource.get("name"),
                    resource.get("last_modified"),
                    f"files/{name}",
                    expected["bytes"],
                    expected["etag"],
                    expected["last_modified"],
                ),
            )
            rows.append((url, expected))
        db.commit()
        pending = [(u, e) for u, e in rows if e is not None]
        need = sum(e["bytes"] or 0 for _, e in pending)
        reserve = reserve_gib * 1024**3
        report(
            "planned",
            resources=len(rows),
            pending=len(pending),
            pending_bytes=need,
            free_bytes=_free(output),
        )
        if _free(output) - need < reserve:
            raise RuntimeError(f"Need {need} bytes plus the reserve; not enough free space")
        if dry_run:
            return {"resources": len(rows), "pending": len(pending), "pending_bytes": need}
        done_bytes = 0
        began = time.monotonic()
        for index, (url, expected) in enumerate(pending, 1):
            target = output / "files" / Path(urlsplit(url).path).name
            if target.exists():
                raise FileExistsError(f"Refusing to overwrite an unrecorded file: {target}")

            def progress(current, url=url, index=index):
                elapsed = time.monotonic() - began
                rate = (done_bytes + current) / elapsed if elapsed else 0
                report(
                    "downloading",
                    file=url,
                    index=index,
                    pending=len(pending),
                    file_bytes=current,
                    done_bytes=done_bytes + current,
                    pending_bytes=need,
                    mb_per_second=round(rate / 1e6, 2),
                    eta_hours=round((need - done_bytes - current) / rate / 3600, 2)
                    if rate
                    else None,
                )

            digest, long_digest, size, members = download_one(
                url, target, expected, reserve=reserve, progress=progress
            )
            db.execute(
                "UPDATE files SET status='complete', sha256=?, sha512=?, bytes=?,"
                " zip_members=?, fetched_at=? WHERE url=?",
                (digest, long_digest, size, members, _now(), url),
            )
            db.commit()
            done_bytes += size
        mismatches = reconcile_published(db, output)
        if mismatches:
            raise ValueError(
                f"{len(mismatches)} archives fail their published SHA-512: {mismatches[:3]}"
            )
        summary = dict(db.execute("SELECT status, count(*) FROM files GROUP BY status").fetchall())
        published = dict(
            db.execute(
                "SELECT published_sha512, count(*) FROM files WHERE published_sha512 IS NOT NULL"
                " GROUP BY published_sha512"
            ).fetchall()
        )
        totals = db.execute(
            "SELECT count(*), coalesce(sum(bytes),0) FROM files WHERE status='complete'"
        ).fetchone()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        result = {
            "statuses": summary,
            "published_sha512": published,
            "complete_files": totals[0],
            "complete_bytes": totals[1],
        }
        report("finished", **result)
        return result
    except BaseException as exc:
        report("FAILED_STOPPED", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        db.close()
        lock.close()


def verify(output):
    """Re-hash every completed archive against the manifest (read-only)."""
    output = Path(output)
    uri = (output / "manifest.sqlite").resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        rows = db.execute(
            "SELECT path, sha256, bytes FROM files WHERE status='complete' ORDER BY path"
        ).fetchall()
    for relative, expected_sha, size in rows:
        path = output / relative
        if path.stat().st_size != size or sha(path) != expected_sha:
            raise ValueError(f"Archive does not match the manifest: {relative}")
    return {"verified_files": len(rows), "verified_bytes": sum(r[2] for r in rows)}


def bulk_download_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="election-audit bulk-download",
        description="Acquire or verify TSE open-data bulk archives with checksums.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Download selected dataset resources.")
    fetch.add_argument("--dataset", action="append", required=True, help="CKAN dataset id.")
    fetch.add_argument("--output", required=True, help="New acquisition root.")
    fetch.add_argument("--include", default=r"\.zip$", help="Regex over resource URLs.")
    fetch.add_argument("--reserve-gib", type=int, default=20, help="Free-space reserve.")
    fetch.add_argument("--resume", action="store_true", help="Resume the same acquisition.")
    fetch.add_argument("--dry-run", action="store_true", help="Catalog and size only.")
    check = commands.add_parser("verify", help="Re-hash completed archives.")
    check.add_argument("--output", required=True, help="Existing acquisition root.")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        result = acquire(
            args.dataset,
            args.output,
            include=args.include,
            resume=args.resume,
            reserve_gib=args.reserve_gib,
            dry_run=args.dry_run,
        )
    else:
        result = verify(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0
