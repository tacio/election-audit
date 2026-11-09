# Election audit — 2026 Brazilian presidential election

Document-ID: EA-ONBOARDING · Revision: 13 · Language: en

[Português](README.pt-BR.md)

Reproducible audit tooling for the TSE logs and ballot reports (BUs) of both rounds
of the 2026 presidential election. Original bytes are preserved, every stage reads
only frozen inputs and writes a new immutable output that pins its parent, and
unknown or partial values stay explicitly unavailable instead of being guessed.
The tooling produces no fraud labels.

## Status (3 November 2026)

- **Acquisition:** both rounds collected from TSE and verified by SHA-256 (499176
  round-1 and 499177 round-2 log versions, with explicit no-log and
  unpublished-auxiliary gaps).
- **Structural processing:** all 498581 eligible runoff logs summarized into one
  immutable Parquet release (structural counts only; each log mixes both rounds).
  Round 1 is not yet processed.
- **Electoral verification, operational semantics, features, models,
  investigations and notebooks:** implemented and exercised on Acre (AC) only.
- **Next:** Phase 19, national inputs, under the revised
  [study protocol](research/analysis-plan.md) and
  [completion plan](research/completion-plan.md). The protocol will be publicly
  pre-registered before any confirmatory analysis.

The [implementation index](docs/en/implementation-index.md) has the full status,
artifact locations and interface map. Start there.

## Setup and checks

Install uv and just (rtk, a token-saving output filter for AI coding agents, is optional:
recipes use it only when it is installed). Linux is the supported platform; native
Windows cannot run the pipeline (use WSL2) and macOS is untested, as
`just doctor` reports. Python 3.14, DuckDB, PyArrow and Ruff are pinned in the
lockfile. Recipes use `/tmp/election-audit-uv-cache`; offline setup needs that cache
populated. Checks never acquire election data. The tests exercise the publication
disk guard with its default reserve and spill cap, so the gate needs about 18 GiB free
in the temporary directory (`TMPDIR`); the demo needs 2 GiB.

```sh
just setup
just doctor
env UV_OFFLINE=1 just check
```

## Try it offline

The walkthrough builds explicitly SYNTHETIC originals (mixed-date archive,
replacement and copied history, manual request/cancellation, unresolved clocks,
malformed nested content) and publishes the full operational → electoral →
partition → ledger chain with both reports. Every output directory must be new.

```sh
env UV_OFFLINE=1 just demo --output data/my-demo
env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
env UV_OFFLINE=1 just review-bundle data/my-review --verify
env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
```

A review bundle contains the frozen selected originals, the complete relative
release chain, exact configurations, source tree, dependency lock, SQL, validation
and logical output digests. It excludes live manifests, acquisition roots, the
environment and credentials. See [reproduction](docs/en/reproduction.md).

## Pipeline

1. **Acquisition** (`download`, `resume`, `inspect`): raw TSE objects plus a SQLite
   manifest. See the [acquisition reference](docs/en/acquisition-reference.md).
2. **Snapshot** (`snapshot`): freezes selected objects and expected-coverage
   denominators. See [snapshots](docs/en/snapshots.md).
3. **Structural parse** (`parse`): bounded nested JEZ/ZIP decoding into ordered
   events. See [archive parsing](docs/en/archive-parsing.md).
4. **Operational reconstruction** (`reconstruct`, `operational-review`): sessions,
   anonymous vote cycles and clock rules with explicit uncertainty. See
   [reconstruction](docs/en/reconstruction.md).
5. **Releases** (`build`, `validate`, `query`, `report`): immutable DuckDB/Parquet.
   See [publication](docs/en/publication.md).
6. **Electoral results** (`import-results`, `electoral-verify`): BWEB and binary BU
   imports and verification. See [electoral results](docs/en/electoral-results.md).
7. **Analysis** (`analyze`, `features`, `research-protocol`, `research-models`,
   `investigations`): descriptive features, frozen partitions, protected final
   evaluation and append-only ledgers. See [analysis](docs/en/analysis.md) and the
   [study protocol](research/analysis-plan.md).
8. **Reproduction** (`demo`, `pilot`, `review-bundle`, `reproduce`, `backfill`).

National-scale structural processing uses resource-bounded parallel summaries
instead of materializing every event; see
[feature-oriented processing](docs/en/feature-oriented-processing.md).
Each command documents itself:

```sh
env UV_OFFLINE=1 just snapshot --help
env UV_OFFLINE=1 just parse --help
env UV_OFFLINE=1 just reconstruct --help
env UV_OFFLINE=1 just build --help
env UV_OFFLINE=1 just import-results --help
env UV_OFFLINE=1 just analyze --help
env UV_OFFLINE=1 just validate --help
env UV_OFFLINE=1 just query --help
env UV_OFFLINE=1 just report --help
env UV_OFFLINE=1 just backfill --help
env UV_OFFLINE=1 just docs-command-check
just resume --help
just inspect --help
```

## Notebooks

The local marimo workspace has coverage, electoral, operational and research
notebooks. Install the optional dashboard dependencies and supply an explicit
checksummed dataset. Protected research outcomes stay withheld until a validated
final evaluation exists. The current dataset covers AC only.

```sh
uv sync --locked --extra dashboard
just dashboard --dataset data/dashboard-ac-2026-10-30/dataset.json
```

## Documentation

English and Portuguese documents share IDs, revisions and byte-identical commands,
SQL, formulas and numbers; `just docs-check` enforces this. See also
[related work](research/related-work.md), the
[completion plan](research/completion-plan.md) and the
[glossary](docs/en/glossary.md).
