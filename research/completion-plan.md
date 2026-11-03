# 2026 audit completion plan

Document-ID: EA-COMPLETION-PLAN · Revision: 9 · Language: en

[Português](completion-plan.pt-BR.md)

Approved implementation scope: the full research workflow for the two 2026 presidential rounds. Each numbered phase is assigned to a fresh sub-agent; integration and acceptance are coordinated by the parent agent. This scope authorizes fitting in phases 15–17 and supersedes historical foundation-only restrictions for new artifacts; old releases retain their original meaning.

Execution status (3 November 2026): phases run one at a time, each assigned to a fresh sub-agent and reviewed before the next is dispatched. Phases 10 and 11 are complete; Phases 12–18 exist as Acre (AC) development artifacts only. This plan and the analysis plan are under revision after the methodology review of 3 November 2026; no new phase is dispatched until that revision lands. Phase 18 (marimo notebooks/dashboard) stays last. Current status, artifacts and remaining work are in the [implementation index](../docs/en/implementation-index.md).

| Phase | Deliverable |
| --- | --- |
| 10 | Verify both round identities; correct explicit round acquisition; preserve all original manifests and bytes. |
| 11 | Stream national processing through bounded disk-backed partitions, checksummed checkpoints and capacity guards; benchmark before expansion. |
| 12 | Decode official binary BUs, link totalized EA18 packages to BWEB, establish choice completeness and reconcile final hierarchies including ZZ. |
| 13 | Validate real log messages, sessions, copied histories and clocks; publish eligible operational measures with uncertainty. |
| 14 | Harmonize both rounds and locations; produce all 21 feature families and explicit availability ledgers. |
| 15 | Freeze research families and grouped partitions; protect test outcomes and preserve all inspection history. |
| 16 | Fit empirical baselines and quantile forests, simulate mechanisms and run one recorded final evaluation. |
| 17 | Investigate symmetric signals and unflagged controls; compute conditional bounds and baseline-relative sensitivities. |
| 18 | Deliver four linked bilingual marimo notebooks and a portable checksummed local/HTTPS dataset interface. |

Defaults: 2026 only; record 2022 backtesting and 2018 stress testing as future phases. Current machine only: durable storage on the HDD and the added output volume, bounded SSD scratch, at most half the allotted CPU capacity, measured real worker parallelism, one library thread per process, 4 GiB aggregate Phase 11 working memory, 8 GiB total per-object scratch budget, a 10 GiB SSD reserve and a 20 GiB HDD floor. Use 60/20/20 stable-location partitions and an additional 10% municipal stress holdout. Protect outcomes until frozen final evaluation. Previously inspected locations remain development data. The originally supplied manifests contain runoff URLs only. Corrected first-round acquisition used `.local-state/tse-2026-t1-verified.sqlite` and `turno-1-verified`; it finished on 31 October 2026, and both rounds were copied to the output volume and SHA-256 verified on 1 November 2026.

Dashboard: coverage/integrity, electoral comparisons, operations, models/investigations. Use standard marimo controls and Altair, shared AuditDataset reader, lazy bounded queries, explicit unavailable states and provenance-bearing exports. Never launch acquisition or fitting from reactive widget changes. Serve on loopback by default; actual remote hosting is future work.

Acceptance requires regression tests, real redacted fixtures, matching-population reconciliation, interrupted/resumed processing, resource measurements, protected-outcome tests, reproducible fitting and simulations, notebook/browser checks, local/HTTP equivalence, paired documentation and compact handoffs. A completed phase must distinguish implemented tools, executed real runs, and unresolved evidence. Missing sources, clocks, signatures or exchangeability never become invented facts. No automatic fraud classification or anonymous candidate attribution.

## Execution record

Phase 11's measured benchmarks, tuning studies, tranches, capacity reviews, move to the added output volume, copied-source migration and the final feature-oriented runoff run are recorded in the [Phase 11 handoff](../docs/en/handoffs/task-11.md) and the [feature-oriented processing guide](../docs/en/feature-oriented-processing.md). Their saved evidence is under `data/national/`.
