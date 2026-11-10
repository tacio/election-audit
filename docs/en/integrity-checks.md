# Tier 1 integrity checks (Phase 20)

Document-ID: EA-INTEGRITY-CHECKS · Revision: 13 · Language: en

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
binding, a summary and file hashes. `discrepancies.jsonl` lists rows that disagree or
fail. Rows a check could not evaluate (a protected or missing log, I5 `unavailable`)
are counted in the manifest summary, not listed; an empty file is therefore no
statement about coverage, which the summary gives (xr1-20261109-P0-07).

```sh
just integrity-check sections \
  --bulk-root $EA_DATA/bulk/2026-arqurnatot \
  --round 2 --output $EA_STAGE/phase20/national-r2-sections-v1-20261105 \
  --workers 6
just integrity-check bweb \
  --sections $EA_STAGE/phase20/national-r2-sections-v1-20261105 \
  --bweb-root $EA_STAGE/inputs/resultados-2026-boletim-de-urna \
  --output $EA_STAGE/phase20/national-r2-bweb-v1-20261105
just integrity-check hierarchy \
  --bweb-root $EA_STAGE/inputs/resultados-2026-boletim-de-urna \
  --ea20-root $EA_STAGE/results-hierarchy/ea20-r2-20261104 \
  --round 2 --output $EA_STAGE/phase20/national-r2-hierarchy-v1-20261105
just integrity-check correspondence \
  --sections $EA_STAGE/phase20/national-r2-sections-v1-20261105 \
  --ceft-root $EA_STAGE/inputs/resultados-2026-correspondencias-esperadas-e-efetivadas-2-turno \
  --output $EA_STAGE/phase20/national-r2-correspondence-v1-20261105
just integrity-check logs \
  --sections $EA_STAGE/phase20/national-r2-sections-v1-20261105 \
  --semantic $EA_STAGE/phase21/national-r2-20261103 \
  --semantic-round1 $EA_STAGE/phase21/national-r1-20261103 \
  --output $EA_STAGE/phase20/national-r2-logs-v1-20261105
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

**I7, clock and session rules** (`integrity-logs-v1` to `integrity-logs-v3`): R1 at least one official
session of the round; R2 the last one (by urn clock since v3) has a closing reading; R3 no backward clock
step inside official sessions; R4 no completion outside a cycle; R5 every official
session starts on the election date; R6 official sessions do not overlap.

**I8, printed BUs** (`printed-bu-v1`, `printed-bu-v2`): BU copies read from the QR codes of the paper
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
`$EA_STAGE/phase20/national-r{1,2}-*-20261105/` (`sections-v1`,
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
`$EA_STAGE/phase20/national-r{1,2}-sections-v3-20261106/`:

```sh
just integrity-check sections \
  --bulk-root $EA_DATA/bulk/2026-arqurnatot \
  --round 1 --output $EA_STAGE/phase20/national-r1-sections-v3-20261106 \
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
  --logs $EA_STAGE/phase20/national-r2-logs-v1-20261105 \
  --semantic $EA_STAGE/phase21/national-r2-20261103 \
  --semantic-round1 $EA_STAGE/phase21/national-r1-20261103 \
  --output $EA_STAGE/phase20b-i6/national-v1-20261107 --workers 6
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
`$EA_STAGE/phase20/national-r{1,2}-logs-v3-20261108/`.

```sh
just integrity-check logs \
  --sections $EA_STAGE/phase20/national-r2-sections-v4-20261107 \
  --semantic $EA_STAGE/phase20b-sessions/v4-national-r2-20261107 \
  --semantic-round1 $EA_STAGE/phase20b-sessions/v4-national-r1-20261107 \
  --output $EA_STAGE/phase20/national-r2-logs-v3-20261108
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
`$EA_STAGE/phase20b-i6/national-v2-20261107/` (same code,
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

Inputs, frozen on 7 November 2026 in `$EA_STAGE/inputs/`:

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
  --bulk-root $EA_DATA/bulk/2026-arqurnatot \
  --cmind $EA_STAGE/inputs/i8-cmind-20261107 \
  --arvor $EA_STAGE/inputs/i8-arvor-20261107 \
  --output $EA_STAGE/phase20b-i8/v1-20261107
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

## Phase 20b: checks added from DataUrnas-BR

Five checks that [DataUrnas-BR](../../research/related-work.md) runs and this
project lacked ran nationally on 8–9 November 2026. Each writes a new root with
`binding.json` and a checksummed `release/`. Operator and voter identifiers never
reach an output.

### Ed521 cross-check

`integrity-check ed521-crosscheck` (`ed521-crosscheck-v1`, module
`ed521_crosscheck`) reruns the section checks (`integrity-sections-v4`) and hands
every Ed521 verdict, on urn signatures and on the CA signature of each urn
certificate, to DataUrnas-BR's own verifier, loaded unmodified from a pinned file.
It also runs the 53 vectors of `ed521rs` (33 edge cases, 2 from ECPy, 18 from 2026
urns) through both verifiers. Inputs, frozen in
`$EA_STAGE/inputs/ed521-crosscheck-refs-20261108/`: DataUrnas-BR's
`ed521.py` at commit `f5e8005` (SHA-256 `bff76f54…`) and the vectors of `ed521rs` at
commit `e711763`.

```sh
just integrity-check ed521-crosscheck \
  --bulk-root $EA_DATA/bulk/2026-arqurnatot \
  --round 1 --workers 6 \
  --reference $EA_STAGE/inputs/ed521-crosscheck-refs-20261108/dataurnas-ed521.py \
  --reference-label alissonlinneker/DataUrnas-BR@f5e80059526e511bea7d52aef6a1570de42c3789 \
  --vectors $EA_STAGE/inputs/ed521-crosscheck-refs-20261108/vectors \
  --output $EA_STAGE/phase20b-ed521/national-r1-20261108
```

| Round | Sections | Urn signatures | CA signatures | Disagreements |
| --- | --- | --- | --- | --- |
| 1 | 399222 | 2794564 | 399222 | 0 |
| 2 | 399250 | 2428563 | 399250 | 0 |

Every signature was valid in both verifiers. On the vectors, DataUrnas-BR's verifier
agrees with this project's strict mode in all 53; it differs from ECPy's decoding in
18, as the strict mode does (RFC 8032 decoding rules). No real signature falls in
those cases.

### Zerésima

The semantic pass (`session-aggregates-v5`, [semantic pass](semantic-pass.md#version-5-phase-20b))
keeps a marker for every zerésima and readiness line. `integrity-check zeresima`
(`integrity-zeresima-v3`, module `zeresima`) reads the markers of each section's
official blocks of the round. Copies of a block in both memories count once. Urns
that recorded votes without a zerésima of their own are counted, not failed: a
contingency urn takes over a section whose zerésima the replaced urn printed. Z6
tests that premise.

- Z1: a section with completed votes in its official blocks has a zerésima;
- Z2: no vote cycle completed before the first zerésima of its stream (file order);
- Z3: every zerésima is dated on the election day (urn clock);
- Z4: no zerésima after a vote cycle completed earlier in its stream;
- Z5: no `Urna pronta para receber votos` before the first zerésima of its stream;
- Z6 (v3, cross-model review xr1-20261109 P4-10): an urn with votes but no zerésima
  of its own starts its first voting session after another urn of the section printed
  one (urn clocks); a session or zerésima without a reading counts as unknown.

```sh
just integrity-check zeresima \
  --sections $EA_STAGE/phase20/national-r1-sections-v4-20261107 \
  --semantic $EA_STAGE/phase20b-zeresima/v5-national-r1-20261108 \
  --output $EA_STAGE/phase20b-zeresima/national-r1-zeresima-v3-20261109
```

| Round | Sections read | Passed | Failed | Without official votes | Two or more urns with a zerésima | Protected or unavailable |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 498580 | 498579 | 1 (Z1) | 12 | 379 | 627 |
| 2 | 498581 | 498580 | 1 (Z1) | 4 | 296 | 626 |

- No zerésima follows a vote in either round, every zerésima is dated on election
  day and none comes after the urn declared itself ready.
- The two Z1 sections, sp/71072/0002/0035 and ma/08893/0047/0609, are the two O17
  sections whose only voting session starts near 11:00: the urn that printed the
  zerésima is not in the package ([O17](observations.md#operations)).
- Version 1 (`integrity-zeresima-v1`, `national-r{1,2}-zeresima-v1-20261108`)
  required one zerésima per section and one in every log. It failed 382 and 298
  sections under Z4 and 13 and 5 under Z1. A second zerésima comes from a replacement
  urn or from an urn restarted before voting, which prints a new one
  ([O18](observations.md#operations)); 12 and 4 logs hold no official vote at all.
  Version 2 tests the property that matters, no zerésima after votes.
- Z6 (v3) fails no section. Urns voting without their own zerésima are in 2118
  sections in round 1 (33 with two such urns) and 1428 in round 2 (27); each starts
  voting after another urn of its section printed one. One urn per round has no
  known order: it is in the Z1 section, which has no zerésima at all. Version 3 is
  otherwise equal to version 2 (0:29 and 0:30, one process, 2.9 GB).

### GEDAI preparation logs

`integrity-check gedai` (`integrity-gedai-v3`, module `gedai`) reads TSE's GEDAI-UE
logs of both rounds (one package per preparation computer, per UF) and keeps only
the correspondence and load-media lines. Per section, against the BU's load code,
urn number and load-media serial:

- G1: the (section, load code, urn) correspondence is in a log, or the (load code,
  urn) of a contingency urn is, registered to the section's zone or another;
- G2: the BU's load-media serial equals that correspondence's;
- G3: a section correspondence's load medium was generated for the section.

A rule is not applied in a zone whose published logs hold nothing it could match:
G1 where no section of the zone matched a correspondence, G3 where none matched a
load medium. Those sections are `zone_unpublished`.

A correspondence enters GEDAI as `Recebida` when it comes back from the load medium
that loaded the urn. For each G1 failure, version 3 records what the logs hold about
that medium (`absent_detail`): `medium_never_read_back` (no correspondence received
from it), `medium_not_read_back_after_load` (correspondences received from it, all
dated before the BU's load time) or `medium_read_back_later_without_it` (received
after the load, holding other loads). The two times come from different clocks, the
GEDAI computer's and the urn's, at minute grain. The detail describes the publication;
it does not clear the failure.

TSE publishes two archives per UF and round, exported the day before and on election
day (`031020261345` and `041020261441`, `241020261329` and `251020261327`), each with
a `.sha512` file; all 112 digests match their archives, and the check reads all four
exports. The `leiame.pdf` in each archive (dated 2024) explains only the file names.

```sh
just integrity-check gedai \
  --sections $EA_STAGE/phase20/national-r1-sections-v4-20261107 \
  --gedai-root $EA_STAGE/inputs/resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno \
  --gedai-root $EA_STAGE/inputs/resultados-2026-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-2-turno \
  --output $EA_STAGE/phase20b-gedai/national-r1-gedai-v3-20261109
```

| Round | Section match | Contingency match | Zone unpublished (G1) | Zone unpublished (G3) | G1 failed | G3 failed | G2 failed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 495387 | 3057 | 482 | 284 | 281 | 0 | 0 |
| 2 | 492667 | 5721 | 482 | 284 | 337 | 1 | 0 |

- Zones without correspondences: am/0050, mg/0339 and pa/0106. Their logs hold
  only media generation (pa/0106 in round 1: two packages, 1199 lines), so the computers that
  loaded the urns are not published. Zones without load media: am/0042, pr/0018
  and sp/0176 ([T11](observations.md#transparency)); version 4 finds one medium of
  sp/0176 and fails G3 there (see
  [cross-model review fixes](#phase-20b-cross-model-review-fixes)).
- sp/0176 also matches only 169 of its 437 sections' correspondences; its 268 and
  267 G1 failures are most of the failures. Of those, 192 per round have a load
  medium from which GEDAI never received a correspondence: the computer that loaded
  them is not in the publication either.
- The rest are 13 sections in 12 zones in round 1 and 70 in 56 zones in round 2,
  each in a zone where every other section matches. None of their BU load codes
  appears anywhere in the GEDAI logs, and most were loaded late: the day before the
  election (10 and 35 sections) or between the rounds (22 in round 2). In 9 and 55 the
  medium was not read back after the load, in 4 and 10 it was read back later holding
  other loads, and in 0 and 5 it was never read back
  ([T13](observations.md#transparency)). Late loads are mostly published (on 24
  October, 663 sections matched and 35 did not), so the gap is in what reached
  GEDAI, not in a cut-off.
- Every matched BU load-media serial equals the GEDAI one (G2).
- Version 1 (`national-r{1,2}-gedai-v1-20261108`) failed the unpublished zones
  (763 and 819 G1, 284 and 285 G3). Version 2 (`national-r{1,2}-gedai-v2-20261109`)
  equals version 3 row for row apart from `absent_detail`.

### Hash lists

`integrity-check hash-lists` (`integrity-hash-lists-v1`, module `hash_lists`)
compares the package signature checks recorded in the logs (the `packages` table of
`session-aggregates-v5`) with TSE's published hash lists for the four urn models
(`path1u13`, `path1u15`, `path1u20`, `path1u22`). The logs carry no program hash, so
the check compares names and results, not file contents. It does not verify program
integrity: the SHA-512 values the lists publish are parsed but nothing local can be
compared with them (xr1-20261109-P3-12):

- H1: every program package verified in a log is named in a list, and how:
  `exact` (its model's list), `other_model`, `model_suffix` (named without the
  model year, e.g. `avmodue2020.vst` against `avmodue.vst`) or `not_listed`;
- H2: every program package verification ended in `SUCESSO`.

The lists were downloaded in a browser on 8 November 2026 (TSE refuses scripted
requests, [T5](observations.md#transparency)) and frozen in
`$EA_STAGE/inputs/tse-www-20261108/` with their URLs; all four
are byte-identical to DataUrnas-BR's copies of 27 October.

```sh
just integrity-check hash-lists \
  --semantic $EA_STAGE/phase20b-zeresima/v5-national-r1-20261108 \
  --semantic $EA_STAGE/phase20b-zeresima/v5-national-r2-20261108 \
  --lists $EA_STAGE/inputs/tse-www-20261108 \
  --output $EA_STAGE/phase20b-hash-lists/national-v1-20261109
```

- Of the 1456 (round, model, application, stage, path) rows, 1040 are data files
  (`.vsc` and digit-masked paths), 296 are named exactly in their model's list, 64
  only without the model year and 56 are not listed.
- The seven unlisted program paths are files of the load media or of the load
  itself: `/dsk/fe/estatico/chave/avusrchave.vst` (the list has the
  internal-memory copy, `/dsk/fi/…`), `/dsk/fe/estatico/jez/vota_apl.vst`,
  `vota_ofi.vst`, `avpart_ofi.vst`, `/boot/boot/avbootcfg.vst` and `.vsu`, and
  `/dsk/fi/estatico/dadoscarga.vsu`. The lists cover the installed software only
  ([T12](observations.md#transparency)).
- H2: 86 program verification lines ended in `ERRO`, all at start-up, in a few urns
  of each model (for example `/boot/boot/avboot.vst` 14, `/lib/avlib.vst` 14;
  round-2 logs repeat the round-1 history, so the rounds overlap). After such an
  error the urn reports an integrity failure and asks to be switched off
  (`Desligue a urna`). Whether any urn recorded votes after such an error is
  checked in [signature errors and votes](#signature-errors-and-votes).

### Signature errors and votes

`integrity-check signature-errors` (`integrity-signature-errors-v3`, module
`signature_errors`) asks whether an urn that logged a signature or integrity error
went on to record votes ([O19](observations.md#operations)). It reads the
`signature_error` markers of `session-aggregates-v5` (a template naming a signature
or integrity together with a failure) in each section's official blocks of the
round, and the sessions of the same logs. An error is `verification` when its
template says the urn verified or validated something (start-up package checks, the
voting application's self-check, the load media) and `signing` when the urn failed
to sign a file it writes. Both ask for the urn to be switched off. An urn switched on
again repeats every start-up check, so votes after a restart are counted, not
failed:

- E1: no vote cycle is completed in the same session after a verification error;
- E2: at most one vote cycle, the voter's cycle in flight, is completed in the same
  session after a signing error;
- E3 (v2, cross-model review xr1-20261109 P4-03): after any error, no vote cycle
  (beyond the one in flight after a signing error) is completed in the urn's stream
  before GAP starts an application again. A later session is not proof of a restart,
  so each object holding an error is reread from its staged copy, checked against its
  certified hash, to find the stream's next GAP start.

v2 failed E3 in 22 sections in round 1 and 9 in round 2. Read in the logs (digits
masked), all 31 have one shape: GAP logs `Erro na verificação de assinatura do arquivo
- <name>.vsu` (`vota` 22, `uenux` 5, `rdv` 3, `ze` 1) during an official start-up,
right after `Iniciando aplicação`; it then logs `Início da sincronização dos arquivos
dinâmicos`, restores the dynamic files from the other memory (external 15, internal
16), logs `Sincronização dos arquivos dinâmicos concluída com sucesso`, and only then
starts VOTA. The `.vsu` files sign the urn's dynamic files (its working state), not its
programs. That synchronisation never follows an ordinary start-up: 0 of 1,810 official
start-ups in 400 random round-1 objects. v3 therefore marks such an error
`recovered_by_sync` when the completed synchronisation comes in the same start-up,
before VOTA starts and before any vote, and leaves it out of E3. This rule was written
after reading the v2 failures; the raw counts stay in `votes_without_restart` and the
recovered errors are listed in the manifest. The log does not show the restored files
verified again ([T14](observations.md#transparency)).

The other three verification errors in those sections (the program `vota.of`, the
signature tree, the voting medium) were followed by the urn being switched off and
restarted, with no vote in between.

Copies of a block in both memories count once.

```sh
just integrity-check signature-errors \
  --sections $EA_STAGE/phase20/national-r1-sections-v4-20261107 \
  --semantic $EA_STAGE/phase20b-zeresima/v5-national-r1-20261108 \
  --output $EA_STAGE/phase20b-signature-errors/national-r1-signature-errors-v3-20261109
```

| Round | Sections with errors | Verification errors (start-up / in session) | Signing errors (start-up / in session) | Errors followed by later votes | Recovered by sync (with votes before a restart) | Failed v2 / v3 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 181 | 280 / 92 | 57 / 12 | 306 | 35 (22) | 22 / 0 |
| 2 | 307 | 360 / 51 | 66 / 24 | 423 | 23 (9) | 9 / 0 |

| Run | Duration | Workers | Peak RAM |
| --- | --- | --- | --- |
| v3 round 1 | 20 s | 1 | 1.4 GB |
| v3 round 2 | 27 s | 1 | 1.4 GB |

Every object holding an official-round error was reread (181 and 307), none
unavailable.

- No urn completed a vote in the session of a verification error. After a program or
  medium error the urn was switched off and restarted before any vote; after a
  dynamic-file error recovered by synchronisation, the urn voted without a further
  restart.
- After a signing error, one section per round completed one vote in the same
  session. Read in the log, both are the vote in flight: the voter confirmed the
  last office, the urn reported the signing failure (round 1: a voter-keyboard fault
  while signing `UENUXDB INT`; round 2: the external medium failed while signing
  `RDV MI`), logged `O voto do eleitor foi computado` within a second, and was
  switched off and restarted. After the restart in round 1, every start-up package
  check ended in `SUCESSO`.
- Errors outside the round's official blocks are counted in the manifest only
  (memory copies included): 674 markers in round 1 from preparation and tests; in
  round 2, 709 such markers and 487 in the round-1 blocks that runoff logs carry.
- The counts are consistent in every error: the votes before an error never exceed
  its block's votes.

### JWS signatures on the published results

TSE publishes a `-u.jws` beside each EA20 `-u.json` result file: a JSON Web
Signature (Ed25519) over the same bytes. `results-hierarchy fetch-signed`
(`signed-results-fetch-v1`) downloads both files for every node of a finished EA20
snapshot, one request at a time with a pause. `integrity-check jws`
(`integrity-jws-v2`, module `signed_results`) checks the pinned key, then every
file:

- the key file: the end-entity certificate holds the JWK's key, the `kid` is the
  certificate's subject key identifier, the chain end entity → `AC DIVULGACAO` →
  `AC TOTALIZACAO` verifies (Ed448), and the certificate was valid on election day;
- with `--crls`, the revocation lists named in the certificates: `acdivulgacao.crl`
  (for the end entity) and `actot.crl` (for `AC DIVULGACAO`) must be signed by
  their issuer and must not revoke the certificate; whether each was current on
  election day is reported;
- J1: the header names that `kid` and `EdDSA`;
- J2: the signature verifies;
- J3: the signed payload equals the plain `-u.json` fetched with it;
- J4: it equals the EA20 snapshot used by I4, or the file was republished since
  (reported, not failed);
- a negative control: one byte changed in each file must be refused.

The key and the three certificates come from appendix B (official keys) of TSE's
JWS verification manual of 16 September 2026, downloaded in a browser and frozen in
`tse-www-20261108/`; `tse-jws-key-20261108/` holds the key file and the script that
extracted it. DataUrnas-BR quotes the same key. The host serving the revocation
lists refuses scripted requests (T5); the user downloaded both in a browser on
9 November 2026, and they are frozen as served (PEM) in `tse-jws-crls-20261109/`.

```sh
just results-hierarchy fetch-signed \
  --ea20-root $EA_STAGE/results-hierarchy/ea20-r1-20261104 \
  --output $EA_STAGE/phase20b-jws/signed-r1-20261108
just integrity-check jws \
  --signed-root $EA_STAGE/phase20b-jws/signed-r1-20261108 \
  --key $EA_STAGE/inputs/tse-jws-key-20261108/key.json \
  --crls $EA_STAGE/inputs/tse-jws-crls-20261109 \
  --output $EA_STAGE/phase20b-jws/national-r1-jws-v2-20261109
```

In both rounds all 5786 files (Brazil, 28 UF files and 5757 municipalities) have
the expected header and a valid signature; each payload equals its plain file and
the 4 November EA20 snapshot (none was republished), and every altered copy was
refused. Both revocation lists verify against their issuers, were issued on
25 August 2026 with their next update due on 23 November 2026, so they were current
on election day, and are empty: neither certificate is revoked. Version 1
(`national-r{1,2}-jws-v1-20261109`) gave the same file results without the lists.

### Runs

| Run | Wall time | CPU time | Peak memory | Output |
| --- | --- | --- | --- | --- |
| Ed521 cross-check, round 1 (6 workers) | 3:00:11 | 67769 s | 1.15 GB | 24 MB |
| Ed521 cross-check, round 2 (6 workers) | 2:31:06 | 56222 s | 1.15 GB | 24 MB |
| Zerésima v2, round 1 / 2 | 0:29 / 0:32 | — | 2.9 GB | 0.8 / 0.6 MB |
| GEDAI v2, round 1 / 2 | 0:49 / 0:45 | — | 2.2 GB | 0.8 / 0.7 MB |
| GEDAI v3, round 1 / 2 | 0:53 / 0:54 | — | 2.3 GB | 0.9 / 0.8 MB |
| Signature errors, round 1 / 2 | 0:13 / 0:14 | — | 1.3 GB | 0.8 / 0.6 MB |
| Hash lists | 0:01 | — | 0.10 GB | 60 kB |
| JWS fetch, round 1 / 2 | 3:11:27 / 2:30:26 | — | 0.08 GB | 256 / 166 MB |
| JWS check, round 1 / 2 | 0:17 / 0:10 | — | 0.11 GB | 0.2 MB |
| JWS check v2 (with revocation lists), round 1 / 2 | 0:11 / 0:09 | — | 0.11 GB | 0.2 MB |

Peak memory is the largest single process; the aggregate of the six cross-check
workers was not measured. The semantic pass v5 that feeds the zerésima and
hash-list checks is in the [semantic pass guide](semantic-pass.md#version-5-phase-20b).

## Phase 20b: cross-model review fixes

The cross-model review of 9 November 2026 (campaign
[`xr1-20261109`](cross-model-review.md), ledger in
`review/campaigns/xr1-20261109/ledger.jsonl`) confirmed findings in several checks.
The fixed versions reran nationally on 9 November 2026 into new roots; earlier
releases stay as they were.

| Check | Version | Change | Ledger (`xr1-20261109-`) |
| --- | --- | --- | --- |
| Sections (I1) | `integrity-sections-v5` | Every signature under an urn key of small order ([4]A = O, `hw_key_small_order`) is refused: cofactorless Ed521 verification accepts a universal forgery under such a key. Certificate, issuer, revocation, file-hash and unlisted-file failures become I1 issue rows | P3-04, P0-05, P3-05 |
| Ed521 vectors | `ed521-crosscheck-v2` | New command `integrity-check ed521-vectors` runs the 53 vectors through the pure-Python verifier, `ed521rs` strict and ECPy, and marks small-order keys | P3-04 |
| Logs (I6, I7) | `integrity-logs-v3` | I6 checks each round-1 file's hash before using it; I7 R2 takes the last session by urn clock, not by archive order | P4-02, P0-04 |
| Signature errors | `integrity-signature-errors-v3` | E3, see [signature errors and votes](#signature-errors-and-votes) | P4-03 |
| GEDAI | `integrity-gedai-v4` | A zone is unpublished only when its logs hold no record of that kind, read from the records themselves, not from matches | P0-02 |
| I8 | `printed-bu-v2` | A copy is authentic only with a verified, unrevoked issuer signature; an unknown certificate match is its own status | P4-01, P3-05 |
| JWS | `integrity-jws-v3` | J4 accepts a different payload only as a later publication of the same node (same identity, strictly later date, time and id); the signed population must equal the EA20 snapshot's | P3-01, P3-02 |
| Section table, semantic pass | (code) | Hash the bytes they read against their manifest; a mismatch is refused or becomes an error row | P0-01, P2-01 |

```sh
just integrity-check sections \
  --bulk-root $EA_DATA/bulk/2026-arqurnatot \
  --round 1 --output $EA_STAGE/phase20/national-r1-sections-v5-20261109 \
  --workers 6
just integrity-check ed521-vectors \
  --reference $EA_STAGE/inputs/ed521-crosscheck-refs-20261108/dataurnas-ed521.py \
  --reference-label alissonlinneker/DataUrnas-BR@f5e80059526e511bea7d52aef6a1570de42c3789 \
  --vectors $EA_STAGE/inputs/ed521-crosscheck-refs-20261108/vectors \
  --output $EA_STAGE/phase20b-ed521/vectors-v2-20261109
just integrity-check logs \
  --sections $EA_STAGE/phase20/national-r2-sections-v4-20261107 \
  --semantic $EA_STAGE/phase20b-sessions/v4-national-r2-20261107 \
  --semantic-round1 $EA_STAGE/phase20b-sessions/v4-national-r1-20261107 \
  --output $EA_STAGE/phase20/national-r2-logs-v4-20261109
```

Results:

- Sections v5: no urn key is of small order, and no new I1 issue: both rounds have
  0 discrepancies, and their summaries equal v4's.
- Vectors: 0 failures of this project's verifiers; 10 vectors use a small-order key.
  DataUrnas-BR's verifier agrees with the strict mode in all 53 and with ECPy in 35.
- I6 is unchanged. I7 R2 now also fails 15 sections in round 1 and 5 in round 2, all
  of which already failed R6 (overlapping sessions). In each, a short session
  without a closing reading has urn-clock readings inside the span of the day's
  closed session, so it sorts last by start; the session that ends last has a
  closing reading in all 20. Those open sessions hold 4 votes in round 1 and 88 in
  round 2 (one section in Espírito Santo, whose two streams overlap all day). No
  section lacks a closing at the end of the day.
- Signature errors v3: 0 E3 failures (v2: 22 and 9).
- GEDAI v4: G1 is unchanged. sp/0176 is no longer unpublished for G3: its logs hold
  one load medium of the zone, generated for 41 sections, which none of its 437 BUs
  used. Its 168 matched sections now fail G3 with `load_medium` `absent` in both
  rounds ([T11](observations.md#transparency)). Round 2 also keeps its one G3 failure
  in mg/0112. G3 stays unpublished in am/0042 (31 sections) and pr/0018 (85).
- I8 v2: all 528 copies equal, every certificate verified and unrevoked.
- JWS v3: all 5786 files in both rounds pass; the signed and snapshot populations are
  equal and no file was republished.
- Input rehash (`review/campaigns/xr1-20261109/repro/rehash_inputs.py`): the
  498580 and 498581 staged log objects of the two semantic releases, and the 112
  BWEB archives, all equal their recorded SHA-256.
- Inspection: the sections of these reruns' rows, including the 31 E3 and 20 new R2
  sections whose logs were read, are registered as development data in
  `$EA_STAGE/inspection/xr1-r4-reruns-20261109.sqlite` (6551
  places, 31 s, 0.9 GB). Every one was already in the Phase 20b registry, so 7824 of
  94751 polling places remain development data.

| Run | Wall time | Workers | Peak memory | Output |
| --- | --- | --- | --- | --- |
| Sections v5, round 1 / 2 | 1:06:58 / 1:02:08 | 6 | 4.8 / 4.1 GB | 629 / 337 MB |
| Ed521 vectors v2 | 0:01 | 1 | 0.07 GB | 18 kB |
| Logs v4 (code v3), round 1 / 2 | 0:26 / 0:48 | 1 | 2.6 / 3.5 GB | 1.2 / 1.7 MB |
| Signature errors v3, round 1 / 2 | 0:20 / 0:27 | 1 | 1.4 GB | 0.8 / 0.6 MB |
| GEDAI v4, round 1 / 2 | 0:59 / 0:52 | 1 | 2.3 GB | 0.9 / 0.8 MB |
| I8 v2 | 0:29 | 1 | 0.56 GB | 0.2 MB |
| JWS v3, round 1 / 2 | 0:12 / 0:09 | 1 | 0.11 GB | 0.2 MB |
| Input rehash | 9:18 | 4 | 0.87 GB | 1 kB |

Second batch, run on 9 and 10 November 2026:

| Check | Version | Change | Ledger (`xr1-20261109-`) |
| --- | --- | --- | --- |
| Sections (I3, I9) | `integrity-sections-v6` | The RDV's load code and urn number must equal the BU's (I9 `rdv_urn`); a contest the RDV cannot recount is an I3 row | P3-10, P4-07 |
| Zerésima | `integrity-zeresima-v3` | Z6, see [zerésima](#zerésima) | P4-10 |
| Logs (I5, I6) | `integrity-logs-v4` | Copies that disagree are I5 `copy_conflict` rows; malformed lines are counted, and an I6 equality over them is reported | P0-12, P2-02 |
| GEDAI | `integrity-gedai-v5` | A BU without load fields is `n/a` in the summary, not passed | P4-08 |
| I8 | `printed-bu-v3` | Content whose code slices cannot be recovered is `chain_unverified`, not `not_authentic` | P4-09 |
| JWS | `integrity-jws-v3` | The key file must have a pinned SHA-256 ([inputs downloaded by hand](manual-inputs.md)) | P3-06 |

- Sections v6: 0 discrepancies in both rounds and summaries equal to v5. Every RDV
  comes from its BU's urn and load, and every contest is recounted.
- Logs v5 (code v4): no copy conflict. Six sections per round have malformed lines,
  all already I6 `differs`, so no I6 equality rests on a malformed line.
- GEDAI v5 and I8 v3: summaries equal to the previous versions. The JWS key file in
  use has the pinned digest, so the JWS results stand.

| Run | Wall time | Workers | Peak memory | Output |
| --- | --- | --- | --- | --- |
| Sections v6, round 1 / 2 | 1:12:17 active (11:24:25 with a 10:12:08 machine suspend) / 1:05:15 | 6 | 4.8 / 4.1 GB | 629 / 337 MB |
| Logs v5 (code v4), round 1 / 2 | 0:25 / 0:47 | 1 | 2.6 / 3.4 GB | 1.2 / 1.7 MB |
| GEDAI v5, round 1 / 2 | 0:52 / 0:51 | 1 | 2.3 GB | 0.9 / 0.8 MB |
| I8 v3 | 0:29 | 1 | 0.56 GB | 0.2 MB |


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
- The JWS revocation lists were read on 9 November 2026; a later list could revoke
  the key after that date. The
  hash-list check compares names and results only, since the logs carry no program
  hash; the GEDAI logs' own signature files are not verified.
- GEDAI: the 13 and 70 isolated G1 sections are late loads whose correspondence did
  not reach the published logs (T13), as far as the logs show; why it did not is
  not established. sp/0176 lacks the preparation logs of most of its urns and the
  load media of all its BUs (T11).
- Agreement among artifacts of the same software chain shows consistency, not voter
  intent.
