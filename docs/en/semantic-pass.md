# Streaming semantic pass (Phase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 1 · Language: en

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

## Limits

- 2022 logs use another software version and need reviewed 2022 rules before
  they can yield official sessions.
- Segment fingerprints compare whole context segments; a first-round segment
  that ends earlier in one log than in the other will not match and needs a
  prefix comparison.
- Sessions with several official runs per object (urn replacement or restarts)
  are kept as observed; grouping them is Phase 22 work.
