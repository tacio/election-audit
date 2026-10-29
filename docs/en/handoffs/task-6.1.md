# Task 6.1 — Immutable operational releases

Document-ID: EA-HANDOFF-6.1 · Revision: 1 · Language: en

Objective: publish bounded frozen reconstruction shards as compressed Parquet facts and compact DuckDB dimensions.
Prerequisites: [5.4](task-5.4.md), [index](../implementation-index.md), operational contracts.

Files/interfaces: `election_audit/publication.py`: `ResourceConfig`, `publish_release`, `inspect_release`, `open_release`, `build_from_parse`, `build_from_snapshot`. `parse_snapshot(..., workers=4)` and `parse --workers` apply bounded parser concurrency. Existing acquisition is preserved.

Deliverables: single nonblocking writer lock; immutable `releases/DIGEST`, checksummed provenance/context, atomic `current`; zstd Parquet facts partitioned by evidenced year/round/UF (unknown retained), SSD DuckDB dimensions. Actual DuckDB thread/memory/spill settings and free-space reserve checks; bounded row batches and object/group reconstruction. Identical immutable inputs resume safely; shared objects and repeated event/session/cycle keys fail. Read-only connections attach temporary fact views and survive store relocation.

Acceptance: five publication fixtures passed (interruption at three stages, concurrent writer, resource/overlap guards, PK/FK failure, relocation/settings, corruption); full repository check exited 0 with 111 offline tests. Entirely synthetic; no real corpus/network/Git operation.

Decisions: defaults parser workers 4, DuckDB threads 4, memory 12 GiB, spill cap 8 GiB, free reserve 10 GiB. Require reserve plus spill budget before/through publication. Missing full snapshot/objects/location context is explicitly deferred, never silently certified. Unknown official selection retains unknown partition. Cross-shard copy overlap remains unresolved; global eligible total stays null.

Unresolved: no real operational adapter/pilot; parser metadata remains resident once. Lifecycle marts and comprehensive release validation are next; no electoral imports or fitting.

Next: **6.2**, operational coverage/session/processing availability/late-voting marts, using publication and reconstruction interfaces only.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_publication.py -v
rtk proxy env UV_OFFLINE=1 just check
```
