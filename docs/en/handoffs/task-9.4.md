# Task 9.4 — Resumable backfill and final onboarding

Document-ID: EA-HANDOFF-9.4 · Revision: 1 · Language: en

Prerequisites: [8.3](task-8.3.md), [index](../implementation-index.md), [analysis](../analysis.md), [reproduction](../reproduction.md), [backfill](../backfill.md). Task 7.1 remains partial; no real BU or national validation is claimed.

Objective/files/interfaces: backfill reuses frozen parse/cache/context/per-object shards and verified releases; no acquisition is run. Paired backfill guide documents explicit whole-available AC–RJ commands, later additional UFs/ZZ and separate round/history imports. Bounded pilot restart and interruption before release rename are verified; the entire population backfill was not executed. README onboarding now describes all implemented stages, demo/pilot/reproduction/report commands and task 7.1 next action.

Deliverables/acceptance/limits: Resource defaults remain 4 parser workers, 4 DuckDB threads, 12 GiB memory, 8 GiB spill, 10 GiB reserve. Initial SSD free approximately 31.6 GB leaves approximately 12.3 GB after reserve/spill, before derived data/headroom. Current Parquet facts and DuckDB are co-located; full-UF metadata is material even for five principals. No promise the full backfill fits. Six new offline tests plus existing 160 passed (166 total); final check output is retained under data/phase9/verification. Git unavailable: no commit claim. Preserve downloader/live raw bytes and immutable releases. Exact remaining task: obtain accessible official TSE BU documentation/original data, implement verified adapter and run real validation for partial task 7.1; review real-message/clock/session evidence before granting operational eligibility. No model fitting, assessed exchangeability, coherent national margin or fraud labels.

```sh
rtk proxy env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
rtk proxy env UV_OFFLINE=1 just check
```
