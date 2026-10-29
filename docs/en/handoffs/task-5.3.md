# Task 5.3 — Evidenced clocks and elapsed time

Document-ID: EA-HANDOFF-5.3 · Revision: 1 · Language: en

Objective: Preserve original readings and apply only explicit section/election timezone, correction and continuity evidence.
Prerequisites: [5.2](task-5.2.md), [implementation index](../implementation-index.md),
[reconstruction guide](../reconstruction.md), relevant session/device/event/cycle/lineage and operational feature contracts.

Files/interfaces and deliverables: `normalize_clocks`, `elapsed_seconds`; four clock fixtures. Separate raw reading, offset, correction, UTC, confidence and rule evidence. Unknown zones stay null; explicit local continuity may support elapsed time. Municipality/overseas rules use exact section/election context. Reversals, changed intervals, clock-change events and ambiguous/nonexistent local times invalidate unsupported durations. No UF defaults or after17 classification.

Acceptance: the commands below exited 0: 23 reconstruction fixtures (six session,
six cycle, four clock and seven summary/publication tests), 106 total repository
tests, lock, Ruff, contracts and paired documentation checks; recipe help and
synthetic CLI passed. No real corpus read, network/Git action or acquisition change.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_reconstruction.py -v
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just reconstruct --help
```

Decisions: `operational-v1` and `operational-evidence-v1`; the structural parser
remains `jez-structural-v1`. Reviewed assertions retain exact source anchors but
are not independent certification of message meaning. Unverified inputs never
select official context. Missing values stay unknown; AC–RJ and samples retain
partial national scope and frozen full-index coverage.

Unresolved: no real operational adapter or authoritative clock/identity rules
validated; Phase 9 must review source meaning. Shards resolve overlap only inside
the selected object group. Phase 6 must retain a disjoint object partition, reject
repeated event/session/cycle keys and preserve cross-shard uncertainty. Full parse
metadata remains in memory once per reader; bounded events/witnesses per group.
No DuckDB publication, electoral import, fitting or fraud labels in this phase.

Next: **5.4**, summaries and immutable publication. Pass this handoff, index,
reconstruction guide and relevant contracts only. For Phase 6 use
`reconstruct_parse(..., object_sha256=[...], reader=reader)`, then
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
retain the shared `contexts` directory when relocating the store.
