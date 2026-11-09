# Task 20b — Integrity completion: checks added from DataUrnas-BR

Document-ID: EA-HANDOFF-20B · Revision: 1 · Language: en

Objective: run nationally, for 2026 and both rounds, the checks DataUrnas-BR runs
and this project lacked: an Ed521 cross-check against DataUrnas-BR's verifier, the
zerésima in every log, urn loads against the GEDAI preparation logs, package names
in the logs against TSE's hash lists, and TSE's JWS signatures on the published
results. The earlier Phase 20b items (Ed521, certificates, I6 prefix, I8, I3/I5) are
recorded in the [implementation index](../implementation-index.md) and the
[integrity checks guide](../integrity-checks.md).

Prerequisites: [completion plan](../../../research/completion-plan.md) Phase 20b;
the section passes `integrity-sections-v4`
(`phase20/national-r{1,2}-sections-v4-20261107`); the staged 2026 logs and the
protection exclusions; the GEDAI input roots; the EA20 snapshots
`results-hierarchy/ea20-r{1,2}-20261104`.

Files and interfaces:

- `election_audit/ed521.py` (`observer` hook), `urn_pki.py` (CA verdicts observed),
  `ed521_crosscheck.py` (`ed521-crosscheck-v1`).
- `semantic_pass.py` (`session-aggregates-v5`: `markers.parquet`,
  `packages.parquet`).
- `zeresima.py` (`integrity-zeresima-v2`), `gedai.py` (`integrity-gedai-v2`),
  `hash_lists.py` (`integrity-hash-lists-v1`), `signed_results.py`
  (`signed-results-fetch-v1`, `integrity-jws-v1`).
- CLI: `integrity-check ed521-crosscheck|zeresima|gedai|hash-lists|jws` and
  `results-hierarchy fetch-signed`.
- Tests: `tests/test_ed521_crosscheck.py`, `test_zeresima.py`, `test_gedai.py`,
  `test_hash_lists.py`, `test_signed_results.py` and the markers and package tests in
  `test_semantic_pass.py`.

Deliverables:

- Releases under `~/data/election-audit-stage/`: `phase20b-ed521/national-r{1,2}-20261108`,
  `phase20b-zeresima/v5-national-r{1,2}-20261108` and
  `national-r{1,2}-zeresima-v2-20261109`, `phase20b-gedai/national-r{1,2}-gedai-v2-20261109`,
  `phase20b-hash-lists/national-v1-20261109`, `phase20b-jws/signed-r{1,2}-20261108`
  and `national-r{1,2}-jws-v1-20261109`. The v1 zerésima and GEDAI releases are kept
  as the record of the first rules.
- Frozen inputs: `inputs/ed521-crosscheck-refs-20261108/`, `inputs/tse-www-20261108/`
  (hash lists and JWS manual, downloaded by the user in a browser) and
  `inputs/tse-jws-key-20261108/`.
- Observations T11, T12, O18 and O19.

Acceptance (9 November 2026):

- Ed521 cross-check: 3193786 and 2827813 signatures (urn and CA), 0 disagreements,
  0 section errors; 53 vectors, DataUrnas-BR equal to strict mode in all.
- Semantic pass v5: sessions, segments, objects and vocabulary equal to v4 row for
  row in both rounds; 5197232 and 10312157 markers.
- Zerésima v2: 498579 and 498580 sections pass; one Z1 per round, both O17 sections.
- GEDAI v2: 498444 and 498388 sections matched, G2 never fails; 482 (G1) and 284
  (G3) sections are `zone_unpublished` (T11); 281 and 337 G1 failures, 268 and 267 of
  them in sp/0176; one G3 failure in round 2.
- Hash lists: seven program paths not listed (T12); 86 `ERRO` start-up lines (O19).
- JWS: key checks all true; 5786 files per round verified, equal to the plain files
  and to the EA20 snapshot; every altered copy refused.
- `UV_OFFLINE=1 just check` passes with 427 tests.
- Not done: the per-session follow-up of O19, the JWS revocation list, the GEDAI log
  signature files.

Decisions:

- Zerésima Z4 fails a zerésima printed after votes in its stream, not a second
  zerésima: restarts and replacements print new ones (O18). Z1 applies only to
  sections whose official blocks hold votes.
- GEDAI rules are not applied in a zone whose published logs hold nothing to match;
  those sections are unavailable, not failed. A zone with some matches keeps its
  failures, so sp/0176 still fails.
- Hash lists are compared by name and result; the model year in a name is reported
  as `model_suffix`, not as a match.
- The JWS key comes from TSE's manual (appendix B), not from the `.jws` files or
  from DataUrnas-BR, which only confirms it.
- TSE's www host refuses scripted downloads; its files are downloaded by the user in
  a browser and frozen, never fetched with a spoofed client.

Unresolved issues:

- O19: whether any urn that logged a program signature error recorded votes after
  it. The markers place each error in its block; a rule over sessions is needed.
- GEDAI: sp/0176 (169 of 437 sections matched, no load media) and the 13 and 70
  isolated G1 sections; round 2 has more, possibly urns prepared again by computers
  whose logs are not published.
- The JWS check does not consult the `AC DIVULGACAO` revocation list.
- The GEDAI log signatures (`.vsc`) are not verified: format not reviewed.
- The aggregate memory of the six cross-check workers was not measured.

Exact next task: the Phase 20b follow-ups above, starting with the per-session rule
for O19 over `session-aggregates-v5`; then register the zerésima, GEDAI, hash-list
and JWS checks and their gaps in the [study protocol](../../../research/analysis-plan.md)
before the Phase 23 freeze.
