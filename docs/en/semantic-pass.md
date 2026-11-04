# Streaming semantic pass (Phase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 2 · Language: en

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

## Outputs

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

## Limits

- 2022 logs use another software version and need reviewed 2022 rules before
  they can yield official sessions.
- SA sections have SA counting measures, not urn session measures: their voting
  happened on paper ballots or on an urn whose log is not published with the SA
  package.
- Segment fingerprints compare whole context segments; a first-round segment
  that ends earlier in one log than in the other will not match and needs a
  prefix comparison.
- Sessions with several official runs per object (urn replacement or restarts)
  are kept as observed; grouping them is Phase 22 work.
