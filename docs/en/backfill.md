# Resumable frozen backfill and storage planning

Document-ID: EA-BACKFILL · Revision: 5 · Language: en

Backfill is an explicit derived-data operation over one immutable snapshot, with one bounded reconstruction group per content object. It does not invoke acquisition. Repeating the identical frozen input, output and resource configuration verifies/reuses parse cache, shared reconstruction context, completed shards and release; it restores the current pointer only to a verified release. New live downloads require a new snapshot and cannot silently enlarge an existing backfill.

The following whole-available-population commands are documented and their recipes/flags checked, but the full AC–RJ backfill was NOT executed; the national structural pass used the summary path in [feature-oriented processing](feature-oriented-processing.md) instead. Replace /large-volume with provisioned storage and SNAPSHOT_DIGEST with the actual frozen directory. Missing/unpublished inputs remain explicit; AC–RJ never becomes national completeness. Acquisition manifests and raw roots are never modified.

```sh
env UV_OFFLINE=1 just snapshot --source $EA_DATA/raw/2026/turno-2 --store /large-volume/audit/snapshots --ufs ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj --reserve-gib 10
env UV_OFFLINE=1 just backfill /large-volume/audit/snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/backfill --max-events 100000
env UV_OFFLINE=1 just backfill /large-volume/audit/snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/backfill --max-events 100000
env UV_OFFLINE=1 just validate /large-volume/audit/backfill/warehouse
env UV_OFFLINE=1 just report /large-volume/audit/backfill/warehouse --output /large-volume/audit/reports --language both
```

Defaults are 4 parser workers, 4 DuckDB threads, 12 GiB memory, 8 GiB spill cap, 10 GiB free reserve, 2048-row batches and 100000 events per reconstruction group. During Phase 9 the SSD had approximately 31.6 GB free (decimal): reserve plus potential spill alone consume approximately 19.3 GB, leaving about 12.3 GB before snapshots, parse cache, shared JSON context, reconstruction files, release database/facts, staging, bundles and headroom. Free-space guards are enforced, but they are not a capacity guarantee.

Current release facts and audit.duckdb are co-located in the release store; the implementation does not place Parquet on HDD and DuckDB alone on SSD through a split-storage flag. Snapshot/parse/reconstruction population context also retains full selected-UF indexes even for five selected principals. Do not claim the entire backfill fits the current SSD. Provision a larger store, or explicitly select/review manageable geographic populations and keep their denominators separate. Whole-national compact analysis populations are additionally bounded by max_events; this is not a national model trainer.

No national size/performance estimate is inferred by multiplying a five-principal sample. Measure frozen inventories and every derived stage before expanding: selected byte totals, full-UF metadata, expansion ratios, context duplication across stores, DB/Parquet sizes, temporary spill/staging, final review copies and remaining free space. Refuse expansion when the reserve/spill/headroom cannot fit. Maximum archive/member/line/event guards can stop oversized objects; retain them for explicit later review rather than raising limits blindly.

The exact bounded pilot resume recipe below is executed twice during acceptance, and an interruptible synthetic fixture raises immediately before release rename, verifies no current success marker, then restarts successfully. Completed artifacts remain immutable; failed staging is not success. The bounded pilot resume is evidence for restart behavior, not proof a full population was run.

```sh
env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
```

Additional runoff UFs including ZZ must be explicit. Their source root must contain those available originals/indexes; missing ones stay unavailable. Other rounds/history use explicit separately documented normalized import bundles with original hashes, exact election/round contracts and reviewed harmonization. `snapshot --round 1` selects first-round pleito 3220/election 6257 (the default is round 2), and `--source-manifest` overrides the manifest found through the root's location marker. Do not relabel runoff bytes as first-round data. Official BU imports are described in the [electoral guide](electoral-results.md).

```sh
env UV_OFFLINE=1 just snapshot --source /explicit/additional-runoff-root --store /large-volume/audit/additional-snapshots --ufs rn ro rr rs sc se sp to zz --reserve-gib 10
env UV_OFFLINE=1 just backfill /large-volume/audit/additional-snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/additional-backfill
env UV_OFFLINE=1 just import-results /large-volume/audit/backfill/warehouse/releases/PARENT_DIGEST --bundle /reviewed/explicit-round-import/bundle.json --store /large-volume/audit/round-imports
```

Use [reproduction](reproduction.md) for the offline review bundle, diagnostic sampling, source/derived identity distinction, actual timing artifacts and bilingual reports. The task 9 handoffs record exact measured outcomes and the smallest remaining task.
