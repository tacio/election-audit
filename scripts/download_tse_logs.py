#!/usr/bin/env python3
"""Collect the official 2026 presidential runoff logs, retaining provenance."""

import argparse
import fcntl
import hashlib
import io
import json
import logging
import shutil
import sqlite3
import stat
import threading
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

BASE = "https://resultados.tse.jus.br/oficial"
UFS = "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz".split()


class CollectionStopped(Exception):
    """An unfinished task cancelled after another task failed."""


class DownloadAlreadyRunning(RuntimeError):
    pass


@contextmanager
def output_lock(root):
    """One downloader per output directory; the OS releases the lock on exit."""
    root.mkdir(parents=True, exist_ok=True)
    # Keep this file: unlinking a lock file would let another process lock a
    # different inode while the first process still owns the original one.
    with (root / ".download.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DownloadAlreadyRunning(
                f"Another downloader is using {root}; wait for it to exit"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def manifest_path(root):
    """Resolve the authoritative database, which may live on a separate SSD."""
    marker = root / "manifest-location.json"
    if not marker.exists():
        return root / "manifest.sqlite"
    location = json.loads(marker.read_text())
    if location.get("version") != 1 or not isinstance(location.get("path"), str):
        raise ValueError(f"Invalid manifest location marker: {marker}")
    path = Path(location["path"])
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"External manifest unavailable: {path}; restore access before resuming")
    return path


def configure_manifest(root, requested=None):
    """Copy the database consistently before switching; caller holds output_lock.

    The original is left as a snapshot. A location marker lets all future runs
    find the new authoritative database without needing the flag again.
    """
    source = manifest_path(root)
    if requested is None:
        return source
    target = requested.expanduser().resolve()
    if target == source.resolve():
        return source
    if target.exists():
        raise ValueError(f"Refusing to overwrite an existing database: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".copying")
    if temporary.exists():
        raise ValueError(
            f"Incomplete previous copy exists: {temporary}; inspect it before retrying"
        )
    logger.info(f"Copying manifest to {target}; raw log files stay in {root}")
    try:
        with closing(sqlite3.connect(temporary)) as destination:
            if source.exists():
                with closing(
                    sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=120)
                ) as original:
                    # Includes committed WAL contents; a plain filesystem copy
                    # could omit these while the original connection is open.
                    original.backup(destination)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    marker = root / "manifest-location.json"
    pending_marker = root / "manifest-location.json.tmp"
    pending_marker.write_text(json.dumps({"version": 1, "path": str(target)}, indent=2) + "\n")
    pending_marker.replace(marker)
    return target


def now():
    return datetime.now(timezone.utc).isoformat()


def presidential_election(config, round_number=2):
    from election_audit.elections import election_for_round

    descriptor = election_for_round(round_number)
    matches = [
        (p, e)
        for p in config["pl"]
        if p["c"] == "ele2026"
        for e in p["e"]
        if e.get("t") == str(round_number)
        and e.get("tp") == "8"
        and any(c["cd"] == "1" for a in e["abr"] for c in a.get("cp", []))
    ]
    if (
        len(matches) != 1
        or matches[0][0]["dt"] != "/".join(reversed(descriptor.election_date.split("-")))
        or str(matches[0][0]["cd"]) != descriptor.pleito_code
        or str(matches[0][1]["cd"]) != descriptor.election_code
    ):
        raise ValueError(
            f"Configuration does not uniquely identify 2026 presidential round {round_number}"
        )
    return str(matches[0][0]["cd"]), str(matches[0][1]["cd"])


def runoff(config):
    """Backward-compatible selector for the presidential runoff."""
    return presidential_election(config, 2)


def validate_manifest_round(connection, pleito) -> None:
    """Reject mixed/wrong-round stores before resume can reuse section keys."""
    prefix = f"{BASE}/ele2026/arquivo-urna/"
    expected = prefix + pleito + "/"
    row = connection.execute(
        "SELECT url FROM files WHERE url >= ? AND url < ? AND NOT (url >= ? AND url < ?) LIMIT 1",
        (prefix, prefix + "\uffff", expected, expected + "\uffff"),
    ).fetchone()
    if row is not None:
        raise ValueError(
            "Manifest contains package URLs for a different election round; use a separate manifest and raw root"
        )


def sections(config, uf, pleito):
    if str(config.get("f", "")).lower() != "o" or str(config.get("cdp")) != pleito:
        raise ValueError("Wrong phase or pleito in section index")
    if not config.get("abr"):
        raise ValueError("Empty section index")
    for area in config["abr"]:
        if area["cd"].lower() != uf:
            raise ValueError("Wrong UF in section index")
        for mun in area["mu"]:
            for zone in mun["zon"]:
                for section in zone["sec"]:
                    yield (
                        uf,
                        str(mun["cd"]).zfill(5),
                        str(zone["cd"]).zfill(4),
                        str(section["ns"]).zfill(4),
                        section,
                    )


def log_urls(aux, directory):
    if str(aux.get("f", "")).lower() != "o":
        raise ValueError("Auxiliary file is not official")
    seen = set()
    for group in aux["hashes"]:
        for entry in group.get("arq", []):
            name = entry["nm"]
            if entry.get("tp", "").lower() != "log" and not name.lower().endswith(
                ("-log.jez", "-log.dat")
            ):
                continue
            if not group.get("hash") or Path(name).name != name or "\\" in name:
                raise ValueError("Invalid log filename or package hash")
            url = f"{directory}/{quote(group['hash'], safe='')}/{quote(name, safe='')}"
            if url not in seen:
                seen.add(url)
                yield url, group.get("st"), group["hash"], name


def bounded_parallel_map(function, items, workers, stop):
    """Keep workers fed as tasks finish, with at most 2 * workers queued/running.

    Results arrive in completion order. Stop scheduling and cancel queued work
    before waiting for in-flight operations on failure or interruption.
    """
    iterator = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = set()

        def refill() -> None:
            while len(pending) < 2 * workers and not stop.is_set():
                try:
                    item = next(iterator)
                except StopIteration:
                    break
                pending.add(pool.submit(function, item))

        try:
            refill()
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                results = [future.result() for future in finished]
                refill()
                yield from results
        except BaseException:
            stop.set()
            for future in pending:
                future.cancel()
            raise


class Collector:
    def __init__(self, root, rps, reserve_gib, timeout) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (root / "objects").mkdir(exist_ok=True)
        self.interval = 1 / rps
        self.reserve = reserve_gib * 1024**3
        self.timeout = timeout
        self.lock = threading.Lock()
        # Rate waits must not prevent another worker from saving a finished file
        # or reporting an error. The storage/state lock above stays independent.
        self.rate_lock = threading.Lock()
        self.db_lock = threading.RLock()
        self.next_request = 0.0
        self.stop = threading.Event()
        self.stop_reason = None
        self.reused_sections = 0
        self.stats_lock = threading.Lock()
        self.stats = Counter()
        # One connection for the whole collector, always used under db_lock.
        # Independent worker connections can starve each other's write attempts
        # on a slow disk even with a long SQLite busy timeout.
        self.manifest = manifest_path(root)
        self._database = sqlite3.connect(self.manifest, timeout=120, check_same_thread=False)
        self._database.execute("PRAGMA journal_mode=WAL").fetchone()
        self.db().executescript("""
            CREATE TABLE IF NOT EXISTS files (
                url TEXT PRIMARY KEY, path TEXT, sha256 TEXT, bytes INTEGER,
                fetched_at TEXT, etag TEXT, last_modified TEXT);
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS run_identity (
                run TEXT PRIMARY KEY, election_descriptor TEXT NOT NULL,
                source_root TEXT NOT NULL, manifest_path TEXT NOT NULL,
                identity_sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sections (
                run TEXT, uf TEXT, municipality TEXT, zone TEXT, section TEXT,
                status TEXT, metadata TEXT, details TEXT,
                PRIMARY KEY (run, uf, municipality, zone, section));
            CREATE TABLE IF NOT EXISTS logs (
                run TEXT, uf TEXT, municipality TEXT, zone TEXT, section TEXT,
                url TEXT, package_status TEXT, package_hash TEXT, filename TEXT,
                PRIMARY KEY (run, url));
            CREATE INDEX IF NOT EXISTS section_history
                ON sections (uf, municipality, zone, section, status, run);
            CREATE INDEX IF NOT EXISTS section_logs
                ON logs (run, uf, municipality, zone, section);
        """)

    def db(self):
        """Raw connection for initialization/tests; workers use query/transaction."""
        return self._database

    def query(self, sql, parameters=(), *, one=False):
        with self.db_lock:
            cursor = self._database.execute(sql, parameters)
            try:
                return cursor.fetchone() if one else cursor.fetchall()
            finally:
                cursor.close()

    @contextmanager
    def transaction(self):
        # No filesystem reads, hashing or network waits inside this context.
        with self.db_lock:
            with self._database:
                self._database.execute("BEGIN IMMEDIATE")
                yield self._database

    def close(self) -> None:
        with self.db_lock:
            self._database.close()

    def abort(self, reason) -> None:
        with self.lock:
            if self.stop_reason is None:
                self.stop_reason = reason
            self.stop.set()

    def add_stats(self, **values) -> None:
        with self.stats_lock:
            self.stats.update(values)

    def statistics(self):
        with self.stats_lock:
            return dict(self.stats)

    def prepare_resume(self, items, run, *, verify_existing=False, progress=None):
        """Check prior successes in bulk and copy their manifest rows in one commit.

        Default checks existence and recorded size. Full SHA-256 revalidation is
        opt-in, avoiding repeated whole-corpus reads during ordinary restarts.
        """
        if not items:
            return [], Counter()
        uf = items[0][0]
        latest = """WITH latest AS (
            SELECT uf,municipality,zone,section,MAX(run) AS source_run FROM sections
            WHERE uf=? AND status='downloaded' GROUP BY uf,municipality,zone,section
        ) """
        previous = self.query(
            latest
            + """SELECT s.run,s.uf,s.municipality,s.zone,s.section,
                s.metadata,s.details FROM latest p JOIN sections s
                ON s.run=p.source_run AND s.uf=p.uf AND s.municipality=p.municipality
                AND s.zone=p.zone AND s.section=p.section""",
            (uf,),
        )
        old_sections = {tuple(row[1:5]): row for row in previous}
        links = self.query(
            latest
            + """SELECT l.uf,l.municipality,l.zone,l.section,l.url,
                l.package_status,l.package_hash,l.filename,f.path,f.sha256,f.bytes
                FROM latest p JOIN logs l ON l.run=p.source_run AND l.uf=p.uf
                AND l.municipality=p.municipality AND l.zone=p.zone AND l.section=p.section
                LEFT JOIN files f ON l.url=f.url""",
            (uf,),
        )
        by_section = defaultdict(list)
        for link in links:
            by_section[tuple(link[:4])].append(link)
        pending, section_rows, log_rows = [], [], []
        skipped = Counter()
        checked = {}
        last_notice = time.monotonic()
        for position, item in enumerate(items, 1):
            if self.stop.is_set():
                raise CollectionStopped()
            current = time.monotonic()
            if progress and current - last_notice >= 10:
                progress(f"resume inventory {position}/{len(items)} checked")
                last_notice = current
            uf, mun, zone, sec, metadata = item
            if metadata.get("nsp"):
                section_rows.append(
                    (
                        run,
                        uf,
                        mun,
                        zone,
                        sec,
                        "aggregated",
                        json.dumps(metadata),
                        str(metadata["nsp"]).zfill(4),
                    )
                )
                skipped["aggregated"] += 1
                continue
            old = old_sections.get(tuple(item[:4]))
            candidates = by_section.get(tuple(item[:4]), [])
            if not old or json.loads(old[5]) != metadata:
                pending.append(item)
                continue
            details = json.loads(old[6])
            if not candidates or len(candidates) != details.get("log_versions"):
                pending.append(item)
                continue
            valid = True
            for link in candidates:
                relative, digest, size = link[8:11]
                cache_key = (relative, digest, size)
                if cache_key not in checked:
                    try:
                        path = self.root / relative if relative else None
                        info = path.stat() if path is not None else None
                        ok = (
                            info is not None and stat.S_ISREG(info.st_mode) and info.st_size == size
                        )
                        if ok and verify_existing:
                            ok = hashlib.sha256(path.read_bytes()).hexdigest() == digest
                        checked[cache_key] = ok
                    except FileNotFoundError:
                        checked[cache_key] = False
                if not checked[cache_key]:
                    valid = False
                    break
            if not valid:
                pending.append(item)
                continue
            details["reused_from"] = old[0]
            section_rows.append(
                (run, uf, mun, zone, sec, "downloaded", old[5], json.dumps(details))
            )
            log_rows.extend((run, *link[:8]) for link in candidates)
            skipped["downloaded"] += 1
        if section_rows:
            if progress:
                progress(
                    f"recording {skipped['downloaded']} saved and {skipped['aggregated']} "
                    "aggregated sections in one manifest batch"
                )
            # One durable commit for the whole state's existing records instead
            # of one fsync-heavy transaction per already-downloaded section.
            with self.transaction() as db:
                db.executemany(
                    "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?,?,?)", section_rows
                )
                db.executemany("INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)", log_rows)
            with self.lock:
                self.reused_sections += skipped["downloaded"]
        return pending, skipped

    def saved_body(self, url):
        cached = self.query("SELECT path,sha256 FROM files WHERE url=?", (url,), one=True)
        if cached:
            try:
                body = (self.root / cached[0]).read_bytes()
            except FileNotFoundError:
                return None
            if hashlib.sha256(body).hexdigest() == cached[1]:
                return body
        return None

    def reuse_section(self, item, run) -> bool:
        """Reuse verified logs only when the current section metadata is unchanged."""
        uf, mun, zone, sec, metadata = item
        previous = self.query(
            """SELECT run,metadata,details FROM sections
            WHERE uf=? AND municipality=? AND zone=? AND section=? AND status='downloaded'
            ORDER BY run DESC LIMIT 1""",
            (uf, mun, zone, sec),
            one=True,
        )
        if not previous or json.loads(previous[1]) != metadata:
            return False
        details = json.loads(previous[2])
        links = self.query(
            """SELECT url,package_status,package_hash,filename FROM logs
            WHERE run=? AND uf=? AND municipality=? AND zone=? AND section=?""",
            (previous[0], uf, mun, zone, sec),
        )
        if not links or len(links) != details.get("log_versions"):
            return False
        if any(self.saved_body(url) is None for url, *_ in links):
            return False
        details["reused_from"] = previous[0]
        with self.transaction() as db:
            db.executemany(
                "INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)",
                [(run, uf, mun, zone, sec, *link) for link in links],
            )
            db.execute(
                "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?,?,?)",
                (run, uf, mun, zone, sec, "downloaded", json.dumps(metadata), json.dumps(details)),
            )
        with self.lock:
            self.reused_sections += 1
        return True

    def fetch(self, url, *, metadata=False):
        if self.stop.is_set():
            raise CollectionStopped()
        if not metadata:
            body = self.saved_body(url)
            if body is not None:
                self.add_stats(cached_logs=1)
                return body
        for attempt in range(4):
            with self.rate_lock:
                if self.stop.wait(max(0, self.next_request - time.monotonic())):
                    raise CollectionStopped()
                self.next_request = time.monotonic() + self.interval
            try:
                self.add_stats(requests=1, metadata_requests=int(metadata))
                req = Request(
                    url, headers={"User-Agent": "election-audit/1.0 (public TSE log collection)"}
                )
                with urlopen(req, timeout=self.timeout) as response:
                    headers = response.headers
                    chunks = []
                    while chunk := response.read(1024 * 1024):
                        chunks.append(chunk)
                        if shutil.disk_usage(self.root).free < self.reserve + sum(map(len, chunks)):
                            raise OSError("Disk reserve reached; choose a larger --output volume")
                    body = b"".join(chunks)
                    expected = headers.get("Content-Length")
                    if expected is not None and len(body) != int(expected):
                        raise IncompleteRead(body, int(expected) - len(body))
                break
            except (HTTPError, URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
                if isinstance(exc, HTTPError):
                    if exc.code in (403, 429):
                        reason = f"HTTP {exc.code}; stopped to avoid extending a TSE block"
                        logger.error("%s: %s", url, reason)
                        self.abort(reason)
                        raise RuntimeError(reason) from exc
                    if exc.code < 500 and exc.code != 408:
                        logger.error("Request failed for %s: %s", url, exc)
                        raise
                if attempt == 3:
                    logger.error(
                        "Request failed for %s after %d attempts: %s: %s",
                        url,
                        attempt + 1,
                        type(exc).__name__,
                        exc,
                    )
                    raise
                logger.warning(
                    "Request failed for %s (attempt %d/4): %s: %s; retrying in %ss",
                    url,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                    2**attempt,
                )
            if self.stop.wait(2**attempt):
                raise CollectionStopped()
        if metadata:
            json.loads(body)
            suffix = ".json"
        else:
            # JEZ files are ZIP containers. Keep originals, checking the CRC before committing.
            if url.lower().endswith(".jez"):
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    bad = archive.testzip()
                    if bad or not archive.namelist():
                        raise ValueError(f"Invalid JEZ archive: {bad}")
            elif body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                raise ValueError("Received HTML instead of a log")
            suffix = Path(url).suffix
        digest = hashlib.sha256(body).hexdigest()
        relative = Path("objects") / digest[:2] / (digest + suffix)
        path = self.root / relative
        path.parent.mkdir(exist_ok=True)
        with self.lock:
            if shutil.disk_usage(self.root).free < self.reserve + len(body):
                self.stop_reason = (
                    self.stop_reason or "Disk reserve reached; choose a larger --output volume"
                )
                self.stop.set()
                raise OSError("Disk reserve reached; choose a larger --output volume")
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                temporary = path.with_suffix(path.suffix + ".part")
                temporary.write_bytes(body)
                temporary.replace(path)
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
                (
                    url,
                    str(relative),
                    digest,
                    len(body),
                    now(),
                    headers.get("ETag"),
                    headers.get("Last-Modified"),
                ),
            )
        if not metadata:
            self.add_stats(new_logs=1, new_log_bytes=len(body))
        return body

    def json(self, url):
        return json.loads(self.fetch(url, metadata=True))

    def section(self, item, pleito, run, missing_only=False):
        uf, mun, zone, sec, metadata = item
        status, details = "error", None
        try:
            if self.stop.is_set():
                raise CollectionStopped()
            if metadata.get("nsp"):
                status = "aggregated"
                details = str(metadata["nsp"]).zfill(4)
            elif not metadata.get("da"):
                status = "aux_not_published"
            elif missing_only and self.reuse_section(item, run):
                return "downloaded"
            else:
                directory = f"{BASE}/ele2026/arquivo-urna/{pleito}/dados/{uf}/{mun}/{zone}/{sec}"
                aux = self.json(
                    f"{directory}/p{int(pleito):06d}-{uf}-m{mun}-z{zone}-s{sec}-aux.json"
                )
                links = list(log_urls(aux, directory))
                # Record every advertised version before attempting any download.
                with self.transaction() as db:
                    db.executemany(
                        "INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)",
                        [
                            (run, uf, mun, zone, sec, url, st, package, name)
                            for url, st, package, name in links
                        ],
                    )
                for url, _, _, _ in links:
                    self.fetch(url)
                status = "downloaded" if links else "no_log_listed"
                details = json.dumps({"section_status": aux.get("st"), "log_versions": len(links)})
        except CollectionStopped:
            return "cancelled"
        except Exception as exc:
            details = f"{type(exc).__name__}: {exc}"
            # A bad URL or unpublished file must be investigated before mass requests continue.
            self.abort(f"{uf}/{mun}/{zone}/{sec}: {details}")
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?,?,?)",
                (run, uf, mun, zone, sec, status, json.dumps(metadata), details),
            )
        if status == "error":
            raise RuntimeError(f"{uf}/{mun}/{zone}/{sec}: {details}")
        return status


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Move/copy the manifest to this database path (e.g. SSD); remembered for later runs",
    )
    parser.add_argument("--ufs", nargs="+", choices=UFS, default=UFS)
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Concurrent section workers (default 16, maximum 64)",
    )
    parser.add_argument("--rps", type=float, default=20, help="Global request rate (maximum 50)")
    parser.add_argument("--reserve-gib", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--limit", type=int, help="Limit sections per UF for a smoke test")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Skip unchanged completed sections using manifest, file existence and size",
    )
    parser.add_argument(
        "--verify-existing",
        action="store_true",
        help="With --missing-only, also rehash saved logs (slower, detects same-size corruption)",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(f"data/tse/2026/turno-{args.round}")
    if (
        not 0 < args.rps <= 50
        or not 1 <= args.workers <= 64
        or args.reserve_gib < 1
        or args.timeout <= 0
        or (args.limit is not None and args.limit < 1)
    ):
        parser.error(
            "Require 0 < rps <= 50, 1 <= workers <= 64, reserve-gib >= 1, timeout > 0, limit >= 1"
        )
    try:
        with output_lock(args.output):
            configure_manifest(args.output, args.manifest)
            collector = Collector(args.output, args.rps, args.reserve_gib, args.timeout)
            try:
                return run_collection(args, collector)
            finally:
                collector.close()
    except (DownloadAlreadyRunning, ValueError) as exc:
        parser.error(str(exc))


def run_collection(args, collector) -> int:
    from election_audit.elections import election_for_round

    round_number = getattr(args, "round", 2)
    descriptor = election_for_round(round_number)
    validate_manifest_round(collector.db(), descriptor.pleito_code)
    run = now()
    run_identity = {
        "run": run,
        "election": descriptor.as_dict(),
        "source_root": str(collector.root.resolve()),
        "manifest_path": str(collector.manifest.resolve()),
    }
    identity_sha = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with collector.transaction() as db:
        db.execute("INSERT INTO runs VALUES (?,?,NULL,?)", (run, run, "running"))
        db.execute(
            "INSERT INTO run_identity VALUES (?,?,?,?,?)",
            (
                run,
                json.dumps(descriptor.as_dict(), sort_keys=True),
                run_identity["source_root"],
                run_identity["manifest_path"],
                identity_sha,
            ),
        )
    outcome = "interrupted"
    error = None
    state_progress = {}
    try:
        pleito, election = presidential_election(
            collector.json(f"{BASE}/comum/config/ele-c.json"), round_number
        )
        logger.info(
            f"Official round {round_number}: pleito={pleito}, election={election}; "
            f"workers={args.workers}, max_rps={args.rps}; "
            f"resume_check={'SHA-256' if args.verify_existing else 'existence+size'}; UFs={','.join(args.ufs)}",
        )
        logger.info(f"Manifest: {collector.manifest}; raw files: {collector.root / 'objects'}")
        for uf in args.ufs:
            url = (
                f"{BASE}/ele2026/arquivo-urna/{pleito}/config/{uf}/{uf}-p{int(pleito):06d}-cs.json"
            )
            items = list(sections(collector.json(url), uf, pleito))
            if not items:
                raise ValueError(f"No sections in the {uf} index; refusing to report coverage")
            if args.limit:
                items = items[: args.limit]
            total = len(items)
            skipped = Counter()
            resume_seconds = 0.0
            if args.missing_only:
                logger.info(
                    f"{uf}: resume scan of {total} sections (manifest + "
                    f"{'SHA-256' if args.verify_existing else 'existence/size'} checks)",
                )
                resume_started = time.monotonic()
                items, skipped = collector.prepare_resume(
                    items,
                    run,
                    verify_existing=args.verify_existing,
                    progress=lambda message: logger.info(f"{uf}: {message}"),
                )
                resume_seconds = time.monotonic() - resume_started
                logger.info(
                    f"{uf}: already saved={skipped['downloaded']}, aggregated={skipped['aggregated']}, "
                    f"remaining={len(items)} (resume scan {resume_seconds:.1f}s)",
                )
                if not items:
                    logger.info(
                        f"{uf}: SKIPPED — all {total} sections accounted for; no section downloads",
                    )
                    state_progress[uf] = {
                        "skipped": skipped["downloaded"],
                        "aggregated": skipped["aggregated"],
                        "processed": 0,
                        "new_logs": 0,
                        "cached_logs": 0,
                        "resume_seconds": resume_seconds,
                    }
                    continue
            baseline = collector.statistics()
            processed = Counter()
            started = time.monotonic()
            last_notice = started
            # prepare_resume has already removed every reusable section. Avoid
            # repeating its per-section lookups and whole-file verification.
            job = lambda item: collector.section(item, pleito, run)
            results = bounded_parallel_map(job, items, args.workers, collector.stop)
            try:
                for completed, status in enumerate(results, 1):
                    processed[status] += 1
                    if collector.stop.is_set():
                        raise RuntimeError(collector.stop_reason or "Collection stopped")
                    current = time.monotonic()
                    if (
                        completed % 256 == 0
                        or completed == len(items)
                        or current - last_notice >= 10
                    ):
                        speed = completed / max(current - started, 0.001)
                        stats = collector.statistics()
                        new_logs = stats.get("new_logs", 0) - baseline.get("new_logs", 0)
                        cached = stats.get("cached_logs", 0) - baseline.get("cached_logs", 0)
                        new_bytes = stats.get("new_log_bytes", 0) - baseline.get("new_log_bytes", 0)
                        logger.info(
                            f"{uf}: processed={completed}/{len(items)} remaining sections "
                            f"({speed:.1f}/s), skipped={skipped['downloaded']}, "
                            f"new logs={new_logs} ({new_bytes / 1024**2:.1f} MiB), cached logs={cached}, "
                            f"aggregated={skipped['aggregated'] + processed['aggregated']}",
                        )
                        last_notice = current
            finally:
                results.close()
                stats = collector.statistics()
                state_progress[uf] = {
                    "skipped": skipped["downloaded"],
                    "aggregated": skipped["aggregated"] + processed["aggregated"],
                    "processed": sum(processed.values()),
                    "resume_seconds": resume_seconds,
                    "new_logs": stats.get("new_logs", 0) - baseline.get("new_logs", 0),
                    "cached_logs": stats.get("cached_logs", 0) - baseline.get("cached_logs", 0),
                }
        outcome = "finished"
    except (Exception, KeyboardInterrupt) as exc:
        collector.stop.set()
        error = collector.stop_reason or f"{type(exc).__name__}: {exc}"
        logger.exception("Collection interrupted: %s", error)
    finally:
        with collector.transaction() as db:
            db.execute("UPDATE runs SET finished_at=?,status=? WHERE id=?", (now(), outcome, run))
        counts = dict(
            collector.query(
                "SELECT status,COUNT(*) FROM sections WHERE run=? GROUP BY status", (run,)
            )
        )
        advertised, saved = collector.query(
            """SELECT COUNT(*), COUNT(f.url) FROM logs l
            LEFT JOIN files f ON l.url=f.url WHERE l.run=?""",
            (run,),
            one=True,
        )
        report = {
            "run": run,
            "status": outcome,
            "error": error,
            "requested_ufs": args.ufs,
            "missing_only": args.missing_only,
            "reused_sections": collector.reused_sections,
            "workers": args.workers,
            "max_rps": args.rps,
            "existing_file_check": "sha256" if args.verify_existing else "existence+size",
            "activity": collector.statistics(),
            "states": state_progress,
            "manifest": str(collector.manifest.resolve()),
            "limited": args.limit is not None,
            "sections": counts,
            "advertised_log_versions": advertised,
            "saved_log_versions": saved,
            "national_coverage": outcome == "finished"
            and not args.limit
            and set(args.ufs) == set(UFS)
            and not any(counts.get(s, 0) for s in ("error", "aux_not_published", "no_log_listed")),
        }
        (args.output / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
        logger.info(json.dumps(report, indent=2))
    return 0 if outcome == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
