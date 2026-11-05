# Task 20 — Tier 1 integrity checks

Document-ID: EA-HANDOFF-20 · Revision: 1 · Language: en

Objective: run the deterministic integrity checks I1–I9 of the study protocol
nationally for 2026, both rounds, with full discrepancy tables and no statistical
model.

Prerequisites: [study protocol](../../../research/analysis-plan.md) (Revision 4)
section 5; [completion plan](../../../research/completion-plan.md) Phase 20; the
Phase 19 inputs ([handoff 19](task-19.md)) and the Phase 21 releases
([handoff 21](task-21.md)).

Files and interfaces: `election_audit/integrity_checks.py` (`integrity-check
sections|bweb|hierarchy|correspondence|logs`; versions `integrity-sections-v1`,
`integrity-logs-v1`), `election_audit/resources/assinatura-2026-observed.asn1`,
`semantic_pass.verified_bulk_archives`, `tests/test_integrity_checks.py` and the
real AC section in `tests/fixtures/integrity-2026/`. Every step writes a new root
with `binding.json` and a checksummed `release/`; `sections` resumes only under an
identical binding. Guide: [integrity checks](../integrity-checks.md).

Deliverables:

- National releases for both rounds in `~/data/election-audit-stage/phase20/`:
  `national-r{1,2}-sections-v1-20261105`, `-bweb-v1c-`, `-hierarchy-v1-`,
  `-correspondence-v1-` and `-logs-v1-20261105`.
- Release tables keep statuses and digests only; vote values appear only in
  discrepancy rows; attendance for I5 is in `release/restricted/`. The 596
  protected/stress logs were hashed, never parsed.
- The observed 2026 signature-file layout, pinned by digest.

Acceptance (5 November 2026):

- I1: all 499207 sections per round match both hash lists; ECDSA (UE2013/UE2015)
  verified in 99985 and 99957 sections with no failure; 399222 and 399250 Ed521
  sections not verified; every BU hash chain intact.
- I2: every contest present in both BU and BWEB is equal; I3: equal except 10
  round-1 contests in two MG SA sections (20 voters each); I4: every vote measure
  equal at all 5786 nodes; I9: the effective urn equals the BU everywhere.
- I5: 85 and 36 sections differ; I6: 99 runoff logs with a differing closed
  round-1 block; I7: 2138 and 1815 sections with a failed rule. Every number is in
  the [guide](../integrity-checks.md#national-results).
- The new code reproduced the AC development release of I2 byte for byte.
- `UV_OFFLINE=1 just check` passes with 371 tests.
- Not attempted: I8 (no source), Ed521, certificate chains, 2022.

Decisions:

- Protected logs: included in the pass and hashed (I1, I9), never parsed; I5–I7
  skip them until the Phase 23 freeze.
- Signatures: hashes and ECDSA now, Ed521 later.
- Blinding: no values are stored for rows that agree.
- RDV party votes keep the typed digits; the party is their first two.
- I4 counts BWEB votes for a candidacy the national EA20 file does not list as
  technical nulls (`vnt`) and compares principal sections with `si`.
- Correspondence load codes drop a leading zero and are padded to 24 digits.
- The aggregate RAM cap was raised from 4 GiB to 6 GiB on 5 November 2026, after
  these runs. The section pass's largest single process peaked at 4.6 GB (round 1)
  and 4.0 GB (round 2); the aggregate across its six workers was not measured, so
  the section pass may have exceeded the old cap and is not shown to fit the new one.
  A measured aggregate (cgroup or per-process sampling) is needed before rerunning it.
- The first national BWEB run ran out of DuckDB memory: one database across UFs and
  an in-memory `string_agg` digest. Now each UF gets its own database, DuckDB only
  groups and sorts, and Python builds the digest with the BU function. The
  following runs stayed over the 4 GiB budget (5.0 GB, then 4.1 GiB), so contest
  rows are now written per UF, the UF database is closed before the Python lookups
  are built and the DuckDB limit is 1 GB per UF (SP alone: 2.4 GB, same time).
  `bweb-v1c` is the release of record; the earlier runs had identical summaries,
  discrepancies and section tables and the same contest rows in the same order, and
  were deleted.

Unresolved issues:

- Ed521 (UE2020/UE2022): the curve of DOC-ICP-01.01 v6.0 (p = 2^521−1,
  d = −376014, SHAKE256 with a `SigEd521` domain prefix) did not verify any
  signature in pure or prehash mode (SHA3-512, SHAKE256-64), with the file hash,
  the list or its DER as message, in either byte order. Needs the exact TSE
  construction.
- I6 compares whole-segment fingerprints, so the open last round-1 block is
  `open_prefix_unverified`; the 99 differing and 3645 extra-block logs need a
  raw block-level re-read.
- I5 open differences, in multi-session logs (likely re-runs summed twice) and in
  single sessions with fewer cycles than attendance: Phase 22 session grouping.
- The two MG SA sections (41238/0039/0168, 50075/0047/0041): the 20-voter gap is
  consistent with paper ballots but unconfirmed; check the SA logs and the
  section's minutes if obtainable.
- Ten municipal elections held with the runoff (6282–6293) have no BWEB source.
- Round-2 bulk archives hold 77 unexplained 47-byte `*.id` members (19 archives,
  25 October) and a log for SP 64777/0395/0298, which the per-section endpoint
  published without one. The `.id` members are in `archive_members.json`; the SP
  log is hashed in its section row.

Exact next task: Phase 22 (session grouping and clock rules), using the I5 and I6
discrepancy tables. Phase 20b of the
[completion plan](../../../research/completion-plan.md) holds the Ed521,
certificate-chain, I6, I2 and I8 gaps and must close, or be written into the
protocol, before the Phase 23 freeze. File the TCU consolidated integrity test report when it is
published (about 24 November 2026).
