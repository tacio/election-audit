"""Streaming summary/witness readers, protected replay, and bounded job launching."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from election_audit.national_migration import atomic, sha
from election_audit.national_parallel import FORMAT, checked, encoded, load
from election_audit.national_resources import cgroup_command
from election_audit.national_summary import replay_lines
from election_audit.types import JSON, Row


def verify_shard(path: Path, job_id: str) -> JSON:
    path = Path(path)
    doc = json.loads((path / "shard.json").read_text())
    expected = hashlib.sha256(encoded([job_id, sorted(doc["objects"])]).encode()).hexdigest()
    marker_digest = hashlib.sha256(
        encoded({k: v for k, v in doc.items() if k != "marker_sha256"}).encode()
    ).hexdigest()
    if (
        doc["version"] != FORMAT
        or marker_digest != doc.get("marker_sha256")
        or doc["job_id"] != job_id
        or path.name != expected
        or sha(path / "summary.sqlite") != doc["database_sha256"]
    ):
        raise ValueError("Published summary shard checksum/identity mismatch")
    return doc


def iter_table(directory: str | Path, table: str = "objects") -> Iterator[Row]:
    """Checksum once per shard, then yield bounded typed rows, never all events."""
    if table not in ("objects", "members", "blocks", "anchors", "errors"):
        raise ValueError("Unknown summary relation")
    spec = load(directory)
    ledger = Path(spec["store"]) / "work.sqlite"
    with closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as work:
        for (group,) in work.execute("SELECT id FROM groups ORDER BY id"):
            path = Path(spec["store"]) / "shards" / group[:2] / group
            marker = verify_shard(path, spec["job_id"])
            with closing(
                sqlite3.connect(
                    (path / "summary.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
                )
            ) as db:
                db.row_factory = sqlite3.Row
                actual = [r[0] for r in db.execute("SELECT sha FROM objects ORDER BY sha")]
                if actual != marker["objects"]:
                    raise ValueError("Shard source population mismatch")
                orders = {
                    "members": "t.member",
                    "blocks": "t.member,t.first_line",
                    "anchors": "t.member,t.line",
                    "errors": "t.ordinal",
                }
                query = (
                    "SELECT sha,payload FROM objects ORDER BY sha"
                    if table == "objects"
                    else "SELECT o.sha,t.* FROM "
                    + table
                    + " t JOIN objects o USING(object_id) ORDER BY o.sha,"
                    + orders[table]
                )
                for row in db.execute(query):
                    value = dict(row)
                    value.pop("object_id", None)
                    for name in ("line_sha", "digest"):
                        if isinstance(value.get(name), bytes):
                            value[name] = value[name].hex()
                    yield value


def iter_source_observations(directory: str | Path) -> Iterator[Row]:
    """Every witness survives, including protected, pending and failed unknowns."""
    spec = load(directory)
    if sha(spec["scope"]) != spec["scope_sha256"]:
        raise ValueError("Frozen source-witness scope changed")
    with closing(sqlite3.connect(Path(spec["scope"]).as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "ATTACH DATABASE ? AS work",
            ((Path(spec["store"]) / "work.sqlite").as_uri() + "?mode=ro",),
        )
        for row in db.execute(
            "SELECT s.*,w.status AS object_work_status,w.shard AS summary_shard FROM observations s LEFT JOIN work.work w ON w.sha=s.sha256 ORDER BY s.url"
        ):
            value = dict(row)
            if value["processing_scope"] != "eligible_structural_preprocessing":
                value.update(object_work_status="deferred_protected_or_stress", summary_shard=None)
            value.update(
                scientific_eligibility="unavailable_structural_only",
                population_rule="deduplicate content before joining publisher witnesses; no count multiplication",
            )
            yield value


def replay(
    directory: str | Path,
    object_sha: str,
    member: int,
    start: int,
    stop: int,
    development_sample: str | Path,
) -> Iterator[JSON]:
    spec = load(directory)
    if sha(spec["scope"]) != spec["scope_sha256"]:
        raise ValueError("Frozen scope changed")
    with closing(sqlite3.connect(Path(spec["scope"]).as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM observations WHERE sha256=? AND processing_scope='eligible_structural_preprocessing' LIMIT 1",
            (object_sha,),
        ).fetchone()
        if row is None:
            raise ValueError("Protected/unregistered source replay prevented before body access")
        row = {**dict(row), "source_root": spec["source_root"]}
    sample = checked(Path(development_sample) / "sample.json")
    inspection = checked(Path(development_sample) / "inspection.json")
    if (
        inspection["state"] != "development_inspected"
        or inspection["sample_id"] != sample["sample_id"]
        or not any(u["sha256"] == object_sha for u in sample["units"])
    ):
        raise ValueError("Replay requires existing approved development-inspection membership")
    yield from replay_lines(row, spec["scratch"], member, start, stop)


def launch(
    directory: str | Path,
    *,
    unit: str = "election-audit-summary",
    use_cgroup: bool = True,
    max_objects: int | None = None,
    analysis_output: str | Path | None = None,
) -> JSON:
    directory = Path(directory).absolute()
    spec = load(directory)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", unit):
        raise ValueError("Unsafe user service name")
    command = [sys.executable, "-B", "-u", str(directory / "run_frozen.py"), "run"]
    if max_objects is not None:
        command.extend(["--max-objects", str(max_objects)])
    if analysis_output is not None:
        command.extend(["--analysis-output", str(Path(analysis_output).absolute())])
    log = directory / "run.log"
    r = spec["resources"]
    manager = (
        subprocess.run(
            ["systemctl", "--user", "show-environment"], capture_output=True, check=False
        )
        if shutil.which("systemctl") and shutil.which("systemd-run")
        else subprocess.CompletedProcess([], 127)
    )
    if use_cgroup and manager.returncode == 0:
        slice_name = "election-audit-phase11.slice"
        subprocess.run(
            [
                "systemctl",
                "--user",
                "set-property",
                "--runtime",
                slice_name,
                "CPUQuota=" + str(r["cpu"]["cpu_quota_percent"]) + "%",
                "MemoryMax=" + str(r["aggregate_memory_bytes"]),
                "MemorySwapMax=0",
            ],
            check=True,
            capture_output=True,
        )
        invocation = cgroup_command(command, r, unit=unit)
        invocation[2:2] = [
            "--slice=" + slice_name,
            "--property=StandardOutput=append:" + str(log),
            "--property=StandardError=inherit",
        ]
        subprocess.run(invocation, check=True, capture_output=True)
        pid = int(
            subprocess.check_output(
                ["systemctl", "--user", "show", unit + ".service", "--property=MainPID", "--value"],
                text=True,
            ).strip()
        )
        enforcement = {
            "mode": "shared-user-cgroup-and-affinity",
            "slice": slice_name,
            "unit": unit + ".service",
            "cpu_quota_percent": r["cpu"]["cpu_quota_percent"],
            "memory_max_bytes": r["aggregate_memory_bytes"],
        }
    else:
        with log.open("ab", buffering=0) as stream:
            child = subprocess.Popen(
                command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
        pid = child.pid
        enforcement = {
            "mode": "affinity-AS-RSS-fallback",
            "reason": "explicit opt-out" if not use_cgroup else "user service manager unavailable",
            "limitation": "no kernel aggregate RSS cgroup guarantee; conservative summed AS envelope and live RSS guard remain active",
        }
    proc = Path("/proc") / str(pid)
    if not pid or not proc.exists():
        raise RuntimeError("Launched job exited during startup; inspect run.log")
    record = {
        "pid": pid,
        "start_ticks": (proc / "stat").read_text().rsplit(")", 1)[1].split()[19],
        "job_id": spec["job_id"],
        "config": str(directory),
        "log": str(log),
        "progress": str(directory / "progress.json"),
        "enforcement": enforcement,
        "started_unix": time.time(),
        "analysis_output": str(Path(analysis_output).absolute()) if analysis_output else None,
    }
    atomic(directory / "current-launch.json", record)
    return record
