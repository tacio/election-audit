# Task 8.1 — Versioned feature foundation

Document-ID: EA-HANDOFF-8.1 · Revision: 1 · Language: en

Objective: immutable descriptive feature registry and long output ledger covering all 21 contracts. Prerequisites: [7.3](task-7.3.md), feature contracts and derivative seam.

Files/interfaces: `analysis.py`, `analysis_reports.py`, derivative producer extension, CLI/recipe `analyze`. `audit_feature_registry` records definitions, source tables, exact dependencies, components, units, denominators, roles, four specification variants and explicit blockers. `audit_features` streams batches from pinned parent views; no parent events or cycles are loaded as a Python list. Every principal/contest retains unavailable components.

Acceptance: two focused synthetic tests passed (exit 0): all 21 registry definitions/roles; operational→electoral→analysis publication, deterministic resume, parent preservation, inherited facts, turnout 10 / 20 = 0.5, unavailable model scores and zero scientifically eligible rows. Full suite follows task 8.3.

Limits: only normalized synthetic arithmetic; verified official BU adapter and real electoral validation remain outstanding from task 7.1. Numeric availability does not imply scientific eligibility. Source timing is unknown and blocks predictive use. No fitting, exchangeability claim or final national margin. Unknown ratios are not zero. Device/logistics adjust one specification and are possible mechanisms in another; no automatic turnout/manual/outage controls. First-round/history-dependent variants remain blocked without imports.

Next: task 8.2, persist seeded whole-location partitions using reviewed stable cross-round links; unknown identity is ineligible.
