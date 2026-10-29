# Task 5.4 — Operational summaries and immutable shards

Document-ID: EA-HANDOFF-5.4 · Revision: 1 · Language: en

Objective: Publish restart-safe bounded reconstruction artifacts and honest operational denominators for Phase 6.
Prerequisites: [5.3](task-5.3.md), [implementation index](../implementation-index.md),
[reconstruction guide](../reconstruction.md), relevant session/device/event/cycle/lineage and operational feature contracts.

Files/interfaces and deliverables: `summarize_operations`, `reconstruct_parse`, `inspect_reconstruction`, `iter_reconstruction_rows`, `load_reconstruction_context`; CLI/recipe `reconstruct`; seven summary/publication fixtures. Separate observed cycles, eligible target counts, unknown methods, explicit attempts, supported durations/gaps, latency, interruptions and evidenced exposure. Atomic checksummed shards share full population metadata once at `contexts/PARSE_ID/parse.json`. `FrozenParseReader` verifies metadata/indexes associations once, then verifies selected object groups; pass it as `reader=` to reuse shared context. All source witnesses remain. Full store relocation and inspection after source/parse removal are tested.

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

Next: **6**, DuckDB/Parquet publication. Pass this handoff, index,
reconstruction guide and relevant contracts only. For Phase 6 use
`reconstruct_parse(..., object_sha256=[...], reader=reader)`, then
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
retain the shared `contexts` directory when relocating the store.
