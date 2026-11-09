# Feature-oriented national processing

Document-ID: EA-FEATURE-PIPELINE · Revision: 5 · Language: en

## Decision and scientific scope

On 2 November 2026 the user approved replacing mandatory national event
materialization with fused source-derived summaries, relevant evidence and indexed
replay, adding real parallelism while leaving the PC usable. This changes the
computational representation, not electoral semantics or eligibility rules.
All retained raw originals, frozen earlier event artifacts, source witnesses and
inspection-history registries remain authoritative and immutable. The current
runoff population retains 499177 source observations, excluding 596 protected/stress
observations and every content alias before semantic or cache access. First-round
copy verification does not authorize first-round analysis.

`source-operational-summary-v1` records exact structural event/message-kind counts,
all error diagnostics and their source-line hashes/member locators, per-member
source order and raw clock bounds/reversals/stream changes, recognized events and
context/error anchors. Unsupported-message counts remain exact. Ordinary unsupported
lines are represented by member/physical-line block indexes and SHA-256 fingerprints;
their individual hashes are derived from retained originals on demand. No message,
personal token or voter identity is retained. The summaries do not certify official
sessions, anonymous cycles, timezone rules, clock corrections, copied-history removal
or electoral results. Incomplete parsing remains partial; unavailable quantities
remain null/unavailable, not zero. Absence of an event table supplies no readiness.

The fused parser preserves archive size/directory/depth/member/CRC/line guards.
Seekable small members use bounded 2 MiB spools, spilling only when necessary.
Calendar validation avoids repeated locale parsing. Typed callbacks avoid temporary
event JSON, reparsing and repeated event-ID generation. Error/evidence amplification
has an explicit bound and fails rather than truncating required diagnostics.
A source is checked against its pinned relocation ledger, hashed once on an opened
file, parsed from that same descriptor, then checked for inode/size/mtime/ctime
stability. There is no fallback to an old raw-data path.

`grouped-source-summary-shards-v3` uses worker processes, bounded prefetch/results
and one grouped SQLite writer. A shard contains indexed objects, members, blocks,
anchors and errors. SQLite FULL transactions, file fsync, atomic directory publication
and a durable group ledger replace per-event/per-object publication overhead.
Published unledgered groups are checksum-checked and reconciled after interruption;
only private unpublished staging is rebuilt. Completed old event artifacts retain
explicit references for optional forensic reuse. Logical output is independent of
worker completion order; physical SQLite bytes need not be identical.

## Resource envelope and practical use

Defaults are 4 GiB aggregate RAM, at most half the allotted CPU capacity, nice +10,
one library thread per process and low best-effort I/O priority. Affinity chooses
whole physical-core/sibling groups where available and leaves desktop headroom.
On this 12-logical-CPU/6-core host the ceiling is 600% CPU, with CPUs 0,1,2,6,7,8
and three initial workers. SMT, shared caches and I/O still contend; this is not
physical isolation or a desktop-latency guarantee. A user-owned systemd slice enforces
one shared CPU quota and MemoryMax=4 GiB, with swap disabled, across auxiliary jobs,
tuning and production. No root or host-global cgroup setting is changed.
The portable fallback uses inherited affinity, bounded address-space allocations,
thread limits and process-tree RSS observation. It needs at least two allotted CPUs;
a one-CPU system needs a separately enforced fractional CPU quota. RAM and worker
limits include the parent, writer, queue and library overhead, not per-worker 4 GiB.

HDD reserves remain 20 GiB, with an explicit 256 GiB output cap and 256 GiB allowance
for future derived data. SSD reserve is 10 GiB plus 8 GiB bounded scratch. No second
144 GB raw copy is needed. Smaller hardware can select fewer workers, smaller groups,
less prefetch and explicit disk allowances; scientific parsing and protocol are
unchanged. Resource failures stop the job and retain durable completed groups.

The existing [national processing guide](national-processing.md) describes source
acquisition, manifest verification, development samples and frozen eligible metadata
scopes. A scope workload is a metadata prerequisite; it does not require a national
event table. Keep its source scope SQLite file, exclusion registry and verified raw
relocation registry accessible. Absolute raw aliases are local custody bindings;
create and verify bindings for your own hardware rather than editing frozen files.

Prepare a manual job using the actual CLI and explicit budgets:

```bash
.venv/bin/python -B -m election_audit.national_parallel prepare --scope-workload work/scope --output work/summary-config --store /path/to/derived/summary --memory-gib 4 --cpu-fraction 0.5 --workers 2 --batch-objects 32 --prefetch 1 --hdd-reserve-gib 20 --ssd-reserve-gib 10 --scratch-gib 8 --output-gib 256 --future-gib 256
.venv/bin/python -B work/summary-config/run_frozen.py run --max-objects 112
.venv/bin/python -B work/summary-config/run_frozen.py status
```

Use an external user cgroup around the frozen launcher when available; affinity
and priority also apply in manual mode. `national_summary_tuning` runs a finite,
balanced forward/reverse sequence of real worker/group configurations against the
same explicit eligible development selection, with fresh stores, at most 900 seconds
and 1 GiB total tuning output. It persists code/source/config pins, every trial,
CPU/RSS/cgroup/I/O telemetry, reasons, repeated medians/MAD and a recommendation.
Unsafe or failed trials stop/back off; interrupted artifacts stay available for
review. A changed identity requires a new study. Gains within noise prefer fewer
resources. The recommendation is the best observed safe local configuration,
not a global optimum. Ordinary OS caches may be warm; cache eviction is not performed.
Tuning changes processing workers/groups only, not scientific feature specifications,
models, protected partitions or final evaluation.

## Revalidated Phase 10–18 dependencies

| Phase | Revised input/output and remaining gate |
|---|---|
| 10 | Finished acquisition plus independently verified raw/metadata custody; absent/unknown publisher rows remain unknown. |
| 11 | Fused summaries, relevant evidence and replay indexes; measured resource-bounded eligible runoff execution. No mandatory national full-event table. |
| 12 | Independent canonical BU/results, full choices, totalization linkage and BR/UF/municipal final totals. Structural logs do not substitute for these records. |
| 13 | Validate session semantics, clocks and copied histories from anchored streams and targeted raw replay. The older global dictionary/max-event reconstruction path still needs a bounded partition/replay adapter before national use. |
| 14 | Materialize qualified feature marts from validated operational summaries/replay and electoral references, with explicit denominators, unknowns and lineage. A Phase 11 object summary is not a feature-release-v1 release. |
| 15 | Freeze targets, roles, families and grouped partitions using qualified feature definitions. Prior inspected locations remain development data. |
| 16 | Fit/calibrate models only on qualified marts; independent validation, power, multiplicity and protected final-evaluation access gates remain unchanged. |
| 17 | Case evidence uses indexed source windows, explicit access/inspection history and optional complete per-object forensic event replay. No anonymous-cycle candidate attribution. |
| 18 | Marimo/dashboard last; explore aggregate marts, coverage, readiness, performance and source evidence pointers without loading a national event lake. |

## Preservation of all 21 feature families

Every family's existing contract and evidence/readiness prerequisites remain binding.
The following is a dependency map, not a claim that these features are implemented
or currently eligible.

| Feature family | Summary/replay input and independent prerequisites |
|---|---|
| population_coverage | All source witnesses and parser states; expected population/composition/location denominators still required. |
| session_summary | Supported anchors, member bounds and raw replay; reviewed session selection and copied-history deduplication still required. |
| cycle_duration_gap | Ordered anchors/windows; validated anonymous cycles, gaps, exposure and clocks still required. |
| processing_event_availability | Explicit receipt/processing/generation/publication metadata; download time is not transmission time. |
| late_voting | Completion anchors and replay; selected deduplicated sessions, absolute clocks and overseas rules still required. |
| section_results | Canonical eligible BU, complete choices and composition, independent of log summary counts. |
| unanimous_results | Complete reconciled BU categories, including special/unknown choices and positive total. |
| result_timing | Explicit result/package endpoints, semantics and comparable clocks. |
| round_comparison | Both rounds' canonical counts and composition/location harmonization; no individual vote-transfer inference. |
| audit_features | Qualified component marts and frozen roles/specifications; unavailable inputs stay explicit. |
| turnout_target | Official attendance/electorate denominators; log completions supply corroboration only. |
| candidate_share_target | Fixed official A/B identities and reconciled candidate-only denominator. |
| blank_null_targets | Complete official category semantics and total ballots. |
| peer_covariates | Location/history/pre-election imports and frozen leakage-safe design. |
| device_logistics | Stream/member boundaries and targeted technical replay; validated device/version exposure and analytic roles. |
| integrity | Raw/source hashes, indexed exact copy replay and independent BU/final/RDV/signature evidence; hashes are not signatures. |
| conditional_unusualness | Qualified features, frozen design, trained/calibrated models and adequate overlap/power. |
| multiplicity | Full prespecified family, valid p-values and protected access history. |
| validation_investigation | Synthetic/benign validation plus authorized source replay and independent corroboration. |
| conditional_margin_bounds | Validated anonymous-cycle/mechanism caps and independent coherent final margin; no candidate attribution of anonymous cycles. |
| counterfactual_excess | Reconciled official results, qualified fitted/calibrated models, mechanism assumptions and full-pipeline resampling. |

## Verification and measured execution

The 112-object baseline was selected before result inspection by minimum source hash
within each already approved UF/size band. Its fresh old-path run took 161.91 seconds.
A full safe 476-object reference comparison validated 4,843,988 structural events and
531,048 retained anchors, with exact counts, diagnostics, error details, source-line
hashes/member locators and block event/unknown counts. Fixtures additionally check
exact on-demand event IDs and all replayed fields, nested archives, missing/corrupt
sources, unknown block fingerprints, output limits and protected-source exclusion.
Real subprocess tests compare one/two workers, logical determinism, resume and
published-but-unledgered shard recovery. Benchmark, tuning and production evidence
is under `data/national/phase11-feature-oriented-2026-11-02/`.

## Completed runoff run

The production job processed the whole eligible runoff scope between 2 and 3
November 2026 (finished 12:28 UTC on 3 November) with three workers and batches of
32 objects. All 498581 eligible objects completed with 0 failures: 498575 complete
and 6 partial parses, the partials retaining all 190 errors. It scanned 5032537448
structural events in 35992 seconds (13.85 objects/second, 111% average CPU, peak
process-tree RSS 195719168 bytes) and wrote 68797890560 bytes of recovery
checkpoints. At completion host I/O pressure was 94% (some, 300-second average)
while the job used 111% of its 600% CPU allowance: storage I/O, not CPU, limited
throughput.

The analytical release
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` holds 546620085
bytes of Parquet: `source_summaries` (498581 rows), `source_witnesses` and
`source_index` (499177 rows each), `members` (511541) and `blocks` (10085027).
Its manifest records `complete_requested_scope=true`, `full_national_complete=false`
(the 596 protected/stress observations are deliberately absent) and
`scientific_eligibility=unavailable_structural_only`. About 90% of scanned events
belong to message classes the structural parser leaves `unknown`; the semantic
pass (Phase 21 of the [completion plan](../../research/completion-plan.md)) must
classify them before sessions, cycles or clocks become eligible. Round 1 has not
been processed.

The per-object counts are not runoff measures. Each runoff `logd.dat` contains
setup events from September, the first-round session and the runoff session (the
earliest member readings fall in September, and 3004 members end on
4 October), so `observed_authorizations` and `observed_completions` (252940011 and
252882361 in total) count both rounds. Use them only as structural diagnostics. The job pointer is `data/national/current-phase11.json`.

## Compact analytical finalization and replay

Recovery uses at most 32 objects per checkpoint (about 15,600 shards for this scope).
Finalization reads the committed shards sequentially once and writes five typed
analytical tables: `source_summaries`, `members`, `blocks`, `source_index` and
`source_witnesses`. Parquet parts target 128 MiB, with bounded row-group overshoot;
there is no partition per section or UF. Anchors/errors remain available through
recovery evidence and targeted raw replay. All full source/line hashes retain 256
bits; per-shard integer source dictionaries and binary hashes reduce checkpoint
storage without changing logical identities. Ordinary analytical queries need the
Parquet release alone, including explicit pending/protected/outside-selection states.
Raw CAS is required for forensic replay; checkpoint SQLite is required for recovery,
not for each analytical query. One consistent audit-state SQLite file accompanies
the deterministic checksummed manifest for provenance.

Prepare metadata-only scope state before a first summary job if necessary; this
opens no log body and does not materialize events:

```bash
.venv/bin/python -B -c "from election_audit.national_workload import initialise; initialise('work/scope')"
```

Launch the complete eligible job with shared user-cgroup enforcement and automatic
analytical finalization after the producer completes:

```bash
.venv/bin/python -B -m election_audit.national_parallel launch work/summary-config --unit election-audit-summary --analysis-output /path/to/derived/analysis-release
```

The launcher creates a narrow user slice with the configuration's CPU/RAM ceilings,
inherited affinity, nice +10 and best-effort I/O priority7. `--no-cgroup` explicitly
selects the affinity/AS/RSS fallback. A paused or completed producer can also publish
an immutable committed-prefix dataset; the producer lock prevents publication and
ingestion from racing over the combined output allowance:

```bash
.venv/bin/python -B work/summary-config/run_frozen.py export --output /path/to/derived/partial-analysis --target-mib 128
```

Publication reserves quota durably, validates shard checksums, writes/fsyncs typed
parts and atomically publishes the release. An interrupted reservation stays
conservative until reviewed/retried; a completed release is checksum-idempotent.
Missing summaries are absent and explicitly unavailable in the witness/index tables.
Observed counts on partial parses are lower-bound observations, not complete totals.
No human test access or qualified feature readiness is granted by publication.

For a bounded real autotune, create a JSON configuration with absolute paths:

```json
{
  "old_workload": "/absolute/project/work/scope",
  "development_sample": "/absolute/project/work/development-sample",
  "selection": "/absolute/project/work/safe-selection.json",
  "resources": "/absolute/project/work/resources.json",
  "output": "/absolute/project/work/tuning",
  "store": "/absolute/derived/tuning"
}
```

`resources.json` contains the `resources` object from the prepared summary config;
`safe-selection.json` contains `{"sha256s": ["..."]}` selected by metadata from the
previously registered development sample. The tuner checks registration, source
membership, protected aliases, code/config/source pins and repeated noisy throughput.
Run it inside the same resource-bounded user slice when available:

```bash
.venv/bin/python -B -m election_audit.national_summary_tuning work/tuning-config.json
```

Read `recommended.json` and apply its workers/group values through the corresponding
`prepare --workers` and `--batch-objects` flags. Manual settings opt out of tuning;
CPU/RAM/disk controls still apply. Completed trials resume only with matching identities;
failed/interrupted trial artifacts remain for diagnosis. A changed code identity needs
a new study or an explicit reviewed compatibility record. The current adoption record
identifies one subsequent error-guard fix: an unavailable overlong-line hash is no
longer mislabeled as a full-line hash. None of the 476 development sources hits it;
ordinary parse/writer/resource kernels are unchanged, and timings remain attributed
to their original frozen runtime.

The controlled 112-object comparison measured a final median 10.117 objects/s with
three workers/group32 versus the old fresh-output baseline of 0.692 objects/s: 14.6×
for this workload. The wider 476-object run scanned 4,843,988 events in 33.805 seconds,
producing 66,191,360 checkpoint bytes versus 164,696,064 before physical normalization.
Peak summed process-tree RSS was 187,535,360 bytes; average CPU was 110% (one logical
CPU is 100%; the imposed ceiling is 600%). The published development analysis release
has five Parquet files totaling 78,251,772 bytes, with all 499177 source witnesses and
explicit unknown/protected states. Fresh one-thread DuckDB aggregate queries took
0.0336 seconds with potentially warm files, without SQLite/raw reads. These measurements
are not a guarantee for cold disks, larger tails, other hardware or later models.

Trial wall time includes runtime verification, initialization, worker startup, queues,
writing/durability and shutdown. Per-object worker time excludes writer/queue costs.
RSS sums all descendant processes; cgroup memory accounting also differs from RSS.
Physical I/O counters may be zero for warm cached reads; host/cgroup pressure and
throttling counters are retained. The later phases gain compact-input scan efficiency,
but BU/signature validation, new raw-message semantics, reconstruction, fitting and
resampling still require independent correctness/performance checks. The current
redacted replay reconstructs exact structural fields/IDs; new semantic classifiers
must stream retained originals under the Phase13 evidence/access protocol.
