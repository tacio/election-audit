# Task 9.1 — Offline synthetic walkthrough

Document-ID: EA-HANDOFF-9.1 · Revision: 1 · Language: en

Prerequisites: [8.3](task-8.3.md), [index](../implementation-index.md), [analysis](../analysis.md), [reproduction](../reproduction.md), [backfill](../backfill.md). Task 7.1 remains partial; no real BU or national validation is claimed.

Objective/files/interfaces: Production walkthrough.py and reproduction.demo ship in the wheel without importing tests. Deterministic ZIP bytes contain mixed device dates, exact copied history, replacement, manual request/cancellation, unresolved clocks and malformed nested content. Hash-anchored review assertions are synthetic only. Known member/principal denominators are 3/2; normalized turnout is 10/20 = 0.5. Four immutable stages preserve partitions and five ledger records including a complete registered null result. Unknown identity and scientific eligibility remain unavailable.

Deliverables/acceptance/limits: data/phase9/demo; reports/operational, reports/electoral and reports/analysis contain paired visibly SYNTHETIC/SINTÉTICO reports with matching IDs/revisions. Frozen source observations retain real capture time; synthetic source timestamps are explicit fixture values. Fresh captures need not share identities.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
```
