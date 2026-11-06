# Task 22 — Section feature table v2

Document-ID: EA-HANDOFF-22 · Revision: 1 · Language: en

Objective: one row per principal section and round, for 2026 and 2022, with the
cross-round crosswalk, voter-profile covariates, polling-place keys, device model
and software, clock rule, integrity status, operational measures and a population
ledger, built from frozen inputs and without reading results or operational values
outside the development UF.

Prerequisites: [completion plan](../../../research/completion-plan.md) Phase 22;
the [study protocol](../../../research/analysis-plan.md) sections 2 and 7; the
Phase 19 inputs ([handoff 19](task-19.md)), the Phase 20 releases
([handoff 20](task-20.md)) and the Phase 21 semantic pass ([handoff 21](task-21.md));
the protection exclusions `data/national/phase11-protection-2026-10-31/exclusions.json`.

Files and interfaces: `election_audit/semantic_pass.py` (`session-aggregates-v3`),
`election_audit/section_table.py` (`section-table build`, `section-features-v2`),
`tests/test_section_table.py`, `election_audit/cli.py`, `justfile`;
[section table](../section-table.md), [semantic pass](../semantic-pass.md#version-3-phase-22),
[observation register](../observations.md). A build writes a new root with
`release/` (`sections.parquet`, `units.parquet`, `ledger.json`, `manifest.json`
and `restricted/`); the output must be new.

Deliverables:

- Semantic pass v3, both years and rounds, in
  `~/data/election-audit-stage/phase22/v3-national-r{1,2}-20261105/` and
  `v3-national-2022-r{1,2}-20261105/`: 1704924, 3393756, 1805887 and 3570943
  sessions, no object errors.
- Section tables in `~/data/election-audit-stage/phase22/table-2026-20261106/`
  (998496 rows, 499248 units) and `table-2022-20261106/` (945386 rows, 472693
  units).
- Copy deduplication by block lineage, legal close rules with Amazonas resolved
  from printed closes, clock states, harmonized units and the ledger.
- Observation register entry O11 (Mato Grosso clock settings in round 2).
- Not produced: any reading of results or operational values outside AC; 2022
  integrity status (Phase 20 did not run for 2022).

Acceptance (5–6 November 2026):

- Every session shard of the four v3 runs has the nine new columns; every column
  shared with the earlier releases (2026 v1, 2022 v2) is equal in every session,
  segment and object row, both ways.
- The tables' public counts are in the [section table guide](../section-table.md#national-results).
  Every unit is `same_principal`; the ledger accounts for every section of each
  round.
- The chunked build equals the earlier per-UF build in content (every Parquet
  file, both ways, and the ledger) on 2022 SP and on both national tables; peak
  memory fell from 5.2 GB to 3.9 GB (2026) and 3.3 GB (2022).
- `UV_OFFLINE=1 just check` passes with 381 tests.

Decisions:

- Copies of one session are recognized by device, block start and rank in block,
  never by text or time; prefix equality of the copies is left to Phase 20b.
- Urn clocks are local. The expected close comes from the legal time zones; for
  Amazonas, only from a municipality's unanimous printed closes, else unresolved.
- The BU-side model is compared with the last kept session's model, since earlier
  sessions can belong to a replaced urn.
- The build holds Python rows for whole municipalities of one UF at a time (about
  10000 sections), with a 1 GB DuckDB limit, to stay inside the 6 GiB budget next to
  a running pass.
- The machine suspended twice during the runs (5 November 20:58–21:51 and
  23:10–06:56). The passes resumed without errors; a sleep inhibitor did not
  prevent the second suspend, so long runs need the desktop's automatic suspend
  turned off.

Unresolved issues:

- Eight 2026 round-1 sections whose log model differs from the BU signer's model,
  and 704 Amazonas sections without a close rule in 2022 (94 in 2026): Phase 20b.
- The 2026 table ran next to the 2022 pass at about 6.9 GB in total, above the
  6 GiB budget, before the chunked build fixed it; nothing failed, and more than
  20 GB of RAM stayed available.

Exact next task: Phase 20b in `../election-audit-20b` (branch
`phase-20b-integrity`): official ASN.1 specifications, national certificate chains
with the revoked serials, the national I1 rerun, the I6 prefix re-read, the
DataUrnas-BR checks and the Phase 22 items. Ask about TSE's reply (protocol
83529705172533) after 25 November 2026.
