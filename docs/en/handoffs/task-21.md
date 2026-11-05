# Task 21 — National semantic log pass

Document-ID: EA-HANDOFF-21 · Revision: 1 · Language: en

Objective: one streaming pass per round over every eligible urn log of 2026 and
2022, applying reviewed message rules and writing per-session aggregates, context
segment fingerprints and a message-template vocabulary, equivalence-tested
against the AC event-level adapter before each national run.

Prerequisites: [completion plan](../../../research/completion-plan.md) Phase 21;
the [study protocol](../../../research/analysis-plan.md) (Revision 3); the Phase 19
inputs ([handoff 19](task-19.md)); the SSD staging and protection exclusions
`data/national/phase11-protection-2026-10-31/exclusions.json`.

Files and interfaces: `election_audit/semantic_pass.py` (`semantic-pass run|equivalence`,
`session-aggregates-v2`), `election_audit/sevenzip.py`, `election_audit/sa_logs.py`
(`sa-logs fetch|summarize`), `election_audit/resources/real-log-rules.json` and
`real-log-rules-2022.json`, `election_audit/elections.py` (2022 descriptors),
`archive_parsing` and `operational_review` (7z and per-year rules). Every run writes
a new root with `binding.json`, `status.json`, shards and a checksummed `release/`;
`--resume` requires an identical binding.

Deliverables:

- 2026, both rounds: 498580 and 498581 objects, no errors, 1704924 and 3393756
  sessions, in `~/data/election-audit-stage/phase21/national-r{1,2}-20261103/`
  (`session-aggregates-v1`). The ledgers reconcile all 499207 sections per round;
  596 protected/stress logs stay unread.
- 2022, both rounds: 471859 and 471983 objects, no errors, 1805887 and 3570943
  sessions, in `~/data/election-audit-stage/phase21/national-2022-r{1,2}-v2-20261104/`.
  The ledgers account for 472024 and 472027 sections from the archive member names.
- A stdlib 7z reader (LZMA, LZMA2 and copy coders, every CRC checked, anything
  else refused) and a bulk mode reading 2022 archive members in physical order;
  bulk mode refuses 2026.
- 2022 rules: 2026 exact semantics only where the 2022 text is identical; 2022
  session, round and software markers read from the logs; unmatched messages stay
  unknown.
- The 60 SA contingency counting logs, attributed to their sections.

Acceptance (all on 4 November 2026 unless stated):

- Equivalence with the adapter: 2026 AC 400 of 400 objects (3 November); 2022 AC
  200 of 200 per round.
- Reproduction: a v2 run of AC 2026 (1674 objects per round) equals the v1
  national rows in every object, session and segment row after casting the four
  seconds columns to `int64`.
- `UV_OFFLINE=1 just check` passes with 359 tests.
- Not attempted: a 2022 BWEB cross-check of the 2022 ledger.

Decisions:

- Authorization method is analysed as biometric versus all other methods (manual,
  no biometrics and unknown pooled): only biometrics verifies the voter, the rest
  rests on the poll worker. The biometric marker text is identical in 2022 and 2026.
- v2 widened the seconds columns to `int64` after a 2022 urn clock restarted at
  23/08/1933 and overflowed int32. The 2026 releases stay v1; read them with the
  cast.
- The 2022 round-2 run first failed on one object (a nested empty 7z archive);
  the reader fix only affects objects that previously failed, so shard 00844 was
  rerun under the same binding.
- The first, crashed v1 run of 2022 round 1 was deleted.

Unresolved issues:

- Clock faults are recorded but not interpreted: four 2022 round-1 sessions restart
  at 01/01/2009 (BA 39799/0106/0049 mid-vote) and PE 25097/0091/0032 at 23/08/1933
  before an operator sets the date (ADH). Clock rules and a count of resets and ADH
  corrections per section are Phase 22 work.
- Sessions with several official runs per object are kept as observed; grouping
  them is Phase 22 work. Segment fingerprints compare whole segments; the round-1
  block comparison (I6) needs a prefix comparison.
- 2022 sections without a log: 54 BU-only ZZ sections in round 1, and BU-and-RDV
  sections MG 51390/0244/0091, RN 16918/0054/0090 (round 1) and five PA sections in
  zone 04650/0006 (round 2). Phase 20 should look at them with the BU files.

Exact next task: Phase 20 integrity checks I1–I9 on the bulk BU/RDV archives
(including `busa.dat`), signatures, correspondences and the EA20 hierarchy, then
Phase 22. File the TCU consolidated integrity test report when it is published
(about 24 November 2026).
