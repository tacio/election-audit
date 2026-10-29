# Task 5.2 — Anonymous operational cycles

Document-ID: EA-HANDOFF-5.2 · Revision: 1 · Language: en

Objective: Implement explicit anonymous transitions without converting requests, repeats or partial histories into votes.
Prerequisites: [5.1](task-5.1.md), [implementation index](../implementation-index.md),
[reconstruction guide](../reconstruction.md), relevant session/device/event/cycle/lineage and operational feature contracts.

Files/interfaces and deliverables: `reconstruct_cycles`; six cycle fixtures. Baseline authorization/completion reconstructs completed unknown-method cycles. Repeated authorization, orphans, unknown intervening events and incomplete histories remain unresolved. Requests never establish manual method. Reviewed full/partial suspension, resumption, attempt/failure, method, cancellation and abandonment rules retain their distinct states and original evidence. No candidate/RDV association.

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

Next: **5.3**, evidenced clocks. Pass this handoff, index,
reconstruction guide and relevant contracts only. For Phase 6 use
`reconstruct_parse(..., object_sha256=[...], reader=reader)`, then
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
retain the shared `contexts` directory when relocating the store.
