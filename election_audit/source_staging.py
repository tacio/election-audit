"""Verified, resumable staging of certified raw objects onto a faster volume.

The source is a hash-certified copy (a ``certificate-r<N>.json`` from the
relocation acceptance plus its frozen manifest). Every object is copied to a new
destination root under the same relative path. Each source body is checked
against the manifest SHA-256 while it is read, and every destination body is
hashed again after a durable flush. Bodies are never decoded. The source root,
the frozen manifest and the certificate are only read.

``benchmark`` compares read orders on fresh, disjoint windows of objects so a full
copy can read the rotational source in its fastest order.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import random
import shutil
import sqlite3
import struct
import time
from pathlib import Path

from election_audit.national_migration import atomic, relative_object, sha

VERSION = "certified-source-staging-v1"
ORDERS = ("path", "inode", "physical")
# Manifest URL order is how section-driven passes (e.g. Phase 11) visit objects.
BENCHMARK_ORDERS = ("url", *ORDERS)
FS_IOC_FIEMAP = 0xC020660B
_FIEMAP_HEADER = struct.Struct("=QQIIII")
_FIEMAP_EXTENT = struct.Struct("=QQQQQIIII")
BATCH_OBJECTS = 2000
BATCH_BYTES = 512 * 1024**2


def load_binding(certificate_path, manifest_path):
    """Return the certificate after proving the manifest copy is the certified one."""
    certificate_path = Path(certificate_path)
    certificate = json.loads(certificate_path.read_bytes())
    manifest_sha = sha(manifest_path)
    if manifest_sha != certificate.get("manifest_sha256"):
        raise ValueError("Manifest copy does not match the certificate digest")
    return {
        "certificate": str(certificate_path.resolve()),
        "certificate_sha256": sha(certificate_path),
        "manifest": str(Path(manifest_path).resolve()),
        "manifest_sha256": manifest_sha,
        "round": certificate.get("round"),
        "source_root": certificate["root"],
        "certified_objects": certificate["objects"],
        "certified_bytes": certificate["bytes"],
    }


def manifest_objects(manifest_path):
    """Distinct (relative path, sha256, bytes) rows, validated, in path order."""
    uri = Path(manifest_path).resolve().as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        if db.execute(
            "SELECT path FROM files GROUP BY path"
            " HAVING count(DISTINCT sha256)>1 OR count(DISTINCT bytes)>1 LIMIT 1"
        ).fetchone():
            raise ValueError("Conflicting manifest path aliases")
        rows = db.execute(
            "SELECT path,min(sha256),min(bytes) FROM files GROUP BY path ORDER BY path"
        ).fetchall()
    for relative, expected_sha, _ in rows:
        relative_object(relative, expected_sha)
    return rows


def inode_numbers(root, rows):
    """Directory-entry inode numbers, read without stat()ing each object."""
    root = Path(root)
    wanted = {}
    for relative, _, _ in rows:
        parent, name = relative.rsplit("/", 1)
        wanted.setdefault(parent, set()).add(name)
    inodes = {}
    for parent in sorted(wanted):
        with os.scandir(root / parent) as entries:
            for entry in entries:
                if entry.name in wanted[parent]:
                    inodes[f"{parent}/{entry.name}"] = entry.inode()
    missing = [r for r, _, _ in rows if r not in inodes]
    if missing:
        raise FileNotFoundError(f"{len(missing)} certified objects missing, e.g. {missing[0]}")
    return inodes


def physical_offset(path):
    """Physical byte offset of the file's first extent (FIEMAP); 0 for no extents."""
    request = bytearray(_FIEMAP_HEADER.size + _FIEMAP_EXTENT.size)
    _FIEMAP_HEADER.pack_into(request, 0, 0, 2**64 - 1, 0, 0, 1, 0)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.ioctl(fd, FS_IOC_FIEMAP, request)
    finally:
        os.close(fd)
    mapped = _FIEMAP_HEADER.unpack_from(request, 0)[3]
    if not mapped:
        return 0
    return _FIEMAP_EXTENT.unpack_from(request, _FIEMAP_HEADER.size)[1]


def order_rows(root, rows, order, inodes=None):
    """Return rows in the requested read order."""
    if order == "path":
        return sorted(rows)
    inodes = inodes if inodes is not None else inode_numbers(root, rows)
    by_inode = sorted(rows, key=lambda row: (inodes[row[0]], row[0]))
    if order == "inode":
        return by_inode
    if order == "physical":
        offsets = {row[0]: physical_offset(Path(root) / row[0]) for row in by_inode}
        return sorted(by_inode, key=lambda row: (offsets[row[0]], inodes[row[0]]))
    raise ValueError(f"Unknown order {order!r}")


def read_verified(root, relative, expected_sha, size, *, evict=False):
    """Read one object fully and prove it matches the manifest."""
    fd = os.open(Path(root) / relative, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_size != size:
            raise ValueError(f"Source size mismatch: {relative}")
        if evict:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        chunks = []
        remaining = size
        while remaining:
            chunk = os.read(fd, min(remaining, 8 * 1024**2))
            if not chunk:
                raise ValueError(f"Source truncated while reading: {relative}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise ValueError(f"Source grew while reading: {relative}")
        if evict:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)
    body = b"".join(chunks)
    if hashlib.sha256(body).hexdigest() != expected_sha:
        raise ValueError(f"Source digest mismatch: {relative}")
    return body


def url_order(manifest_path):
    """Object paths in the order of their first manifest URL (section order)."""
    uri = Path(manifest_path).resolve().as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        return [
            row[0] for row in db.execute("SELECT path FROM files GROUP BY path ORDER BY min(url)")
        ]


def benchmark(certificate, manifest, output, *, window=2000, orders=ORDERS, seed=20261103):
    """Read disjoint fresh windows in each order and record throughput."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Benchmark output must be new: {output}")
    binding = load_binding(certificate, manifest)
    root = binding["source_root"]
    rows = manifest_objects(manifest)
    started = time.monotonic()
    inodes = inode_numbers(root, rows)
    scan_seconds = time.monotonic() - started
    by_path = sorted(rows)
    by_inode = sorted(rows, key=lambda row: (inodes[row[0]], row[0]))
    rng = random.Random(seed)
    slots = rng.sample(range(len(rows) // window), len(orders))
    results = []
    for order, slot in zip(orders, slots):
        if order == "url":
            by_row = {row[0]: row for row in rows}
            source = [by_row[path] for path in url_order(manifest)]
        else:
            source = by_path if order == "path" else by_inode
        chosen = source[slot * window : (slot + 1) * window]
        prepare = 0.0
        if order == "physical":
            began = time.monotonic()
            chosen = order_rows(root, chosen, "physical", inodes)
            prepare = time.monotonic() - began
        began = time.monotonic()
        total = 0
        for relative, expected_sha, size in chosen:
            read_verified(root, relative, expected_sha, size, evict=True)
            total += size
        seconds = time.monotonic() - began
        rate = total / seconds if seconds else None
        results.append(
            {
                "order": order,
                "window_start": slot * window,
                "objects": len(chosen),
                "bytes": total,
                "prepare_seconds": round(prepare, 3),
                "read_seconds": round(seconds, 3),
                "mb_per_second": round(rate / 1e6, 2) if rate else None,
                "objects_per_second": round(len(chosen) / seconds, 1) if seconds else None,
                "projected_full_read_hours": (
                    round(
                        (binding["certified_bytes"] / rate + prepare * len(rows) / window) / 3600, 2
                    )
                    if rate
                    else None
                ),
            }
        )
        print(json.dumps(results[-1], sort_keys=True), flush=True)
    report = {
        "version": VERSION + "-benchmark",
        "binding": binding,
        "objects_total": len(rows),
        "directory_scan_seconds": round(scan_seconds, 3),
        "seed": seed,
        "results": results,
        "limits": (
            "Each order reads a different window so no window is warm from another; data "
            "pages are evicted with POSIX_FADV_DONTNEED before reading, but inode and "
            "directory caches cannot be cleared without privileges. Windows differ in "
            "object sizes and placement, so treat differences under about 2x as noise."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic(output, report)
    return report


def _free_bytes(path):
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def _ledger(destination):
    db = sqlite3.connect(destination / "staging-ledger.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS binding(value TEXT NOT NULL)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS staged("
        "path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL)"
    )
    return db


def stage(certificate, manifest, destination, *, order="inode", floor_gib=100, resume=False):
    """Copy every certified object to a new root, verifying both sides."""
    destination = Path(destination).expanduser().absolute()
    binding = load_binding(certificate, manifest)
    binding["order"] = order
    if destination.exists() and not resume:
        raise FileExistsError(f"Destination must be new (or pass --resume): {destination}")
    if resume and not (destination / "staging-ledger.sqlite").exists():
        raise FileNotFoundError("Nothing to resume at this destination")
    source = Path(binding["source_root"])
    if source.resolve() == destination.resolve() or destination.is_relative_to(source):
        raise ValueError("Destination must be outside the certified source root")
    rows = manifest_objects(manifest)
    if (
        len(rows) != binding["certified_objects"]
        or sum(r[2] for r in rows) != binding["certified_bytes"]
    ):
        raise ValueError("Manifest rows do not reconcile with the certificate")
    destination.mkdir(parents=True, exist_ok=resume)
    lock = (destination / "staging.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = _ledger(destination)
    encoded = json.dumps(binding, sort_keys=True)
    previous = db.execute("SELECT value FROM binding").fetchone()
    if previous and previous[0] != encoded:
        db.close()
        lock.close()
        raise ValueError("Resume binding differs from the original staging run")
    if not previous:
        db.execute("INSERT INTO binding VALUES(?)", (encoded,))
        db.commit()
    started_unix = time.time()
    status_path = destination / "staging-status.json"

    def report(stage_name, **extra) -> None:
        atomic(
            status_path,
            {
                "stage": stage_name,
                "pid": os.getpid(),
                "started_unix": started_unix,
                "updated_unix": time.time(),
                **extra,
            },
        )

    try:
        # The frozen manifest travels with the staged root so it is self-contained.
        staged_manifest = destination / "manifest.sqlite"
        if not staged_manifest.exists() or sha(staged_manifest) != binding["manifest_sha256"]:
            temporary = destination / "manifest.sqlite.part"
            shutil.copyfile(binding["manifest"], temporary)
            os.chmod(temporary, 0o444)
            os.replace(temporary, staged_manifest)
            os.sync()
            if sha(staged_manifest) != binding["manifest_sha256"]:
                raise ValueError("Staged manifest digest mismatch")
        for stale in destination.glob("objects/*/*.part"):
            stale.unlink()
        done = dict(
            (path, (digest, size))
            for path, digest, size in db.execute("SELECT path,sha256,bytes FROM staged")
        )
        remaining_bytes = sum(size for path, _, size in rows if path not in done)
        floor = floor_gib * 1024**3
        if _free_bytes(destination) - remaining_bytes < floor:
            raise RuntimeError("Not enough free space above the destination floor")
        report("ordering", order=order)
        ordered = [row for row in order_rows(source, rows, order) if row[0] not in done]
        copied_objects = len(done)
        copied_bytes = sum(size for _, size in done.values())
        batch = []
        batch_bytes = 0
        began = time.monotonic()
        session_bytes = 0

        def flush() -> None:
            nonlocal batch, batch_bytes
            if not batch:
                return
            os.sync()
            db.executemany("INSERT INTO staged VALUES(?,?,?)", batch)
            db.commit()
            batch = []
            batch_bytes = 0
            if _free_bytes(destination) < floor:
                raise RuntimeError("Destination free-space floor breached")
            elapsed = time.monotonic() - began
            rate = session_bytes / elapsed if elapsed else 0
            left = binding["certified_bytes"] - copied_bytes
            report(
                "copying",
                objects=copied_objects,
                bytes=copied_bytes,
                total_objects=len(rows),
                total_bytes=binding["certified_bytes"],
                session_mb_per_second=round(rate / 1e6, 2),
                eta_hours=round(left / rate / 3600, 2) if rate else None,
            )

        for relative, expected_sha, size in ordered:
            body = read_verified(source, relative, expected_sha, size)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            with temporary.open("wb") as stream:
                stream.write(body)
            os.chmod(temporary, 0o444)
            os.replace(temporary, target)
            batch.append((relative, expected_sha, size))
            batch_bytes += size
            copied_objects += 1
            copied_bytes += size
            session_bytes += size
            if len(batch) >= BATCH_OBJECTS or batch_bytes >= BATCH_BYTES:
                flush()
        flush()
        copy_seconds = time.monotonic() - began
        report("verifying_destination", objects=copied_objects, bytes=copied_bytes)
        verified = verify_destination(destination, rows)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        certificate_body = {
            "version": VERSION,
            **binding,
            "destination": str(destination),
            "objects": verified["objects"],
            "bytes": verified["bytes"],
            "copy_seconds_last_session": round(copy_seconds, 1),
            "verify_seconds": verified["seconds"],
            "ledger_sha256": sha(destination / "staging-ledger.sqlite"),
            "verification": (
                "source sha256 on read; destination sha256 after os.sync; "
                "no missing or extra objects"
            ),
            "semantic_inspection": False,
        }
        atomic(destination / "staging-certificate.json", certificate_body)
        report("finished", objects=verified["objects"], bytes=verified["bytes"])
        return certificate_body
    except BaseException as exc:
        report("FAILED_STOPPED", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        db.close()
        lock.close()


def verify_destination(destination, rows):
    """Hash every staged object and prove the object tree has nothing extra."""
    destination = Path(destination)
    began = time.monotonic()
    total = 0
    for relative, expected_sha, size in rows:
        path = destination / relative
        if path.is_symlink() or path.stat().st_size != size:
            raise ValueError(f"Staged object missing or wrong size: {relative}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b""):
                digest.update(block)
        if digest.hexdigest() != expected_sha:
            raise ValueError(f"Staged object digest mismatch: {relative}")
        total += size
    expected = {row[0] for row in rows}
    extra = [
        str(p.relative_to(destination))
        for p in (destination / "objects").glob("*/*")
        if str(p.relative_to(destination)) not in expected
    ]
    if extra:
        raise ValueError(f"{len(extra)} unexpected staged files, e.g. {extra[0]}")
    return {"objects": len(rows), "bytes": total, "seconds": round(time.monotonic() - began, 1)}


def stage_sources_main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit stage-sources",
        description="Benchmark read orders or stage certified raw objects onto a new root.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bench = commands.add_parser("benchmark", help="Compare read orders on fresh windows.")
    copy = commands.add_parser("copy", help="Copy and verify every certified object.")
    for sub in (bench, copy):
        sub.add_argument("--certificate", required=True, help="Relocation certificate JSON.")
        sub.add_argument("--manifest", required=True, help="Certified frozen manifest copy.")
    bench.add_argument("--output", required=True, help="New results JSON path.")
    bench.add_argument("--window", type=int, default=2000, help="Objects per order.")
    bench.add_argument("--orders", nargs="+", choices=BENCHMARK_ORDERS, default=list(ORDERS))
    bench.add_argument("--seed", type=int, default=20261103, help="Window draw seed.")
    copy.add_argument("--destination", required=True, help="New staged root directory.")
    copy.add_argument("--order", choices=ORDERS, default="inode", help="Source read order.")
    copy.add_argument("--floor-gib", type=int, default=100, help="Destination free-space floor.")
    copy.add_argument("--resume", action="store_true", help="Resume the same staging run.")
    args = parser.parse_args(argv)
    if args.command == "benchmark":
        benchmark(
            args.certificate,
            args.manifest,
            args.output,
            window=args.window,
            orders=args.orders,
            seed=args.seed,
        )
    else:
        result = stage(
            args.certificate,
            args.manifest,
            args.destination,
            order=args.order,
            floor_gib=args.floor_gib,
            resume=args.resume,
        )
        print(json.dumps({k: result[k] for k in ("destination", "objects", "bytes")}))
    return 0
