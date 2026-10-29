# Task 2.2 — Feature/readiness contracts

Document-ID: EA-HANDOFF-2.2 · Revision: 1 · Language: en

Objective: identify required inputs, denominators, roles and explicit unavailable
states for every planned mart and protocol target without fitting models.

Prerequisites: task 2.1 and `research/analysis-plan.md`; no new data import required.

Files/interfaces: `election_audit/resources/contracts/features.json`, paired
`docs/en/feature-readiness.md` / `docs/pt-BR/feature-readiness.md`, contract validator
and its failure-oriented tests. `load_contract("features")` exposes 21 feature
contracts, 18 required-input definitions, readiness states/reasons and ledger fields.

Deliverables: operational coverage, session summaries, processing-event
availability, late voting, canonical section results, strict unanimity, result
timing, harmonized round comparison and long audit-feature roles; turnout/share/
blank-null targets, covariates, device/logistics alternatives, integrity,
unusualness/calibration, multiplicity, validation/investigation and conditional
impact/counterfactual prerequisites. Every feature starts `not_evaluated`.
Exclusions: no features computed, national model, fitting, fraud labels or
candidate attribution of anonymous cycles.

Acceptance: `rtk proxy env UV_OFFLINE=1 just check` exited 0 with 43 passing tests,
registry validation and documentation parity checks. Tests cover missing-denominator
prerequisites and package processing availability independent of BU imports.

Decisions: domestic after17 is completion strictly after 17:00:00 Brasilia;
equality does not count, overseas is separate and unresolved clocks block the
absolute-time feature. Strict unanimity requires positive total, exactly one
candidate with all ballots, complete categories and zero blank/null/special/
unresolved votes. Partial AC–RJ is never national inference. Other rounds/history
are explicit imports. Zero denominator gives undefined ratio, not zero. Roles and
mechanism specifications prevent automatically controlling away hypothesized effects.

Unresolved: no frozen input, validated reconstruction or electoral imports are
provided by these registries. Readiness requires later per-unit evaluation.
Exchangeability, independent evidence, mechanisms and counterfactuals may remain
unsupported even with populated tables. No final national margin is asserted.

Exact next task: **2.3**, bilingual protocol/acquisition references and docs checks;
consult existing English research files, README reference, docs pair convention
and template. Completed here; handoff [2.3](task-2.3.md).
