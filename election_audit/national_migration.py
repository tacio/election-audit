"""Fail-closed overnight copy acceptance; hashes destinations without decoding bodies.

This module deliberately uses only the standard library so its frozen first stage
can wait for a transfer while the separately pinned continuation is being reviewed.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import time
from collections.abc import Callable, Collection, Iterable, Iterator
from pathlib import Path
from typing import Any

type Stat = tuple[int, int, int, int, int]
type Report = Callable[..., None]


HDD_RESERVE_BYTES = 20 * 1024**3  # free space kept on the copy's volume


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path: str | Path, value: Any) -> None:
    path = Path(path)
    body = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    temporary = path.with_name(path.name + ".new")
    with temporary.open("wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def process(pid: int | str) -> dict[str, Any] | None:
    try:
        root = Path("/proc") / str(pid)
        fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
        argv = (root / "cmdline").read_bytes().split(b"\0")
        return {
            "pid": int(pid),
            "start": int(fields[19]),
            "state": fields[0],
            "argv": [x.decode(errors="replace") for x in argv if x],
            "exit_status": int(fields[49]) if len(fields) > 49 and fields[0] == "Z" else None,
        }
    except FileNotFoundError, ProcessLookupError:
        return None


def processes() -> Iterator[dict[str, Any]]:
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            try:
                value = process(path.name)
            except PermissionError:
                continue
            if value:
                yield value


def transfer_alive(expected: dict[str, Any], current: dict[str, Any] | None) -> bool:
    return bool(current and current["start"] == expected["start"] and current["state"] != "Z")


def writers(roots: Iterable[str | Path], *, allowed: Collection[int] = ()) -> None:
    """Detect other transfer processes and writable file descriptors in these roots."""
    roots = [str(Path(p)).rstrip("/") for p in roots]
    for proc in processes():
        if proc["pid"] == os.getpid() or proc["pid"] in allowed or proc["state"] == "Z":
            continue
        argv = proc["argv"]
        if argv and Path(argv[0]).name == "rsync" and any(a.rstrip("/") in roots for a in argv[1:]):
            raise RuntimeError(f"Unexpected transfer PID {proc['pid']}")
        # Match the frozen source root, not unrelated temporary/test launchers.
        # Reading this small workload declaration performs no raw-body access.
        launchers = [Path(a) for a in argv if Path(a).name == "run_frozen.py"]
        if launchers and "run" in argv:
            for launcher in launchers:
                try:
                    source_root = json.loads((launcher.parent / "workload.json").read_bytes())[
                        "source"
                    ]["root"]
                except (OSError, KeyError, ValueError) as exc:
                    raise RuntimeError(
                        f"Unidentifiable structural worker PID {proc['pid']}"
                    ) from exc
                if os.path.abspath(source_root).rstrip("/") in roots:
                    raise RuntimeError(f"Existing structural worker PID {proc['pid']}")
        directory = Path("/proc") / str(proc["pid"])
        try:
            for fd in (directory / "fd").iterdir():
                try:
                    name = os.readlink(fd)
                    if not any(name == r or name.startswith(r + "/") for r in roots):
                        continue
                    flags = (
                        (directory / "fdinfo" / fd.name)
                        .read_text()
                        .split("flags:\t", 1)[1]
                        .splitlines()[0]
                    )
                    if int(flags, 8) & os.O_ACCMODE:
                        raise RuntimeError(
                            f"Writable destination descriptor PID {proc['pid']}: {name}"
                        )
                except FileNotFoundError, ProcessLookupError:
                    continue
        except FileNotFoundError, ProcessLookupError:
            continue
        except PermissionError as exc:
            # Linux ptrace restrictions can hide unrelated same-user descriptors.
            # Fail closed for a command naming these destinations; disclose that
            # inaccessible unrelated commands are not a proof against hostile writers.
            try:
                owner = directory.stat().st_uid
            except FileNotFoundError:
                continue
            if owner == os.getuid() and any(any(r in a for r in roots) for a in argv):
                raise RuntimeError("Cannot inspect same-user destination writers") from exc


def wait_transfers(plan: dict[str, Any], report: Report) -> dict[str, dict[str, int | None]]:
    expected = plan["transfers"]
    outcomes: dict[str, dict[str, int | None]] = {}
    roots = [r[k] for r in plan["rounds"] for k in ("new_root", "old_root")]
    while True:
        alive = []
        for item in expected:
            current = process(item["pid"])
            if current and current["start"] == item["start"]:
                if current["state"] != "Z" and current["argv"] != item["argv"]:
                    raise RuntimeError("Tracked transfer command changed")
                if current["exit_status"] is not None:
                    code = os.waitstatus_to_exitcode(current["exit_status"])
                    outcomes[str(item["pid"])] = {"observed_exit_code": code}
                    if code:
                        raise RuntimeError(f"Tracked rsync exited {code}")
            if transfer_alive(item, current):
                alive.append(item["pid"])
            else:
                outcomes.setdefault(str(item["pid"]), {"observed_exit_code": None})
        writers(roots, allowed=alive)
        report("waiting_for_rsync", {"alive": alive, "transfer_outcomes": outcomes})
        if not alive:
            time.sleep(plan.get("quiescence_seconds", 10))
            writers(roots)
            return outcomes
        time.sleep(plan.get("poll_seconds", 20))


def relative_object(relative: str | Path, expected_sha: str) -> Path:
    p = Path(relative)
    if (
        p.is_absolute()
        or len(p.parts) != 3
        or p.parts[:2] != ("objects", expected_sha[:2])
        or p.name not in (expected_sha + ".dat", expected_sha + ".jez", expected_sha + ".json")
        or len(expected_sha) != 64
        or any(c not in "0123456789abcdef" for c in expected_sha)
    ):
        raise ValueError("Unsafe or inconsistent manifest object path")
    return p


def file_stat(root: str | Path, relative: str | Path) -> Stat:
    target = Path(root)
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("Symlink in copied source root")
    for part in (".", *Path(relative).parts):
        target = target / part
        if target.is_symlink():
            raise ValueError(f"Symlink in copied object path: {target}")
    value = target.stat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError("Copied object is not a regular file")
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def verify_file(root: str | Path, relative: str | Path, expected_sha: str, size: int) -> Stat:
    relative_object(relative, expected_sha)
    before = file_stat(root, relative)
    if before[2] != size:
        raise ValueError(f"Copied object size mismatch: {relative}")
    fd = os.open(Path(root) / relative, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        value = os.fstat(fd)
        if (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        ) != before:
            raise ValueError("Copied object changed before hashing")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024**2), b""):
                digest.update(block)
        if digest.hexdigest() != expected_sha or file_stat(root, relative) != before:
            raise ValueError(f"Copied object digest/stability mismatch: {relative}")
    finally:
        os.close(fd)
    return before


def manifest_identity(db: sqlite3.Connection, pleito: str | int) -> dict[str, Any]:
    run = db.execute(
        "SELECT id,started_at,finished_at,status FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not run or run[3] != "finished" or not run[2]:
        raise ValueError("Source acquisition is not finished")
    prefix = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/"
    expected = prefix + str(pleito) + "/"
    if db.execute(
        "SELECT url FROM files WHERE url>=? AND url<? AND NOT(url>=? AND url<?) LIMIT 1",
        (prefix, prefix + "\uffff", expected, expected + "\uffff"),
    ).fetchone():
        raise ValueError("Manifest contains another election round")
    digest = hashlib.sha256()
    count = 0
    for row in db.execute("SELECT url,path,sha256,bytes FROM files ORDER BY url"):
        digest.update((json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n").encode())
        count += 1
    return {
        "run": list(run),
        "file_rows": count,
        "rows_sha256": digest.hexdigest(),
        "section_status_counts": dict(
            db.execute(
                "SELECT status,count(*) FROM sections WHERE run=? GROUP BY status", (run[0],)
            )
        ),
        "package_status_counts": dict(
            db.execute(
                "SELECT package_status,count(*) FROM logs WHERE run=? GROUP BY package_status",
                (run[0],),
            )
        ),
        "national_coverage_complete": False,
    }


def verify_round(
    item: dict[str, Any], state: str | Path, report: Report, guard: Callable[[], None]
) -> dict[str, Any]:
    state = Path(state)
    snapshot = state / f"manifest-r{item['round']}.sqlite"
    source = Path(item["manifest"])
    if not snapshot.exists():
        tmp = snapshot.with_suffix(".new")
        with (
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as live,
            sqlite3.connect(tmp) as frozen,
        ):
            live.backup(frozen)
        os.replace(tmp, snapshot)
    with sqlite3.connect(snapshot) as frozen:
        identity = manifest_identity(frozen, item["pleito"])
        snapshot_sha = sha(snapshot)
        root = Path(item["new_root"])
        root_stat = root.stat()
        binding = {
            "manifest_sha256": snapshot_sha,
            "identity": identity,
            "root": str(root),
            "root_identity": [root_stat.st_dev, root_stat.st_ino],
            "mount": item["mount"],
        }
        ledger = state / f"verification-r{item['round']}.sqlite"
        with sqlite3.connect(ledger) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA cache_size=-16384")
            db.execute("CREATE TABLE IF NOT EXISTS binding(value TEXT)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS verified(path TEXT PRIMARY KEY,sha TEXT,size INTEGER,dev INTEGER,ino INTEGER,mtime INTEGER,ctime INTEGER)"
            )
            encoded = json.dumps(binding, sort_keys=True)
            previous = db.execute("SELECT value FROM binding").fetchone()
            if previous and previous[0] != encoded:
                raise ValueError("Verification resume binding changed")
            if not previous:
                db.execute("INSERT INTO binding VALUES(?)", (encoded,))
                db.commit()
            if frozen.execute(
                "SELECT path FROM files GROUP BY path HAVING count(DISTINCT sha256)>1 OR count(DISTINCT bytes)>1 LIMIT 1"
            ).fetchone():
                raise ValueError("Conflicting manifest path aliases")
            done = byte_count = pending = 0
            started = time.monotonic()
            for relative, expected_sha, size in frozen.execute(
                "SELECT path,min(sha256),min(bytes) FROM files GROUP BY path ORDER BY path"
            ):
                relative_object(relative, expected_sha)
                old = db.execute(
                    "SELECT sha,size,dev,ino,mtime,ctime FROM verified WHERE path=?", (relative,)
                ).fetchone()
                if old:
                    if old[:2] != (expected_sha, size) or file_stat(root, relative) != (
                        old[2],
                        old[3],
                        size,
                        old[4],
                        old[5],
                    ):
                        raise ValueError(f"Previously verified copy changed: {relative}")
                else:
                    value = verify_file(root, relative, expected_sha, size)
                    db.execute(
                        "INSERT INTO verified VALUES(?,?,?,?,?,?,?)",
                        (relative, expected_sha, size, value[0], value[1], value[3], value[4]),
                    )
                    pending += 1
                done += 1
                byte_count += size
                if done % 512 == 0:
                    db.commit()
                    pending = 0
                    guard()
                    report(
                        "verifying_copied_sources",
                        {
                            "round": item["round"],
                            "objects": done,
                            "bytes": byte_count,
                            "elapsed_seconds": time.monotonic() - started,
                        },
                    )
            if pending:
                db.commit()
            # A second stat-only pass catches mutation after any committed group.
            guard()
            for relative, size, dev, ino, mtime, ctime in db.execute(
                "SELECT path,size,dev,ino,mtime,ctime FROM verified ORDER BY path"
            ):
                if file_stat(root, relative) != (dev, ino, size, mtime, ctime):
                    raise ValueError(f"Verified destination mutated: {relative}")
            with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as live:
                if manifest_identity(live, item["pleito"]) != identity:
                    raise ValueError("Finished acquisition manifest changed during acceptance")
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        certificate = {
            **binding,
            "round": item["round"],
            "old_root": item["old_root"],
            "ledger": str(ledger),
            "ledger_sha256": sha(ledger),
            "objects": done,
            "bytes": byte_count,
            "verification": "destination-only-sha256-and-second-stat-pass",
            "semantic_inspection": False,
        }
        atomic(state / f"certificate-r{item['round']}.json", certificate)
        return certificate


def execute(plan_path: str | Path) -> None:
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    state = Path(plan["state"])
    state.mkdir(parents=True, exist_ok=True)
    lock = (state / "migration.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    started = time.time()

    def report(stage: str, extra: dict[str, Any] | None = None) -> None:
        value = {
            "stage": stage,
            "pid": os.getpid(),
            "started_unix": started,
            "updated_unix": time.time(),
            "plan_sha256": sha(plan_path),
            **(extra or {}),
        }
        atomic(state / "status.json", value)
        print(json.dumps(value, sort_keys=True), flush=True)

    try:
        outcomes = wait_transfers(plan, report)
        roots = [x[k] for x in plan["rounds"] for k in ("new_root", "old_root")]

        def guard() -> None:
            writers(roots)
            for item in plan["rounds"]:
                anchor = Path(item["mount"])
                if not anchor.is_mount() or (
                    Path(item["new_root"]).stat().st_dev != anchor.stat().st_dev
                ):
                    raise RuntimeError("Copied source mount changed")
                if os.statvfs(anchor).f_bavail * os.statvfs(anchor).f_frsize < HDD_RESERVE_BYTES:
                    raise RuntimeError("HDD reserve breached")

        guard()
        certificates = [verify_round(item, state, report, guard) for item in plan["rounds"]]
        registry = {
            "version": "verified-source-relocation-v1",
            "certificates": certificates,
            "transfer_outcomes": outcomes,
            "writer_guard": "exact transfer argv plus accessible writable descriptors; unrelated ptrace-hidden descriptors cannot be inspected; assumes cooperative exclusive custody",
            "nonchild_exit_status_limitation": "Unknown exit status is not claimed successful; complete destination hashes are authoritative.",
        }
        atomic(state / "relocation.json", registry)
        report("copies_verified_waiting_for_pinned_continuation")
        gate = Path(plan["ready_gate"])
        deadline = time.monotonic() + plan.get("ready_timeout_seconds", 21600)
        while not gate.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Reviewed continuation gate was not published")
            time.sleep(10)
        ready = json.loads(gate.read_text())
        for name, expected in ready["files"].items():
            if Path(name).is_symlink() or sha(name) != expected:
                raise RuntimeError("Continuation code/config pin mismatch")
        guard()
        report("running_pinned_continuation", {"gate_sha256": sha(gate)})
        result = subprocess.run(ready["command"], check=False)
        if result.returncode:
            raise RuntimeError(f"Continuation failed with exit code {result.returncode}")
        report("continuation_finished", {"gate_sha256": sha(gate)})
    except BaseException as exc:
        report("FAILED_STOPPED", {"error": f"{type(exc).__name__}: {exc}"})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    execute(parser.parse_args().plan)
