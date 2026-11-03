# Task 11 — Bounded national structural processing and hardware tuning

Document-ID: EA-HANDOFF-11 · Revision: 8 · Language: en

## Outcome — 3 November 2026

Phase 11 is complete for the eligible runoff scope. On 2 November the user approved
replacing the event-level production job with feature-oriented summaries
([guide](../feature-oriented-processing.md)). The event-level job in
`data/national/phase11-overnight-2026-11-01/` was stopped by SIGTERM at 15425 of
498581 objects; its artifacts are preserved and it must not be resumed.

The summary job `c7b864888159193cb15257415757f0368d675b54a8376ed335ddc6ed79626333`
(`data/national/phase11-feature-oriented-2026-11-02/production/`) completed all
498581 eligible objects at 2026-11-03 12:28 UTC: 0 failures, 498575 complete and 6
partial parses (190 errors retained), 5032537448 structural events, 35992 seconds
elapsed, three workers, 111% average CPU, peak process-tree RSS 195719168 bytes and
68797890560 checkpoint bytes. Its analytical release
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` is in
`runoff-summary-analysis-full-20261102/` on the output volume, with 546620085
Parquet bytes: `source_summaries` (498581 rows), `source_witnesses` and
`source_index` (499177 each), `members` (511541) and `blocks` (10085027).

The 596 protected/stress observations remain deferred. Round 1 is registered for
custody only and has not been processed. Scientific eligibility stays
`unavailable_structural_only`. The sections below are the dated execution log;
statements that a job is running, scheduled or pending are superseded.

## Approved workflow and scope

The user authorized one Phase 11 implementation sub-agent while corrected first-round
acquisition continues. Later phases remain paused and marimo is last. The user also
requested a 4 GiB aggregate working-memory budget and measured hardware autotuning
with portable documentation. The prior ~128 MiB measurements were observed RSS,
not an imposed cap. [User guide](../national-processing.md) covers setup, actual
CLI flags, manual opt-out, tuning, replay, resume and external-original dependencies.

Implemented tools and real bounded runs are distinct from full national execution.
A completed source-size/geography profile covers 499177 runoff log mappings and
90350525589 bytes. First-round acquisition remains incomplete; its correct source
is `turno-1-verified` with `.local-state/tse-2026-t1-verified.sqlite`. The supplied
older first-round root is a runoff duplicate. The collector was not interrupted,
restarted or duplicated; raw bytes and frozen earlier releases are preserved.

## Interfaces, provenance and resources

`national.py` supplies disk-backed census, preflight, resume/status and verified
per-content checkpoints. Explicit sources contain round/root/manifest/UFs and may
restrict `section_keys`. The census retains source mappings and historical metadata
without inventing historical URL-to-byte associations. The larger payload path
freezes originals into its own store; unbounded object processing requires an
explicit positive output allowance. Status distinguishes legacy diagnostic-policy
artifacts and current structural completeness.

`national_benchmark.py` supplies metadata-only SQLite workload profiling, deterministic
UF/size-quartile selection, prior development-inspection registration, optional pinned
protected-section exclusions, bounded payload/compact execution and measured reports.
Selection never reads electoral outcomes. Selected stable locations must remain
excluded from untouched tests across both rounds after identity linkage.

`national_storage.py` publishes typed lossless compact Parquet. It stores the exact
32-byte source-line digest, per-row strings/sequence/line number and shared member
locator templates. `iter_compact` reconstructs every original logical field and
deterministic event ID, verifying physical checksums and the complete event-stream
digest. No truncated hash or omitted event evidence is used. Structural errors stream
without the old issue-row cap. Unsupported-message information is counted exactly
and individually addressable through unknown event rows. Old capped artifacts stay
unchanged under their legacy keys.

The compact producer registers verified original collector CAS dependencies instead
of duplicating the whole source store. It rehashes originals before/after parsing
and on reuse. Artifacts explicitly state external dependency and are not self-contained.
The original root must be retained. Publication uses checksums, fsync, atomic target
rename, per-content locks and a failure ledger; scratch/publication failures never
become success. Compact outputs are under `compact/KEY_PREFIX/KEY/`, joining source
hashes to frozen profile/census observations. The shared historical store directory
is named `phase11-ac`, but scope is defined by its catalogs, not that old name.

Current production is one worker. RAM is budgeted at 4 GiB aggregate; the tuned CLI
uses a hard 3 GiB worker address-space limit, 512 MiB supervisor RSS allowance and
512 MiB headroom, with host/process-tree RSS pressure checks during tuning. This is
not a cgroup RSS guarantee. The HDD floor is 20 GiB, SSD reserve 10 GiB and bounded
per-object scratch 8 GiB. Shared-volume guards add spill and output allowances;
separate volumes are checked separately. Row and byte batch limits both apply.
Four workers/four threads remain upper planning limits, not active concurrency.

## Measured real evidence

Earlier evidence remains at `data/national/phase11-ac/benchmark.json` and
`phase11-review-2026-10-31/`: full AC metadata plus three logs, then the retained
five-principal development pilot. Those small earlier runs are not national runs.

`phase11-stratified-2026-10-31/` contains the metadata profile and 252-target sample:
two hash ranks per UF size quartile plus maximum-size tails, all 28 UFs/ZZ and all
regions. It processed 47760088 source bytes into 2660764 events and 218718728
payload bytes in 1100.888 seconds, peak RSS 124012 KiB. One RJ maximum-size object
is genuinely partial: 70 timestamp errors and 111 malformed-column errors, all
retained. Its 18228 unsupported-message infos are exactly counted and addressable.
An official uppercase `f:O` metadata value exposed a case-normalization mismatch;
the census now accepts it consistently with the collector while preserving raw bytes.

`phase11-compact-2026-10-31/sample/benchmark.json` contains the exact same 252 logical
event streams: 102914374 output bytes, 1270.869 seconds including full comparison,
312268 KiB peak RSS. Every event ID, field, line hash and locator matches the payload
stream; diagnostic counts/status also match. Output/source ratios are min 2.0057,
median 2.1586, p95 2.1855, max 2.2642. Allocated filesystem bytes including subdirectories
were 104990208. Exact source snapshots/pins distinguish loaded implementations from
later hardening changes.

`phase11-tuning-v3-2026-10-31/` records six fresh trials on six already inspected
regional/ZZ sources, two balanced repeats, batch sizes 2048/8192/32768, 128 MiB total
output and 900-second limit. It completed in 135.844 seconds, produced 13444806 bytes,
and peaked at 173486080 aggregate RSS bytes. Median events/second were respectively
3194.220, 2797.049 and 2798.317; relative MAD was 11.42%, 5.71% and 3.88%. Larger
batches did not establish a safe sustained gain; the best observed setting is 2048,
not a global optimum. All full logical streams/counts matched. The first interrupted
monitoring study is retained; the zombie-process RSS race is tested and fixed.

A 476-target next tranche is admitted under `phase11-tranche-2026-10-31/`, four
eligible hash ranks per quartile plus tails, verified reuse, no original copies and
4 GiB output cap. Its measured v3 recommendation was applied to real production.
It completed in 1044.902 seconds: 4843988 events from 86934493 source bytes,
187528258 logical / 191419904 allocated output bytes, peak RSS 93052 KiB. It reused
247 verified objects and freshly produced 229 (2232828 events in 553.635 production
seconds). Every full logical stream verified; only the known RJ partial remains.
`tranche-review.json` separates fresh processing timings from old checkpoint timings.
`planning-scenarios.json` uses four eligible primary objects per stratum: allocated
national output point 198525442560 bytes, sequential fresh-source mean scenario
14.304 days; no national guarantee and no downstream allowance. The final matching-code study at `phase11-tuning-final-2026-10-31/` also
completed all six trials in 131.656 seconds. Its current usable `recommended.json`
retains 2048 rows: median events/second 3067.749 versus 3019.755 (8192) and 2854.901
(32768), with 172756992 bytes maximum aggregate RSS and 13444799 output bytes.
No material larger-batch gain is claimed. It pins code snapshots, CPU/I/O counters
and exact logical equivalence. Completed-state recovery atomically reconstructs a
missing recommendation without rerunning trials; an active attempt retains its
original code pins. No new production run is needed merely to republish metadata.

## Protection review and national capacity gate

`phase11-protection-2026-10-31/impact.json` records a metadata-only review of the
original sample: four AC sections overlap the existing protected partition, and one
the municipal-stress partition. No electoral values, final evaluation or individual
operational metrics were opened. The pre-parse development registry is conservative:
do not assert those locations remain untouched. Preserve the frozen old protocol and
propagate the inspection history in Phase 15 before any new final evaluation. The
new tranche excludes all 596 protected/stress AC sections across 171 stable locations;
none of the six tuning sources is AC. No later-phase registry or protocol was rewritten.

`phase11-capacity-2026-10-31/capacity.json` pins full source counters and measured
allocated bytes. At observation HDD free was 272355491840 bytes; SSD 29056479232.
Reserving an additional 90643145031 acquisition bytes, the 20 GiB floor and 4 GiB
tranche leaves 155942543033 bytes. UF/size-weighted compact national logical output
point is 193092144007.5 bytes and allocated-output point 197122369024; the observed
within-stratum maximum-ratio scenario is 195806592270.4 bytes. Sequential timing at
primary-sample means is 17.179 days. These are scenarios, not confidence bounds,
capacity/runtime guarantees or allowances for later derivatives. Acquisition growth
is an assumption, not a first-round upper bound. Full national execution does not
fit this growth scenario even without another raw copy.

## Acceptance and remaining dependencies

Targeted tests cover large streaming histories, exact parser identity, corruption,
round/scope isolation, output/scratch/HDD limits, locking, resume, streamed diagnostics,
compact full-event round trips, real batch-layout effects, tuning resource rejection,
noise/plateau selection, identity pins, backoff and interrupted-output accounting.
The paired user guide, README/index links, plans and handoffs are part of acceptance.
Forty targeted tests pass; Ruff, formatting, paired-document and command checks
pass (238 commands, 14 SQL statements, 19 help invocations). Saved current-code
verification and final acceptance are under `data/national/phase11-acceptance-2026-10-31/`.

Do not freeze incomplete first-round populations. Await actual completed source size,
review storage/downstream allowances, propagate inspection history and connect
cross-object operational/electoral/model producers before claiming a national pipeline.
These are explicit remaining gates, not capabilities supplied by structural parsing.
Phase 11 broader benchmarks and tooling are real; the full two-round national goal
is not complete and no later phase is dispatched by this handoff.

```sh
rtk proxy .venv/bin/python -B -m unittest discover -s tests -p 'test_national*.py' -q
rtk proxy .venv/bin/python -B -m election_audit.national_benchmark --help
rtk proxy .venv/bin/python -B -m election_audit.national_tuning prepare --help
rtk proxy .venv/bin/python -B -m scripts.check_docs
rtk proxy .venv/bin/python -B -m scripts.check_doc_commands
```

## New-drive continuation — running, not complete

The dedicated project directory is now owned by the user; the native fsynced write
probe and current mount/capacity checks passed. The new output volume resolves the
old single-drive capacity gate. Runoff output is capped at 256 GiB including 2 GiB
metadata, with a separate 256 GiB future first-round derivative allowance and 20 GiB
floor. The old source HDD retains an 85 GiB acquisition-growth scenario plus its
20 GiB floor; SSD retains 10 GiB reserve and 8 GiB spill. Shared-volume obligations
are added once with the largest reserve. These are allowances, not guarantees for
an unfinished first-round derivative. No original data or unrelated drive files
were moved or deleted; the collector is untouched.

The new-drive tuner completed six fresh trials in 134.158 seconds on six already
inspected non-AC sources. Batch 2048 remained best observed: median 5702.844 events/s,
versus 5403.572 (8192) and 1500.777 (32768); maximum observed aggregate RSS 172212224
bytes. All complete logical event digests/counts matched. No larger-batch improvement
or global optimum is claimed. The study and review are at
`data/national/phase11-new-drive-tuning-2026-10-31/`.

The real initial tranche completed 256 objects and 2603602 events in 206.947 seconds
after metadata setup: 183 verified reuses and 73 new checkpoints (31174656 allocated
bytes), zero failures/partials/issues. The new outputs recorded 83.429 production
seconds for 754471 events; the maximum checkpoint-recorded HWM was 124272 KiB.
All new streams were logically replay-verified and no protected work rows exist.
The initial 256 validation targets were conservatively registered before body access
in `execution/initial-tranche-inspection.json`; propagate this alongside earlier
inspection histories across stable locations/both rounds. Mixed-cache throughput
is not a national runtime estimate. Initial artifacts are preserved under their
original immutable configuration; their review records the initially omitted passive
helper pin. Final production now freezes helper scripts and dependency locks as well,
and explicitly references the validated initial checkpoints without raw copying.

The active configuration is
`data/national/phase11-new-drive-2026-10-31/production/`, job
`3016f117a075e64281fe8730e254e47bcf5e6cd0d76790a93506a12c78ad72dc`, output subtree
`election-audit/2026/runoff-production`. Its 58 frozen runtime files include the
passive source/coverage helper imports; an import-origin regression verifies this.
Use `production/run_frozen.py` for future status/resume; it verifies the snapshot
before import. It still requires the locked environment and retained raw/reused
stores. Fifty targeted tests, Ruff, formatting and paired-document/command checks pass.

Scope is 499177 source observations, 596 protected/stress exclusions and 498581
eligible unique objects. Byte-equal aliases of protected content are excluded too,
before any body/cache access. `iter_observations` streams all witnesses; deferred,
pending and failed counts remain null. Partial parsing and unavailable scientific
eligibility remain explicit. No first-round population or later phase is processed.
Bulk preprocessing does not assert untouched-test eligibility; prior development
registries and the original impact record remain binding.

The detached GNU time supervisor and worker are recorded in `current-launch.json`;
workspace `production/progress.json`, `processing.log` and `monitor-latest.json`
provide aggregate live state. The time resource report finalizes on attempt exit.
Live SQLite WAL status must be read from the host mount; the agent's read-only bind
may fail, so use the workspace progress snapshot there, never `immutable=1` on an
active ledger. A read-only latency probe on a fixed development source found slow
external cache verification on the old fuseblk store; it is not a fresh processing
trial or proof about national throughput. The bounded initial new outputs remain
verified; production progress must be measured separately. The job is running and
its pending population is not a completed national analysis. Later phases/marimo
remain paused and the first-round collector remains independent.

## Unattended copied-source migration (1 November 2026)

The current overnight job is `data/national/phase11-overnight-2026-11-01/`.
It waits for every recorded rsync PID/start-time identity, then accepts each copied
round only after a consistent SQLite manifest snapshot, every unique manifest
object's size and SHA-256, and a second stat-only stability pass. Hashing includes
protected originals as blind integrity work; no electoral bodies are decoded at
this stage. Missing files, changed copies, unexpected relevant writers, mount or
reserve changes stop the job. No repair, deletion or old-source fallback occurs.
The parent cannot recover a departed nonchild rsync's exit status: unknown statuses
stay unknown; complete destination hashes provide copy acceptance. Ptrace-hidden
unrelated process descriptors cannot prove exclusive custody against hostile writers.

After acceptance, the pinned continuation copies only the 476 previously approved
safe pilot checkpoints still needed from the old drive, verifies eligible existing
checkpoints' physical and full logical streams, registers both relocated source
roots, performs fresh bounded tuning on six already development-inspected regional
units, freezes a new runoff job, validates a 25-object resume tranche and continues
runoff structural processing. Frozen checkpoint/config bytes are preserved; strict
registry aliases resolve old references solely to verified new originals. The first
round is registered for custody only. The 596 protected/stress observations and
content aliases remain excluded before semantic/cache access; prior inspection
history remains binding. Existing parser partials retain all diagnostics and remain
partial; operational exceptions stop the chain immediately.

The job keeps the 4 GiB aggregate RAM allocation, 256 GiB runoff output cap,
256 GiB future-derived allowance, 20 GiB HDD floor, 10 GiB SSD reserve and 8 GiB
spill allowance. Source-growth allowance is now zero for the two finished copies.
The process-tree working set is bounded by the one production worker's 3 GiB
address-space cap plus supervisor/headroom allocations; this is not a cgroup RSS
guarantee. The old drive may still be read to copy those derived checkpoints,
but original source bodies are resolved and verified exclusively on the new drive.
Keep both source copies and old frozen releases until the migration is accepted.

Run this viewer from the repository; Ctrl-C stops only the viewer:

```bash
rtk proxy .venv/bin/python -B data/national/phase11-overnight-2026-11-01/watch.py --watch
```

`overnight.log`, `current-launch.json`, `continuation-status.json` and, after launch,
`current-production.json` and `production/progress.json` record the actual stage,
PID, counters and failures. Destination-side `migration-2026-11-01/` contains the
consistent manifests, batched durable verification ledgers, certificates and strict
relocation registry. `continuation-ready.json` pins the full frozen runtime and
configuration before automatic execution. No running interpreter imports later
checkout edits. A restart must use the same pinned plan and accepted files; stale
inode/stat bindings, changed ledgers or unpublished checkpoint copies stop for
review. Do not run the old frozen production launcher: it preserves the old roots.
A launched or resumed job is not a completed national analysis.
