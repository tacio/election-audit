"""Finite, resumable same-work tuning of real summary workers and commit groups."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

from election_audit.national_migration import atomic, sha
from election_audit.national_parallel import checked, prepare, status
from election_audit.national_resources import apply

FILES = (
    "national_summary.py",
    "national_parallel.py",
    "national_summary_tuning.py",
    "national_resources.py",
    "archive_parsing.py",
    "national_relocation.py",
    "national_migration.py",
    "source_inventory.py",
    "national_summary_release.py",
    "national_summary_tools.py",
)


def save_state(path, state) -> None:
    value = {k: v for k, v in state.items() if k != "state_sha256"}
    checksum = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    atomic(path, {**value, "state_sha256": checksum})


def read_state(path):
    state = json.loads(Path(path).read_text())
    expected = state.pop("state_sha256")
    actual = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual != expected:
        raise ValueError("Tuning state checksum mismatch")
    return state


def cgroup_snapshot():
    try:
        relative = next(
            line.split("::", 1)[1]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if "::" in line
        )
        root = Path("/sys/fs/cgroup") / relative.lstrip("/")
        ancestry = []
        node = root
        while node.is_relative_to("/sys/fs/cgroup"):
            limits = {
                name: (node / name).read_text().strip()
                for name in ("cpu.max", "cpu.stat", "memory.max", "memory.peak", "memory.swap.max")
                if (node / name).exists()
            }
            ancestry.append({"path": str(node), **limits})
            if node == Path("/sys/fs/cgroup"):
                break
            node = node.parent
        return {
            "path": str(root),
            "ancestor_limits": ancestry,
            **{
                name: (root / name).read_text().strip()
                for name in ("cpu.max", "cpu.stat", "memory.max", "memory.peak", "io.stat")
                if (root / name).exists()
            },
        }
    except OSError, StopIteration:
        return {"enforcement": "affinity/address-space fallback; cgroup telemetry unavailable"}


def choose(trials):
    groups = {}
    for trial in trials:
        if trial["state"] == "accepted":
            groups.setdefault((trial["workers"], trial["batch_objects"]), []).append(
                trial["objects_per_second"]
            )
    summaries = []
    for (workers, batch), values in sorted(groups.items()):
        if len(values) < 2:
            continue
        median = statistics.median(values)
        noise = statistics.median(abs(v - median) for v in values) / median
        summaries.append(
            {
                "workers": workers,
                "batch_objects": batch,
                "median_objects_per_second": median,
                "relative_mad": noise,
            }
        )
    if not summaries:
        raise ValueError("No repeated safe candidate")
    best = summaries[0]
    for candidate in summaries[1:]:
        threshold = max(0.03, 2 * best["relative_mad"], 2 * candidate["relative_mad"])
        if candidate["median_objects_per_second"] > best["median_objects_per_second"] * (
            1 + threshold
        ):
            best = candidate
    return {
        "selected": best,
        "candidates": summaries,
        "claim": "best observed safe local configuration; finite balanced repeats; lower resource use wins gains within noise; not a global optimum",
    }


def tune(config_path):
    config_path = Path(config_path).absolute()
    config = json.loads(config_path.read_text())
    output = Path(config["output"])
    output.mkdir(parents=True, exist_ok=True)
    code = {name: sha(Path(__file__).with_name(name)) for name in FILES}
    source_pins = {name: sha(config[name]) for name in ("selection", "resources")}
    development = Path(config["development_sample"])
    sample = checked(development / "sample.json")
    inspection = checked(development / "inspection.json")
    if (
        inspection["state"] != "development_inspected"
        or inspection["sample_id"] != sample["sample_id"]
    ):
        raise ValueError("Prior development-inspection registration required for tuning")
    source_pins["development_sample"] = sha(development / "sample.json")
    source_pins["inspection"] = sha(development / "inspection.json")
    source_pins["scope_workload"] = sha(Path(config["old_workload"]) / "workload.json")
    identity = hashlib.sha256(
        json.dumps(
            {"config_sha256": sha(config_path), "code": code, "source_pins": source_pins},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    state_path = output / "tuning-state.json"
    state = (
        read_state(state_path)
        if state_path.exists()
        else {"identity": identity, "code": code, "trials": [], "state": "prepared"}
    )
    if state["identity"] != identity:
        raise ValueError("Tuning code/source/config identity changed; preserve prior study")
    if state["state"] == "complete":
        return state
    selected = json.loads(Path(config["selection"]).read_text())["sha256s"]
    if not set(selected).issubset({u["sha256"] for u in sample["units"]}):
        raise ValueError("Tuning selection contains previously unregistered development bodies")
    base = json.loads(Path(config["resources"]).read_text())
    apply(base)
    maximum = min(
        3,
        len(base["cpu"]["allowed_cpus"]),
        max(
            1, (base["aggregate_memory_bytes"] - base["parent_allowance_bytes"]) // (512 * 1024**2)
        ),
    )
    candidates = [(1, 16)] + [(workers, 32) for workers in range(2, maximum + 1)]
    if maximum == 1:
        candidates.append((1, 32))
    schedule = candidates + list(reversed(candidates))
    elapsed_prior = sum(t.get("wall_seconds", 0) for t in state["trials"])
    started = time.monotonic()
    for index, (workers, batch) in enumerate(schedule):
        if index < len(state["trials"]):
            continue
        if any(sha(Path(__file__).with_name(name)) != expected for name, expected in code.items()):
            raise ValueError(
                "Tuning code changed during study; prior measurements preserved, no mixed-code acceptance"
            )
        if elapsed_prior + time.monotonic() - started > 900:
            raise TimeoutError("Finite tuning wall budget exhausted")
        r = {
            **base,
            "workers": workers,
            "batch_objects": batch,
            "prefetch": 1,
            "queue_limit": workers + 1,
            "worker_address_space_bytes": (
                base["aggregate_memory_bytes"] - base["parent_allowance_bytes"]
            )
            // workers,
        }
        remaining_output = 1024**3 - sum(t.get("output_bytes", 0) for t in state["trials"])
        r["output_budget_bytes"] = min(r["output_budget_bytes"], remaining_output)
        directory = output / f"trial-{index:02d}"
        store = Path(config["store"]) / f"trial-{index:02d}"
        if directory.exists():
            raise ValueError(
                "Interrupted fresh trial preserved; explicit review required before retry"
            )
        spec = prepare(config["old_workload"], directory, store, resources=r, selection=selected)
        before = cgroup_snapshot()
        tick = time.monotonic()
        state.update(state="running", active=index)
        save_state(state_path, state)
        with (output / f"trial-{index:02d}.log").open("ab", buffering=0) as log:
            child = subprocess.run(
                [sys.executable, "-B", str(directory / "run_frozen.py"), "run"],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=240,
                check=False,
            )
        wall = time.monotonic() - tick
        if any(sha(Path(__file__).with_name(name)) != expected for name, expected in code.items()):
            raise ValueError("Tuning code changed during trial; candidate not accepted")
        result = status(directory)
        progress = (
            json.loads((directory / "progress.json").read_text())
            if (directory / "progress.json").exists()
            else {}
        )
        reason = None
        if child.returncode or result["completed"] != len(selected) or result["failures"]:
            reason = "operational_failure_or_incomplete_work"
        if progress.get("peak_process_tree_rss_bytes", 0) > base["aggregate_memory_bytes"]:
            reason = "aggregate_memory_violation"
        trial = {
            "index": index,
            "workers": workers,
            "batch_objects": batch,
            "state": "rejected" if reason else "accepted",
            "reason": reason,
            "objects": result.get("completed", 0),
            "wall_seconds": wall,
            "objects_per_second": len(selected) / wall,
            "output_bytes": result.get("output_bytes"),
            "metrics": progress,
            "cgroup_before": before,
            "cgroup_after": cgroup_snapshot(),
            "job_id": spec["job_id"],
            "source_selection_sha256": sha(config["selection"]),
            "cache_disclosure": "same safe development objects, SHA order, fresh output stores; warm OS caches possible; no cache eviction; balanced forward/reverse candidate order",
        }
        state["trials"].append(trial)
        state.update(state="running", active=None)
        save_state(state_path, state)
        if reason:
            state.update(state="backoff_stopped", stop_reason=reason)
            save_state(state_path, state)
            raise RuntimeError("Rejected resource/operational trial; automatic expansion stopped")
        allocated = sum(t["output_bytes"] for t in state["trials"])
        if allocated > 1024**3:
            raise OSError("Explicit 1GiB tuning output cap exceeded")
        time.sleep(2)
    decision = choose(state["trials"])
    chosen = decision["selected"]
    r = {**base, **{k: chosen[k] for k in ("workers", "batch_objects")}}
    r.update(
        queue_limit=r["workers"] + r["prefetch"],
        worker_address_space_bytes=(r["aggregate_memory_bytes"] - r["parent_allowance_bytes"])
        // r["workers"],
    )
    state.update(state="complete", winner=decision, resources=r, active=None)
    save_state(state_path, state)
    atomic(
        output / "recommended.json",
        {"identity": identity, "code": code, "resources": r, "decision": decision},
    )
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    print(json.dumps(tune(parser.parse_args().config)))
