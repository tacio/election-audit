# Task 19 — National inputs

Document-ID: EA-HANDOFF-19 · Revision: 1 · Language: en

Objective: acquire and freeze, with checksums and immutable manifests, every
national input the revised Phases 20–26 read: BWEB for both 2026 rounds and 2022;
binary BUs, RDVs, signatures and logs; the hierarchical EA20 results; voter profile
and polling places; media correspondences; GEDAI preparation logs; the
election-day integrity test reports; and pinned certified manifests.

Prerequisites: [completion plan](../../../research/completion-plan.md) Phase 19;
the Phase 10 acquisition and certified migration
([handoff 10](task-10.md)); the [acquisition reference](../acquisition-reference.md).

Files and interfaces: `bulk_acquisition` (`bulk-download fetch|verify`),
`sa_logs` (`sa-logs fetch|summarize`), `results_hierarchy`
(`results-hierarchy fetch`, `results-hierarchy-v1`), `integrity_documents`
(`integrity-docs ingest`, `integrity-documents-v1`), the pin file
`election_audit/resources/pins/certified-manifests-2026.json`, and the matching
`justfile` recipes. Every fetch writes into a new root, stores bodies
content-addressed and read-only, and keeps the source URL, ETag and Last-Modified.

Deliverables:

- Open data (CKAN): 2026 and 2022 BWEB, results, voter profile and polling
  places, media correspondences, and 2026 GEDAI logs, all 12 small datasets
  complete with every published `.sha512` matching.
- Bulk BU/RDV/log archives: 56 per year (2026: 219.2 GB, 2022: 168.5 GB),
  re-hashed against their manifests on 2026-11-04.
- SA contingency logs: all 60 (31 and 29), byte-identical to the bulk archives.
- EA20: 5815 files per round (BR, 27 UFs and ZZ, 5757 municipalities, progress
  files), every unified file final. Round 2 was generated on 2026-10-25. Round 1
  was generated on 2026-10-05, except all of ZZ (186 cities and the ZZ total),
  regenerated on 2026-10-24.
- Certified manifests: digests pinned; both copies of each manifest and both
  certificates re-hashed and matching on 2026-11-04. The stale pre-split manifest
  stays documented in the [acquisition reference](../acquisition-reference.md).
- Integrity test documents: a browser-collected sample of ten courts (SP, AC,
  AL, DF, ES, PR, MG, RJ, BA, RS), 125 documents filed by SHA-256, plus one dead
  link recorded as not served.

Acceptance: `just check` passes with 348 tests. Real runs:
`results-hierarchy fetch` for both rounds (5815 files each, 0 not final);
`integrity-docs ingest` (125 filed, 0 missing, 1 not served); the SHA-256 of both
manifest copies and certificates equals the pins.

Decisions:

- EA20 and totalization reports change after retotalizations, so every fetch is
  a dated snapshot. Each EA20 row keeps the file's own generation stamp.
- Integrity documents are matched to records by SHA-256, never by file name,
  because browsers rename downloads.
- TRE sites refuse scripted requests. They were read in the user's own browser,
  without changing request identity.
- The integrity documents are a sample. Courts publish different things: SP, DF,
  ES, MG, RJ and BA post test minutes; AC, AL, PR and RS post only the
  urn-selection lists.

Unresolved issues:

- Integrity documents for the other 17 courts. The TCU observed the tests in all
  27 UFs and is due to send TSE a consolidated report within 30 days of the
  second round; file it as the national source when it is published.
- The round-1 ZZ regeneration on 2026-10-24 is unexplained. Phase 20 must compare
  it with the ZZ SA results (`busa.dat`).
- Four sample documents are a ZIP, an RTF, a CSV and an OpenDocument spreadsheet.
  Their media types are recorded; their contents are not parsed.

Exact next task: Phase 21 for 2022 (rules review, equivalence, national run), then
Phase 20. Phase 20 reads the bulk BU/RDV archives (including `busa.dat`), the EA20
roots under `~/data/election-audit-stage/results-hierarchy/`, the
correspondences, and the pinned manifests.
