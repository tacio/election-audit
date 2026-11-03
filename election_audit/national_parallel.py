"""Bounded multiprocess source summaries with a single durable grouped-shard writer."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import multiprocessing
import os
import shutil
import signal
import sqlite3
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import closing
from pathlib import Path

from election_audit.national_migration import atomic, sha
from election_audit.national_relocation import configure
from election_audit.national_resources import apply, metrics, policy, validate
from election_audit.national_summary import VERSION, summarize

FORMAT = "grouped-source-summary-shards-v3"
_POLICY = None
_STOP = False


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checked(path):
    path = Path(path)
    if sha(path) != Path(str(path) + ".sha256").read_text().strip():
        raise ValueError("Pinned metadata checksum mismatch")
    return json.loads(path.read_text())


def prepare(old_workload, output, store, *, resources=None, selection=None):
    """Freeze metadata scope; optional selection only restricts already eligible SHAs."""
    old_workload, output, store = (Path(x).absolute() for x in (old_workload, output, store))
    if output.exists() or store.exists():
        raise ValueError("New versioned configuration and empty store paths required")
    old = checked(old_workload / "workload.json")
    scope = Path(old["store"]) / "scope/observations.sqlite"
    scope_doc = checked(scope.parent / "scope.json")
    if (
        sha(scope) != scope_doc["files"][scope.name]["sha256"]
        or scope_doc["job_id"] != old["job_id"]
    ):
        raise ValueError("Frozen protected scope checksum/identity mismatch")
    if sha(old["exclusions"]) != old["exclusions_sha256"]:
        raise ValueError("Frozen exclusion registry changed")
    registry = old["relocation_registry"]
    if not registry or sha(registry["path"]) != registry["sha256"]:
        raise ValueError("Verified relocation registry required")
    resources = resources or policy()
    validate(resources)
    custody = json.loads(Path(registry["path"]).read_text())
    for certificate in custody["certificates"]:
        for name in ("root", "old_root"):
            raw = Path(certificate[name]).absolute()
            if (
                store.is_relative_to(raw)
                or output.is_relative_to(raw)
                or Path(old["scratch"]).absolute().is_relative_to(raw)
            ):
                raise ValueError(
                    "Derived/config/scratch paths must remain outside every raw source alias"
                )
    selected = sorted(set(selection)) if selection is not None else None
    if selected is not None and (not selected or len(selected) > 10000):
        raise ValueError(
            "Benchmark selections must contain 1..10000 explicit eligible content hashes"
        )
    with closing(sqlite3.connect(scope.as_uri() + "?mode=ro", uri=True)) as db:
        for object_sha in selected or ():
            if not db.execute(
                "SELECT 1 FROM observations WHERE sha256=? AND processing_scope='eligible_structural_preprocessing'",
                (object_sha,),
            ).fetchone():
                raise ValueError(
                    "Protected or absent benchmark source prevented before body access"
                )
    output.mkdir(parents=True)
    root = Path(__file__).resolve().parent.parent
    runtime = output / "runtime"
    sources = [
        *Path(__file__).parent.glob("*.py"),
        *(p for p in (Path(__file__).parent / "resources").rglob("*") if p.is_file()),
        root / "scripts/__init__.py",
        root / "scripts/download_tse_logs.py",
        root / "pyproject.toml",
        root / "uv.lock",
    ]
    pins = {}
    for source in sources:
        relative = source.relative_to(root)
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        with destination.open("rb") as f:
            os.fsync(f.fileno())
        pins[str(relative)] = sha(destination)
    spec = {
        "version": FORMAT,
        "summary_version": VERSION,
        "old_job_id": old["job_id"],
        "old_workload": str(old_workload),
        "old_store": old["store"],
        "scope": str(scope),
        "scope_sha256": sha(scope),
        "scope_counts": old["scope"],
        "exclusions": old["exclusions"],
        "exclusions_sha256": old["exclusions_sha256"],
        "source_root": old["source"]["root"],
        "round": old["source"]["round"],
        "relocation_registry": registry,
        "selection": selected,
        "store": str(store),
        "scratch": old["scratch"],
        "volume_anchor": old["volume_anchor"],
        "resources": resources,
        "runtime_files": pins,
        "compatibility": "raw/member/line anchors retain old structural parser semantics; summaries do not certify official sessions/clocks/results; old event artifacts retained as optional forensic dependencies",
        "scientific_eligibility": "unavailable_structural_only",
    }
    spec["job_id"] = hashlib.sha256(encoded(spec).encode()).hexdigest()
    atomic(output / "config.json", spec)
    (output / "config.json.sha256").write_text(sha(output / "config.json") + "\n")
    (output / "run_frozen.py").write_text("""from pathlib import Path
import hashlib,json,sys,os
d=Path(__file__).resolve().parent
body=(d/'config.json').read_bytes()
if hashlib.sha256(body).hexdigest()!=(d/'config.json.sha256').read_text().strip(): raise ValueError('Config changed')
s=json.loads(body)
for n,h in s['runtime_files'].items():
 p=d/'runtime'/n
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h: raise ValueError('Runtime changed')
os.environ['PYTHONPATH']=str(d/'runtime')
os.chdir(d/'runtime');sys.path.insert(0,str(d/'runtime'))
from election_audit.national_parallel import main
if __name__=='__main__': main([sys.argv[1] if len(sys.argv)>1 else 'status',str(d),*sys.argv[2:]])
""")
    return spec


def load(directory):
    spec = checked(Path(directory) / "config.json")
    validate(spec["resources"])
    if (
        hashlib.sha256(
            encoded({k: v for k, v in spec.items() if k != "job_id"}).encode()
        ).hexdigest()
        != spec["job_id"]
    ):
        raise ValueError("Job identity mismatch")
    if sha(spec["exclusions"]) != spec["exclusions_sha256"]:
        raise ValueError("Protected exclusion pins changed")
    configure(spec["relocation_registry"]["path"], spec["relocation_registry"]["sha256"])
    return spec


def connection(path):
    db = sqlite3.connect(path, uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA cache_size=-8192")
    return db


def capacity(spec, used=0):
    anchor = Path(spec["volume_anchor"])
    store = Path(spec["store"])
    parent = store
    while not parent.exists():
        parent = parent.parent
    if not anchor.is_mount() or parent.stat().st_dev != anchor.stat().st_dev:
        raise OSError("Output mount unavailable; no fallback writes")
    r = spec["resources"]
    needed = (
        r["hdd_reserve_bytes"] + r["future_budget_bytes"] + max(0, r["output_budget_bytes"] - used)
    )
    if shutil.disk_usage(anchor).free < needed:
        raise OSError("HDD reserve/output/future allowance unavailable")
    if shutil.disk_usage(spec["scratch"]).free < r["ssd_reserve_bytes"] + r["scratch_budget_bytes"]:
        raise OSError("SSD reserve/spill allowance unavailable")


def initialise(spec):
    store = Path(spec["store"])
    store.mkdir(parents=True, exist_ok=True)
    owner = store / "owner.json"
    if owner.exists():
        if json.loads(owner.read_text())["job_id"] != spec["job_id"]:
            raise ValueError("Store belongs to a different immutable job")
    else:
        if any(p.name != ".lock" for p in store.iterdir()):
            raise ValueError("Refusing unowned nonempty store")
        atomic(owner, {"job_id": spec["job_id"], "version": FORMAT})
    db = connection(store / "work.sqlite")
    db.executescript(
        "CREATE TABLE IF NOT EXISTS work(sha TEXT PRIMARY KEY,url TEXT,path TEXT,bytes INTEGER,status TEXT,shard TEXT,legacy_ref TEXT); CREATE INDEX IF NOT EXISTS work_state ON work(status,sha); CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY,objects INTEGER,events INTEGER,bytes INTEGER); CREATE TABLE IF NOT EXISTS failures(at REAL,sha TEXT,error_type TEXT); CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);"
    )
    if not db.execute("SELECT 1 FROM metadata WHERE key='initialised'").fetchone():
        if sha(spec["scope"]) != spec["scope_sha256"]:
            raise ValueError("Frozen scope changed")
        db.execute("ATTACH DATABASE ? AS scope", (Path(spec["scope"]).as_uri() + "?mode=ro",))
        db.execute("CREATE TEMP TABLE selected(sha TEXT PRIMARY KEY)")
        if spec["selection"]:
            db.executemany("INSERT INTO selected VALUES(?)", ((s,) for s in spec["selection"]))
        condition = "AND sha256 IN(SELECT sha FROM selected)" if spec["selection"] else ""
        db.execute(
            "INSERT OR IGNORE INTO work SELECT sha256,min(url),min(path),min(bytes),'pending',NULL,NULL FROM scope.observations WHERE processing_scope='eligible_structural_preprocessing' "
            + condition
            + " GROUP BY sha256"
        )
        old_ledger = Path(spec["old_store"]) / "work.sqlite"
        if old_ledger.exists():
            db.execute("ATTACH DATABASE ? AS legacy", (old_ledger.as_uri() + "?mode=ro",))
            db.execute(
                "UPDATE work SET legacy_ref=(SELECT artifact FROM legacy.work l WHERE l.sha256=work.sha AND l.status='complete')"
            )
        db.execute("INSERT INTO metadata VALUES('initialised','yes')")
        db.executemany(
            "INSERT INTO metadata VALUES(?,?)",
            [
                ("total", str(db.execute("SELECT count(*) FROM work").fetchone()[0])),
                ("completed", "0"),
                ("events", "0"),
                ("bytes", "0"),
                ("failures", "0"),
                ("released_bytes", "0"),
                ("group_count", "0"),
            ],
        )
        db.commit()
    db.execute("UPDATE work SET status='pending' WHERE status='running'")
    db.commit()
    return db


def shard_database(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA cache_size=-8192")
    db.executescript(
        "CREATE TABLE objects(object_id INTEGER PRIMARY KEY,sha TEXT UNIQUE,payload TEXT); CREATE TABLE members(object_id INTEGER,member INTEGER,payload TEXT,PRIMARY KEY(object_id,member)) WITHOUT ROWID; CREATE TABLE blocks(object_id INTEGER,member INTEGER,first_line INTEGER,last_line INTEGER,digest BLOB,bytes INTEGER,events INTEGER,unknown INTEGER,PRIMARY KEY(object_id,member,first_line)) WITHOUT ROWID; CREATE TABLE anchors(object_id INTEGER,member INTEGER,line INTEGER,sequence INTEGER,line_sha BLOB,time TEXT,device TEXT,app TEXT,level TEXT,kind TEXT,stream_changed INTEGER,clock_reverse INTEGER,PRIMARY KEY(object_id,member,line)) WITHOUT ROWID; CREATE TABLE errors(object_id INTEGER,ordinal INTEGER,payload TEXT,PRIMARY KEY(object_id,ordinal)) WITHOUT ROWID;"
    )
    db.execute("BEGIN")
    return db


def insert_document(db, doc, object_id):
    object_sha = doc["object_sha256"]
    metadata = {k: v for k, v in doc.items() if k not in ("members", "blocks", "anchors", "errors")}
    db.execute("INSERT INTO objects VALUES(?,?,?)", (object_id, object_sha, encoded(metadata)))
    db.executemany(
        "INSERT INTO members VALUES(?,?,?)",
        ((object_id, r[0], encoded(r)) for r in doc["members"]),
    )
    db.executemany(
        "INSERT INTO blocks VALUES(?,?,?,?,?,?,?,?)",
        ((object_id, *r[:3], bytes.fromhex(r[3]), *r[4:]) for r in doc["blocks"]),
    )
    db.executemany(
        "INSERT INTO anchors VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        ((object_id, *r[:3], bytes.fromhex(r[3]), *r[4:]) for r in doc["anchors"]),
    )
    db.executemany(
        "INSERT INTO errors VALUES(?,?,?)",
        ((object_id, i, encoded(r)) for i, r in enumerate(doc["errors"])),
    )


def worker_init(resources, registry, scratch):
    global _POLICY
    _POLICY = resources
    apply(resources, worker=True)
    configure(registry["path"], registry["sha256"])
    Path(scratch).mkdir(parents=True, exist_ok=True)
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    atomic(
        Path(scratch) / f"worker-{os.getpid()}.json",
        {"pid": os.getpid(), "start_ticks": fields[19]},
    )


def worker(row, scratch):
    started = time.monotonic()
    result = summarize(row, scratch, output_limit=_POLICY["worker_output_limit_bytes"])
    return result, {"elapsed_seconds": time.monotonic() - started, "pid": os.getpid()}


def publish(spec, temporary, group_id, objects, events):
    database = temporary / "summary.sqlite"
    with database.open("rb") as stream:
        os.fsync(stream.fileno())
    marker = {
        "version": FORMAT,
        "job_id": spec["job_id"],
        "objects": sorted(objects),
        "events": events,
        "database_sha256": sha(database),
        "bytes": database.stat().st_size,
    }
    marker["marker_sha256"] = hashlib.sha256(encoded(marker).encode()).hexdigest()
    atomic(temporary / "shard.json", marker)
    destination = Path(spec["store"]) / "shards" / group_id[:2] / group_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.rename(temporary, destination)
    fd = os.open(destination.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return destination, marker


def reconcile(spec, db):
    for marker_path in (Path(spec["store"]) / "shards").glob("*/*/shard.json"):
        group_id = marker_path.parent.name
        if db.execute("SELECT 1 FROM groups WHERE id=?", (group_id,)).fetchone():
            continue
        marker = json.loads(marker_path.read_text())
        if (
            hashlib.sha256(
                encoded({k: v for k, v in marker.items() if k != "marker_sha256"}).encode()
            ).hexdigest()
            != marker.get("marker_sha256")
            or marker["job_id"] != spec["job_id"]
            or sha(marker_path.parent / "summary.sqlite") != marker["database_sha256"]
            or hashlib.sha256(
                encoded([spec["job_id"], sorted(marker["objects"])]).encode()
            ).hexdigest()
            != group_id
        ):
            raise ValueError("Unledgered published shard failed integrity")
        for object_sha in marker["objects"]:
            row = db.execute("SELECT status FROM work WHERE sha=?", (object_sha,)).fetchone()
            if row is None or row[0] == "complete":
                raise ValueError("Shard reconciliation scope overlap")
            db.execute(
                "UPDATE work SET status='complete',shard=? WHERE sha=?",
                (str(marker_path.parent), object_sha),
            )
        db.execute(
            "INSERT INTO groups VALUES(?,?,?,?)",
            (group_id, len(marker["objects"]), marker["events"], marker["bytes"]),
        )
        increment(db, len(marker["objects"]), marker["events"], marker["bytes"])
        db.commit()


def increment(db, objects, events, size):
    db.executemany(
        "UPDATE metadata SET value=CAST(value AS INTEGER)+? WHERE key=?",
        [(objects, "completed"), (events, "events"), (size, "bytes")],
    )
    db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='group_count'")


def status(directory):
    spec = load(directory)
    path = Path(spec["store"]) / "work.sqlite"
    if not path.exists():
        return {"state": "not_started", "job_id": spec["job_id"], "resources": spec["resources"]}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        counters = {
            r[0]: int(r[1])
            for r in db.execute("SELECT key,value FROM metadata WHERE key!='initialised'")
        }
        objects, events, size, failures = (
            counters[k] for k in ("completed", "events", "bytes", "failures")
        )
        states = {"complete": objects, "uncommitted": counters["total"] - objects}
    return {
        "job_id": spec["job_id"],
        "format": FORMAT,
        "state": "scope_complete" if not states["uncommitted"] else "incomplete",
        "work_status": states,
        "completed": objects,
        "structural_events_scanned": events,
        "output_bytes": size,
        "failures": failures,
        "resources": spec["resources"],
        "full_national_complete": False,
        "scientific_eligibility": "unavailable_structural_only",
    }


def run(directory, *, max_objects=None):
    global _STOP
    _STOP = False
    directory = Path(directory).absolute()
    spec = load(directory)
    if max_objects is not None and (type(max_objects) is not int or max_objects < 1):
        raise ValueError("max_objects must be positive")
    capacity(spec)
    apply(spec["resources"])
    scratch = Path(spec["scratch"]) / spec["job_id"]
    scratch.mkdir(parents=True, exist_ok=True)
    store = Path(spec["store"])
    store.mkdir(parents=True, exist_ok=True)
    lock = (store / ".lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for record in scratch.glob("worker-*.json"):
        previous = json.loads(record.read_text())
        proc = Path("/proc") / str(previous["pid"])
        try:
            fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            continue
        if fields[19] == previous["start_ticks"] and fields[0] != "Z":
            raise RuntimeError("Previous job worker remains active; refusing scratch reuse")
    for private in [*scratch.glob("summary-*"), *store.glob(".building-*")]:
        if private.is_symlink() or not private.is_dir():
            raise ValueError("Unsafe unpublished private staging")
        shutil.rmtree(private)
    db = initialise(spec)
    reconcile(spec, db)
    started, processed, peak_rss, cpu_seconds = time.monotonic(), 0, 0, 0
    worker_seconds_total, worker_seconds_max = 0.0, 0.0
    initial_failures = int(
        db.execute("SELECT value FROM metadata WHERE key='failures'").fetchone()[0]
    )
    workers = spec["resources"]["workers"]
    old_handler = signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("_STOP", True))
    pool = ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=worker_init,
        initargs=(spec["resources"], spec["relocation_registry"], str(scratch)),
    )
    try:
        while not _STOP and (max_objects is None or processed < max_objects):
            limit = (
                min(spec["resources"]["batch_objects"], max_objects - processed)
                if max_objects is not None
                else spec["resources"]["batch_objects"]
            )
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM work WHERE status='pending' ORDER BY sha LIMIT ?", (limit,)
                )
            ]
            if not rows:
                break
            used = int(db.execute("SELECT value FROM metadata WHERE key='bytes'").fetchone()[0])
            reserved_metadata = min(2 * 1024**3, spec["resources"]["output_budget_bytes"] // 4)
            releases = int(
                db.execute("SELECT value FROM metadata WHERE key='released_bytes'").fetchone()[0]
            )
            metadata_estimate = (
                sum(p.stat().st_blocks * 512 for p in store.glob("work.sqlite*"))
                + int(
                    db.execute("SELECT value FROM metadata WHERE key='group_count'").fetchone()[0]
                )
                * 8192
            )
            if metadata_estimate > reserved_metadata:
                raise OSError("Ingestion metadata allowance exhausted")
            data_remaining = (
                spec["resources"]["output_budget_bytes"] - reserved_metadata - used - releases
            )
            if data_remaining < 1024**2:
                raise OSError("Combined recovery/analysis output allowance exhausted")
            capacity(spec, used + releases)
            group_id = hashlib.sha256(
                encoded([spec["job_id"], [r["sha"] for r in rows]]).encode()
            ).hexdigest()
            temporary = store / (".building-" + group_id)
            if temporary.exists():
                # Only unpublished private files are discarded under the job lock.
                if temporary.is_symlink() or not temporary.is_dir():
                    raise ValueError("Unsafe unpublished staging path")
                shutil.rmtree(temporary)
            temporary.mkdir()
            writer = shard_database(temporary / "summary.sqlite")
            db.executemany(
                "UPDATE work SET status='running' WHERE sha=?", ((r["sha"],) for r in rows)
            )
            db.commit()
            pending, iterator, finished, event_count = {}, iter(rows), [], 0
            object_ids = {r["sha"]: i for i, r in enumerate(rows)}
            group_timings = []

            def submit():
                row = next(iterator, None)
                if row is None:
                    return False
                source = {
                    "source_root": spec["source_root"],
                    "path": row["path"],
                    "sha256": row["sha"],
                    "bytes": row["bytes"],
                    "url": row["url"],
                }
                pending[pool.submit(worker, source, str(scratch))] = row["sha"]
                return True

            for _ in range(spec["resources"]["queue_limit"]):
                if not submit():
                    break
            try:
                while pending:
                    done, _ = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    observed = metrics([os.getpid(), *pool._processes.keys()])
                    peak_rss = max(peak_rss, observed["rss_bytes"])
                    cpu_seconds = max(cpu_seconds, observed["cpu_seconds"])
                    if observed["rss_bytes"] > spec["resources"]["aggregate_memory_bytes"]:
                        raise MemoryError("Aggregate process-tree RAM budget exceeded")
                    if _STOP:
                        raise InterruptedError(
                            "Cancellation requested; unpublished group retained for safe restart"
                        )
                    for future in done:
                        object_sha = pending.pop(future)
                        document, timing = future.result()
                        group_timings.append(timing["elapsed_seconds"])
                        worker_seconds_total += timing["elapsed_seconds"]
                        worker_seconds_max = max(worker_seconds_max, timing["elapsed_seconds"])
                        if document["object_sha256"] != object_sha:
                            raise ValueError("Worker returned another source identity")
                        insert_document(writer, document, object_ids[object_sha])
                        page_count = writer.execute("PRAGMA page_count").fetchone()[0]
                        page_size = writer.execute("PRAGMA page_size").fetchone()[0]
                        if page_count * page_size > data_remaining:
                            raise OSError("Grouped output budget exceeded before publication")
                        event_count += document["counts"].get("events", 0)
                        finished.append(object_sha)
                        del document
                        submit()
                writer.commit()
            except BaseException as exc:
                writer.close()
                for future in pending:
                    future.cancel()
                db.execute(
                    "INSERT INTO failures VALUES(?,?,?)",
                    (time.time(), locals().get("object_sha"), type(exc).__name__),
                )
                db.execute(
                    "UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='failures'"
                )
                db.commit()
                raise
            writer.close()
            if (temporary / "summary.sqlite").stat().st_size > data_remaining:
                raise OSError("Explicit output budget exhausted before publication")
            destination, marker = publish(spec, temporary, group_id, finished, event_count)
            db.executemany(
                "UPDATE work SET status='complete',shard=? WHERE sha=?",
                ((str(destination), s) for s in finished),
            )
            db.execute(
                "INSERT INTO groups VALUES(?,?,?,?)",
                (group_id, len(finished), event_count, marker["bytes"]),
            )
            increment(db, len(finished), event_count, marker["bytes"])
            db.commit()
            processed += len(finished)
            elapsed = time.monotonic() - started
            progress = {
                **status(directory),
                "pid": os.getpid(),
                "processed_this_attempt": processed,
                "elapsed_seconds": elapsed,
                "objects_per_second": processed / elapsed,
                "peak_process_tree_rss_bytes": peak_rss,
                "process_tree_cpu_seconds": cpu_seconds,
                "average_cpu_percent": 100 * cpu_seconds / elapsed,
                "last_group_worker_seconds": sorted(group_timings),
                "worker_seconds_total": worker_seconds_total,
                "maximum_object_worker_seconds": worker_seconds_max,
                "resource_observation": observed,
                "updated_unix": time.time(),
            }
            atomic(directory / "progress.json", progress)
            with (directory / "timings.jsonl").open("a") as telemetry:
                for source_sha, seconds in zip(finished, group_timings, strict=True):
                    telemetry.write(
                        encoded({"sha256": source_sha, "worker_seconds": seconds}) + "\n"
                    )
            print(
                encoded(
                    {
                        k: progress[k]
                        for k in (
                            "completed",
                            "objects_per_second",
                            "peak_process_tree_rss_bytes",
                            "average_cpu_percent",
                        )
                    }
                ),
                flush=True,
            )
        return status(directory)
    except BaseException as exc:
        if (
            int(db.execute("SELECT value FROM metadata WHERE key='failures'").fetchone()[0])
            == initial_failures
        ):
            db.execute(
                "INSERT INTO failures VALUES(?,?,?)", (time.time(), None, type(exc).__name__)
            )
            db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='failures'")
            db.commit()
        atomic(
            directory / "progress.json",
            {
                **status(directory),
                "pid": os.getpid(),
                "run_state": "cancelled"
                if isinstance(exc, InterruptedError)
                else "stopped_failure",
                "error_type": type(exc).__name__,
                "updated_unix": time.time(),
                "peak_process_tree_rss_bytes": peak_rss,
            },
        )
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        db.close()
        lock.close()
        signal.signal(signal.SIGTERM, old_handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser(
        "prepare",
        help="Freeze a feature-oriented job from an existing eligible metadata scope; no event materialization required",
    )
    for name in ("scope-workload", "output", "store"):
        setup.add_argument("--" + name, required=True)
    setup.add_argument("--memory-gib", type=float, default=4)
    setup.add_argument("--cpu-fraction", type=float, default=0.5)
    setup.add_argument("--workers", type=int)
    setup.add_argument("--batch-objects", type=int, default=32)
    setup.add_argument("--prefetch", type=int, default=1)
    setup.add_argument("--hdd-reserve-gib", type=float, default=20)
    setup.add_argument("--ssd-reserve-gib", type=float, default=10)
    setup.add_argument("--scratch-gib", type=float, default=8)
    setup.add_argument("--output-gib", type=float, default=256)
    setup.add_argument("--future-gib", type=float, default=256)
    setup.add_argument(
        "--selection",
        help="JSON with explicit eligible sha256s; omit for the complete eligible scope",
    )
    for action in ("run", "status", "launch", "replay", "export"):
        p = sub.add_parser(action)
        p.add_argument("directory")
        if action in ("run", "launch"):
            p.add_argument("--max-objects", type=int)
            p.add_argument(
                "--analysis-output",
                help="Publish compact analytical Parquet after requested scope completes",
            )
        if action == "launch":
            p.add_argument("--unit", default="election-audit-summary")
            p.add_argument("--no-cgroup", action="store_true")
        if action == "replay":
            p.add_argument("object_sha256")
            p.add_argument("member", type=int)
            p.add_argument("first_line", type=int)
            p.add_argument("last_line", type=int)
            p.add_argument("--development-sample", required=True)
        if action == "export":
            p.add_argument("--output", required=True)
            p.add_argument("--target-mib", type=int, default=128)
    args = parser.parse_args(argv)
    if args.action == "prepare":
        r = policy(
            memory_bytes=int(args.memory_gib * 1024**3),
            workers=args.workers,
            batch=args.batch_objects,
            prefetch=args.prefetch,
            cpu_fraction=args.cpu_fraction,
        )
        for key, value in (
            ("hdd_reserve_bytes", args.hdd_reserve_gib),
            ("ssd_reserve_bytes", args.ssd_reserve_gib),
            ("scratch_budget_bytes", args.scratch_gib),
            ("output_budget_bytes", args.output_gib),
            ("future_budget_bytes", args.future_gib),
        ):
            if value < 0:
                raise ValueError("Budgets cannot be negative")
            r[key] = int(value * 1024**3)
        selection = (
            json.loads(Path(args.selection).read_text())["sha256s"] if args.selection else None
        )
        print(
            encoded(
                prepare(
                    args.scope_workload, args.output, args.store, resources=r, selection=selection
                )
            )
        )
        return
    if args.action == "launch":
        from election_audit.national_summary_tools import launch

        print(
            encoded(
                launch(
                    args.directory,
                    unit=args.unit,
                    use_cgroup=not args.no_cgroup,
                    max_objects=args.max_objects,
                    analysis_output=args.analysis_output,
                )
            )
        )
        return
    if args.action == "replay":
        from election_audit.national_summary_tools import replay

        for event in replay(
            args.directory,
            args.object_sha256,
            args.member,
            args.first_line,
            args.last_line,
            args.development_sample,
        ):
            print(encoded(event))
        return
    if args.action == "export":
        from election_audit.national_summary_release import publish_release

        print(
            encoded(
                publish_release(args.directory, args.output, target_bytes=args.target_mib * 1024**2)
            )
        )
        return
    result = (
        run(args.directory, max_objects=args.max_objects)
        if args.action == "run"
        else status(args.directory)
    )
    if args.action == "run" and args.analysis_output and result["state"] == "scope_complete":
        from election_audit.national_summary_release import publish_release

        result["analytical_release"] = publish_release(args.directory, args.analysis_output)
    print(encoded(result))


if __name__ == "__main__":
    main()
