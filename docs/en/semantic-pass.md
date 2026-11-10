# Streaming semantic pass (Phase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 9 · Language: en

[Português](../pt-BR/semantic-pass.md) · [Implementation index](implementation-index.md)

`semantic-pass` turns raw urn logs into per-session aggregates in one streaming
read. It replaces the national use of the event-level adapter
(`operational_review`, `real-operational-v1`), whose rules and session/cycle state
machine it mirrors exactly, and keeps only what later phases need.

## Inputs

- A certified staged root (`stage-sources copy`): objects, `manifest.sqlite` and
  `staging-certificate.json`. The pass refuses a root of the other round.
- The protected/stress exclusions
  (`data/national/phase11-protection-2026-10-31/exclusions.json`). Objects with any
  witness in an excluded section are never opened, in either round.
- `resources/real-log-rules.json` (software 10.23.0.0). Other software versions
  never become official sessions.
- For 2022, the verified bulk archives and `resources/real-log-rules-2022.json`
  instead ([2022 logs](#2022-logs)).

## Outputs

Version `session-aggregates-v2` stores the completion-gap and clock-backstep
seconds as 64-bit integers: a 2022 urn clock stepped back about 89 years, which
overflowed the 32-bit columns of v1. The 2026 national releases are v1 and hold no
value beyond the 32-bit range. Rerunning them with the current code gives v2 with
the same values: on 4 November 2026 a v2 run of AC 2026 (1674 objects per round)
equalled the AC rows of both v1 national releases in every object, session and
segment row once the four seconds columns were cast to `int64`. Read the 2026
releases with that cast.

`<output>/release/` holds four Parquet tables and a `manifest.json` with the
binding (rules, staging certificate, manifest and exclusions hashes) and file
hashes:

| Table | One row per | Main columns |
| --- | --- | --- |
| `objects` | log object | status, error, section witnesses, package status, line/event counts, sessions, kind counts |
| `sessions` | session | kind (`official_vota` or `unresolved`), end reason, readings, cycles by state × method, interrupted completions, manual requests, failures, orphans, completions by reading hour, completion gaps, backward clock steps |
| `segments` | context segment of a stream | context (`initial`, `official_round_N`, `other_context`), lines, byte fingerprint, first/last line hash, first/last reading |
| `vocabulary` | application × message template | event count; every digit run masked as `#`, long hex runs as `<hex>` |

Readings are local urn clock readings, not normalized times. Cycles are
anonymous; there is no candidate attribution and no attendance reconciliation
(Phase 20/22). Voter, poll-worker and authenticator values are not exported.

## Equivalence

`semantic-pass equivalence` re-runs the event-level adapter on a seeded sample
and compares the ordered per-session signatures (kind, end reason, closing,
software, cycles by state × method, interrupted completions) and the object
orphan and manual-request counts. On 3 November 2026 it matched on 200 of 200
sampled AC objects per round (45003 and 39466 completed cycles); the pass took
12.8 s and 19.5 s against 268.2 s and 412.3 s for the adapter.

```sh
just semantic-pass equivalence \
  --staged-root $EA_STAGE/2026/turno-2 --round 2 \
  --output $EA_STAGE/phase21/equivalence-r2-ac-200 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --uf ac --sample 200 --seed 2103
just semantic-pass run \
  --staged-root $EA_STAGE/2026/turno-2 --round 2 \
  --output $EA_STAGE/phase21/national-r2-20261103 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --workers 6
```

The run is sharded (500 objects per shard), resumable with `--resume` under the
same binding, records per-object errors without stopping, and stays within half
the CPUs. Unit tests: `tests/test_semantic_pass.py`.

## National runs

Both 2026 rounds ran on 3–4 November 2026 with 6 workers from the SSD staging,
with no object errors. Each output root holds `binding.json`, `status.json`, the
998 shards and `release/` (`objects`, `sessions`, `segments` and `vocabulary`
Parquet files with `manifest.json`).

| Round | Objects | Sessions | Segments | Wall time |
| --- | --- | --- | --- | --- |
| 1 | 498580 | 1704924 | 5048597 | 6642 s |
| 2 | 498581 | 3393756 | 9474325 | 2158 s + 11457 s (resumed once) |

Runoff logs also carry setup and first-round events, so round 2 yields more
sessions. Population ledger: both certified stagings hold 499207 section
auxiliary files.

| Round | Sections | Urn log | SA counting, no urn log | Published without log | Excluded | Processed |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 499207 | 499176 | 31 | 0 | 596 | 498580 |
| 2 | 499207 | 499177 | 29 | 1 | 596 | 498581 |

SA sections were counted with the contingency counting system: their package lists
`busa`, `logsa`, `rdv` and `sa` files and no urn `log`. Two MG sections
(41238/0039/0168, 50075/0047/0041) used SA in round 1 only. SP 64777/0395/0298 was
published in round 2 with `bu`, `rdv` and `vota` files and no log.

## Version 3 (Phase 22)

`session-aggregates-v3` adds nine session columns for the
[section table](section-table.md) and changes nothing else: `model`,
`software_version`, the clock evidence recorded before the session
(`clock_adh_before`, `clock_adh_shift_s_before`, `clock_tz_shifts_before`,
`clock_tz_shift_s_before`, `clock_dst_before`), `configured_close` and
`segment_ordinal`. The clock counters accumulate per stream. The section table
describes each column.

All four national runs used 5 workers on 5–6 November 2026, with no object
errors. Active time excludes two machine suspends.

| Year | Round | Objects | Sessions | Segments | Active time |
| --- | --- | --- | --- | --- | --- |
| 2026 | 1 | 498580 | 1704924 | 5048597 | 8002 s |
| 2026 | 2 | 498581 | 3393756 | 9474325 | 12808 s |
| 2022 | 1 | 471859 | 1805887 | 5242171 | 7277 s |
| 2022 | 2 | 471983 | 3570943 | 9845999 | 11809 s |

Acceptance, per run: every session shard has the nine columns, and every column
shared with the earlier release (2026 v1, 2022 v2) is equal in every session,
segment and object row, both ways. The roots are
`$EA_STAGE/phase22/v3-national-r{1,2}-20261105/` and
`v3-national-2022-r{1,2}-20261105/`. Each run has a single software version among
official sessions (`10.23.0.0 - Praia da Barra do Cahy` in 2026,
`8.26.0.0 - Onça-pintada` in 2022). A few sessions have no version line: 1 in
2026 round 1, 8 in 2022 round 1, 1 in 2022 round 2.

## Version 4 (Phase 20b)

`session-aggregates-v4` applies session rules `sessions-v2`, shared with the
event-level adapter:

- A `GAP` restart line that names the round in effect keeps that round's context.
  The urn does not repeat the official-round marker after a mid-day restart, so
  version 3 closed the context there and lost every later vote of the day.
- A session of the round's context that started before election day (an urn
  switched on early and left running) becomes official at its first voting event
  on election day, and is flagged `started_before_election_day`. Version 3 left
  these sessions unresolved.

Sessions are the same rows as in version 3; segments are fewer because restarts no
longer split the context. The equivalence check against the adapter passed on 200 of
200 sampled AC objects in each year and round (2026: 45003 and 39683 completed
cycles; 2022: 43707 and 40360).

| Year | Round | Objects | Sessions | Segments | Official sessions added | Started before election day | Wall time | CPU time | Peak memory | Release |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 | 1 | 498580 | 1704924 | 3312661 | 1742 | 1569 | 1:53:15 | 39767 s | 0.96 GB | 545 MB |
| 2026 | 2 | 498581 | 3393756 | 5518787 | 1506 | 1361 | 3:03:41 | 64676 s | 1.00 GB | 838 MB |
| 2022 | 1 | 471859 | 1805887 | 3396296 | 1440 | 871 | 1:45:28 | 39053 s | 1.01 GB | 533 MB |
| 2022 | 2 | 471983 | 3570943 | 5726472 | 1284 | 835 | 2:52:30 | 63535 s | 1.08 GB | 830 MB |

All four ran on 7–8 November 2026 with 6 workers and no object errors, into
`$EA_STAGE/phase20b-sessions/v4-national-r{1,2}-20261107/` and
`v4-national-2022-r{1,2}-20261107/`. Peak memory is the largest single process. Each
sample equivalence took 3:10 to 5:41, almost all of it in the adapter. Sections with
no official session of the round fall from 1636 and 1449 to 12 and 4 in 2026, and
from 1013 and 1007 to 15 and 12 in 2022 ([section table](section-table.md#national-results)).

## Version 5 (Phase 20b)

`session-aggregates-v5` adds two tables for the integrity checks of Phase 20b and
leaves sessions, segments, objects and vocabulary unchanged:

- `markers.parquet`: one row per zerésima and readiness line (`await_datetime`,
  `await_confirmation`, `asked_to_print`, `zeresima_start`, `zeresima_end`,
  `zeresima_print`, `summary_start`, `summary_end`, `summary_print`, `ready`,
  `sa_zeresima`), per other line naming the zerésima (`other`) and per signature or
  integrity failure line (`signature_error`). Each row has its object, stream,
  block, session and device, the line number, the urn clock reading, the masked
  template and the vote cycles completed earlier in the same block.
- `packages.parquet`: national counts of package signature verifications
  (`Verificação de assinatura … - [ERRO|SUCESSO]`) by urn model, application, stage
  (`aplicação`, `dado` or `startup`), path, file and result, with events and logs.
  Digits are masked only in data-file paths. SCUE logs its checks before the model
  line, so rows take the model of their stream.

The [zerésima](integrity-checks.md#zerésima) and
[hash-list](integrity-checks.md#hash-lists) checks read them.

| Round | Objects | Markers | Package rows | Wall time | CPU time | Peak memory | Release |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 498580 | 5197232 | 846 | 2:18:03 | 45819 s | 0.98 GB | 594 MB |
| 2 | 498581 | 10312157 | 850 | 3:34:03 | 75786 s | 1.06 GB | 922 MB |

Both ran on 9 November 2026 with 6 workers and no object errors, into
`$EA_STAGE/phase20b-zeresima/v5-national-r{1,2}-20261108/`. Their
sessions, segments, objects and vocabulary tables equal version 4 row for row
(`EXCEPT ALL` both ways, zero rows). Runoff logs carry the round-1 history, so the
round-2 release holds both rounds' markers; checks select blocks by context.

## Version 6 (cross-model review, not yet run)

`session-aggregates-v6` changes the vote-cycle machine where the cross-model review
of 9 November 2026 (`xr1-20261109`) found it could attach a completion to the wrong
voter:

- an authorization whose following VOTA events fall off election day (a clock
  excursion) ends `unresolved` instead of taking a completion read after the clock
  returns (P2-04);
- an orphan completion (one without an authorized cycle) ends a pending manual
  request as `unresolved`, so its flags never reach the next voter (P2-05);
- the release's `rules_sha256` covers the built-in 2026 templates when the rules
  file has none (P2-08).

The national releases of this guide are version 5. The changes reach at most the
cycles near 39 and 13 backward clock steps inside official sessions (rounds 1 and 2)
and one orphan completion in round 1. Rerunning the pass also requires rerunning
every check and table built on it.

## Contingency counting (SA) logs

Sections counted with the Sistema de Apuração (SA), TSE's contingency counting
system, publish `logsa.jez`, `busa.dat`, `imgbusa.dat` and `sa.vsc` instead of urn
files. An SA log records counting, not voting: the contingency urn's setup, each
counting attempt (section identity, counting type, reason, BU typing, counting
and the generation of `busa.dat`), cancellations and printed reports. The urn
vote-cycle rules do not apply, so these logs have their own summary.

`sa-logs fetch` lists every SA log named in the certified staging's frozen
auxiliary files, fetches it from the same official host into a new
content-addressed root, checks the ZIP CRCs and compares each file with the
matching member of the verified bulk archive. `sa-logs summarize` requires the
protection exclusions, skips protected sections before reading them and writes one
row per section to `sa_sections.parquet`.

```sh
just sa-logs fetch \
  --staged-root $EA_STAGE/2026/turno-1 --round 1 \
  --output $EA_STAGE/sa-logs/fetch-r1-20261104 \
  --bulk-root $EA_DATA/bulk/2026-arqurnatot
just sa-logs summarize \
  --input $EA_STAGE/sa-logs/fetch-r1-20261104 \
  --input $EA_STAGE/sa-logs/fetch-r2-20261104 \
  --output $EA_STAGE/sa-logs/summary-20261104 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json
```

An SA urn can count many sections, and each section's file is a snapshot of that
urn's growing log; round-2 files also carry the round-1 attempts. Attempts are
attributed to a section only when the log prints its municipality, zone and
section number on the round's election date; the counting type is the last one
selected before the identity was confirmed. Operator identifiers in the log never
reach the summary.

On 4 November 2026 all 31 round-1 and 29 round-2 SA logs were fetched, all 60
matched the bulk archives byte for byte, none was protected, and all 60 were
attributed by printed identity:

| Round | Sections | Counting type | Reason | Cancelled attempts before success |
| --- | --- | --- | --- | --- |
| 1 | 2 (MG 41238/0039/0168, 50075/0047/0041) | `DIGITAÇÃO DO BU MAIS CÉDULAS` | `Urna encerrada com eleitores na fila` | 1 each |
| 1 | 29 (ZZ) | `DIGITAÇÃO DE BUEx` | `Outros` | 1 section |
| 2 | 29 (ZZ) | `DIGITAÇÃO DE BUEx` | `Outros` | 1 section |

Vote totals for SA sections come from `busa.dat`, which the bulk archives contain;
Phase 20 must read it alongside `bu.dat`.

## 2022 logs

2022 is the negative control (analysis plan section 7.6). Its logs come from the
verified bulk archives (`bulk-download`, 28 per round), not from a staging, and
are 7z archives rather than ZIP. `election_audit/sevenzip.py` reads them with the
standard library only: plain or LZMA-encoded headers, single LZMA, LZMA2 or copy
coders, every declared CRC checked, anything else refused. It matched the `7z`
tool byte for byte on 300 sampled AC logs. The structural parser, the event-level
adapter and the pass all open 7z at any nesting depth.

With `--bulk-root`, the parent process alone reads each archive's log members in
header-offset (physical) order and hands their bytes to the workers, with at most
`workers + 2` shards in flight. Object hashes are computed from the member bytes
and witnesses come from the member name (`o00406-MMMMMZZZZSSSS.logjez`). Bulk mode
refuses 2026, whose archives hold the protected logs, and takes no exclusions.

`resources/real-log-rules-2022.json` (software 8.26.0.0, `tse-real-log-rules-2022-v1`)
keeps the 2026 state machine and applies a 2026 rule only where the 2022 message
text is identical. The session, round and software markers differ in 2022 and are
read from its logs:

| Marker | 2026 | 2022 |
| --- | --- | --- |
| Official round (GAP) | `ELEIÇÃO OFICIAL SEGUNDO TURNO - 2º turno` | `ELEIÇÃO OFICIAL SEGUNDO TURNO - Oficial - 2º turno` |
| Session start (VOTA) | `Iniciando aplicação - 2º turno` | `Iniciando aplicação - Oficial - 2º turno` |
| Software | `10.23.0.0 - Praia da Barra do Cahy` | `8.26.0.0 - Onça-pintada` |
| Operator authorization | `Mesário # habilitou o eleitor` | absent |

No official 2022 message catalogue was found, so 2022 messages without an
identical 2026 rule stay unknown and are listed in the rules file. In particular,
a manual authorization in 2022 shows the poll worker's fingerprint
(`Capturada a digital do mesário`) instead of the 2026 operator marker, so 2022
manual cycles count as method `unknown`. `Título inválido` and
`O eleitor não possui biometria` are not mapped either. The analysis compares
biometric with all other methods (analysis plan rev 3), and the biometric marker is
identical in both years, so this does not limit 2022.

On 4 November 2026 the pass matched the adapter on 200 of 200 sampled 2022 AC
objects per round (43707 and 40220 completed cycles); the pass took 10.4 s and
16.4 s against 203.2 s and 319.6 s for the adapter.

```sh
just semantic-pass equivalence \
  --bulk-root $EA_DATA/bulk/2022-arqurnatot \
  --year 2022 --round 2 \
  --output $EA_STAGE/phase21/equivalence-2022-r2-ac-200 \
  --uf ac --sample 200 --seed 2103
just semantic-pass run \
  --bulk-root $EA_DATA/bulk/2022-arqurnatot \
  --year 2022 --round 2 \
  --output $EA_STAGE/phase21/national-2022-r2-v2-20261104 \
  --workers 6
```

National 2022 runs, 4 November 2026, 6 workers, reading the bulk archives from
the output volume:

| Round | Objects | Sessions | Segments | Wall time | Peak RSS |
| --- | --- | --- | --- | --- | --- |
| 1 | 471859 | 1805887 | 5242171 | 6441 s | 1.06 GB |
| 2 | 471983 | 3570943 | 9845999 | 14202 s + 112 s (resumed once) | 1.16 GB |

Round 2 first finished with one error: SP 71072/0002/0310 nests a 32-byte empty 7z
archive (`…-01.jez`, signature header only), which the reader refused as truncated
although `7z` accepts it. The reader now returns no entries for exactly that case,
shard 00844 was moved out of the output and the pass resumed under the same
binding; the object matched the adapter. The fix changes only objects that
previously failed, and round 1 had none.

Population ledger, from the archive member names (`o0040N-MMMMMZZZZSSSS.ext`):

| Round | Sections | Urn log | SA counting | BU only (`bu`, `vscmr`) | BU and RDV, no log | Processed |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 472024 | 471859 | 109 | 54 | 2 | 471859 |
| 2 | 472027 | 471983 | 39 | 0 | 5 | 471983 |

Every section with a log was processed once and no section has two logs. SA
sections hold `busa`, `imgbusa`, `logsajez`, `rdv` and `vscsa`; 99 of the round-1
and 33 of the round-2 SA sections are abroad (ZZ). All 54 BU-only sections are ZZ
round 1. The sections with BU and RDV but no log are MG 51390/0244/0091 and RN
16918/0054/0090 in round 1, and PA 04650/0006/0059, 0060, 0072, 0109 and 0111 in
round 2. No 2022 BWEB was cross-checked.

The logs record clock faults as they happened: four round-1 sessions restart at
01/01/2009 (one, BA 39799/0106/0049, mid-vote on election day), and PE
25097/0091/0032 restarts during preparation at 23/08/1933 before an operator sets
the date with the ADH application. The bytes pass every CRC and the archive
SHA-256; these are urn clock events for Phase 22, not corruption.

## Limits

- 2022 manual authorizations are not separated from other non-biometric ones (no
  reviewed counterpart of the 2026 operator marker). Analyses use biometric versus
  non-biometric in both years.
- SA sections have SA counting measures, not urn session measures: their voting
  happened on paper ballots or on an urn whose log is not published with the SA
  package.
- Segment fingerprints compare whole context segments; a first-round segment
  that ends earlier in one log than in the other will not match and needs a
  prefix comparison.
- Sessions with several official runs per object (urn replacement or restarts)
  are kept as observed, and so are copies of one session in several memories of an
  urn. The section table and I5–I7 count such copies once by block lineage.
- Events whose urn clock reading is off election day are skipped. Voting closes at
  17:00, so this needs a clock error or a closing after midnight; such a session
  keeps its earlier counts and loses only those events (xr1-20261109-P2-06).
- `operational-review` (Phase 13) finds memory-copy candidates only among streams
  that end on the same line; the national path deduplicates copies by device and
  block start instead (xr1-20261109-P2-09).
- A staged root is read with its `manifest.sqlite` opened immutable, which ignores
  uncommitted WAL frames: stage a checkpointed manifest. A stale read is refused by
  the reconciliation with the staging certificate (xr1-20261109-P1-07).
