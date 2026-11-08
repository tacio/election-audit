# Tier 1 integrity checks (Phase 20)

Document-ID: EA-INTEGRITY-CHECKS · Revision: 6 · Language: en

[Português](../pt-BR/integrity-checks.md) · [Implementation index](implementation-index.md)

`integrity-check` runs the deterministic checks I1–I9 of the
[study protocol](../../research/analysis-plan.md#5-tier-1-deterministic-integrity-checks)
for 2026, both rounds. Every step reads frozen, hash-checked inputs, writes a new
output root and reports counts with full discrepancy tables. No statistical model is
involved.

## Data access

- Release tables hold statuses and digests, never vote counts. Values appear only in
  `discrepancies.jsonl`, for rows that disagree.
- Attendance and vote totals that later checks need (I5) are written to
  `release/restricted/attendance.parquet`. Check code reads them; nothing reports or
  queries them before the Phase 23 freeze.
- The section pass reads every member of the bulk archives, the 596 protected/stress
  logs included, but the parent process only hashes logs and BU images with SHA-512.
  Workers receive the BU, RDV and signature file of each section; no log is parsed.
- I5–I7 read the Phase 21 semantic-pass releases, which never opened the protected
  logs. Those sections are reported as `protected_or_unavailable`.

## Steps

| Step | Checks | Reads | Writes |
| --- | --- | --- | --- |
| `sections` | I1 (hashes, ECDSA and Ed521 signatures, urn certificates, BU hash chain), I3, I9 (files, identity) | bulk BU/RDV/log archives | `sections`, `contests`, `restricted/attendance`, `archive_members.json` |
| `bweb` | I2 | a `sections` release, BWEB | `contests`, `sections` |
| `hierarchy` | I4 | BWEB, EA20 | `nodes` |
| `correspondence` | I9 (effective urn) | a `sections` release, correspondences (CEFT) | `sections` |
| `logs` | I5, I6, I7 | a `sections` release, Phase 21 releases | `sections` |

Each `release/` also holds `discrepancies.jsonl` and a `manifest.json` with the
binding, a summary and file hashes.

```sh
just integrity-check sections \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --round 2 --output ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --workers 6
just integrity-check bweb \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --bweb-root ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna \
  --output ~/data/election-audit-stage/phase20/national-r2-bweb-v1-20261105
just integrity-check hierarchy \
  --bweb-root ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna \
  --ea20-root ~/data/election-audit-stage/results-hierarchy/ea20-r2-20261104 \
  --round 2 --output ~/data/election-audit-stage/phase20/national-r2-hierarchy-v1-20261105
just integrity-check correspondence \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --ceft-root ~/data/election-audit-stage/inputs/resultados-2026-correspondencias-esperadas-e-efetivadas-2-turno \
  --output ~/data/election-audit-stage/phase20/national-r2-correspondence-v1-20261105
just integrity-check logs \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --semantic ~/data/election-audit-stage/phase21/national-r2-20261103 \
  --semantic-round1 ~/data/election-audit-stage/phase21/national-r1-20261103 \
  --output ~/data/election-audit-stage/phase20/national-r2-logs-v1-20261105
```

## What each check compares

**I1, signatures.** Each section's signature file (`-vota.vsc`, `-sa.vsc`) holds two
lists of per-file SHA-512 hashes: a software one signed with CEPESC and a hardware
one signed with the urn key. The pass checks every published file against both
lists, each list's self-hash and that the two lists agree. The lists also name
seven files TSE does not publish (`jufa`, `imgze`, `hash`, three `wsq*` biometric
images and `mr.ver`); they are recorded as unpublished, not as failures.

- UE2013 and UE2015 urns sign with ECDSA P-521. Their DER certificate (issued by
  `AC URNA`) verifies the hardware self-signature, every published file's signature
  and the signature over each BU's vote-total hash chain. Signatures are DER and
  cover the 64-byte SHA-512 hash, hashed again with SHA-512.
- UE2020 and UE2022 urns sign with EdDSA on E-521 (Ed521, ICP-Brasil DOC-ICP-01.01;
  PEM certificates from `AC UE2020` and `AC UE2022`), over the same double hash.
  Since Phase 20b (`integrity-sections-v3`) these are verified with
  [`ed521rs`](https://pypi.org/project/ed521rs/) under RFC 8032 decoding rules, which
  give the verdicts of `election_audit/ed521.py`. Each signature is also checked as
  ECPy, the verifier in TSE's 2026 format package, would check it;
  `ed521_ecpy_disagreements` counts the signatures where the two verdicts differ.
- Each urn certificate is checked against the published CA certificate that issued
  it (`urn-pki-v2`): the CA's signature (ECDSA P-521 with SHA-512, or Ed521 over the
  raw TBSCertificate, as in TSE's `mr_util.valida_certificado`), the serial against
  that CA's revocation list, and the CA certificate's validity on election day. The
  CA certificates and revocation lists are pinned in `resources/pki/` with their
  provenance. The next link (to `AC RAIZ UE` and `AC URNA v2`) is not checked: those
  certificates are not public ([T1](observations.md#transparency)).
- CEPESC is not public; software signatures are never verified.

Since Phase 20b, BU, RDV and signature files are decoded with the official
specifications of TSE's 2026 format package (`resources/*-2026-official.asn1`,
provenance in `resources/tse-format-2026-official.json`), replacing the mirrored and
observed ones ([T7](observations.md#transparency)). Values do not change; enumeration
labels do (the urn type `reservaSecao` is `contingenciaSecao`).

**I1, BU hash chain.** Each BU election carries a SHA-512 chain over its vote totals.
The header is `pleito|election|municipality|zone|section|load code` (zero-padded to
5, 5, 5, 4, 4 and 24 digits); each block is
`PREVIOUS_HASH_UPPER_HEX|order|office|vote type|count[|candidate|party]`, in print
and hash order. Every block hash and the final `ultimoHashVotosVotavel` must match.

**I2, BU against BWEB.** For every section and contest, the canonical digest of the
nonzero `(class, number, count)` entries of the binary BU must equal that of the BWEB
rows. Classes are N (nominal), L (party), B (blank), X (null) and S (no candidate).
Eligible voters, attendance, polling place, urn serial, load code, flash card, load,
opening, closing and emission times are compared too. BWEB omits zero counts.

**I3, RDV recount.** Every RDV contest is recounted and compared with the BU totals.
A party vote keeps what was typed (an incomplete or unknown candidate number); its
party is the first two digits.

**I4, hierarchy.** BWEB section sums of the presidential contest (tied to the BU by
I2) are compared with every EA20 municipality file, municipalities with their UF
file and UFs (with ZZ) with the national file. EA20 reports votes for a candidacy
voided after the election as technical nulls (`vnt`), which BWEB keeps as nominal;
such votes are mapped before comparing. EA20 counts installed sections (`si`) and
sections not installed (`sni`, with no BU); principal sections are compared with
`si`.

**I5, attendance.** Completed vote cycles in the round's official sessions (summed
over restarts) must equal BU attendance, and biometric cycles the BU's biometric
authorizations. Since `integrity-logs-v2`, a session copied in several memories of
one urn counts once, by block lineage, as in the section table.

**I6, round-1 blocks.** Every round-1 block of a runoff log must equal the block that
starts with the same line on the same urn in the round-1 log. The last round-1 block
continues in the runoff log after the round-1 log was written, so it can only match
as a prefix; Phase 21 kept whole-segment fingerprints, so that block is reported as
`open_prefix_unverified`.

**I7, clock and session rules** (`integrity-logs-v1`, `integrity-logs-v2`): R1 at least one official
session of the round; R2 the last one has a closing reading; R3 no backward clock
step inside official sessions; R4 no completion outside a cycle; R5 every official
session starts on the election date; R6 official sessions do not overlap.

**I8, printed BUs** (`printed-bu-v1`): BU copies read from the QR codes of the paper
printed at the polling station, collected by third parties, against the published BU
of the same section. See [Phase 20b: I8 printed BUs](#phase-20b-i8-printed-bus).

**I9, population and identity.** File presence per section, file names against BU and
RDV contents, pleito and phase, BWEB identity, unexpected archive members, and each
section's effective urn in the correspondence files (urn serial, load code, flash
card, load time) against its BU.

## Development results

On AC (both rounds, development data) and ZZ (round 1), before the national runs:

- I1: every published file matched both lists; ZZ ECDSA signatures (1310 sections,
  including 29 SA packages) and BU chain signatures all verified; AC certificates
  are `AC UE2020` (989) and `AC UE2022` (1281), valid on election day.
- I2, I3, I4: no discrepancy (AC: 11350 and 4540 contests, 22 municipalities and the
  UF node).
- I5: AC completed cycles equal BU attendance, and biometric cycles equal biometric
  authorizations, in every section with a log (1667 and 1663).
- I6 (AC round 2): 1651 sections equal in every closed round-1 block, with the last
  block open; 17 runoff logs have no round-1 block (the urn was reloaded), one is
  another urn, and five runoff logs have round-1 blocks absent from the round-1 log.
- I9: the effective urn matched the BU in every AC and ZZ section once the
  correspondence load codes (which drop a leading zero) were padded.

## National results

Runs of 5 November 2026, both rounds, 499207 sections each, into
`~/data/election-audit-stage/phase20/national-r{1,2}-*-20261105/` (`sections-v1`,
`bweb-v1c`, `hierarchy-v1`, `correspondence-v1`, `logs-v1`). The section pass took
64 and 59 minutes with six workers.

| Check | Round 1 | Round 2 |
| --- | --- | --- |
| I1 published files match both lists, lists agree, self-hashes | 499207 | 499207 |
| I1 ECDSA verified (UE2013/UE2015), files and BU chain signatures | 99985, 0 failed | 99957, 0 failed |
| I1 Ed521, not verified (UE2020/UE2022) | 399222 | 399250 |
| I1 BU hash chains intact | 2490805 of 2490805 | 539817 of 539817 |
| I3 RDV recount equal | 2490795 of 2490805 | 539817 of 539817 |
| I2 BU contest equal to BWEB | 2490804 of 2490805 | 538944 of 539819 |
| I4 nodes equal in every vote measure | 5786 of 5786 | 5786 of 5786 |
| I5 completed cycles equal BU attendance | 496859 (85 differ, 2263 unavailable) | 497096 (36 differ, 2075 unavailable) |
| I7 sections with a failed rule | 2138 | 1815 |
| I9 effective urn matches the BU | 499207 | 499207 |

- I1: every certificate is valid on election day. No signature that could be checked
  failed.
- I3: the 10 round-1 differences are every contest of two MG sections counted with
  the SA system (41238/0039/0168 and 50075/0047/0041). In both, each contest's BU has
  exactly 20 more voters than the RDV (40 senate votes). These are the only two SA
  packages outside ZZ; the other 29 recount exactly. Phase 20b found the cause: their
  RDVs hold two blocks per contest (20 ballots, then 261 and 258), and
  `integrity-sections-v3` kept only the last. `integrity-sections-v4` sums the blocks
  ([O5](observations.md#operations)).
- I2: no contest present on both sides differs. The rest are presence or field
  differences with a known cause:
  - Round 2, 871 `bu_only` contests: ten municipal elections held with the runoff
    (elections 6282–6293: supplementary mayoral elections, cargo 11, and three
    consultations, cargos 25–27) in 13 municipalities of MT, PR, RJ, RS, SP and TO.
    The national BWEB files carry only the presidential runoff, so these contests have
    no BWEB counterpart and stay unverified against BWEB.
  - ZZ 29564/0091 (both rounds) and 30686/0443 (round 2): SA sections with zero
    attendance. BWEB omits the section (round 1) or writes one placeholder row with
    cargo `-1` (round 2), so the BU's empty presidential contest is `bu_only` and the
    placeholder `bweb_only`.
  - 30 and 29 `section_fields` rows: the polling place of every SA package. The SA BU
    records place `0001`; BWEB records the section's own place.
- I4: every vote measure (candidates, blank, null, technical null) and every section
  count but the two below equal EA20 at all 5757 municipalities, 28 UF nodes and the
  national node. Electorate differs at 41 and 42 ZZ municipalities, all with no
  presidential BWEB row: 40 abroad cities with voters but no installed section, plus
  the zero-attendance SA sections above (one in round 1, two in round 2), which EA20
  counts as installed.
- I5: the 85 and 36 differences are open. In 7 and 3 the logs hold more completed
  cycles than BU attendance, all with several sessions (one ES round-2 section has
  612 = 2 × 306), which points at re-run sessions summed twice. In 78 and 33 they hold
  fewer, 51 and 17 of them in a single session; unresolved cycles explain only 4 and
  2. Grouping multi-run sessions is Phase 22 work. Phase 20b reconciled them: see
  [session rules v2 and the I3/I5 reconciliation](#phase-20b-session-rules-v2-and-the-i3i5-reconciliation).
- I6 (round 2): 493122 sections are equal in every closed round-1 block with the last
  block open. 3645 more are equal except that they also hold round-1 blocks absent
  from the round-1 log (3553 with the open block, 92 without); 1464 have no round-1 block; 162 are another
  urn; 99 have at least one closed round-1 block that differs; 2 have no round-1 log
  (the MG SA sections). The rest are small combinations listed in the manifest.
- I7: R1 (no official session of the round) fails in 1636 and 1449 sections, R2
  (last session without a closing reading) in 438 and 349, R3 (backward clock step)
  in 34 and 9, R6 (overlapping sessions) in 31 and 9, R4 in 1 and 0; R5 never fails.
- I9: the correspondence files list 3060 and 2721 sections whose effective urn is not
  the expected one; in every section the effective urn equals the BU's urn, load
  code, flash card and load time.
- SA, missing and protected logs: 627 and 626 sections are `protected_or_unavailable`
  for I5–I7.

## Phase 20b: signatures and certificates

Runs of 6 November 2026 into
`~/data/election-audit-stage/phase20/national-r{1,2}-sections-v3-20261106/`:

```sh
just integrity-check sections \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --round 1 --output ~/data/election-audit-stage/phase20/national-r1-sections-v3-20261106 \
  --workers 6
```

| Check | Round 1 | Round 2 |
| --- | --- | --- |
| Hardware self-signature verified | 499207 of 499207 | 499207 of 499207 |
| ECDSA sections (UE2013/UE2015) | 99985 | 99957 |
| Ed521 sections (UE2020/UE2022) | 399222 | 399250 |
| File signatures verified | 1996828, 0 failed | 1996828, 0 failed |
| BU chain signatures verified | 997114, 0 failed | 539817, 0 failed |
| Urn certificate signed by its CA | 499207 | 499207 |
| Urn certificate serial revoked | 0 | 0 |
| Ed521 verdicts differing from ECPy's | 0 | 0 |

- Every urn certificate was valid on election day. `AC URNA` (99985 and 99957
  sections) was not: its published certificate expired on 2026-07-18
  ([T2](observations.md#transparency)).
- In 14 and 3 sections the signature file was signed by an urn other than the BU's;
  every signature in them verifies with that urn's valid, unrevoked certificate
  ([O13](observations.md#operations)). They account for six of the eight model
  mismatches reported by I9 in Phase 20.
- The same pass first ran with the pure-Python verifier (`integrity-sections-v2`,
  into `national-r{1,2}-sections-v2-20261106`). The `ed521rs` runs are equal to it row
  for row in the section, contest and restricted tables of both rounds.

| Run | Ed521 verifier | Wall time | CPU time | Peak memory |
| --- | --- | --- | --- | --- |
| Round 1, v2 | `election_audit/ed521.py` | 2:57:15 | 65017 s | 4.8 GB |
| Round 2, v2 | `election_audit/ed521.py` | 2:21:17 | 50280 s | 4.1 GB |
| Round 1, v3 | `ed521rs` 0.1.0 | 1:07:49 | 10210 s | 4.9 GB |
| Round 2, v3 | `ed521rs` 0.1.0 | 1:00:38 | 5411 s | 4.2 GB |

All runs used six workers. The v3 runs used a local `ed521rs` wheel built from the
commit before the `v0.1.0` tag, with the same verification code; the AC runs on the
PyPI wheel are equal to them row for row. The manifest records the version, the SIMD
backend and the SHA-256 of the native module.

## Phase 20b: I6 prefix re-read

`integrity-check prefix` (`integrity-round1-prefix-v1`, module `round1_prefix`)
replaces the fingerprint-only I6 comparison for every pair of round-1 blocks whose
lengths differ. It re-reads, from the certified staging, only objects the Phase 21
releases already read, so the protected/stress logs stay unread, and re-hashes each
object against its certified SHA-256. Streams and segments are rebuilt from the
line counts Phase 21 recorded; a rebuilt segment is used only if it reproduces the
recorded fingerprint and first-line hash, otherwise the pair is
`realignment_failed`. The first N lines of the longer block are then hashed and
compared with the shorter block's fingerprint. Pairs that still differ are read on
both sides and described by their common prefix, the round-1 lines found again
afterwards and up to ten digit-masked message templates of the differing lines, in
`differences.jsonl`. The release also holds `pairs.parquet` (one row per round-1
block pair of different content) and `sections.parquet`, which keeps the
`integrity-logs-v1` status as `i6_v1` next to the revised `i6` and counts blocks by
state.

Run of 7 November 2026:

```sh
just integrity-check prefix \
  --logs ~/data/election-audit-stage/phase20/national-r2-logs-v1-20261105 \
  --semantic ~/data/election-audit-stage/phase21/national-r2-20261103 \
  --semantic-round1 ~/data/election-audit-stage/phase21/national-r1-20261103 \
  --output ~/data/election-audit-stage/phase20b-i6/national-v1-20261107 --workers 6
```

| Round-1 block pairs | Pairs | Status |
| --- | --- | --- |
| Last round-1 block, runoff longer, first N lines equal | 496793 | `prefix_open` |
| Last round-1 block, still differs | 3 | `differs` |
| Closed round-1 block, runoff shorter and a prefix of it | 6 | `runoff_prefix_of_round1` |
| Closed round-1 block, still differs | 110 | `differs` |

No object failed and no segment failed to rebuild. Every open last block of the
round-1 log is an exact prefix of its runoff copy: 493125 sections are now
`equal_open_prefix_equal`, where `integrity-logs-v1` left 493122 as
`equal_closed_open_prefix_unverified` and 3 as `open_prefix_unverified`.

The 113 pairs that still differ were read line by line:

- 97 are the same lines with different block limits. The runoff block is an
  in-order subsequence of the round-1 log's stream that skips only lines written
  when the urn restarts, before `Iniciando registro do log na MI e na ME` (95 skip
  exactly six: `Início das operações do logd`, `Urna ligada em …`,
  `Estrutura de diretórios da ME: OK`, `Iniciando aplicação - #º turno`, the
  software version and the urn model). Without the context-reset line the block does
  not close, so it runs on into the startup lines
  ([O14](observations.md#operations)).
- 15 are in sections whose logs carry several memories of an urn (MI and ME
  members, contingency `-01` members). In 12 every runoff line is in the round-1 log
  in another stream; in 3 the round-1 log holds the external-memory copy and lacks
  the same three restart lines.
- 1, rj/60011/0008/0061, is a real disagreement among copies of one urn's
  election day ([O15](observations.md#operations)). The published round-1 log has 311
  computed votes, equal to BU attendance; the external-memory copy carried in the
  runoff log has 305, ends later and has corrupted bytes; the internal-memory copy has
  303. The round-1 log's stream is broken by one line whose urn identifier differs in
  two digits, which is why Phase 21 counted only one session of 36 votes and I5
  reported this section.

Of the 7079 round-1 blocks present only in the runoff log, 5809 start after the
round-1 log's last line on the same urn and 1269 are on urns with no round-1 block in
the round-1 log (mostly memories of other urns carried in multi-member objects); one
is unexplained. 1464 sections have no round-1 block in the runoff log, 162 a
different urn and 2 no round-1 log, as before.

| Run | Objects read | Wall time | CPU time | Peak memory |
| --- | --- | --- | --- | --- |
| Round 2, prefix v1 | 496793 | 1:19:42 | 26699 s | 3.6 GB |

Six workers; the peak is the planning process, which holds the block pairs in
DuckDB and Python. The release is 36 MB, the per-chunk shards 198 MB.

## Phase 20b: session rules v2 and the I3/I5 reconciliation

Runs of 7–8 November 2026. `integrity-sections-v4` sums an RDV's blocks for one
contest ([O5](observations.md#operations)): I3 is now equal in all 2490805 and
539817 contests. The release differs from v3 only in the rows of the two MG SA
sections (their 10 contests); round 2 is identical. The semantic pass was
rerun with session rules `sessions-v2` (`session-aggregates-v4`,
[semantic pass](semantic-pass.md#version-4-phase-20b)). I5–I7 then ran twice: on
the new passes (`logs-v2`, code `integrity-logs-v1`), and with memory copies of a
session counted once (`logs-v3`, code `integrity-logs-v2`,
[O16](observations.md#operations)). The final roots are
`~/data/election-audit-stage/phase20/national-r{1,2}-logs-v3-20261108/`.

```sh
just integrity-check logs \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v4-20261107 \
  --semantic ~/data/election-audit-stage/phase20b-sessions/v4-national-r2-20261107 \
  --semantic-round1 ~/data/election-audit-stage/phase20b-sessions/v4-national-r1-20261107 \
  --output ~/data/election-audit-stage/phase20/national-r2-logs-v3-20261108
```

| Check | Phase 20, round 1 | Phase 20b, round 1 | Phase 20, round 2 | Phase 20b, round 2 |
| --- | --- | --- | --- | --- |
| I3 RDV recount equal | 2490795 of 2490805 | 2490805 of 2490805 | 539817 of 539817 | 539817 of 539817 |
| I5 equal / differ / unavailable | 496859 / 85 / 2263 | 498558 / 10 / 639 | 497096 / 36 / 2075 | 498570 / 7 / 630 |
| I5 biometric equal / differ | — | 497277 / 10 | — | 497290 / 6 |
| I7 R1 (no official session) | 1636 | 12 | 1449 | 4 |
| I7 R2 (no closing reading) | 438 | 434 | 349 | 347 |
| I7 R3 (backward clock step) | 34 | 34 | 9 | 9 |
| I7 R5 (session started before election day) | 0 | 1569 | 0 | 1361 |
| I7 R6 (overlapping sessions) | 31 | 24 | 9 | 7 |

R4 fails in one round-1 section in both runs. The unavailable sections are the 627
and 626 without a semantic-pass log plus those with no official session. R1 falls
and R5 rises for the same reason: an urn switched on before election day and left
running now has an official session, flagged `started_before_election_day`. R5
fails in exactly the sections that have such a session, one per object.

Of the 85 and 36 Phase 20 differences, the `sessions-v2` rules resolve 69 and 27
(mid-day restarts that lost later votes, urns left on overnight), and counting
memory copies once resolves 6 and 2 more. No section differs that did not differ in
Phase 20. Each of the 17 that remain was read session by session:

| Cause | Round 1 | Round 2 |
| --- | --- | --- |
| Log short by no more than its unresolved cycles (1 or 2) | 7 | 3 |
| Log one cycle short beyond its unresolved cycle | 0 | 1 (rs/89060/0017/0191) |
| Package holds another section's urn ([O13](observations.md#operations)) | 0 | 1 (es/57932/0009/0085) |
| Broken stream ([O15](observations.md#operations)) | 1 (rj/60011/0008/0061) | 0 |
| Log covers only part of election day ([O17](observations.md#operations)) | 2 | 2 |

The seven round-1 sections short by their unresolved cycles are es/56995/0053/0211,
rj/58971/0087/0184, rn/16039/0029/0028, rs/89036/0083/0044, sp/64254/0291/0346,
sp/71072/0260/0037 and sp/63614/0227/0305; the three round-2 sections are
ba/34711/0021/0178, pb/21750/0002/0254 and pi/11533/0003/0216. In no remaining
section does the log hold more completed cycles than BU attendance, except
es/57932/0009/0085, whose package carries two urns. None of the 17 has a printed BU
copy (I8).

**DataUrnas-BR.** Its round-1 per-section log table (commit `f5e8005`, frozen in
`inputs/dataurnas-br-f5e8005-20261108/`) covers all 499207 sections and flags 40
whose log votes differ from attendance: 31 SA sections, which have no urn log, and
9 others. Those 9 are our round-1 sections other than rj/60011/0008/0061, with the
same log count in every one. For rj/60011/0008/0061 it counts 311, equal to
attendance, because it does not split the stream on the urn identifier
([O15](observations.md#operations)). In the sections where we counted memory copies
twice, its count equals attendance (rs/89036/0083/0044: one short, as ours now):
it counts identical lines repeated across a package's files once. Its round-2
section table has no log counts, so round 2 was not compared. Its RDV recount
reports no divergence in either round, which agrees with I3 v4. Only these
sections and DataUrnas-BR's national counts were read.

**I6 rerun.** `integrity-check prefix` ran again on `logs-v2` and the v4 passes into
`~/data/election-audit-stage/phase20b-i6/national-v2-20261107/` (same code,
`integrity-round1-prefix-v1`). The new block limits change the pairs: 497032 block
pairs, 496999 objects read, no object or rebuild error.

| Round-1 block pairs | v1 | v2 |
| --- | --- | --- |
| Last round-1 block, runoff longer, first N lines equal (`prefix_open`) | 496793 | 496911 |
| Runoff block a prefix of the round-1 block (`runoff_prefix_of_round1`) | 6 | 6 |
| Still differs, closed block | 110 | 110 |
| Still differs, last block | 3 | 5 |

The 115 pairs that still differ are in 101 sections. 110 differ only by restart
lines ([O14](observations.md#operations)): in 99 the runoff copy lacks them, in 11
the round-1 copy does. 4 are the two memory copies of mg/44458/0103/0221
([O16](observations.md#operations)) paired across each other, which end at
different lines. The last is rj/60011/0008/0061 ([O15](observations.md#operations)).
493160 sections are now `equal_open_prefix_equal` (493125 in v1). Blocks present
only in the runoff log (7079, of which 5809 start after the round-1 log ends), 1464
sections without a round-1 block, 162 with another urn and 2 without a round-1 log
are unchanged.

| Run | Wall time | CPU time | Peak memory | Release |
| --- | --- | --- | --- | --- |
| Sections v4, round 1 (6 workers) | 1:10:48 | 10838 s | 4.7 GB | 266 MB |
| Sections v4, round 2 (6 workers) | 1:02:15 | 5650 s | 4.1 GB | 118 MB |
| Logs v2, round 1 / round 2 | 0:27 / 0:51 | — | 2.7 / 3.2 GB | 1 / 2 MB |
| Logs v3, round 1 / round 2 | 0:22 / 0:41 | — | 2.6 / 3.3 GB | 1 / 2 MB |
| Prefix v2 (6 workers) | 1:08:02 | 22707 s | 3.6 GB | 36 MB (+199 MB shards) |

The logs runs are one process; their peak is the session table held in DuckDB and
Python.

## Phase 20b: I8 printed BUs

`integrity-check printed` (`printed-bu-v1`, module `printed_bu`) follows TSE's 2026
manual for the BU QR codes (format VRQR 6.0). Each `QRBU` code holds a slice of the
BU content and `HASH`, the SHA-512 of everything before it; the last code adds
`ASSI`, the urn's signature over the SHA-512 of the final hash (Ed521 on
UE2020/UE2022, ECDSA P-521 on UE2013/UE2015), and two `QRCE` codes carry the urn
certificate. For every collected copy the pass recomputes the hash chain, verifies
the signature and the certificate's TSE issuing authority (as in Phase 20b above),
then compares every printed field with the binary BU published for that section:
header (urn number, load code and history, software version, polling place, voters,
attendance, enablement counts, opening and closing times) and, per election and
office, every candidate, party, blank and null count and the eligible voters. It also
compares the QR certificate with the hardware certificate of the section's signature
file and checks the printed totals against the counts they sum. Printed fields that
have no BU field (`AGRE`, `ORLC`, `PROC`, `DTPL`, `VERC`) are not compared; any
unparsed token is recorded.

Inputs, frozen on 7 November 2026 in `~/data/election-audit-stage/inputs/`:

- `i8-cmind-20261107`: the 120 BUs of CMInd's Totalização Paralela, from its public
  API (`/api/public-bu`, the endpoint its site calls without login), with the raw QR
  text, fetched one at a time with a 3-second pause, with `SHA256SUMS`.
- `i8-arvor-20261107`: Arvor's Totalização paralela as published in
  `ArvorCo/PNAD` at commit `570e7a2`, checked against its own manifest: 408 runoff
  BUs with the reassembled content, final hash, signature and certificate. The
  per-code slices are not published; the pass recovers them by finding the cut points
  whose chain gives the final hash (every copy fitted one code).
- `i8-tse-qrbu-20261107`: TSE's QR manual (SHA-256 `ffded730…`) and example BUs
  (`8b1e28fd…`). TSE refuses scripted requests, so the hashes were computed in a
  browser on TSE's site and the bytes taken from Arvor's copies, which match.

Arvor declares a political side; CMInd presents itself as citizen oversight. Neither
selection is random, and both depend on who chose to scan.

```sh
just integrity-check printed \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --cmind ~/data/election-audit-stage/inputs/i8-cmind-20261107 \
  --arvor ~/data/election-audit-stage/inputs/i8-arvor-20261107 \
  --output ~/data/election-audit-stage/phase20b-i8/v1-20261107
```

| Collection | Round | Copies | Equal |
| --- | --- | --- | --- |
| CMInd | 1 | 49 | 49 |
| CMInd | 2 | 71 | 71 |
| Arvor | 2 | 408 | 408 |

All 528 copies have an intact chain, a verified urn signature (Ed521 on 382, ECDSA
P-521 on 146) and a certificate signed by its TSE authority, not revoked; each
certificate equals the one in the section's published signature file. Every printed
field equals the published BU (739 contests), and no printed total disagrees with its
counts. The copies cover 518 sections: 49 in round 1 (4 UFs, 7 municipalities) and
469 in the runoff (21 UFs and abroad, 78 municipalities); 10 sections have a copy in
both collections, with the same final hash. None of the remaining I5 sections has a
copy.

| Run | Copies | Wall time | Peak memory |
| --- | --- | --- | --- |
| I8 v1 | 528 | 0:22 | 0.56 GB |

One process; reading the bulk archives' central directories dominates (one archive
open at a time). The release (`printed.parquet` and its manifest) is 140 kB.

## Limits

- Certificate chains are verified only up to the intermediate CAs; the root and
  `AC URNA v2` certificates are not public.
- I6 covers only the non-protected logs; the 596 protected/stress logs are read
  after the Phase 23 freeze. One round-1 block present only in the runoff log is
  unexplained.
- I8 covers 518 sections chosen by whoever scanned them, not a sample; it says
  nothing about other sections.
- The ten municipal elections held with the runoff are not in the national BWEB, so
  I2 does not cover them.
- I5 differs in 10 and 7 sections. All but one have a known cause (unresolved
  cycles, another section's urn, a broken stream, a log covering part of the day);
  rs/89060/0017/0191 is one cycle short beyond its unresolved cycle. Four logs cover
  only part of election day (O17), so their measures are partial.
- Agreement among artifacts of the same software chain shows consistency, not voter
  intent.
