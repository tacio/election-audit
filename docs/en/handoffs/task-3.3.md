# Task 3.3 — Immutable snapshot CLI

Document-ID: EA-HANDOFF-3.3 · Revision: 1 · Language: en

Objective: freeze reviewable, restart-safe inputs that later downloads cannot alter.
Prerequisites: [3.2](task-3.2.md), source/snapshot/coverage/lineage contracts.

Files/interfaces: `election_audit/snapshots.py`; `create_snapshot`,
`publish_snapshot`, `inspect_snapshot`, `snapshot_tables`. CLI adapters in
`election_audit/cli.py`; usable `just snapshot` and `just snapshot-inspect` recipes.
The [paired guide](../snapshots.md) defines flags, output and identity semantics.
`--source` follows the marker; `--store` must be outside the raw root. Optional
repeated `--section` bounds assets while preserving full selected-UF denominators.

Deliverables: independent SHA-256-verified copies, atomic staging/rename with
fsync and a derived-store lock, space reserve, immutable content identity,
checksummed JSON, frozen schema/runtime/implementation/selection provenance,
inspection independent of acquisition, contract row/FK checks, preserved unknown
and failed evidence. Same captured inventory/implementation republishes
idempotently; a fresh capture has a new observation time and may get a new ID.
Legacy `inspect` and acquisition remain unchanged. No archives, DuckDB/Parquet,
BU import, canonical results, electoral reconstruction or fitting.

Acceptance: final full command below exited 0: lock, Ruff format/lint, contract
metadata, paired documentation and 66 offline tests passed, including 23 dedicated
inventory/population/snapshot tests. Both new recipes' `--help` commands exited 0.
No live corpus, national inventory, network fetch or Git operation was attempted.
An existing collector ResourceWarning remains non-fatal.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just snapshot --help
rtk proxy env UV_OFFLINE=1 just snapshot-inspect --help
```

Decisions: downstream consumers call `inspect_snapshot(path, verify_objects=True)`
and `snapshot_tables(document)`. `source_object.storage_locator` is relative to
the completed snapshot directory; do not reopen original paths retained under
`payload.inventory`. Stored contract is `payload.schema`; normalized tables are
`payload.tables`. `snapshot` and membership wrapper rows are included by
`snapshot_tables`. JSON-pointer lineage has exact original record paths, no
invented line/byte spans. `snapshot:v1:` identity hashes the canonical inventory
digest; snapshot-scoped keys use `pending-snapshot` when computing that inventory
digest to avoid circularity. The guide specifies the whole format.

Current verified metadata emits package observations/assets. Exact `Totalizado`
maps to `totalized` with version `tse-package-status-exact-v1`; all other raw labels,
case variants and numeric flags deliberately stay unknown. Original raw statuses
and the mapping/version are frozen. Null/non-text status produces explicit issues
instead of invented normalized rows. All historical run/log associations retain
null byte attribution; current local objects cannot establish historical content.

Unresolved: no usable inherited Git history; no commit identifier invented.
Manifest `running` cannot prove liveness; missing run arguments and historical
fetch/metadata mappings are unrecoverable. General publication/reconciliation
checks and additional validated status adapters remain later work. Abandoned
staging directories are ignored, not silently removed. Unknown installation and
BU/parser readiness are preserved. Partial AC–RJ remains partial nationally.

Exact next task: **Phase 4**, archive decoding/parsing from frozen snapshots only.
Pass only this handoff, implementation index, snapshot guide, source/lineage/
parsing-issue contracts and parser-specific format references. Preserve duplicate
member occurrences and nested archive locators; write derived outputs separately,
never modify snapshot directories. Do not inventory/hash the real corpus yet;
the bounded real pilot belongs to Phase 9.
