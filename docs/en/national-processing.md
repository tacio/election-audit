# Bounded structural processing and hardware tuning

Document-ID: EA-NATIONAL-PROCESSING · Revision: 6 · Language: en

[Português](../pt-BR/national-processing.md) · [Phase 11 evidence](handoffs/task-11.md)

This guide covers the **event-level** structural path. The national runoff pass
used the faster summary path described in
[feature-oriented processing](feature-oriented-processing.md); use the commands
below for event-level benchmarks, hardware studies or a full event-level store.

This workflow profiles a completed collector manifest, registers a metadata-selected
development sample, and processes lossless structural events. Its finite autotuner
measures event batch sizes on your hardware. It does not tune electoral verification,
session reconstruction, model fitting or final scientific evaluation. A faster batch
does not change scientific eligibility or the research protocol.

## Setup and input

Use Linux with `/proc`, Python 3.14 and the locked dependencies; DuckDB and PyArrow
are already included. Install uv, just and rtk, then run these commands from the
repository root. An offline installation needs the dependencies cached already.
No command here starts acquisition, a dashboard or model fitting.

```sh
rtk proxy just setup
rtk proxy .venv/bin/python -B -m election_audit.national_benchmark --help
rtk proxy .venv/bin/python -B -m election_audit.national_tuning --help
```

Create `data/my-national-sources.json` with your actual completed manifest, original
collector root and explicit UFs. Relative paths resolve from the working directory.
The small example selects AC/SP/ZZ, not the whole country. Both the declared round
and official source URLs must agree; filenames do not prove round identity.

```json
{
  "version": "national-structural-v1",
  "sources": [{
    "round": 2,
    "root": "data/tse/2026/turno-2",
    "manifest": ".local-state/tse-2026.sqlite",
    "ufs": ["ac", "sp", "zz"]
  }]
}
```

The profile reads URL/hash/size/geography metadata into SQLite, not log outcomes.
Selection takes content-hash ranks within each UF's four source-size quartiles,
plus its largest object. Before parsing, `inspection.json` marks selected sections
as development-inspected. Propagate that history to stable locations across both
rounds before freezing any untouched test partition; unknown identity is not test
eligible. Prior pilots and existing protected partitions remain binding. If a frozen protocol already exists, pass `select --exclusions PATH` with its reviewed checksummed `structural-sample-exclusions-v1` registry: matching `round`, expanded protected/stress `section_keys`, and evidence pins. Exclude every section linked to each protected stable location, not merely one principal. Missing cross-round identity remains unavailable. The current repository review is recorded in `data/national/phase11-protection-2026-10-31/`; its overlap ledger must be propagated before a new scientific evaluation.

```sh
rtk proxy .venv/bin/python -B -m election_audit.national_benchmark profile --config data/my-national-sources.json --output data/my-profile --scratch .local-state/my-scratch
rtk proxy .venv/bin/python -B -m election_audit.national_benchmark select --profile data/my-profile --output data/my-sample --per-band 1
rtk proxy env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B -m election_audit.national_benchmark compact --sample data/my-sample --output data/my-baseline --store data/my-national-store --scratch .local-state/my-scratch --output-budget-gib 0.25 --batch-rows 2048 --memory-gib 4
```

The last command is a bounded baseline and the manual opt-out from tuning. A
completed baseline provides pinned event digests/counts against which every trial
is checked. New profile, selection, report and tuning directories must be new;
existing verified per-content artifacts may be reused by ordinary processing.

## Tune and apply

The tuner chooses at most six previously inspected sources, one per available
region including overseas. Every candidate processes those same originals into
fresh, distinct durable outputs. Two balanced forward/reverse repetitions reduce
order effects. The default search is 2048/8192/32768 event rows, always also bounded
by 8 MiB per batch. Processing stays at one worker; this version does not claim to
optimize worker counts. Original reads and caches may be warm; caches are not evicted.

```sh
rtk proxy .venv/bin/python -B -m election_audit.national_tuning prepare --sample data/my-sample --comparison data/my-baseline/benchmark.json --output data/my-tuning --store data/my-national-store --scratch .local-state/my-scratch --memory-gib 4 --output-mib 128 --seconds 900 --batches 2048 8192 32768
rtk proxy .venv/bin/python -B -m election_audit.national_tuning run data/my-tuning
rtk proxy env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B -m election_audit.national_benchmark compact --sample data/my-sample --output data/my-tuned-report --store data/my-national-store --scratch .local-state/my-scratch --output-budget-gib 0.25 --tuning-config data/my-tuning/recommended.json
```

The final command applies the recommendation to production processing. Existing
verified objects keep their original physical batch layout; use a newly registered
sample to measure fresh production work. Tuning outputs are separate benchmark
artifacts and are not silently substituted for the main store's checkpoints.

The objective is median fresh **events per second**, from verified source reads
through parsing, encoding and durable publication. Full logical replay validation
is timed separately within each trial's wall time; it does not enter that objective.
Reported worker RSS and conservatively summed process-tree RSS include monitoring
headroom. Reused historical artifact timings never become trial observations.
Gains must exceed 3% and the observed repeat noise; otherwise the smaller batch wins.
The finite search returns the best observed safe configuration, not a global optimum
or a guarantee on another workload or machine. Source mixes, filesystem cache,
concurrent acquisition and HDD tails can dominate timing.

## Budgets, recovery and portability

The default 4 GiB is an aggregate Phase 11 working-memory budget, not a per-worker
allocation or a target to fill. At that setting the worker has a hard 3 GiB virtual
address-space limit, the supervisor is allowed 512 MiB RSS and another 512 MiB is
headroom. The supervisor samples process-tree RSS and host available memory/pressure
every 100 ms, rejecting trials on pressure, time or disk violations. This is a
conservative address-space bound plus monitoring, not an OS cgroup RSS guarantee.
The collector is outside the tuning process tree but affects host-pressure readings.

`prepare` accepts `--memory-gib`, `--output-mib`, `--seconds`, `--hdd-reserve-gib`,
`--ssd-reserve-gib`, `--scratch-gib` and `--batches`. Manual `compact` accepts the
same memory/reserve/scratch flags, `--output-budget-gib` and `--batch-rows`.
Recommendation resources take precedence when `--tuning-config` is supplied.
On smaller hardware start with 1–2 GiB RAM, batch 2048, at least 1 GiB scratch
and smaller explicit output allowances; lower disk reserves only after accounting
for your other workloads. Below 1 GiB the autotuner refuses to run. Keep the thread
environment shown above, especially for small address-space limits.

On the reference machine, retain the 20 GiB HDD floor, 10 GiB SSD reserve and
8 GiB scratch budget. These are separate
from the output allowance. Reserve both spill and output if they share a volume.
An incomplete acquisition cannot be frozen as a complete population. Bounded samples
and observed storage scenarios do not authorize an unaffordable full national run.

`spec.json` pins source hashes/expected logical outputs, sample, configurations,
module hashes and runtime versions. Atomic `state.json` contains its own checksum;
per-trial reports/logs retain accepted and rejected measurements. `recommended.json`
is published only after the finite search completes. Run the same `run` command
to resume. A live prior worker prevents duplication. Interrupted work consumes its
actual retained output/time allowance and is not accepted as a timing observation.
Resource rejection cools down and saves a backoff reason; two rejections or the
total time/output budget stop the study. Resolve pressure before resuming. Changed
code/source identity requires a new explicitly pinned study. Do not delete originals
or overwrite frozen trials to force a successful result.

Compact events retain full line hashes, event IDs, member/line locators and all
logical fields; readers verify physical checksums and the reconstructed full-stream
digest. Structural errors are streamed without the old issue-row cap. Unsupported
message information is counted exactly and remains addressable in event rows.
These facts still have unresolved scientific meaning.

Compact processing registers a verified external dependency on original collector
CAS files instead of copying the whole raw store. It rehashes originals on processing
and checkpoint reuse. Retain that collector root: these artifacts are **not
self-contained**. To move them, preserve the original CAS bytes and paths or create
a new verified local source configuration. For selected self-contained originals,
the separate `national resume` census path copies/fixes originals into its own store
and requires a larger explicit capacity budget; it currently writes the larger
payload representation. No self-contained compact export is claimed.

An earlier study on the original output volume selected 2048 rows: median
3067.749 events/second, compared with 3019.755 at 8192 and 2854.901 at 32768. No
material larger-batch gain was established. The applied 476-object tranche produced
4843988 events in 1044.902 seconds, peak RSS 93052 KiB; it reused 247 objects and
freshly produced 229. These observations support bounded processing, not a complete
national run. Measured acceptance and national-capacity limitations are in the paired
Phase 11 handoff. The user-facing commands operate without this repository's machine-specific
HDD path, and no tuning choice grants access to protected outcomes.

## Disk-backed eligible-population jobs

`national_workload` schedules a completed frozen profile through a SQLite work
ledger instead of loading a national list. Supply reviewed checksummed exclusions;
`data/my-exclusions.json` in this example must exist and describe your protected
sections/round/evidence. Existing protected/stress stable-location groups must be
expanded to all source section keys. Identical content shared with any excluded
observation is excluded everywhere before opening bodies or cached originals.
Absence from this list does not grant scientific or untouched-test eligibility.

```sh
rtk proxy .venv/bin/python -B -m election_audit.national_workload --help
rtk proxy .venv/bin/python -B -m election_audit.national_workload prepare --profile data/my-profile --exclusions data/my-exclusions.json --tuning-config data/my-tuning/recommended.json --output data/my-workload --store data/my-national-store/workload --scratch .local-state/my-scratch --reuse-store data/my-national-store --output-budget-gib 4 --future-budget-gib 4 --source-growth-gib 0
rtk proxy .venv/bin/python -B data/my-workload/run_frozen.py preflight
rtk proxy .venv/bin/python -B data/my-workload/run_frozen.py status
rtk proxy env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B data/my-workload/run_frozen.py run --max-objects 32
rtk proxy env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B data/my-workload/run_frozen.py run
```

The example's 4 GiB output and 4 GiB future allowances deliberately bound work;
they are not national capacity estimates. Choose reviewed allowances for your source
population. `--source-growth-gib` separately reserves ongoing acquisition capacity;
it is zero only when no additional source growth needs reserving. Shared-volume
budgets are added, not independently double-spent. A mounted volume anchor is pinned
to prevent fallback writes if an external drive disappears. `--volume-anchor PATH`
can identify your intended mount explicitly. The 4 GiB RAM policy and real batch
size come from the pinned recommendation; current execution remains one worker.

The job retains all observations, including explicit exclusions, in a checksummed
immutable scope. A separate durable ledger records unique content, attempts,
failures, allocated output, and verified external checkpoint references. External
reuse rechecks bytes and original custody; it does not copy or silently adopt old
results. Newly published outputs receive full logical replay verification. Existing
raw stores and reused checkpoint stores must remain available.

The generated `run_frozen.py` verifies a frozen package/resource copy before import,
so later workspace edits do not change a long-running job or its resume behavior.
It still requires the locked environment and external originals; it is not a wheel
bundle or a self-contained data export. Use this launcher for resume/status. Progress
contains aggregate processing counts, not new case-level outcome inspection. Prior
development-inspection records remain binding. Missing identity/history remains
unavailable. Protected observations remain deliberately unprocessed coverage gaps.

Run with `--max-objects` for a reviewed initial tranche, then resume the same job
without that cap. A failure stops processing and is retained in the ledger; after
resolving its cause use `run --retry-failed`. Output exhaustion stops before further
publication. A larger allowance requires a new pinned specification/store with
explicit verified reuse of the previous store; do not edit frozen manifests.
Only private unpublished scratch/staging created by this job may be cleaned during
recovery. Frozen checkpoints, original files and other drive data are preserved.

## Reference-machine history

On the reference machine this path produced the Phase 11 tuning studies, the
476- and 256-object tranches and a frozen eligible-runoff job. That job was stopped
on 2 November 2026 at 15425 of 498581 objects when the summary path replaced it.
Its artifacts are preserved under `data/national/` and described in the
[Phase 11 handoff](handoffs/task-11.md). Do not resume its launchers: they pin the
old source roots.
