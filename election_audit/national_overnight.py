"""Pinned continuation after destination acceptance: relocate, validate, tune, resume.

Only the completed runoff's previously frozen eligible structural scope is run.
The first round is registered for custody, never semantically processed here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from election_audit import national_tuning as tuning
from election_audit import national_workload as workload
from election_audit.national import _read_json, _verify_files, _write_json
from election_audit.national_migration import atomic, sha, writers
from election_audit.national_relocation import configure
from election_audit.national_storage import iter_compact, resolve_original
from election_audit.source_inventory import hash_file
from election_audit.types import JSON


def checked_copy(source: str | Path, destination: str | Path) -> Path:
    """Copy a checkpoint without symlinks; accept only complete hash-equal bytes."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or any(p.is_symlink() for p in source.parents):
        raise ValueError("Checkpoint source symlink")
    if destination.exists():
        _verify_files(destination, _read_json(destination / "checkpoint.json"))
        if hash_file(source / "checkpoint.json") != hash_file(destination / "checkpoint.json"):
            raise ValueError("Existing copied checkpoint has different provenance")
        return destination
    temporary = destination.with_name(".migration-" + destination.name)
    if temporary.exists():
        # Never remove a previous unpublished copy: explicit restart diagnosis.
        raise ValueError(f"Unpublished checkpoint copy needs review: {temporary}")
    temporary.mkdir(parents=True)
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in [*dirs, *files]:
            if (Path(directory) / name).is_symlink():
                raise ValueError("Checkpoint tree contains a symlink")
        target = temporary / Path(directory).relative_to(source)
        target.mkdir(exist_ok=True)
        for name in files:
            original, copied = Path(directory) / name, target / name
            before = original.stat()
            shutil.copyfile(original, copied)
            with copied.open("rb") as stream:
                os.fsync(stream.fileno())
            after = original.stat()
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) or hash_file(original) != hash_file(copied):
                raise ValueError("Checkpoint changed while copying")
        fd = os.open(target, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    _verify_files(temporary, _read_json(temporary / "checkpoint.json"))
    os.rename(temporary, destination)
    fd = os.open(destination.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return destination


def verify_checkpoint(path: Path, row: JSON) -> JSON:
    doc = _read_json(Path(path) / "checkpoint.json")
    if doc["object_sha256"] != row["sha256"]:
        raise ValueError("Checkpoint content does not match eligible scope")
    _verify_files(Path(path), doc)
    reference = doc["original_reference"]
    if (reference["object_sha256"], reference["bytes"], reference["relative_path"]) != (
        row["sha256"],
        row["bytes"],
        row["path"],
    ):
        raise ValueError("Checkpoint source reference does not match frozen source metadata")
    resolve_original(reference)  # strict registry: old roots cannot be opened
    if sum(1 for _ in iter_compact(Path(path) / "events")) != doc["counts"]["events"]:
        raise ValueError("Checkpoint logical event count mismatch")
    return doc


def execute(config_path: str | Path) -> None:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    # Trial subprocesses use -m: bind their import search/cwd to this reviewed
    # frozen closure, rather than whatever mutable checkout launched the waiter.
    runtime = Path(__file__).resolve().parent.parent
    os.environ["PYTHONPATH"] = str(runtime)
    os.chdir(runtime)
    workspace = Path(config["workspace"])
    state = Path(config["migration_state"])
    registry_path = state / "relocation.json"
    registry_sha = sha(registry_path)
    registry = json.loads(registry_path.read_text())
    plan = json.loads(Path(config["migration_plan"]).read_text())
    for item in plan["rounds"]:
        certificate = next(c for c in registry["certificates"] if c["round"] == item["round"])
        if (certificate["root"], certificate["old_root"], certificate["mount"]) != (
            item["new_root"],
            item["old_root"],
            item["mount"],
        ):
            raise ValueError("Accepted relocation differs from frozen migration plan")
    configure(registry_path, registry_sha)
    anchor = Path(config["anchor"])
    budget = 256 * 1024**3
    workspace.mkdir(parents=True, exist_ok=True)

    def report(stage: str, **extra: Any) -> None:
        value = {
            "stage": stage,
            "pid": os.getpid(),
            "updated_unix": time.time(),
            "registry_sha256": registry_sha,
            "config_sha256": sha(config_path),
            **extra,
        }
        atomic(workspace / "continuation-status.json", value)
        print(json.dumps(value, sort_keys=True), flush=True)

    def capacity() -> None:
        if (
            not anchor.is_mount()
            or Path(config["cache_store"]).parent.stat().st_dev != anchor.stat().st_dev
        ):
            raise OSError("Declared destination mount unavailable")
        if shutil.disk_usage(anchor).free < 2 * budget + 20 * 1024**3:
            raise OSError(
                "Insufficient destination headroom for output, future allowance and reserve"
            )
        if shutil.disk_usage(config["scratch"]).free < 18 * 1024**3:
            raise OSError("Insufficient SSD reserve plus spill allowance")

    try:
        writers([i[k] for i in plan["rounds"] for k in ("new_root", "old_root")])
        capacity()
        report("relocation_registered", first_round_processing=False)
        old_spec = _read_json(Path(config["old_workload"]) / "workload.json")
        profile_path = Path(old_spec["profile"])
        profile_doc = _read_json(profile_path / "profile.json")
        if hash_file(profile_path / "profile.sqlite") != (
            old_spec["profile_sqlite"]["sha256"],
            old_spec["profile_sqlite"]["bytes"],
        ):
            raise ValueError("Frozen source metadata differs")
        if hash_file(profile_path / "profile.json")[0] != old_spec["profile_json_sha256"]:
            raise ValueError("Frozen profile declaration differs")
        old_scope = Path(old_spec["store"]) / "scope/observations.sqlite"
        old_scope_doc = _read_json(Path(old_spec["store"]) / "scope/scope.json")
        if (
            old_scope_doc["job_id"] != old_spec["job_id"]
            or old_scope_doc["exclusions_sha256"] != old_spec["exclusions_sha256"]
            or old_scope_doc["source_rows_sha256"] != old_spec["source_rows_sha256"]
        ):
            raise ValueError("Previous checkpoint scope identity differs")
        _verify_files(old_scope.parent, old_scope_doc)
        if hash_file(Path(old_spec["exclusions"]))[0] != old_spec["exclusions_sha256"]:
            raise ValueError("Protected registry changed")
        report("copying_safe_external_checkpoints")
        comparison = _read_json(Path(config["safe_comparison"]))
        cache = Path(config["cache_store"])
        mapped = {}
        with closing(sqlite3.connect(old_scope.as_uri() + "?mode=ro", uri=True)) as scope:
            scope.row_factory = sqlite3.Row
            for record in comparison["records"]:
                row = scope.execute(
                    "SELECT * FROM observations WHERE sha256=? AND processing_scope='eligible_structural_preprocessing' LIMIT 1",
                    (record["source_sha256"],),
                ).fetchone()
                if row is None:
                    raise ValueError("Safe-copy request includes protected or absent content")
                source = Path(record["artifact"])
                key = source.name
                destination = cache / "compact" / key[:2] / key
                mapped[record["source_sha256"]] = str(checked_copy(source, destination))
                if len(mapped) % 25 == 0:
                    capacity()
                    report("copying_safe_external_checkpoints", copied=len(mapped))
            tuning_comparison = _read_json(Path(config["tuning_comparison"]))
            new_comparison = {
                **tuning_comparison,
                "records": [
                    {**record, "artifact": mapped[record["source_sha256"]]}
                    for record in tuning_comparison["records"]
                    if record["source_sha256"] in mapped
                ],
                "relocation_provenance": {
                    "original_report": config["tuning_comparison"],
                    "original_report_sha256": sha(config["tuning_comparison"]),
                    "registry_sha256": registry_sha,
                },
            }
            comparison_path = workspace / "relocated-comparison.json"
            if not comparison_path.exists():
                _write_json(comparison_path, new_comparison)
            elif _read_json(comparison_path) != new_comparison:
                raise ValueError("Pinned comparison continuation differs")
            verification = sqlite3.connect(state / "checkpoints.sqlite")
            verification.execute("PRAGMA journal_mode=WAL")
            verification.execute("PRAGMA synchronous=FULL")
            verification.execute(
                "CREATE TABLE IF NOT EXISTS verified(path TEXT PRIMARY KEY,checkpoint_sha TEXT,registry_sha TEXT,events INTEGER)"
            )
            old_work = sqlite3.connect(
                Path(old_spec["store"]).as_uri() + "/work.sqlite?mode=ro", uri=True
            )
            # Build a disk-backed set of eligible checkpoint references. Every old
            # external reference is replaced by the copied safe cache before open.
            verification.execute(
                "CREATE TABLE IF NOT EXISTS candidates(sha TEXT PRIMARY KEY,path TEXT)"
            )
            for object_sha, artifact in old_work.execute(
                "SELECT sha256,artifact FROM work WHERE status='complete' ORDER BY sha256"
            ):
                target = Path(mapped.get(object_sha, artifact))
                if not target.is_relative_to(anchor):
                    raise ValueError("Unregistered old-volume checkpoint dependency")
                verification.execute(
                    "INSERT OR IGNORE INTO candidates VALUES(?,?)", (object_sha, str(target))
                )
            old_work.close()
            for object_sha, target in mapped.items():
                verification.execute(
                    "INSERT OR IGNORE INTO candidates VALUES(?,?)", (object_sha, target)
                )
            verification.commit()
            total = verification.execute("SELECT count(*) FROM candidates").fetchone()[0]
            count = events = 0
            for object_sha, target in verification.execute(
                "SELECT sha,path FROM candidates ORDER BY sha"
            ):
                capacity()
                row = scope.execute(
                    "SELECT * FROM observations WHERE sha256=? AND processing_scope='eligible_structural_preprocessing' LIMIT 1",
                    (object_sha,),
                ).fetchone()
                if row is None:
                    raise ValueError("Protected checkpoint access prevented")
                checkpoint_sha = sha(Path(target) / "checkpoint.json")
                previous = verification.execute(
                    "SELECT checkpoint_sha,registry_sha,events FROM verified WHERE path=?",
                    (target,),
                ).fetchone()
                if previous:
                    if previous[:2] != (checkpoint_sha, registry_sha):
                        raise ValueError("Verified checkpoint resume identity changed")
                    # Physical checks always repeated; full logical stream was
                    # verified under this exact checkpoint's declared file hashes.
                    doc = _read_json(Path(target) / "checkpoint.json")
                    _verify_files(Path(target), doc)
                    resolve_original(doc["original_reference"])
                    n = previous[2]
                else:
                    doc = verify_checkpoint(target, row)
                    n = doc["counts"]["events"]
                    verification.execute(
                        "INSERT INTO verified VALUES(?,?,?,?)",
                        (target, checkpoint_sha, registry_sha, n),
                    )
                count += 1
                events += n
                if count % 25 == 0:
                    verification.commit()
                    report(
                        "verifying_checkpoint_logical_streams",
                        verified=count,
                        total=total,
                        events=events,
                    )
            verification.commit()
            verification.close()
        report("checkpoint_reuse_verified", checkpoints=count, events=events)
        # Preserve original profile bytes, publish a new declaration/root binding.
        new_profile = Path(
            config.get("new_profile", anchor / "election-audit/2026/relocated-profile")
        )
        new_profile.mkdir(parents=True, exist_ok=True)
        database = new_profile / "profile.sqlite"
        if not database.exists():
            shutil.copyfile(profile_path / "profile.sqlite", database)
            with database.open("rb") as stream:
                os.fsync(stream.fileno())
        if hash_file(database) != hash_file(profile_path / "profile.sqlite"):
            raise ValueError("Relocated metadata copy differs")
        runoff = next(c for c in registry["certificates"] if c["round"] == 2)
        declaration = {
            **profile_doc,
            "source": {
                **profile_doc["source"],
                "root": runoff["root"],
                "manifest": str(state / "manifest-r2.sqlite"),
            },
            "relocation_provenance": {
                "original_profile": str(profile_path),
                "original_profile_sha256": old_spec["profile_json_sha256"],
                "registry_sha256": registry_sha,
            },
        }
        if not (new_profile / "profile.json").exists():
            _write_json(new_profile / "profile.json", declaration)
        elif _read_json(new_profile / "profile.json") != declaration:
            raise ValueError("Relocated profile identity changed")
        # Real bounded trials, fresh outputs, new code pins; old timings reused only
        # as history. The registered development sample and choices are unchanged.
        tuning_dir = workspace / "tuning"
        if not tuning_dir.exists():
            tuning.prepare(
                config["sample"],
                comparison_path,
                tuning_dir,
                config["tuning_store"],
                config["scratch"],
                policy=tuning.limits(),
                candidates=(2048, 8192, 32768),
            )
        report("retuning_relocated_production_path")
        tuning.run(tuning_dir)
        recommendation = tuning.recommendation(tuning_dir / "recommended.json")
        report("tuning_complete", event_batch_rows=recommendation["event_batch_rows"])
        run_dir = workspace / "production"
        if not run_dir.exists():
            spec = workload.prepare(
                new_profile,
                old_spec["exclusions"],
                tuning_dir / "recommended.json",
                run_dir,
                config["production_store"],
                config["scratch"],
                output_budget_bytes=budget,
                future_budget_bytes=budget,
                source_growth_budget_bytes=0,
                volume_anchor=anchor,
                reuse_stores=(old_spec["store"], config["initial_store"], cache),
                relocation_registry=registry_path,
            )
        else:
            spec = workload._load(run_dir)
        atomic(workspace / "capacity-before-resume.json", workload.preflight(run_dir))
        launcher = [sys.executable, "-B", "-u", str(run_dir / "run_frozen.py")]
        report("validating_real_resume_tranche", job_id=spec["job_id"])
        subprocess.run([*launcher, "run", "--max-objects", "25"], check=True)
        status = workload.status(run_dir)
        required = min(25, spec["scope"]["eligible_unique_content"])
        if status["counters"]["completed"] < required or status["counters"]["failed"]:
            raise RuntimeError("Initial resumed tranche did not meet acceptance")
        atomic(workspace / "resume-acceptance.json", status)
        # Child has its own session; this orchestrator waits and reports its exit.
        log_path = workspace / "production.log"
        with log_path.open("ab", buffering=0) as log:
            child = subprocess.Popen(
                [*launcher, "run"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        atomic(
            workspace / "current-production.json",
            {
                "pid": child.pid,
                "job_id": spec["job_id"],
                "log": str(log_path),
                "progress": str(run_dir / "progress.json"),
                "registry_sha256": registry_sha,
                "status_command": f"rtk proxy {sys.executable} {run_dir / 'run_frozen.py'} status",
            },
        )
        report(
            "production_running",
            worker_pid=child.pid,
            completed=status["counters"]["completed"],
            progress=str(run_dir / "progress.json"),
            log=str(log_path),
        )
        returncode = child.wait()
        if returncode:
            raise RuntimeError(f"Production stopped with exit code {returncode}")
        final = workload.status(run_dir)
        if final["counters"]["failed"]:
            raise RuntimeError("Production failure counter is nonzero")
        remaining = final["work_status"].get("pending", 0)
        report(
            "production_scope_finished" if remaining == 0 else "production_budget_stop",
            final_status=final,
            national_scientific_processing_complete=False,
        )
    except BaseException as exc:
        report("FAILED_STOPPED", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    execute(parser.parse_args().config)
