# Implementation index

Document-ID: EA-IMPLEMENTATION-INDEX · Revision: 44 · Language: en

[Português](../pt-BR/implementation-index.md)

This is the single current-state entry point. It says what exists, what has
actually run, where the results are and what comes next. Guides under `docs/en/`
describe how each tool behaves. Handoffs under `docs/en/handoffs/` are dated
records of what each task did at the time; read them for detail, not for status.
Plans live in `research/`. State below is as of **11 November 2026**.

## Current state

**Acquisition (Phase 10): finished for both rounds.** The downloader collected
every log version advertised by the TSE per-section endpoints.

| Round | Pleito / election / date | Run finished (UTC) | Log versions | Aggregated | No log listed | Auxiliary file not published |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3220 / 6257 / 2026-10-04 | 2026-10-31 23:27 | 499176 | 17931 | 31 | 41 |
| 2 | 3221 / 6258 / 2026-10-25 | 2026-10-29 22:56 | 499177 | 17931 | 30 | 41 |

Round 1 packages are all `Totalizado`; round 2 has 488333 `Totalizado` and 10844
`Recebido`. Because of the no-log and unpublished-auxiliary sections, neither run
meets the downloader's `national_coverage` criterion; those sections stay explicit
gaps. On 1 November both raw stores (53722200971 and 90643145031 bytes) were copied
to the output volume and every object was verified by SHA-256. The copies are the
authoritative originals for derived processing; the `.local-state/` manifests are
preserved unchanged. On 3 November the old-HDD roots' metadata was archived with
hashes and their raw objects, duplicates of the certified copies, were released
for deletion.

The move needed no manifest rewrite: manifest paths are relative to the object
root (`objects/xx/<sha>.<ext>`), and each new root's `manifest-location.json`
points at its SSD manifest (`.local-state/tse-2026.sqlite` for round 2,
`.local-state/tse-2026-t1-verified.sqlite` for round 1). The certified copies
`migration-2026-11-01/manifest-r{1,2}.sqlite` match their certificate hashes, and
on 3 November their files, logs, sections and runs rows were found identical to the
live SSD manifests. Analyses pin the certified copies. Leftovers to ignore: `raw/2026/turno-2/manifest.sqlite`
is the stale pre-split database; `.local-state/tse-2026-t1.sqlite` is a superseded
round-1 manifest; and `migration-2026-11-01/status.json` reads `FAILED_STOPPED`
because the job chained after the verified copy was stopped, not because the copy
failed.

**Structural processing (Phase 11): finished for the eligible runoff scope.** The
feature-oriented summary job processed all 498581 eligible runoff objects (499177
observations minus 596 protected/stress observations and their content aliases),
with 0 failures, in 35992 seconds using three workers under the 4 GiB / half-CPU
budget. 498575 objects parsed completely and 6 partially (190 retained errors).
It scanned 5032537448 structural events; about 90% fall in message classes the
structural parser leaves `unknown`. The published release
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88`
(`source-summary-analysis-release-v1`, 546.6 MB of Parquet) holds per-log counts,
member structure and block hashes; the 68.8 GB of grouped checkpoints are kept only
for recovery and evidence.

What it cannot be used for: each runoff `logd.dat` runs from setup in September
through the first round to the runoff, so the per-log authorization and completion
counts (252940011 and 252882361 in total) mix rounds and are not runoff measures.
There are no sessions, clocks or timings. The 596 protected/stress logs and all of
round 1 are unprocessed. Every operational measure needs the semantic pass of
Phase 21.

Phase 11 read 91.5 GB of small objects at about 2.5 MB/s with 94% I/O pressure,
while writing checkpoints to the same drive. The 3 November benchmark
(`stage-sources benchmark`, 2000-object windows, both rounds) found the cause: read
order. The certified copies were written in path order, so section (manifest URL)
order reads at 1.9–3.5 MB/s, path order at 41–61 MB/s and physical (FIEMAP) order
at 73–92 MB/s.

**SSD staging (3 November): done for both rounds.** Every raw object was copied in
physical order to `$EA_STAGE/2026/turno-1/` and `turno-2/`
(998412 and 998413 objects, 53722200971 and 90643145031 bytes), each source body
checked against the certified manifest SHA-256, then every staged body re-hashed
on the SSD. The copies took 931 s and 1587 s (about 57 MB/s), the re-hashes 954 s
and 1431 s; 86 minutes in all. Each root holds its manifest copy, a ledger and a
`staging-certificate.json` bound to the certified manifest digest. The home
directory is eCryptfs, so one reader re-hashes at only 56–63 MB/s. The
[completion plan](../../research/completion-plan.md#resource-and-io-rules) sets
the I/O rules for the next pass.

**Phase 19 (national inputs): complete; integrity test documents sampled.** `bulk-download` fetched, with
SHA-256/SHA-512 and the TSE catalog JSON, the 2026 and 2022 BWEB (112 archives
each year, all 56 per year with a published `.sha512` match). All 12 small
input datasets (BWEB and results for 2026 and 2022, voter profile and polling places,
media correspondences for both rounds of 2026 and 2022, 2026 GEDAI logs for both
rounds) are complete in `$EA_STAGE/inputs/`, every published
`.sha512` matching. The CDN can serve stale cached HEAD or GET copies, so
`bulk-download` revalidates with a throwaway query and still requires matching
ETag and length. Totalization reports are re-zipped every few hours and change
after retotalizations; see the
[acquisition reference](acquisition-reference.md#totalization-reports-are-a-moving-target).
The bulk BU/RDV/log archives (56 per year; 2026: 219.2 GB, 2022: 168.5 GB) are
complete in `bulk/` on the output volume, and `bulk-download verify` re-hashed all
112 against their manifests on 2026-11-04 (TSE publishes no `.sha512` for them).
`results-hierarchy` fetched the presidential EA20 hierarchy for both rounds (BR,
27 UFs and ZZ, 5757 municipalities and the progress files: 5815 files per round,
all final); round-1 ZZ was regenerated on 2026-10-24. The certified manifest
digests are pinned in `election_audit/resources/pins/certified-manifests-2026.json`
and both copies re-hashed against them. Integrity test documents are not open
data and the TRE sites refuse scripted requests, so a browser collected a sample
of ten courts (SP, AC, AL, DF, ES, PR, MG, RJ, BA, RS): `integrity-docs` filed 125
documents, every one matching its browser hash
([acquisition reference](acquisition-reference.md#integrity-test-documents-tre-sites)).
See the [Phase 19 handoff](handoffs/task-19.md).

**Phase 20b (integrity completion): complete; TSE's root-certificate reply pending.** Ed521 is implemented
(`election_audit/ed521.py`, confirmed with the verifier in TSE's 2026 format package)
and runs nationally through [`ed521rs`](https://pypi.org/project/ed521rs/), whose
verdicts equal the pure-Python ones in every row and ECPy's in every signature. BU,
RDV and signature files are decoded with TSE's official 2026 specifications. Urn
certificates are checked against the published CAs `AC URNA`, `AC UE2020` and
`AC UE2022` and their revocation lists. The national rerun
(`$EA_STAGE/phase20/national-r{1,2}-sections-v3-20261106/`)
verified every hardware self-signature, 1996828 file signatures per round and
997114 and 539817 BU chain signatures, with no failure; every urn certificate is
signed by its CA and none is revoked. In 14 and 3 sections another urn signed the
files ([O13](observations.md#operations)). The section tables were rebuilt as
version 3 (`table-2026-v3-20261107/`, `table-2022-v3-20261106/`): eleven Amazonas
municipalities on Acre time are pinned with their sources
([O12](observations.md#operations)) and no section is left without a close rule.
The I6 prefix re-read (`integrity-check prefix`, 7 November,
`$EA_STAGE/phase20b-i6/national-v1-20261107/`) re-read 496793
runoff logs with no error: every open last round-1 block is an exact prefix of its
runoff copy (493125 sections now fully equal). Of the 113 block pairs that still
differ, 112 hold the same lines with different block limits, because restart lines
written before logging to MI and ME are missing from some copies
([O14](observations.md#operations)); one, rj/60011/0008/0061, is a real disagreement
among three copies of an urn's election day, and the published round-1 log is the
one that matches the BU ([O15](observations.md#operations)).
I8 (`integrity-check printed`, 7 November,
`$EA_STAGE/phase20b-i8/v1-20261107/`) checked the 528 printed BU
copies read from QR codes by CMInd's Totalização Paralela and Arvor's Totalização
paralela (518 sections, 49 in round 1, 469 in the runoff): every hash chain is intact,
every urn signature and certificate verifies, each certificate equals the one in the
section's signature file, and every printed field equals the published BU. The
collections are not samples. The I2 municipal gap is recorded in protocol revision 5.
The I3/I5 reconciliation is done (7–8 November). RDV blocks of one contest are
summed (`integrity-sections-v4`), so I3 is equal in every contest of both rounds.
Session rules `sessions-v2` (`session-aggregates-v4`) keep the round's context
across mid-day restarts and make official the sessions of urns left on overnight.
I5–I7 count memory copies of a session once (`integrity-logs-v2`,
[O16](observations.md#operations)). Of the 85 and 36 I5 differences, 10 and 7
remain. Every one has a recorded cause except rs/89060/0017/0191, one cycle short;
four logs cover only part of election day ([O17](observations.md#operations)).
DataUrnas-BR's round-1 log table flags the same sections with the same counts,
except the broken stream of O15, which it reads whole. The
semantic passes, I6 prefix re-read and section tables (version 4) were rerun on the
new rules; result and unit files are unchanged.
The checks added from DataUrnas-BR ran nationally on 8–9 November. DataUrnas-BR's
own Ed521 verifier agreed with every verdict (3193786 and 2827813 signatures, 0
disagreements). No zerésima follows a vote; the one Z1 section per round is an O17
section whose first urn is not in the package, and several zerésimas per section come
from restarts and replacements before voting ([O18](observations.md#operations)).
GEDAI matched 498444 and 498388 sections' urn loads; 482 sections in three zones and
284 in three others cannot be checked because those zones' preparation logs are not
published ([T11](observations.md#transparency)), and 281 and 337 sections fail G1,
most in sp/0176; the other 13 and 70 are late loads whose correspondence never
reached the published logs ([T13](observations.md#transparency)). Every package name verified in the logs is in TSE's hash lists
except seven load-media and load files ([T12](observations.md#transparency)); 86
start-up verification lines ended in `ERRO` ([O19](observations.md#operations)), and
no urn completed a vote in the session of a signature verification error: votes
after an error come only after a restart. All
5786 JWS-signed result files per round verify against TSE's official key and equal
the EA20 snapshot, and the key's revocation lists (current on election day) revoke
nothing. Semantic pass `session-aggregates-v5` adds the markers and package
tables these checks read and is equal to version 4 elsewhere. See the
[Phase 20b handoff](handoffs/task-20b.md), the
[integrity checks guide](integrity-checks.md#phase-20b-checks-added-from-dataurnas-br),
its [signatures section](integrity-checks.md#phase-20b-signatures-and-certificates),
[integrity checks guide](integrity-checks.md#phase-20b-signatures-and-certificates),
its [reconciliation section](integrity-checks.md#phase-20b-session-rules-v2-and-the-i3i5-reconciliation),
its [I6 prefix section](integrity-checks.md#phase-20b-i6-prefix-re-read) and its
[I8 section](integrity-checks.md#phase-20b-i8-printed-bus).

**Phase 22 (section table v2): complete for 2026 and 2022.** Semantic pass
`session-aggregates-v3` adds device model, software and clock evidence per session.
It ran nationally for both years and rounds with no errors, and every column shared
with the earlier releases is equal in every row
([semantic pass](semantic-pass.md#version-3-phase-22)). `section-table build`
wrote 998496 section rows in 499248 harmonized units for 2026 and 945386 rows in
472693 units for 2022, into `$EA_STAGE/phase22/table-{2026,2022}-20261106/`.
Copies of one session in internal and external memory are counted once. Clocks are
judged against legal closing times, with Amazonas resolved from the closing times
the urns print. Every unit keeps the same principal section in both rounds.
Results and operational measures are written only under `restricted/` and were not
read. Both items left open were settled in Phase 20b: six of the eight round-1
model differences are signature files signed by another urn, and the Amazonas
sections without a close rule now take it from the list of municipalities on Acre
time (version 3 tables, below). See the [section table guide](section-table.md#national-results), the
[observation register](observations.md) and the [Phase 22 handoff](handoffs/task-22.md).

**Phase 21 (semantic pass): complete for both 2026 rounds and 2022.**
`semantic-pass` matched the event-level adapter on 400 of 400 sampled AC objects
(84469 completed cycles). The national runs processed 498580 round-1 and 498581
round-2 objects with no errors (1704924 and 3393756 sessions) into
`$EA_STAGE/phase21/national-r{1,2}-20261103/`. The population
ledger reconciles every one of the 499207 sections per round: 31 and 29 sections
were counted with the SA contingency system and have no urn log, one round-2 SP
section was published without a log, and 596 are excluded. `sa-logs` fetched all
60 SA logs (byte-identical to the bulk archives) and attributed every one to its
section ([SA logs](semantic-pass.md#contingency-counting-sa-logs)). The 2026 releases are
`session-aggregates-v1`; the current code writes v2 (64-bit seconds columns) and
reproduced the AC rows of both rounds exactly. For 2022 (the negative control),
a stdlib 7z reader and reviewed 2022 rules (`tse-real-log-rules-2022-v1`) feed a
bulk mode over the 2022 archives that refuses 2026. It matched the adapter on 200
of 200 AC objects per round, then processed 471859 and 471983 objects with no
errors (1805887 and 3570943 sessions) into
`$EA_STAGE/phase21/national-2022-r{1,2}-v2-20261104/`. The 2022
ledger accounts for every section in the archives (472024 and 472027). Analyses
compare biometric with all other authorizations (analysis plan rev 3). See the
[semantic pass guide](semantic-pass.md#2022-logs) and the
[Phase 21 handoff](handoffs/task-21.md).

**Phase 20 (Tier 1 integrity checks): complete for 2026, both rounds.**
`integrity-check` ran I1–I9 over all 499207 sections per round into
`$EA_STAGE/phase20/national-r{1,2}-*-20261105/`. Every published
BU, RDV and image file matches both signed hash lists; ECDSA signatures of the
UE2013/UE2015 urns verified in 99985 and 99957 sections with no failure, while the
399222 and 399250 Ed521 sections (UE2020/UE2022) are not verified. Every BU hash
chain is intact; every contest present in both BU and BWEB is equal; every EA20
vote measure equals the BWEB sums at all 5786 nodes; and every effective urn in the
correspondences equals its BU. The RDV recount differs only in two MG SA sections
(20 voters each, round 1). Open: 85 and 36 I5 attendance differences, 99 runoff
logs with a differing round-1 block (I6), I7 rule failures in 2138 and 1815
sections, Ed521 and I8. See the
[integrity checks guide](integrity-checks.md#national-results) and the
[Phase 20 handoff](handoffs/task-20.md).

**Phases 12–18: closed as Acre (AC) development pilots.** The 3 November
methodology review replaced their definitions; the revised work is Phases 19–26.
Their tools exist, were exercised on real AC data and are reused, but nothing ran
nationally:

- Phase 12: 2270 AC runoff sections content-verified between binary BU and BWEB;
  UF totals match. Signatures, RDV recount and national hierarchy are not done.
- Phase 13: real-message adapter (`real-operational-v1`) run on one AC log per
  round. Absolute clocks and attendance reconciliation are not done.
- Phase 14: 2270 AC units, 54480 feature rows, 668 same-round location groups.
  No cross-round identity and no first-round electoral features.
- Phase 15: frozen AC protocol (training 1259, calibration 399, protected test
  340, municipal stress 256, development-inspected 16).
- Phase 16: one AC turnout fit (`no_first_round` variant) evaluated on
  calibration data only. No final evaluation has run; four protected test sections
  (and one municipal-stress section) were structurally parsed, without values, in the
  Phase 11 stratified sample before the exclusions existed (`impact.json`).
- Phase 17: 126 AC development case packets (20 + 20 ranked, 86 unflagged controls).
- Phase 18: four marimo notebooks over the AC export; browser QA not done.

No national electoral result, national margin, fitted national model or fraud
label exists.

**Checks.** The full offline gate `just check` passes (lock, format, lint,
type check, contracts, docs, documented commands and all 445 tests). Every
function in `election_audit/`, `scripts/` and `tests/` is annotated (ruff `ANN`)
and `ty check` (pinned 0.0.94) reports no diagnostics; the conventions are in
`CLAUDE.md`.

## Next step

Finish the first [cross-model review](cross-model-review.md) campaign
(`xr1-20261109`, `review/campaigns/xr1-20261109/`): rounds 1–3 are done (98 findings,
65 confirmed or partly confirmed). In round 4 the Phase 23 blockers and the fixes to
the integrity checks are done and reran nationally on 9 November 2026
([cross-model review fixes](integrity-checks.md#phase-20b-cross-model-review-fixes)):
sp/0176 now fails G3 in 168 sections per round, I7 R2 adds 20 sections that already
failed R6, and E3's 31 start-up recoveries are recorded (T14); no other result
changed. The portability fixes and the low-severity rows are done (every confirmed row
links to its fix; P7-08 waits for Phase 23), and sections v6 reran nationally with 0
discrepancies. Section tables v5.1 were rebuilt on 11 November 2026
([section table](section-table.md#national-results)): the new rule that results must
add up first marked 9.3% of the 2026 sections unavailable, because a blank or null
category with no BWEB row was read as missing; it is zero when the other counts equal
the attendance, and v5.1 restores them. Still to do: the decision whether to rerun
semantic pass v6 nationally (about 6 hours for 2026, plus everything built on it; the
new rules touch about 39 cycles and 13 backward clock steps), then round 5 verifies
the fixes. Before Phase 23, discuss the consequence of the 8.3% development-place
share. Then
start Phase 23 (development modelling, power study,
protocol freeze) on development data only. Phase 20b is complete and its checks and gaps are registered in the
protocol ([handoff](handoffs/task-20b.md)); before the freeze, add TSE's reply on the
root certificates and the TCU report to the protocol. TSE's reply to the root-certificate request (protocol
83529705172533) is due by 25 November 2026. File the TCU consolidated integrity test
report when it is published (due within 30 days of the second round). The
[study protocol](../../research/analysis-plan.md) (Revision 11) defines the claims,
the threat-to-observable map, the integrity checks I1–I9, the confirmatory tests
C1–C6, the power study and the data policy; the
[completion plan](../../research/completion-plan.md) (Revision 14) defines
Phases 19–26. The protocol is a draft until it is frozen and publicly
pre-registered in Phase 23.

## Working rules

Read the repository `CLAUDE.md`, this index, the assigned handoff and only the
relevant contracts. Run one phase at a time. After each numbered task, write a
paired handoff from the [template](task-handoff-template.md) and update this
index in both languages. Keep processing within half the CPU, 6 GiB of aggregate
RAM (4 GiB until 5 November 2026) and one library thread per process.

The 596 protected/stress runoff observations stay excluded before any semantic or
cache access. Inspection histories in `data/phase15/inspection.sqlite`,
`data/national/phase11-protection-2026-10-31/` and the Phase 11 tranche registries
remain binding: any location they list is development data, never untouched test
data. Missing cross-round identity stays unavailable.

## Phase status

Foundation tasks 1.1–9.4 are complete. Their acceptance (29 October 2026): 166
offline tests, lock, Ruff, contracts and paired-document checks; a frozen
five-region real pilot (AC/AL/DF/ES/PR) with every session, cycle and clock left
unresolved. Task 7.1 later added the official BWEB adapter with real AC arithmetic
checks (177 tests).

| Task | Deliverables | Handoff |
| --- | --- | --- |
| 1.1 | Python 3.14, uv lock, package/CLI, DuckDB/PyArrow | [1.1](handoffs/task-1.1.md) |
| 1.2 | Ruff, mechanical legacy formatting | [1.2](handoffs/task-1.2.md) |
| 1.3 | just recipes, paired onboarding, index/template | [1.3](handoffs/task-1.3.md) |
| 2.1 | 30 dimensional contracts, dictionary, lineage, safe joins | [2.1](handoffs/task-2.1.md) |
| 2.2 | 21 feature/readiness contracts, denominators and blockers | [2.2](handoffs/task-2.2.md) |
| 2.3 | Paired research/acquisition translations, glossary/diagrams, docs checks | [2.3](handoffs/task-2.3.md) |
| 3.1 | Read-only selected source inventory, WAL isolation, honest historical unknowns | [3.1](handoffs/task-3.1.md) |
| 3.2 | Frozen expected indexes, member/principal coverage and bounded asset selection | [3.2](handoffs/task-3.2.md) |
| 3.3 | Atomic immutable copies, snapshot/inspection CLI, frozen provenance and guide | [3.3](handoffs/task-3.3.md) |
| 4.1 | Bounded nested JEZ/ZIP decoding, CRC and duplicate member locators | [4.1](handoffs/task-4.1.md) |
| 4.2 | Ordered structural events, naive clocks, safe bounded diagnostics | [4.2](handoffs/task-4.2.md) |
| 4.3 | Verified immutable parse cache, all frozen associations, CLI/API and guide | [4.3](handoffs/task-4.3.md) |
| 5.1 | Candidate/official contexts, separate identities, exact copied-block lineage | [5.1](handoffs/task-5.1.md) |
| 5.2 | Anonymous authorization/completion/suspension/cancellation state machine | [5.2](handoffs/task-5.2.md) |
| 5.3 | Evidenced section/overseas clock rules, UTC/corrections and continuity | [5.3](handoffs/task-5.3.md) |
| 5.4 | Operational denominators, immutable bounded shards/shared context, CLI/API | [5.4](handoffs/task-5.4.md) |
| 6.1 | Immutable bounded DuckDB/Parquet releases, resource limits, atomic current | [6.1](handoffs/task-6.1.md) |
| 6.2 | Coverage/session/lifecycle availability/late-voting marts, clock uncertainty | [6.2](handoffs/task-6.2.md) |
| 6.3 | Build/validate/read-only query/bilingual reports | [6.3](handoffs/task-6.3.md) |
| 7.1 | Normalized imports plus pinned official BWEB adapter; real AC arithmetic verified | [7.1](handoffs/task-7.1.md) |
| 7.2 | Immutable parent-pinned derivatives, evidenced canonical selection, reconciliation | [7.2](handoffs/task-7.2.md) |
| 7.3 | Four electoral marts, bounded SELECT, validation and paired reports | [7.3](handoffs/task-7.3.md) |
| 8.1 | Versioned 21-contract feature registry and streamed descriptive outputs | [8.1](handoffs/task-8.1.md) |
| 8.2 | Seeded reviewed stable-location partitions, strata and municipal holdouts | [8.2](handoffs/task-8.2.md) |
| 8.3 | Immutable protocol/exploration/investigation/scenario ledgers and test access history | [8.3](handoffs/task-8.3.md) |
| 9.1 | Synthetic offline walkthrough, four immutable stages and paired reports | [9.1](handoffs/task-9.1.md) |
| 9.2 | Frozen five-region real diagnostic pilot | [9.2](handoffs/task-9.2.md) |
| 9.3 | Relocatable review bundles, frozen replay/logical digests | [9.3](handoffs/task-9.3.md) |
| 9.4 | Verified bounded restart and backfill/storage guide | [9.4](handoffs/task-9.4.md) |

| Phase | Status | Remaining | Handoff |
| --- | --- | --- | --- |
| 10 | Complete: both rounds acquired, copied and SHA-256 verified | Gap sections stay explicit; BWEB, registers, RDV/signature sources for other UFs are separate imports | [10](handoffs/task-10.md) |
| 11 | Complete for eligible runoff scope (498581 objects, 0 failures) | Protected logs read only after the Phase 23 freeze | [11](handoffs/task-11.md) |
| 12 | AC only: 2270 sections content-verified, UF totals match | Other UFs, both rounds, signatures, RDV, BR/UF/municipal/ZZ hierarchy | [12](handoffs/task-12.md) |
| 13 | AC sample: one log per round | National sessions, clocks, copied histories, attendance reconciliation | [13](handoffs/task-13.md) |
| 14 | AC only: 54480 feature rows | National features, cross-round identity, first-round results | [14](handoffs/task-14.md) |
| 15 | AC protocol frozen | Replaced by the Phase 23 freeze and pre-registration | [15](handoffs/task-15.md) |
| 16 | AC turnout development fit | Full target/variant family, refit simulations, final evaluation | [16](handoffs/task-16.md) |
| 17 | AC development case packets | National cases, corroboration, impact bounds, full-pipeline sensitivity | [17](handoffs/task-17.md) |
| 18 | Notebooks over AC export | Browser QA, national datasets | [18](handoffs/task-18.md) |
| 19 | Complete: BWEB, BU/RDV/log archives, voter profile, correspondences, GEDAI, EA20 hierarchy, pinned manifests, both rounds and 2022 | Integrity test documents for the 17 courts outside the sample; TCU consolidated report | [19](handoffs/task-19.md) |
| 20 | Complete: I1–I9 for 2026, both rounds, all sections; ECDSA verified, BWEB, EA20 and correspondences agree | Ed521 signatures, certificate chains, I6 prefix re-read, I5/I6 open differences, I8, 2022 | [20](handoffs/task-20.md) |
| 21 | Complete: 2026 both rounds (v1, reproduced by v2 on AC) and 2022 both rounds (v2); ledgers reconcile every section; SA logs attributed | Grouping multi-run sessions and clock rules move to Phase 22 | [21](handoffs/task-21.md) |
| 22 | Complete: semantic pass v3 nationally (2026 and 2022, equal to earlier releases on shared columns); section tables for both years with crosswalk, clock rules and ledger | Results and operational values unread until the freeze; model differences and Amazonas close rules move to Phase 20b | [22](handoffs/task-22.md) |
| 20b | Complete: Ed521 verified nationally (`ed521rs`, equal to the pure-Python verifier), official TSE specifications, urn certificates checked against the published CAs and revocation lists, section tables v3 with the Amazonas list, I6 prefix re-read (every open block a verified prefix; 112 of 113 differing pairs explained, O14/O15), I8 (528 printed copies, all equal), I2 municipal gap recorded, I3/I5 reconciled (session rules v2, memory copies counted once, I5 85/36 → 10/7, O16/O17; semantic passes, I6 and section tables v4 rerun); checks added from DataUrnas-BR run (Ed521 cross-check 0 disagreements, zerésima v2, GEDAI v3 with T11/T13, hash lists with T12/O19, signature errors (O19 resolved: no vote in the session of an error), JWS all verified with the revocation lists; semantic pass v5); registered in the protocol (Revision 9); complete | Roots requested from TSE | [20b](handoffs/task-20b.md) |
| 23–26 | Not started; defined in the [completion plan](../../research/completion-plan.md#revised-phases) | All | — |

## Where results are

Paths under `data/` are relative to the repository and ignored by Git. Documented
commands and locations use two roots that each machine sets for itself:

- `$EA_DATA`: the large volume holding raw acquisitions, bulk archives and national
  outputs (on the reference machine, an external HDD mounted at
  `/media/<user>/<volume-uuid>/election-audit`);
- `$EA_STAGE`: the fast working area for staged copies, frozen inputs and Phase 20+
  outputs (on the reference machine, `~/data/election-audit-stage` on the SSD).

The [reproduction guide](reproduction.md#what-to-expect-on-the-national-data) gives
the space each needs. Inputs that TSE serves only to browsers are listed, with their
digests, in [inputs downloaded by hand](manual-inputs.md).

| Artifact | Location |
| --- | --- |
| Raw originals, both rounds (authoritative copies) | `raw/2026/turno-1/`, `raw/2026/turno-2/` on the output volume |
| Copy certificates, certified manifest copies (analysis inputs), verification ledgers | `2026/migration-2026-11-01/` on the output volume |
| Hash-verified SSD staging of both rounds (read these in log passes), with staging certificates | `$EA_STAGE/2026/turno-1/`, `$EA_STAGE/2026/turno-2/` |
| Read-order benchmarks | `$EA_STAGE/benchmarks/` |
| Phase 19 small inputs (BWEB, results, voter profile, correspondences, GEDAI), each with catalog, manifest and status | `$EA_STAGE/inputs/<dataset>/` |
| Phase 19 bulk BU/RDV/log archives, 2026 and 2022 | `bulk/2026-arqurnatot/`, `bulk/2022-arqurnatot/` on the output volume |
| Phase 20 integrity-check releases (sections, BWEB, hierarchy, correspondences, logs), AC/ZZ development runs | `$EA_STAGE/phase20/` |
| Phase 20b I6 prefix re-read (national releases v1 and v2, AC development run) | `$EA_STAGE/phase20b-i6/` |
| Phase 20b semantic passes v4 (2026, 2022), AC equivalence samples, section tables v4, run logs and scripts | `$EA_STAGE/phase20b-sessions/` |
| DataUrnas-BR tables used in the I3/I5 reconciliation, frozen at commit `f5e8005` | `$EA_STAGE/inputs/dataurnas-br-f5e8005-20261108/` |
| Phase 20b Ed521 cross-check; its frozen references | `$EA_STAGE/phase20b-ed521/`; `$EA_STAGE/inputs/ed521-crosscheck-refs-20261108/` |
| Phase 20b semantic passes v5 and zerésima checks; GEDAI checks; hash-list check; signature-error checks; JWS files and checks | `$EA_STAGE/phase20b-zeresima/`, `phase20b-gedai/`, `phase20b-hash-lists/`, `phase20b-signature-errors/`, `phase20b-jws/` |
| TSE hash lists and JWS manual (browser downloads); the JWS key file | `$EA_STAGE/inputs/tse-www-20261108/`, `tse-jws-key-20261108/` |
| Phase 20b I8 printed BUs; its frozen inputs (CMInd, Arvor, TSE QR manual) | `$EA_STAGE/phase20b-i8/`; `$EA_STAGE/inputs/i8-cmind-20261107/`, `i8-arvor-20261107/`, `i8-tse-qrbu-20261107/` |
| Phase 21 equivalence reports, AC development pass, AC v2 reproduction, national passes (2026 and 2022) | `$EA_STAGE/phase21/` |
| Phase 22 v3 semantic passes, section tables (2026, 2022), AC development runs, Phase 20 root selections | `$EA_STAGE/phase22/` |
| TSE 2026 format package (specifications, reference verifier, CA certificates) and the five revocation lists, frozen | `$EA_STAGE/inputs/tse-format-docs-20261105/`, `$EA_STAGE/inputs/tse-crls-20261105-complete/` |
| SA (contingency counting) logs per round and their section summary | `$EA_STAGE/sa-logs/` |
| EA20 hierarchical presidential results, both rounds | `$EA_STAGE/results-hierarchy/` |
| Integrity test documents, ten-court sample, with browser record files; the original browser downloads | `$EA_STAGE/inputs/integrity-tests-2026-sample-20261104/`; `$EA_STAGE/integrity-downloads-20261104/` |
| Original acquisition manifests (live) | `.local-state/` |
| Old-HDD acquisition metadata (coverage, markers, stale pre-split manifest) and the early Phase 11 AC event-level store, hash-verified; the old-HDD raw objects duplicated the certified copies and were released for deletion on 3 November 2026 | `archive/old-hdd-2026-11-03/` on the output volume |
| Acquisition run logs and launch records | `data/phase10/` |
| Phase 11 runoff summary release | `2026/runoff-summary-analysis-full-20261102/` on the output volume |
| Phase 11 job configuration, progress and benchmarks | `data/national/phase11-feature-oriented-2026-11-02/`, pointer `data/national/current-phase11.json` |
| Superseded event-level job (stopped 2 November at 15425 objects) | `data/national/phase11-overnight-2026-11-01/`; do not resume |
| Earlier Phase 11 tuning, tranches, capacity and protection reviews | `data/national/phase11-*-2026-10-31/` |
| Foundation demo, pilot and review bundles | `data/phase9/` |
| Official AC BWEB import | `data/official-bu/ac-runoff-2026-10-30/` |
| AC development artifacts, Phases 12–17 | `data/phase12/` … `data/phase17/` |
| Dashboard datasets | `data/dashboard-ac-2026-10-30/`, `data/dashboard-development-2026-10-30/` |

## Interface map

| Area | Modules and guides |
| --- | --- |
| Runtime | `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked` |
| CLI | `election_audit/cli.py`. Legacy: `download resume inspect doctor`. Pipeline: `snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill`. Extensions: `national electoral-verify operational-review features research-protocol research-models investigations dashboard dashboard-export stage-sources bulk-download semantic-pass sa-logs results-hierarchy integrity-docs integrity-check section-table` |
| Recipes | `justfile`; one recipe per CLI command plus `setup doctor fmt lint test contracts-check docs-check docs-command-check check` |
| Acquisition | `scripts/download_tse_logs.py` (`--round 1` or `--round 2`), `election_audit/elections.py`; SSD staging `source_staging` (`stage-sources`); open-data archives `bulk_acquisition` (`bulk-download`); EA20 hierarchy `results_hierarchy` (`results-hierarchy`); TRE integrity test documents `integrity_documents` (`integrity-docs`); certified manifest pins `resources/pins/`; [acquisition reference](acquisition-reference.md) |
| Snapshot/source/coverage | `source_inventory`, `coverage`, `snapshots`; [snapshots](snapshots.md) |
| Structural parse | `archive_parsing` (`jez-structural-v1`), `sevenzip` (2022 7z logs); [archive parsing](archive-parsing.md) |
| Operational reconstruction | `reconstruction` (`operational-v1`), `operational_review` (`real-operational-v1`, Phase 13), `semantic_pass` (`session-aggregates-v5`, session rules `sessions-v2`, Phases 21–22 and 20b; rules `real-log-rules.json` and `real-log-rules-2022.json`), `sa_logs` (`sa-log-summary-v1`); [reconstruction](reconstruction.md), [semantic pass](semantic-pass.md) |
| Operational releases | `publication`, `operational_marts`, `release_tools`; [publication](publication.md) |
| National structural processing | Summary path: `national_parallel`, `national_summary`, `national_summary_release`, `national_summary_tools`, `national_summary_tuning`, `national_resources`; [feature-oriented processing](feature-oriented-processing.md). Event-level path: `national_benchmark`, `national_tuning`, `national_workload`, `national`, `national_storage`, `national_relocation`, `national_migration`, `national_overnight`; [national processing](national-processing.md) |
| Integrity checks | `integrity_checks` (`integrity-sections-v4`, `integrity-logs-v2`; signature layout `resources/assinatura-2026-observed.asn1`), `round1_prefix` (`integrity-round1-prefix-v1`, `integrity-check prefix`), `printed_bu` (`printed-bu-v1`, `integrity-check printed`), `ed521_crosscheck` (`ed521-crosscheck-v1`), `zeresima` (`integrity-zeresima-v2`), `gedai` (`integrity-gedai-v3`), `hash_lists` (`integrity-hash-lists-v1`), `signature_errors` (`integrity-signature-errors-v1`), `signed_results` (`signed-results-fetch-v1`, `integrity-jws-v2`; `results-hierarchy fetch-signed`); [integrity checks](integrity-checks.md) |
| Electoral imports and verification | `electoral_imports`, `electoral_results`, `derivatives`, `electoral_reports`, `official_bu`; `binary_bu` and `electoral_verification` (Phase 12); [electoral results](electoral-results.md). `electoral_references` is an unwired, untested prototype for official reference sets |
| Analysis foundation | `analysis`, `analysis_partitions`, `analysis_ledgers`, `analysis_reports`; [analysis](analysis.md) |
| Section table | `section_table` (`section-features-v5.1`, Phases 22 and 20b); [section table](section-table.md), [observation register](observations.md) |
| Research path | `features` (Phase 14), `research_protocol` and `research_evaluation` (Phase 15), `research_models` (Phase 16), `investigations` (Phase 17); see their handoffs |
| Dashboard | `dashboard`, `dashboard_data`, `dashboard_ui`, `dashboard_development`, `election_audit/notebooks/` (Phase 18) |
| Reproduction | `reproduction`, `pilot`, `walkthrough`; [reproduction](reproduction.md) (national run times and resources: [what to expect](reproduction.md#what-to-expect-on-the-national-data)), [backfill](backfill.md) |
| Cross-model review | `scripts/cross_review.py` (`prepare`, `run`, `prompt`), `review/` (prompts, packets, schema, campaigns); [cross-model review](cross-model-review.md) |
| Contracts | `election_audit/resources/contracts/schema.json` and `features.json`; `contracts.py`; [schema dictionary](schema-dictionary.md), [feature readiness](feature-readiness.md), [transformation conventions](transformation-conventions.md) |
| Research documents | [study protocol](../../research/analysis-plan.md), [completion plan](../../research/completion-plan.md), [download sources](../../research/download-sources.md), [related work](../../research/related-work.md) |
| Documentation checks | `scripts/check_docs.py` (pairs, revisions, links, fenced parity), `scripts/check_doc_commands.py` (flags via `--help`, SQL syntax) |

Pairs under `docs/en/` and `docs/pt-BR/` share Document-ID and Revision; research
documents keep English paths with `.pt-BR.md` counterparts. Bump both revisions
together. Code, commands, SQL, formulas and numbers stay byte-identical.
