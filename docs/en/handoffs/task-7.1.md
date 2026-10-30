# Task 7.1 — Explicit electoral imports

Document-ID: EA-HANDOFF-7.1 · Revision: 2 · Language: en

The source-access/official-adapter gap is closed for the verified AC BWEB layout.
The normalized importer remains available. `official_bu.py` adds a bounded,
versioned official CSV adapter through `read_import` and `import-results`.
The original archive, checksum, catalog/resource metadata, decompressed CSV and
bundled dictionary are preserved by hash in immutable derivatives. Record witnesses
cover dimensions, composition, choices, totals and raw processing-event tokens.
`bweb-2026-layout.json` pins dictionary/header/encoding/category semantics.

Real AC source: 1254611-byte ZIP, SHA-256
`35c1f1676e04d0824eb57df158f40d3c1e943926fd4754933a9d2863ccf06e1b`;
published SHA-512 and ZIP CRCs pass. 17622 input rows split into 8697 presidential
and 8925 excluded governor rows. 2270 presidential principal sections, 2411 member
sections and 668 locations are imported. Published choices sum to 453654 votes.
All 2270 published-vote-sum/attendance and electorate-accounting checks match.

Limits: missing choices never become zero; no complete choice ledger is certified.
Apurada does not certify Totalizado; official result status remains unknown.
No canonical electoral ratio, timezone conversion, independent final hierarchy,
signature certification, national BU coverage or scientific eligibility is claimed.
BU composition uses a separate source snapshot; operational linkage needs explicit
review. Other layouts/categories fail until reviewed. First-round/history and
external final/electorate references still use explicit normalized contracts.

Regression coverage includes an attributed real CSV subset and exact dictionary,
unknown choices/clocks/status, office filtering, aggregations, retransmissions,
contradictory immutable records, corrupt pins/checksums, unknown categories,
resource/encoding/header/dictionary bounds and immutable derivative relocation.
Official verification survives loader/validator/report and snapshot-specific feature
quality flags; no model is fitted. Earlier source-access failures remain historical
evidence. See [guide](../electoral-results.md) for the bundle and real validation commands.

Acceptance: `rtk just check` passed with 177 offline tests, formatting, lint,
lock, contract registries, paired documentation and harmless command/SQL checks.
Real source validation is in `data/official-bu/ac-runoff-2026-10-30/validation-final.json`;
immutable release validation, reports and the current release ID are beside it in
`release-validation.json`, `reports/` and `run-evidence.json`. New observations of
identical bytes append separate frozen result/event/observation witnesses without
changing old snapshots. Original log acquisition and existing pilot releases are unchanged.
