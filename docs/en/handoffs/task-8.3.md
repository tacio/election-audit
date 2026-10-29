# Task 8.3 — Immutable analysis and investigation foundation

Document-ID: EA-HANDOFF-8.3 · Revision: 1 · Language: en

Objective: persist protocol/run/snapshot, full exploration/null-result, score/calibration configuration, investigation, test-access and conditional-impact records without fitting. Prerequisites: [8.1](task-8.1.md), [8.2](task-8.2.md), [analysis guide](../analysis.md), immutable derivative seam only.

Files/interfaces: `analysis.py`, `analysis_partitions.py`, `analysis_ledgers.py`, `analysis_reports.py`; derivative producer seam; CLI/recipe `analyze PARENT --bundle FILE --store STORE`; existing `validate/query/report --language en|pt-BR|both`. Registry/output, partition plans/assignments, analysis ledger, impact scenarios and test status use manifest-driven tables. Parent facts and every prior artifact remain untouched. Configuration is preserved as exact bytes; source and schema pins, grains, logical digests, bounded SELECT and parent-chain integrity remain checked.

Deliverables: immutable record IDs and typed references; frozen/exploratory families include outcome/subgroup/window/scale/model/history; complete snapshots cannot omit registered or explored/null outcomes. Model configs remain fitted=false. Calibration membership and score/investigation populations are validated. Evidence anchors resolve to frozen source_object hashes; supplied review semantics remain assertions. Query workflow reserves untouched tests; training_features filters linked development units. Logged test inspection creates a new child and marks those stable locations development for later analyses, including reseeds. This is an auditable workflow, not a security barrier against reading parent paths, files or internal loaders directly.

Conditional scenarios: one exact snapshot/election/contest and candidate pair, normalized canonical count agreement, completed-ballot caps, explicit mechanism/margin assumptions and frozen anchors. Disjoint principals or corroborated union counts only; overlaps remain unavailable. Exact/at-most anonymous removal and switching bounds preserve unknown choices. Missing final margin stays unavailable; tied assumed margin needs one switch for strict win. No candidate attribution, causal identification, certified p-values/FDR, fitted model or fraud labels.

Acceptance: 16 focused Phase 8 synthetic tests passed, exit 0. Cases cover all 21 feature contracts/roles; normalized turnout 10 / 20 = 0.5 and unavailable model outputs; immutable parent→electoral→analysis query/validate/paired-report chain; persisted unknown identities; verified stable cross-round grouping; seed/order/resume/population/stress behavior; stale/conflicting/unresolvable evidence; immutable ledger restart/conflict atomicity; null results and complete-family snapshots; calibration/score populations; test access/contamination/reseed behavior; conditional overlap/caps/missing margin/tie. Final `rtk proxy env UV_OFFLINE=1 just check` passed, exit 0: lock, Ruff, contracts, paired docs and 160 offline tests in 33.478s. `analyze/query/report --help` passed, exit 0.

Limits: all acceptance is synthetic. Task 7.1 remains partial: official TSE BU adapter and real BU validation outstanding; normalized checks do not prove official compatibility/signatures. Source observation availability remains unknown, so numeric features remain scientifically ineligible. No real corpus read, national download or acquisition change. Git is unavailable; no commit/hash claim. Compact analysis context is bounded by max_events and configuration by 8 MiB; feature output is streamed in bounded SQL batches.

Exact next task: Phase 9 fresh agent gets only this handoff, index, analysis guide, CLI and tests/test_analysis*.py plus selected frozen-input/publication contracts when needed. Create a small reproducible synthetic demo and review bundle containing complete relative release chain, source evidence/configuration, SQL, availability/denominators, all null results and limits. Then explicitly select a bounded frozen AC–RJ raw pilot, inspect real-message semantics and provide reproduction/performance/review evidence. Preserve running acquisition/original bytes and the outstanding official adapter blocker. Do not reopen all research, download nationally, fit models or label fraud.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just analyze --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
```
