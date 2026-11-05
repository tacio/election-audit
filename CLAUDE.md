# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Reproducible audit tooling for the TSE 2026 Brazilian presidential election logs (urna JEZ archives, BWEB/binary BU results). The emphasis is provenance and honesty about coverage: original bytes are preserved, every stage reads only frozen inputs, and unknown or partial values stay explicitly unavailable instead of being guessed. Start further work at `docs/en/implementation-index.md`, which holds the current state, next step, phase status, artifact locations and interface map, then read the assigned handoff in `docs/en/handoffs/`.

## Commands

Install `uv`, `just` and `rtk`. Every recipe already wraps itself in `rtk proxy uv run --locked`. The uv cache is `/tmp/election-audit-uv-cache`, and offline runs need that cache populated.

```sh
rtk proxy just setup                      # uv sync --locked
rtk proxy env UV_OFFLINE=1 just check     # full gate: lock, ruff format --check, lint, contracts, docs, doc-commands, tests
rtk proxy just fmt                        # ruff format
rtk proxy just lint                       # ruff check
rtk proxy just test                       # python -m unittest discover -s tests -v
rtk proxy just contracts-check            # python -m election_audit.contracts
rtk proxy just docs-check                 # paired en/pt-BR doc metadata, links, fenced-block parity
rtk proxy just docs-command-check         # validates documented CLI flags (via --help only) and SQL syntax
```

Tests use stdlib `unittest`, not pytest:

```sh
rtk proxy uv run --locked python -m unittest tests.test_cli -v
rtk proxy uv run --locked python -m unittest tests.test_cli.CliTests.test_delegation_preserves_options_and_restores_process_arguments
```

Optional extras are imported lazily: `dashboard` (marimo/altair), `research` (scikit-learn, quantile-forest) and `verification` (asn1tools, cryptography). To exercise them, install with `uv sync --locked --extra <name>`. `tests/test_electoral_verification.py` skips when `verification` is missing. Ruff selects only `E4 E7 E9 F I` with line length 100 and targets py314.

## Architecture

**Single CLI dispatcher.** `election_audit/cli.py:main` routes `election-audit <command>` to a `*_main(argv)` function in the matching module, importing that module only when its command runs. Each module owns its own argparse. The legacy commands `download`/`resume`/`inspect` forward `sys.argv` unchanged to `scripts/download_tse_logs.py` and `scripts/inspect_tse_logs.py` (`resume` adds `--missing-only`). A new command must be added in three places: `cli.py` (routing and the fallback `choices`), a `justfile` recipe, and `CLI_COMMANDS` in `scripts/check_doc_commands.py` if docs use it.

**Pipeline of immutable stages.** Each stage writes a new, content-addressed, immutable output that pins its parent and its versions:

1. Acquisition (`scripts/download_tse_logs.py`): raw TSE objects plus a SQLite manifest found through `manifest_path(root)` and `manifest-location.json`. The manifest runs in WAL mode, and live manifests sit in `.local-state/`.
2. Snapshot (`source_inventory`, `coverage`, `snapshots`): a consistent read of the manifest freezes copies of selected objects and the expected-coverage denominators.
3. Structural parse (`archive_parsing`, `jez-structural-v1`): bounded nested JEZ/ZIP decoding into ordered events, with exact member and line locators.
4. Operational reconstruction (`reconstruction`, `operational-v1`): sessions, the anonymous vote-cycle state machine and clock rules, all carrying explicit uncertainty.
5. Release (`publication`, `operational_marts`, `release_tools`): immutable DuckDB/Parquet releases. `query` is a single bounded, read-only SELECT.
6. Electoral derivatives (`electoral_imports`, `electoral_results`, `derivatives`, `official_bu`, `binary_bu`): parent-pinned imports of normalized/BWEB/binary BU results.
7. Analysis (`analysis*`, `features`, `research_*`, `investigations`): descriptive features, frozen partitions and append-only ledgers. A protected final-evaluation population is withheld.
8. Reproduction (`reproduction`): synthetic `demo`, relocatable `review-bundle`, `reproduce` and `backfill`.

`national*.py` holds the resource-bounded national structural processing: parallel workers, tuning, storage relocation and fused summaries (`source-operational-summary-v1`, `grouped-source-summary-shards-v3`). Read `docs/en/feature-oriented-processing.md` and `docs/en/national-processing.md` before touching it. Parallelism is capped at half the CPU and 6 GiB of aggregate RAM (raised from 4 GiB on 5 November 2026; Phase 11 configurations keep their recorded 4 GiB), with one library thread per process.

**Contracts.** `election_audit/resources/contracts/schema.json` defines the dimensional tables and `features.json` the feature registry. `election_audit/contracts.py` validates both structurally. Pinned TSE layouts and ASN.1 specs (BWEB layout, BU/RDV/signature) live alongside them in `election_audit/resources/`.

## Invariants that are easy to break

- Never modify `data/`, `.local-state/`, raw acquisition roots or live manifests. A downloader may be running, and you must never copy a live SQLite file without its WAL. Every output directory passed to the CLI must be new.
- Joins and sums follow `docs/en/transformation-conventions.md`. Select one canonical result per `(snapshot_id, principal_section_id, contest_id)` and aggregate choices to result grain before attaching totals. Never repair a multiplied join with `SUM(DISTINCT ...)`.
- Unknown is not zero. Missing, unresolved or partial values stay null or unavailable, with a reason and a denominator. A passing subset (e.g. AC) is never national coverage, and no fraud labels are produced.
- Opaque IDs are versioned-namespace digests of canonical JSON natural keys. Event identity uses the object/member occurrence, the source line and the parser version, never the timestamp plus the message text.
- Do not put voter or mesário IDs, or other unnecessary sensitive tokens, into structured outputs.

## Bilingual documentation

Every doc under `docs/en/` has a `docs/pt-BR/` counterpart at the same relative path, and every `research/*.md` has a `.pt-BR.md` sibling. Each starts with `Document-ID: <ID> · Revision: <N> · Language: <en|pt-BR>`. When you edit one file of a pair, update the other and bump both revisions together. Fenced code, commands, SQL, formulas and numbers must be byte-identical across languages; Mermaid labels are the only exception. `just docs-check` enforces this. `just docs-command-check` parses shell examples in docs against real `--help` output and the justfile recipes, so a renamed flag breaks docs. After each numbered task, write a paired handoff from `docs/en/task-handoff-template.md` and update the implementation index in both languages.
