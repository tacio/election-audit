"""Finite, resumable hardware tuning of lossless structural event batches.

Trials process the same already-inspected originals into distinct durable artifacts.
Only measured fresh production time enters the objective; no checkpoint timing reuse.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

from election_audit.national import LIMITS, _lock, _read_json, _sync_dir, _write_json
from election_audit.source_inventory import canonical, digest, hash_file, utc_now

VERSION = "structural-batch-tuning-v1"
CODE_FILES = (
    "national.py",
    "national_storage.py",
    "national_relocation.py",
    "national_migration.py",
    "national_tuning.py",
    "national_benchmark.py",
    "archive_parsing.py",
    "source_inventory.py",
)


def save_state(path, value) -> None:
    """One atomic file contains both mutable state and its intrinsic digest."""
    path = Path(path)
    envelope = {**value, "state_sha256": digest(value)}
    with tempfile.NamedTemporaryFile(prefix=".state-", dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(canonical(envelope) + b"\n")
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)
    _sync_dir(path.parent)


def load_state(path):
    value = json.loads(Path(path).read_bytes())
    expected = value.pop("state_sha256")
    if digest(value) != expected:
        raise ValueError("Tuning state checksum mismatch")
    return value


def code_pins():
    return {name: hash_file(Path(__file__).with_name(name))[0] for name in CODE_FILES}


def rss_bytes(pid):
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
        for line in lines:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
        if any(line.startswith("State:") and line.split()[1] in ("Z", "X") for line in lines):
            return 0
    except FileNotFoundError, ProcessLookupError:
        return 0
    raise OSError("Cannot observe process RSS")


def tree_rss(pid):
    total, pending, seen = 0, [pid], set()
    while pending:
        child = pending.pop()
        if child in seen:
            continue
        seen.add(child)
        total += rss_bytes(child)
        try:
            pending.extend(
                int(p) for p in Path(f"/proc/{child}/task/{child}/children").read_text().split()
            )
        except FileNotFoundError, ProcessLookupError:
            pass
    return total


def host_pressure():
    memory = {
        line.split(":", 1)[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith(("MemAvailable:", "MemTotal:"))
    }
    full = next(
        line
        for line in Path("/proc/pressure/memory").read_text().splitlines()
        if line.startswith("full ")
    )
    return {
        "memory_available_bytes": memory["MemAvailable"],
        "memory_total_bytes": memory["MemTotal"],
        "memory_pressure_full_avg10": float(full.split("avg10=", 1)[1].split()[0]),
        "load_average": list(os.getloadavg()),
    }


def limits(
    memory_bytes=4 * 1024**3,
    output_bytes=256 * 1024**2,
    seconds=900,
    hdd_reserve_bytes=20 * 1024**3,
    ssd_reserve_bytes=10 * 1024**3,
    scratch_bytes=8 * 1024**3,
):
    if type(memory_bytes) is not int or memory_bytes < 1024**3:
        raise ValueError(
            "Tuning requires at least 1 GiB aggregate RAM; use manual batching below this"
        )
    if output_bytes < 1024**2 or seconds < 1:
        raise ValueError("Need positive bounded time and at least 1 MiB output")
    if hdd_reserve_bytes < 0 or ssd_reserve_bytes < 0 or scratch_bytes < 1024**3:
        raise ValueError("Reserves cannot be negative; scratch must allow at least 1 GiB")
    headroom = max(128 * 1024**2, memory_bytes // 8)
    supervisor = max(256 * 1024**2, memory_bytes // 8)
    return {
        "aggregate_memory_bytes": memory_bytes,
        "memory_headroom_bytes": headroom,
        "supervisor_rss_limit_bytes": supervisor,
        "worker_address_space_bytes": memory_bytes - headroom - supervisor,
        "minimum_host_available_bytes": memory_bytes,
        "maximum_memory_pressure_full_avg10": 5.0,
        "output_budget_bytes": output_bytes,
        "wall_time_budget_seconds": seconds,
        "trial_timeout_seconds": min(120, seconds),
        "cooldown_seconds": 2,
        "maximum_rejections": 2,
        "hdd_reserve_bytes": hdd_reserve_bytes,
        "ssd_reserve_bytes": ssd_reserve_bytes,
        "scratch_budget_bytes": scratch_bytes,
        "workers": 1,
        "event_batch_byte_limit": 8 * 1024**2,
    }


def tuning_guard(spec, extra) -> None:
    policy = spec["policy"]
    existing = []
    for location in (spec["store"], spec["scratch"]):
        path = Path(location)
        while not path.exists():
            path = path.parent
        existing.append(path)
    if existing[0].stat().st_dev == existing[1].stat().st_dev:
        checks = [
            (
                existing[0],
                max(policy["hdd_reserve_bytes"], policy["ssd_reserve_bytes"])
                + policy["scratch_budget_bytes"]
                + extra,
            )
        ]
    else:
        checks = [
            (existing[0], max(policy["hdd_reserve_bytes"], policy["ssd_reserve_bytes"]) + extra),
            (existing[1], policy["ssd_reserve_bytes"] + policy["scratch_budget_bytes"]),
        ]
    for path, needed in checks:
        if shutil.disk_usage(path).free < needed:
            raise OSError("Tuning disk reserve failed")


def resource_reason(policy, pressure, aggregate_rss, supervisor_rss) -> str | None:
    if supervisor_rss > policy["supervisor_rss_limit_bytes"]:
        return "supervisor_memory_limit"
    if aggregate_rss > policy["aggregate_memory_bytes"] - policy["memory_headroom_bytes"]:
        return "aggregate_memory_headroom"
    if pressure["memory_available_bytes"] < policy["minimum_host_available_bytes"]:
        return "host_memory_available"
    if pressure["memory_pressure_full_avg10"] > policy["maximum_memory_pressure_full_avg10"]:
        return "host_memory_pressure"
    return None


def winner(trials, *, minimum_gain=0.03, repeats=2):
    """Prefer the smaller batch when observed gains do not exceed repeat noise."""
    groups = {}
    for trial in trials:
        if trial["state"] == "accepted":
            groups.setdefault(trial["batch_rows"], []).append(trial["events_per_second"])
    summaries = []
    for batch, values in sorted(groups.items()):
        if len(values) < repeats:
            continue
        median = statistics.median(values)
        mad = statistics.median(abs(v - median) for v in values)
        summaries.append(
            {
                "batch_rows": batch,
                "median_events_per_second": median,
                "relative_mad": mad / median,
                "repeats": len(values),
            }
        )
    if not summaries:
        return None
    best = summaries[0]
    for candidate in summaries[1:]:
        threshold = max(minimum_gain, 2 * best["relative_mad"], 2 * candidate["relative_mad"])
        if candidate["median_events_per_second"] > best["median_events_per_second"] * (
            1 + threshold
        ):
            best = candidate
    return {
        **best,
        "summaries": summaries,
        "minimum_gain": minimum_gain,
        "interpretation": "best observed safe finite-grid configuration; smaller batches win within measured noise; not a global optimum",
    }


def prepare(
    sample_dir,
    comparison_report,
    directory,
    store,
    scratch,
    *,
    policy=None,
    candidates=(2048, 8192, 32768),
):
    sample_dir, directory = Path(sample_dir).resolve(), Path(directory).resolve()
    if directory.exists():
        raise ValueError("Tuning directory must be new; resume it with run")
    candidates = tuple(sorted(set(candidates)))
    if (
        not candidates
        or len(candidates) > 4
        or any(type(v) is not int or not 1 <= v <= 65536 for v in candidates)
    ):
        raise ValueError("Need one to four batch candidates between 1 and 65536")
    sample = _read_json(sample_dir / "sample.json")
    inspection = _read_json(sample_dir / "inspection.json")
    comparison = _read_json(Path(comparison_report))
    if (
        inspection["sample_id"] != sample["sample_id"]
        or inspection["state"] != "development_inspected"
    ):
        raise ValueError("Source sample lacks prior development inspection registration")
    if comparison["sample_id"] != sample["sample_id"]:
        raise ValueError("Comparison report uses another source sample")
    from election_audit.national_benchmark import REGIONS

    selected = {}
    for unit in sorted(sample["units"], key=lambda u: u["sha256"]):
        selected.setdefault(REGIONS[unit["uf"]], unit)
    records = {r["source_sha256"]: r for r in comparison["records"]}
    profile = Path(sample["profile"])
    profile_doc = _read_json(profile / "profile.json")
    if hash_file(profile / "profile.json")[0] != sample["profile_sha256"]:
        raise ValueError("Frozen source profile changed")
    sources = []
    with closing(
        sqlite3.connect((profile / "profile.sqlite").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        for region, unit in sorted(selected.items()):
            row = db.execute("SELECT * FROM sources WHERE url=?", (unit["url"],)).fetchone()
            if row is None or row["sha256"] != unit["sha256"]:
                raise ValueError("Selected source metadata differs")
            record = records[unit["sha256"]]
            event_metadata = _read_json(Path(record["artifact"]) / "events/compact.json")
            sources.append(
                {
                    "region": region,
                    "row": {**dict(row), "source_root": profile_doc["source"]["root"]},
                    "expected_logical_events_sha256": event_metadata["logical_events_sha256"],
                    "expected_counts": record["counts"],
                }
            )
    spec = {
        "version": VERSION,
        "code": code_pins(),
        "sample_id": sample["sample_id"],
        "sample_file_sha256": hash_file(sample_dir / "sample.json")[0],
        "comparison_report_sha256": hash_file(Path(comparison_report))[0],
        "sources": sources,
        "store": str(Path(store).resolve()),
        "scratch": str(Path(scratch).resolve()),
        "policy": policy or limits(),
        "candidates": list(candidates),
        "repeats": 2,
        "cache_disclosure": "originals and filesystem metadata may be warm; no system cache eviction; balanced forward/reverse order; all trial outputs fresh",
        "scope": "structural processing only; previously development-inspected units; scientific parser and protocol unchanged",
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pyarrow": __import__("pyarrow").__version__,
        },
    }
    spec["spec_id"] = digest(spec)
    directory.mkdir(parents=True)
    snapshots = directory / "code-snapshot"
    snapshots.mkdir()
    for name, expected in spec["code"].items():
        body = Path(__file__).with_name(name).read_bytes()
        target = snapshots / name
        target.write_bytes(body)
        if hash_file(target)[0] != expected:
            raise ValueError("Code changed during tuning preparation")
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
    _sync_dir(snapshots)
    _write_json(directory / "spec.json", spec)
    save_state(
        directory / "state.json",
        {
            "version": VERSION,
            "spec_id": spec["spec_id"],
            "state": "prepared",
            "trials": [],
            "active": None,
            "elapsed_seconds": 0,
        },
    )
    return spec


def validate_state(spec, state) -> None:
    if spec["code"] != code_pins() or state["spec_id"] != spec["spec_id"]:
        raise ValueError("Tuning code/source identity changed; create a new pinned study")
    unsigned = {k: v for k, v in spec.items() if k != "spec_id"}
    if digest(unsigned) != spec["spec_id"]:
        raise ValueError("Tuning specification identity mismatch")


def configure_production(policy) -> None:
    """Apply real single-process bounds, including a hard worker address-space limit."""
    LIMITS.update(
        memory_bytes=policy["aggregate_memory_bytes"],
        hdd_reserve_bytes=policy["hdd_reserve_bytes"],
        reserve_bytes=policy["ssd_reserve_bytes"],
        spill_bytes=policy["scratch_budget_bytes"],
    )
    bound = policy["worker_address_space_bytes"]
    current = next(
        int(s.split()[1]) * 1024
        for s in Path("/proc/self/status").read_text().splitlines()
        if s.startswith("VmSize:")
    )
    if current >= bound:
        raise OSError(
            "Existing virtual memory exceeds worker allowance; start with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1"
        )
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    bound = min(bound, hard) if hard != resource.RLIM_INFINITY else bound
    resource.setrlimit(resource.RLIMIT_AS, (bound, bound))
    import pyarrow as pa

    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)


def recommendation(path):
    path = Path(path)
    doc = _read_json(path) if Path(str(path) + ".sha256").exists() else load_state(path)
    if doc["version"] != VERSION or doc["code"] != code_pins() or doc["workers"] != 1:
        raise ValueError(
            "Recommendation code/format differs; retune or use an explicit manual configuration"
        )
    if not 1 <= doc["event_batch_rows"] <= 65536:
        raise ValueError("Invalid recommended batch size")
    return doc


def publish_recommendation(directory, spec, state) -> None:
    if state.get("winner") is None or state["state"] != "complete":
        return
    value = {
        "version": VERSION,
        "spec_id": spec["spec_id"],
        "code": spec["code"],
        "event_batch_rows": state["winner"]["batch_rows"],
        "workers": 1,
        "resources": spec["policy"],
        "winner": state["winner"],
        "application": "manual or run_compact_sample(batch_rows=event_batch_rows); does not tune later model experiments",
    }
    path = Path(directory) / "recommended.json"
    if path.exists():
        if recommendation(path) != value:
            raise ValueError("Published tuning recommendation differs from completed state")
        return
    save_state(path, value)


def worker(directory, trial_id, batch_rows, output_budget_bytes):
    spec = _read_json(Path(directory) / "spec.json")
    validate_state(spec, {"spec_id": spec["spec_id"]})
    policy = spec["policy"]
    from election_audit.national_storage import iter_compact, process_compact_original

    configure_production(policy)
    store = Path(spec["store"]) / "tuning" / spec["spec_id"] / trial_id
    if store.exists():
        raise ValueError("Trial output already exists; never reuse its processing timings")
    if not 0 < output_budget_bytes <= policy["output_budget_bytes"]:
        raise ValueError("Invalid remaining trial output budget")
    remaining, produced, seconds, events = output_budget_bytes, 0, 0.0, 0
    artifacts = []
    for source in spec["sources"]:
        started = time.monotonic()
        path = process_compact_original(
            source["row"],
            store,
            spec["scratch"],
            output_budget_bytes=remaining,
            batch_rows=batch_rows,
        )
        seconds += time.monotonic() - started
        checkpoint = _read_json(path / "checkpoint.json")
        meta = _read_json(path / "events/compact.json")
        count = sum(1 for _ in iter_compact(path / "events"))
        if (
            meta["logical_events_sha256"] != source["expected_logical_events_sha256"]
            or checkpoint["counts"] != source["expected_counts"]
            or count != checkpoint["counts"]["events"]
        ):
            raise ValueError("Tuning changed the deterministic logical event output")
        size = (
            sum(v["bytes"] for v in checkpoint["files"].values())
            + (path / "checkpoint.json").stat().st_size
            + 65
        )
        produced += size
        remaining -= size
        events += count
        artifacts.append(str(path))
    result = {
        "state": "accepted",
        "batch_rows": batch_rows,
        "fresh_production_seconds": seconds,
        "events": events,
        "events_per_second": events / seconds,
        "objects_per_second": len(artifacts) / seconds,
        "output_bytes": produced,
        "artifacts": artifacts,
        "logical_equivalence": "all full streams verified and exact pinned event digests/counts matched",
        "worker_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "worker_cpu_seconds_including_validation": {
            "user": resource.getrusage(resource.RUSAGE_SELF).ru_utime,
            "system": resource.getrusage(resource.RUSAGE_SELF).ru_stime,
        },
        "worker_os_reported_block_io": {
            "input_blocks": resource.getrusage(resource.RUSAGE_SELF).ru_inblock,
            "output_blocks": resource.getrusage(resource.RUSAGE_SELF).ru_oublock,
            "scope": "OS process counters; not whole-device I/O and may omit filesystem-cache/FUSE traffic",
        },
    }
    _write_json(Path(directory) / (trial_id + ".json"), result)
    return result


def run(directory):
    directory = Path(directory).resolve()
    spec, state = _read_json(directory / "spec.json"), load_state(directory / "state.json")
    validate_state(spec, state)
    if state["state"] == "complete":
        with _lock(directory, "tuner"):
            publish_recommendation(directory, spec, state)
        return state
    policy = spec["policy"]
    if state["active"]:
        pid = state["active"].get("pid")
        command = Path(f"/proc/{pid}/cmdline") if pid else None
        if (
            command
            and command.exists()
            and b"election_audit.national_tuning" in command.read_bytes()
        ):
            raise ValueError("A prior tuning worker is still present; do not launch duplicate work")
        active = state["active"]
        interrupted_store = Path(spec["store"]) / "tuning" / spec["spec_id"] / active["trial_id"]
        state["elapsed_seconds"] = max(
            state["elapsed_seconds"],
            active.get("elapsed_at_start", 0)
            + max(0, time.monotonic() - active.get("monotonic_started", time.monotonic())),
        )
        state["trials"].append(
            {
                **state["active"],
                "state": "rejected",
                "reason": "interrupted_not_a_timing_measurement",
                "output_bytes": sum(
                    p.stat().st_size for p in interrupted_store.rglob("*") if p.is_file()
                ),
            }
        )
        state["active"] = None
    sequence = spec["candidates"] + list(reversed(spec["candidates"]))
    started = time.monotonic()
    previous_elapsed = state["elapsed_seconds"]
    with _lock(Path(spec["store"]), "national"), _lock(directory, "tuner"):
        for schedule_index, batch in enumerate(sequence):
            if any(
                t["state"] == "accepted" and t.get("schedule_index") == schedule_index
                for t in state["trials"]
            ):
                continue
            rejected = sum(t["state"] == "rejected" for t in state["trials"])
            elapsed = previous_elapsed + time.monotonic() - started
            used = sum(t.get("output_bytes", 0) for t in state["trials"])
            if (
                rejected >= policy["maximum_rejections"]
                or elapsed >= policy["wall_time_budget_seconds"]
                or used >= policy["output_budget_bytes"]
            ):
                state["state"], state["stop_reason"] = (
                    "bounded_stop",
                    "trial_time_output_or_rejection_budget",
                )
                break
            pressure = host_pressure()
            reason = resource_reason(
                policy, pressure, rss_bytes(os.getpid()), rss_bytes(os.getpid())
            )
            if reason:
                state["state"], state["stop_reason"] = "backoff", reason
                state["last_pressure"] = pressure
                time.sleep(policy["cooldown_seconds"])
                break
            tuning_guard(spec, policy["output_budget_bytes"] - used)
            trial_id = f"trial-{len(state['trials']):03d}"
            state["active"] = {
                "trial_id": trial_id,
                "batch_rows": batch,
                "schedule_index": schedule_index,
                "started_at": utc_now(),
                "monotonic_started": time.monotonic(),
                "elapsed_at_start": elapsed,
            }
            state["state"] = "running"
            save_state(directory / "state.json", state)
            env = {
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "ARROW_NUM_THREADS": "1",
            }
            log = (directory / (trial_id + ".log")).open("ab")
            trial_started = time.monotonic()
            with log:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "election_audit.national_tuning",
                        "worker",
                        str(directory),
                        trial_id,
                        str(batch),
                        str(policy["output_budget_bytes"] - used),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
                state["active"]["pid"] = child.pid
                save_state(directory / "state.json", state)
                peak, reason = 0, None
                while child.poll() is None:
                    try:
                        supervisor = rss_bytes(os.getpid())
                        aggregate = supervisor + tree_rss(child.pid)
                        peak = max(peak, aggregate)
                        pressure = host_pressure()
                        reason = resource_reason(policy, pressure, aggregate, supervisor)
                    except OSError:
                        reason = "resource_observation_failed"
                    if time.monotonic() - trial_started > min(
                        policy["trial_timeout_seconds"],
                        policy["wall_time_budget_seconds"] - elapsed,
                    ):
                        reason = "trial_time_budget"
                    try:
                        tuning_guard(spec, policy["output_budget_bytes"] - used)
                    except OSError:
                        reason = "disk_reserve"
                    if reason:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                        break
                    time.sleep(0.1)
            result_path = directory / (trial_id + ".json")
            if child.returncode == 0 and result_path.exists() and reason is None:
                trial = _read_json(result_path)
            else:
                trial = {
                    "state": "rejected",
                    "batch_rows": batch,
                    "reason": reason or "worker_failed",
                    "output_bytes": sum(
                        p.stat().st_size
                        for p in (
                            Path(spec["store"]) / "tuning" / spec["spec_id"] / trial_id
                        ).rglob("*")
                        if p.is_file()
                    ),
                }
            trial.update(
                {
                    "trial_id": trial_id,
                    "schedule_index": schedule_index,
                    "wall_seconds": time.monotonic() - trial_started,
                    "aggregate_peak_rss_bytes": peak,
                    "host_pressure_end": pressure,
                }
            )
            state["trials"].append(trial)
            state["active"] = None
            state["elapsed_seconds"] = previous_elapsed + time.monotonic() - started
            state["winner"] = winner(state["trials"])
            save_state(directory / "state.json", state)
            print(
                json.dumps(
                    {
                        "trial": trial_id,
                        "batch_rows": batch,
                        "state": trial["state"],
                        "events_per_second": trial.get("events_per_second"),
                        "aggregate_peak_rss_bytes": peak,
                    }
                ),
                flush=True,
            )
            if trial["state"] == "rejected":
                state["state"], state["stop_reason"] = "backoff", trial["reason"]
                time.sleep(policy["cooldown_seconds"])
                break
        else:
            state["state"] = "complete"
            state["stop_reason"] = (
                "finite_grid_repeated; best_observed_safe_configuration_with_noise_threshold"
            )
        state["elapsed_seconds"] = previous_elapsed + time.monotonic() - started
        state["winner"] = winner(state["trials"])
        save_state(directory / "state.json", state)
        publish_recommendation(directory, spec, state)
    return state


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("prepare")
    for name in ("sample", "comparison", "output", "store", "scratch"):
        setup.add_argument("--" + name, required=True)
    setup.add_argument("--memory-gib", type=float, default=4)
    setup.add_argument("--output-mib", type=int, default=256)
    setup.add_argument("--seconds", type=int, default=900)
    setup.add_argument("--hdd-reserve-gib", type=float, default=20)
    setup.add_argument("--ssd-reserve-gib", type=float, default=10)
    setup.add_argument("--scratch-gib", type=float, default=8)
    setup.add_argument("--batches", type=int, nargs="+", default=[2048, 8192, 32768])
    resume = sub.add_parser("run")
    resume.add_argument("directory")
    work = sub.add_parser("worker", help=argparse.SUPPRESS)
    work.add_argument("directory")
    work.add_argument("trial_id")
    work.add_argument("batch_rows", type=int)
    work.add_argument("output_budget_bytes", type=int)
    args = parser.parse_args(argv)
    if args.action == "prepare":
        value = prepare(
            args.sample,
            args.comparison,
            args.output,
            args.store,
            args.scratch,
            policy=limits(
                int(args.memory_gib * 1024**3),
                args.output_mib * 1024**2,
                args.seconds,
                int(args.hdd_reserve_gib * 1024**3),
                int(args.ssd_reserve_gib * 1024**3),
                int(args.scratch_gib * 1024**3),
            ),
            candidates=args.batches,
        )
    elif args.action == "worker":
        value = worker(args.directory, args.trial_id, args.batch_rows, args.output_budget_bytes)
    else:
        value = run(args.directory)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
