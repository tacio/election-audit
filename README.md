# Election audit — 2026 presidential runoff

Document-ID: EA-ONBOARDING · Revision: 5 · Language: en

[Português](README.pt-BR.md)

This project preserves original acquisition bytes and publishes frozen snapshots → structural parses → operational reconstruction → immutable DuckDB/Parquet releases → normalized electoral imports → descriptive features, partitions and immutable analysis ledgers. Raw log acquisition now spans all UFs and ZZ, with explicit unpublished/no-log gaps; frozen derived releases retain their original partial populations. No model is fitted and no fraud label is produced.

Install uv, just and rtk. Python 3.14, DuckDB 1.5.3, PyArrow 24.0.0 and Ruff are pinned in the lockfile. Recipes use `/tmp/election-audit-uv-cache`; offline setup needs an existing populated cache. Checks never acquire election data.

```sh
rtk proxy just setup
rtk proxy just doctor
rtk proxy env UV_OFFLINE=1 just check
```

The small offline walkthrough creates explicitly SYNTHETIC originals, a mixed-date archive, replacement/copied history, manual request/cancellation, unresolved clocks and malformed nested content. It publishes the complete operational → normalized electoral → partition → null-result ledger chain and both reports. Every output directory below must be new.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
```

The review bundle contains frozen selected originals, the complete relative release parent chain, exact configurations, source and dependency lock, SQL, validation and logical output digests. It excludes the live manifest, acquisition root, environment and credentials. Offline reproduction requires the pinned dependencies already installed or cached; wheels/cache are not bundled. Container bytes and creation times can differ; frozen input identities and normalized logical payloads are checked.

Use the [reproduction and peer-review guide](docs/en/reproduction.md) for the bounded real pilot, evidence review and reproducibility limits; use the [backfill guide](docs/en/backfill.md) for resource planning and restart. Commands operate on frozen inputs unless an explicit acquisition command is invoked.

```sh
rtk proxy env UV_OFFLINE=1 just snapshot --help
rtk proxy env UV_OFFLINE=1 just parse --help
rtk proxy env UV_OFFLINE=1 just reconstruct --help
rtk proxy env UV_OFFLINE=1 just build --help
rtk proxy env UV_OFFLINE=1 just import-results --help
rtk proxy env UV_OFFLINE=1 just analyze --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
rtk proxy env UV_OFFLINE=1 just backfill --help
rtk proxy env UV_OFFLINE=1 just docs-command-check
rtk proxy just resume --help
rtk proxy just inspect --help
```

Task 7.1 now includes the official `tse-bweb-2026-v1` adapter, verified against real AC runoff bytes and the bundled dictionary. All 2270 presidential sections pass published-row arithmetic checks. Missing choice rows, official totalization linkage, independent final totals and clocks remain unresolved; no canonical result or scientific eligibility is inferred. See the [electoral guide](docs/en/electoral-results.md).

Legacy downloader flags, object layout, authoritative `manifest-location.json` and live WAL behavior are preserved. Keep one downloader per raw root. Fresh snapshot capture observes current committed state; reproduce an existing frozen snapshot to avoid changing source observation identities. Additional UFs/ZZ and rounds/history require explicit snapshots/imports.

Further work starts at the [implementation index](docs/en/implementation-index.md). See [snapshots](docs/en/snapshots.md), [archive parsing](docs/en/archive-parsing.md), [reconstruction](docs/en/reconstruction.md), [publication](docs/en/publication.md), [electoral imports](docs/en/electoral-results.md), [analysis](docs/en/analysis.md), [research protocol](research/analysis-plan.md) and [acquisition reference](docs/en/acquisition-reference.md). English and Portuguese documents share IDs/revisions and exact commands, SQL, formulas and numerical examples. Mechanical checks complement human translation review.
