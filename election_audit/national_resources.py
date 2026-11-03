"""Desktop-friendly process-tree budgets: affinity, priority and optional cgroups."""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
from pathlib import Path


def cpu_allocation(fraction=0.5):
    if not 0 < fraction <= 0.5:
        raise ValueError("CPU fraction must be >0 and <=0.5")
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 2:
        raise ValueError(
            "Affinity fallback needs two allotted CPUs; use a <=50% CPU cgroup on one-CPU hosts"
        )
    groups = {}
    for cpu in allowed:
        base = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        try:
            key = (
                (base / "physical_package_id").read_text().strip(),
                (base / "core_id").read_text().strip(),
            )
        except OSError:
            key = ("unknown", str(cpu))
        groups.setdefault(key, []).append(cpu)
    capacity = max(1, min(len(allowed) - 1, int(len(allowed) * fraction)))
    chosen = []
    # Prefer whole physical core/sibling groups; retain at least one whole core
    # for interactive work when topology permits. Affinity is not SMT isolation.
    for siblings in list(groups.values())[: max(1, int(len(groups) * fraction))]:
        chosen.extend(siblings[: max(0, capacity - len(chosen))])
    return {
        "available_cpus": allowed,
        "allowed_cpus": chosen[:capacity],
        "fraction": fraction,
        "cpu_quota_percent": min(50 * len(allowed), 100 * len(chosen)),
        "physical_core_groups": len(groups),
        "selected_core_groups": max(1, int(len(groups) * fraction)),
        "limitation": "Affinity caps aggregate runnable CPUs; SMT/shared caches and I/O still contend; no desktop latency guarantee",
    }


def policy(*, memory_bytes=4 * 1024**3, workers=None, batch=32, prefetch=1, cpu_fraction=0.5):
    cpus = cpu_allocation(cpu_fraction)
    maximum = min(
        len(cpus["allowed_cpus"]), max(1, (memory_bytes - 768 * 1024**2) // (512 * 1024**2))
    )
    chosen = min(cpus["selected_core_groups"], maximum) if workers is None else workers
    if type(chosen) is not int or not 1 <= chosen <= maximum:
        raise ValueError("Worker count exceeds CPU or aggregate RAM envelope")
    if not 1 <= batch <= 64 or not 0 <= prefetch <= chosen or memory_bytes < 1024**3:
        raise ValueError("Invalid bounded batch/prefetch/memory budget")
    return {
        "version": "desktop-resource-policy-v1",
        "cpu": cpus,
        "workers": chosen,
        "aggregate_memory_bytes": memory_bytes,
        "parent_allowance_bytes": 768 * 1024**2,
        "worker_address_space_bytes": (memory_bytes - 768 * 1024**2) // chosen,
        "worker_output_limit_bytes": min(32 * 1024**2, memory_bytes // (16 * (chosen + prefetch))),
        "batch_objects": batch,
        "prefetch": prefetch,
        "queue_limit": chosen + prefetch,
        "nice": 10,
        "io_priority": "best-effort-7",
        "library_threads": 1,
        "hdd_reserve_bytes": 20 * 1024**3,
        "ssd_reserve_bytes": 10 * 1024**3,
        "scratch_budget_bytes": 8 * 1024**3,
        "output_budget_bytes": 256 * 1024**3,
        "future_budget_bytes": 256 * 1024**3,
    }


def apply(policy, *, worker=False):
    os.sched_setaffinity(0, policy["cpu"]["allowed_cpus"])
    current = os.getpriority(os.PRIO_PROCESS, 0)
    if current < policy["nice"]:
        os.nice(policy["nice"] - current)
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "ARROW_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"
    if shutil.which("ionice"):
        subprocess.run(
            ["ionice", "-c", "2", "-n", "7", "-p", str(os.getpid())],
            check=True,
            capture_output=True,
        )
    limit = policy["worker_address_space_bytes"] if worker else policy["parent_allowance_bytes"]
    resource.setrlimit(
        resource.RLIMIT_AS, (limit, limit if worker else policy["aggregate_memory_bytes"])
    )
    return {
        "pid": os.getpid(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "nice": os.getpriority(os.PRIO_PROCESS, 0),
        "address_space_limit": limit,
    }


def validate(resources):
    cpus = resources["cpu"]
    if (
        not cpus["allowed_cpus"]
        or not set(cpus["allowed_cpus"]).issubset(cpus["available_cpus"])
        or len(cpus["allowed_cpus"]) > len(cpus["available_cpus"]) // 2
        or cpus["cpu_quota_percent"] > 50 * len(cpus["available_cpus"])
    ):
        raise ValueError("CPU policy exceeds half the allotted capacity")
    workers = resources["workers"]
    if (
        not 1 <= workers <= len(cpus["allowed_cpus"])
        or not 0 <= resources["prefetch"] <= workers
        or resources["queue_limit"] != workers + resources["prefetch"]
        or not 1 <= resources["batch_objects"] <= 64
        or workers * resources["worker_address_space_bytes"] + resources["parent_allowance_bytes"]
        > resources["aggregate_memory_bytes"]
    ):
        raise ValueError("Worker/queue/memory envelope invalid")
    for name in ("hdd_reserve_bytes", "ssd_reserve_bytes", "future_budget_bytes"):
        if resources[name] < 0:
            raise ValueError("Negative disk allowance")
    if resources["output_budget_bytes"] < 1024**2 or resources["scratch_budget_bytes"] < 1024**3:
        raise ValueError("Need at least 1MiB output and 1GiB bounded scratch")


def cgroup_command(command, policy, *, unit):
    """Build a narrow user service; caller probes manager before selecting it."""
    return [
        "systemd-run",
        "--user",
        "--unit=" + unit,
        "--collect",
        "--property=Type=exec",
        "--property=CPUQuota=" + str(policy["cpu"]["cpu_quota_percent"]) + "%",
        "--property=MemoryMax=" + str(policy["aggregate_memory_bytes"]),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=IOSchedulingClass=best-effort",
        "--property=IOSchedulingPriority=7",
        "--property=AllowedCPUs=" + ",".join(map(str, policy["cpu"]["allowed_cpus"])),
        "--",
        *command,
    ]


def metrics(pids):
    # Include multiprocessing's resource tracker and any nested helpers, not only
    # executor workers. Threads share the process RSS and inherited CPU affinity.
    expanded = set(pids)
    queue = list(pids)
    while queue:
        pid = queue.pop()
        try:
            children = (
                (Path("/proc") / str(pid) / "task" / str(pid) / "children").read_text().split()
            )
        except FileNotFoundError, PermissionError, ProcessLookupError:
            continue
        for child in map(int, children):
            if child not in expanded:
                expanded.add(child)
                queue.append(child)
                if len(expanded) > 128:
                    raise RuntimeError("Unexpected process-tree expansion")
    pids = expanded
    rss, cpu_seconds, read_bytes, write_bytes = 0, 0, 0, 0
    hz = os.sysconf("SC_CLK_TCK")
    for pid in pids:
        root = Path("/proc") / str(pid)
        try:
            fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
            cpu_seconds += (int(fields[11]) + int(fields[12])) / hz
            rss += int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
            io = dict(line.split(":", 1) for line in (root / "io").read_text().splitlines())
            read_bytes += int(io.get("read_bytes", 0))
            write_bytes += int(io.get("write_bytes", 0))
        except FileNotFoundError, PermissionError, ProcessLookupError:
            continue
    pressure = {}
    for name in ("cpu", "io", "memory"):
        try:
            pressure[name] = (Path("/proc/pressure") / name).read_text().strip()
        except OSError:
            pass
    return {
        "rss_bytes": rss,
        "cpu_seconds": cpu_seconds,
        "physical_read_bytes": read_bytes,
        "physical_write_bytes": write_bytes,
        "host_pressure": pressure,
    }
