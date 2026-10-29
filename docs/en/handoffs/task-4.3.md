# Task 4.3 — Immutable parse cache and publication

Document-ID: EA-HANDOFF-4.3 · Revision: 1 · Language: en

Objective: parse identical content once while retaining every frozen source,
package and snapshot association. Prerequisites: [4.2](task-4.2.md), [snapshot
guide](../snapshots.md), relevant source/lineage/issue contracts.

Files/interfaces: `election_audit/archive_parsing.py`, CLI `parse`, recipe `just
parse`, [paired archive guide](../archive-parsing.md), `tests/test_archive_parsing.py`.
`parse_snapshot(snapshot, store, config=ParseConfig())` returns a publication path.

Deliverables: content/parser/config cache identity, streamed checksummed immutable
artifacts/diagnostics, verified hits, atomic publication/fsync/derived locks,
interruption recovery and quarantined corrupt caches. Separate immutable
`parses/PUBLICATION_DIGEST/parse.json` retains snapshot, observations, package
assets, context tables, unknown history, missing assets and full coverage.
`cache/KEY/` holds events/issues plus checksummed `artifact.json`.

Acceptance: commands below exited 0: 15 parser fixtures; 83 repository tests,
lock, Ruff, contracts and paired docs; usable recipe help. Synthetic CLI parsing
also passed after original raw objects were removed. Multiple packages and a
second snapshot reuse one content artifact with every association retained;
corruption and interruption fixtures recover. Existing collector ResourceWarnings
are non-fatal. No live corpus, network or Git operation; acquisition untouched.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just parse --help
```

Decisions: `iter_event_witnesses(path)` streams snapshot/observation-scoped
`witness_event_id` plus shared content `event_id` and all package assets;
`iter_lineage(path)` and `iter_parsing_issues(path)` emit contract-shaped rows.
`inspect_parse(path)` verifies publication and cache independently of raw inputs.
`source_line_sha256` is exact original physical-line evidence, including newline
bytes, not an equivalence rule. `selection_state=context_unresolved` everywhere.

Unresolved: only three exact VOTA classes are decoded in `jez-structural-v1`;
extensions need a versioned adapter. Unsupported ZIP variants and bounded partial
artifacts stay explicit. No sessions, cycles, timezone conversion or DuckDB build.

Next: **Phase 5**, operational reconstruction. Pass only this handoff,
[implementation index](../implementation-index.md), archive guide, relevant
session/device/event/cycle/lineage contracts and required format references.
Read witnesses from the parse publication and frozen `context_tables`; retain
source/parser limits and full-index denominators. Never sum package witnesses or
deduplicate by timestamp/kind alone. Real corpus work remains Phase 9.
