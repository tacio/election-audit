# Task 3.1 — Source inventory

Document-ID: EA-HANDOFF-3.1 · Revision: 1 · Language: en

Objective: freeze an honest read-only acquisition view before coverage selection.
Prerequisites: task 2.1, implementation index, schema dictionary/conventions.

Files/interfaces: `election_audit/source_inventory.py` exposes
`read_manifest(root, ufs=DEFAULT_UFS)` and `inventory_sources(root, ufs=DEFAULT_UFS)`.
The downloader's `manifest_path(root)` resolves the location marker. One SQLite
`mode=ro` transaction includes committed WAL; no acquisition lock is taken.
`canonical`, `digest` and `identity` provide versioned canonical JSON identities.

Deliverables: selected original run/section/log/file rows, original metadata,
details, fetch times, validators, URLs, paths and package flags; verified current
`source_object`/`source_observation` rows and all failed object checks. Locators
identify manifest table and primary key; unknown byte spans stay null. Exclusions:
no network, raw mutation, directory walk, archive parsing or historical inference.

Acceptance: isolated fixture command below exited 0; 5 tests passed. Tests cover
marker resolution, committed WAL, cross-table snapshot isolation during a writer
commit, corrupt/missing/escaping objects, missing manifest and later URL updates.
No live corpus or national hash inventory was run.
`rtk proxy env UV_OFFLINE=1 just check` also exited 0: lock, Ruff, contracts,
paired docs and 48 offline tests passed. A legacy collector ResourceWarning did
not fail the suite.

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_snapshots.py -v
```

Decisions: current mappings become new local inventory observations with a
synthetic inventory run and capture time. These are local reads, not HTTP attempts;
HTTP status stays unknown. Original client fetch timestamps remain verbatim in
`manifest_rows`. Every historical log advertisement keeps null object identity
and `historical_mapping_unknown`, even when the latest URL is verified. The
manifest does not record per-run fetch attempts or trustworthy old byte mappings.

Unresolved: no usable Git history/network access; no commit/hash/download claims.
Source bytes can change after the database capture: later snapshot publication
must copy and reverify them atomically. Running means unfinished at capture,
without claiming whether a collector process is alive. Default configured scope
is the 19 alphabetical UFs AC–RJ, pleito 3221/election 6258, partial nationally.

Exact next task: **3.2**, population ledger from frozen verified UF indexes and
manifest evidence. Read this handoff, inventory API and coverage/composition
contracts; retain unknown denominators and unresolved composition.
