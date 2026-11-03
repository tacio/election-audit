# Frozen snapshots and coverage

Document-ID: EA-SNAPSHOTS · Revision: 2 · Language: en

[Português](../pt-BR/snapshots.md) · [Implementation index](implementation-index.md)

`snapshot` creates a self-contained local input population. It reads the
authoritative manifest through `manifest_path(root)` and its location marker,
using one read-only SQLite transaction that includes committed WAL. Acquisition
and original files remain unchanged. No network, directory walk, archive parsing,
electoral import or DuckDB publication occurs.

The default selection is the 2026 federal presidential runoff, pleito `3221`,
election `6258`, round `2`, date `2026-10-25`, and the 19 alphabetical UFs AC–RJ.
This is **partial national coverage**. `--ufs` can explicitly select any official
UF including ZZ in a later snapshot. `--round 1` selects the first round (pleito
`3220`, election `6257`, `2026-10-04`); `--source-manifest` overrides the manifest
found through the root's location marker. History needs explicit import adapters.
Missing indexes and unavailable UFs never become zero population.

For a bounded pilot, explicitly select sections. Only those section objects and
selected-UF index/configuration objects are hashed/copied; original object
directories are never traversed. Whole-UF indexes still define the denominator.
Members outside the asset selection remain in coverage as `not_selected`, with
`outside_asset_selection`; aggregation does not automatically expand the sample.
The following paths and section are illustrative, not a live-corpus command run.

```sh
rtk proxy env UV_OFFLINE=1 just snapshot --source /path/to/raw --store /path/to/derived --ufs ac --section ac/01120/0001/0001 --reserve-gib 10
rtk proxy env UV_OFFLINE=1 just snapshot-inspect /path/to/derived/SNAPSHOT_DIGEST --verify-objects
```

Repeat `--section UF/MUNICIPALITY/ZONE/SECTION` for more assets; codes must have
widths `2/5/4/4`, with lowercase UF. Omit `--section` only when intentionally
freezing all selected-UF assets. `--source` and `--store` are required. The store
must be outside the acquisition root. Default free-space reserve is `10` GiB;
insufficient space fails before copying. The CLI prints the completed directory.
The original `inspect` command retains its raw-message diagnostic behavior.

A completed directory contains `snapshot.json`, `snapshot.sha256` and independent
copied `objects/` addressed by SHA-256. Object locators in emitted contract tables
are relative to that directory. `payload.inventory` retains original raw paths
as evidence; downstream parsers must use the emitted tables' frozen paths.
Metadata is canonical UTF-8 JSON. `inventory_sha256` hashes the payload with
snapshot-scoped foreign keys replaced by the documented `pending-snapshot`
sentinel to avoid circular identity; `snapshot_id` uses `snapshot:v1:` plus the
canonical JSON digest of that inventory digest. A file checksum protects the
whole wrapper too, including creation time. Stored schema, implementation hashes,
runtime/package versions, exact selection and normalization policy are frozen.

Publication copies and rehashes each verified object into a private staging
directory, fsyncs files/directories, then atomically renames it. Source changes
during copying abort publication. Failed/missing inputs can still produce an
honest partial snapshot with null objects and preserved checks. Existing snapshots
are validated and never overwritten. Re-publishing the same captured inventory
and implementation is idempotent; a fresh CLI capture records a new observation
time and may create a new ID. Interrupted `.snapshot-building-*` directories are
ignored on restart; their cleanup is separate from completed artifacts.

Inspection checks wrapper checksum, inventory identity, the frozen schema's row
shapes/keys/null states and emitted foreign keys, plus object existence/length.
`--verify-objects` additionally rehashes frozen copies. It never rereads the live
manifest/raw root, so later downloads or deleted originals cannot alter a snapshot.
General electoral reconciliation, signatures and canonical results remain later
work; availability does not establish electoral eligibility.

Legacy `files` is only the latest URL mapping. Current rows become new local
inventory observations with synthetic inventory-run identity and capture time;
they are not HTTP requests, so HTTP status remains unknown. Original `fetched_at`,
ETag and Last-Modified stay verbatim in `manifest_rows`. Historical `logs` rows keep
their original run/section/package/status/filename/URL, null object mapping and
`historical_mapping_unknown`. They never borrow current bytes as historical fact.
The legacy manifest cannot recover every request attempt or historical index.

Verified frozen UF indexes supply expected registered **members**, including
aggregated members. Duplicate/invalid/absent indexes leave expected counts null;
manifest-only sections remain visible as observed-only. Direct terminal principal
self-maps establish a separate unique-principal denominator. Conflicts, missing
principals and chains/cycles remain unresolved. Each retained section appears
once in the disjoint member accounting: acquired, aggregated, missing, failed,
unresolved, not_published or not_selected. Failed historical attempts remain
explicit even when current bytes are available. Finished run status proves no
coverage; unfinished rows cannot distinguish active from abandoned processes.

`Totalizado` maps exactly to `totalized` under `tse-package-status-exact-v1`, based
on the supplied [acquisition reference](acquisition-reference.md). Other labels,
case variants and numeric flags deliberately remain `unknown` until validated;
raw values survive. Null/non-text raw status cannot fit the v1 non-null contract:
its exact auxiliary bytes and a metadata issue remain, without inventing a label.
Installation, BU availability, unvalidated publisher timestamps, parsing and
reconciliation stay unknown/not attempted. JSON lineage uses original JSON
pointers and archive segments `[]`; unknown byte/line spans remain null.

| Python interface | Returned artifact / use |
| --- | --- |
| `source_inventory.read_manifest(root, ufs, section_keys=...)` | Consistent selected original manifest rows and digest |
| `source_inventory.inventory_sources(root, ufs, section_keys=...)` | Verified current objects/observations, failures and unknown historical advertisements |
| `coverage.build_population(inventory)` | Contract table subset, coverage summary and explicit adapter evidence |
| `snapshots.publish_snapshot(inventory, population, store, reserve_bytes=0)` | Idempotently materialize one captured input |
| `snapshots.create_snapshot(root, store, ufs, section_keys=..., reserve_bytes=0)` | Capture and publish a fresh immutable input |
| `snapshots.inspect_snapshot(path, verify_objects=False)` | Validated document, independent of acquisition |
| `snapshots.snapshot_tables(document)` | Contract tables including snapshot/membership |

`section_keys` is either `None` or a nonempty sequence of four-string tuples.
`ufs` defaults to AC–RJ. Modules live under `election_audit/`. Consumers use
`document["payload"]["tables"]` for source/section/coverage/lineage rows, and
`snapshot_tables` to include `snapshot`/`snapshot_observation`. The stored schema
is `document["payload"]["schema"]`. These JSON contract rows are not a DuckDB or
Parquet publication. The [structural parser](archive-parsing.md) reads only frozen
object locators and preserves nested member occurrences; see the
[3.3 handoff](handoffs/task-3.3.md) for acceptance detail.
