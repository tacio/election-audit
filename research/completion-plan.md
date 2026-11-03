# 2026 audit completion plan

Document-ID: EA-COMPLETION-PLAN · Revision: 11 · Language: en

[Português](completion-plan.pt-BR.md) · [Study protocol](analysis-plan.md)

Approved scope: the full research workflow for the two 2026 presidential rounds,
with the 2022 presidential election as a negative control. The study design is the
[study protocol](analysis-plan.md); this plan turns it into phases. Each numbered
phase is assigned to a fresh sub-agent, runs alone and is reviewed before the next
is dispatched. Current status and artifact locations are in the
[implementation index](../docs/en/implementation-index.md).

## Status (3 November 2026)

| Phase | Deliverable | State |
| --- | --- | --- |
| 10 | Verify both round identities; explicit round acquisition; preserve all original manifests and bytes | Done |
| 11 | Resource-bounded national structural processing; benchmark before expansion | Done for the 498581 eligible runoff logs (structural only; see below) |
| 12–18 | First-version phases: binary BU, operational semantics, features, protocol, models, investigations, notebooks | Closed as Acre (AC) development pilots; tools are reused below |

The methodology review of 3 November 2026 replaced the first-version definitions of
Phases 12–18. Their code and AC artifacts stay as development pilots and their
handoffs stay as dated records. The revised work continues as Phases 19–26, so
that new handoffs never overwrite old ones.

What Phase 11 does and does not provide: per-log structural counts, member
structure and block hashes for every eligible runoff log. Each runoff log also
contains setup and first-round events, so its counts mix rounds; there is no
session, clock or timing information; the 596 protected/stress logs and the whole
first round are unprocessed. Every operational measure therefore needs the
semantic pass of Phase 21.

## Revised phases

| Phase | Deliverable | Reuses |
| --- | --- | --- |
| 19 | **National inputs.** Acquire and freeze, with checksums and immutable manifests: BWEB for 27 UFs and ZZ, both rounds; binary BUs, RDVs and signatures for totalized packages; hierarchical results (EA20); voter profile by section and polling places; 2022 presidential BWEB, BUs, logs and voter profile, both rounds; TSE election-day integrity test reports. Pin the certified manifest copies as analysis inputs and document the stale manifest files. | `official_bu`, `electoral_imports`, downloader |
| 20 | **Tier 1 integrity checks (I1–I9)** nationally, both rounds: deterministic reports with full discrepancy tables, source hashes and a population ledger. Collect independent printed BU copies for I8. | `binary_bu`, `electoral_verification` (AC pilot) |
| 21 | **National semantic log pass,** both rounds and 2022: one streaming pass per round applies the reviewed message rules and writes per-session aggregates (cycles by authorization method, suspensions, opening/closing readings, hourly counts, cadence, clock events), round-1 block comparisons (I6) and a message-template vocabulary. Equivalence-tested against the AC event-level adapter before the national run. | `national_summary`, `operational_review`, `real-log-rules.json` |
| 22 | **Section feature table v2:** cross-round harmonized units with an explicit crosswalk, voter-profile covariates, polling-place keys, device model and software, operational measures, availability ledger. | `features` (AC pilot) |
| 23 | **Development modelling, power study and protocol freeze.** On development data only: beta-binomial swing model, within-location contrasts, cross-fitting, the quantile-forest comparator, the C1–C6 tests and their simulated nulls; fix the known first-version model defects (fixed `1e-6` scale floor, tied zero scores, leaf selection inconsistent with location-held-out calibration, optimistic forest-vs-baseline comparison). Run the injection study and report minimum detectable manipulation. Draw and hash the sealed holdout. Freeze and publicly pre-register (OSF and signed git tag). | `research_models`, `research_protocol`, `research_evaluation` |
| 24 | **Confirmatory run,** once: cross-fitted scores for every section, C1–C6 with BY control, 2022 negative control, placebo tests; then the single opening of the sealed holdout. All deviations recorded. | Phase 23 frozen code |
| 25 | **Investigations and outcome sensitivity:** triage packets for ranked and random unflagged locations, corroboration requests, conditional margin bounds and baseline-relative excess. | `investigations` |
| 26 | **Publication:** bilingual findings report led by integrity results and minimum detectable manipulation; claims register; laptop replication kit; marimo explorer over the released tables; review bundle rebuilt on a clean machine. | `dashboard*`, `reproduction` |

## Resource and I/O rules

The machine has two rotational data drives and an NVMe root (eCryptfs home, about
241 GB free on 3 November after staging). Phase 11 read 91.5 GB at about 2.5 MB/s
with 94% I/O pressure, while writing 68.8 GB of checkpoints to the same drive to
produce a 547 MB release. The 3 November benchmark traced this to read order: on
the data drive, section (manifest URL) order reads at 1.9–3.5 MB/s and physical
order at 73–92 MB/s. Both 2026 rounds are now staged on the SSD with hash
certificates (144.4 GB in 86 minutes). Every full pass must therefore:

- read raw objects from the certified SSD staging or, on a rotational drive, in
  physical or path order, never in section order, and group results afterwards;
- benchmark parallel reads on the SSD before choosing worker counts (one reader
  re-hashed at 56–63 MB/s through eCryptfs);
- keep checkpoint and output volume proportional to the result, off the drive
  being read;
- write large, sequentially read archives (bulk TSE zips) to the ext4 data drive,
  not to the SSD or the shared NTFS drive;
- stay within half the CPU, 4 GiB of aggregate RAM and one library thread per
  process, with explicit SSD and HDD free-space floors (staging used 100 GiB on the
  SSD).

## Data policy

- Development data: AC, the five pilot UFs (AC, AL, DF, ES, PR) and every location
  in the Phase 11 and Phase 15 inspection registries.
- Sealed holdout: 10% of polling places drawn by UF at the freeze (Phase 23) and
  opened once, after the confirmatory run (Phase 24).
- The 596 protected/stress runoff logs stay unread until the freeze, then follow
  the same draw as every other location.
- Analyses read the certified manifest copies by hash, never live manifests.
- Unknown is never zero; no fraud labels; no candidate attribution of anonymous
  cycles.

## Acceptance

Each phase needs regression tests, real redacted fixtures, population ledgers that
reconcile, interrupted/resumed runs where long, resource measurements, paired
documentation and a compact handoff. A phase report distinguishes implemented
tools, executed real runs and unresolved evidence. Missing sources, clocks,
signatures or exchangeability never become invented facts.

## Execution record

Phase 11's measured benchmarks, tuning studies, tranches, capacity reviews, move to
the added output volume, copied-source migration and the final feature-oriented
runoff run are recorded in the [Phase 11 handoff](../docs/en/handoffs/task-11.md)
and the [feature-oriented processing guide](../docs/en/feature-oriented-processing.md).
Their saved evidence is under `data/national/`. The first-version Phase 12–18
pilots are recorded in their handoffs.
