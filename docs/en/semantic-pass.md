# Streaming semantic pass (Phase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 3 · Language: en

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
value beyond the 32-bit range.

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
  --staged-root ~/data/election-audit-stage/2026/turno-2 --round 2 \
  --output ~/data/election-audit-stage/phase21/equivalence-r2-ac-200 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --uf ac --sample 200 --seed 2103
just semantic-pass run \
  --staged-root ~/data/election-audit-stage/2026/turno-2 --round 2 \
  --output ~/data/election-audit-stage/phase21/national-r2-20261103 \
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
  --staged-root ~/data/election-audit-stage/2026/turno-1 --round 1 \
  --output ~/data/election-audit-stage/sa-logs/fetch-r1-20261104 \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
just sa-logs summarize \
  --input ~/data/election-audit-stage/sa-logs/fetch-r1-20261104 \
  --input ~/data/election-audit-stage/sa-logs/fetch-r2-20261104 \
  --output ~/data/election-audit-stage/sa-logs/summary-20261104 \
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
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2022-arqurnatot \
  --year 2022 --round 2 \
  --output ~/data/election-audit-stage/phase21/equivalence-2022-r2-ac-200 \
  --uf ac --sample 200 --seed 2103
just semantic-pass run \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2022-arqurnatot \
  --year 2022 --round 2 \
  --output ~/data/election-audit-stage/phase21/national-2022-r2-v2-20261104 \
  --workers 6
```

National 2022 results are pending: both runs were in progress when this revision was written.

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
  are kept as observed; grouping them is Phase 22 work.
