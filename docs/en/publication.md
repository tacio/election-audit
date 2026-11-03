# Operational publication and initial reports

Document-ID: EA-PUBLICATION · Revision: 3 · Language: en

[Português](../pt-BR/publication.md) · [Implementation index](implementation-index.md)

The pipeline reads frozen artifacts only. A release covers exactly the snapshot it
was built from; a UF subset is partial national coverage. Acceptance used synthetic
fixtures plus the Phase 9 five-region real pilot; no authoritative clock rules have
been certified. Reviewed real-message semantics are a separate Phase 13 adapter
(`operational_review`), not part of these releases. Original acquisition, manifests
and bytes are preserved.

Stages: frozen snapshot → structural parse/cache → bounded operational
reconstruction groups → immutable DuckDB/Parquet release → validation → read-only
queries and initial reports. Select exactly one snapshot/parse input or one or
more disjoint reconstruction shards. No BU import, candidate attribution, model
fitting or fraud labels are produced.

```sh
rtk proxy env UV_OFFLINE=1 just build /path/to/snapshot --input-kind snapshot --store /ssd/audit --parser-workers 4
rtk proxy env UV_OFFLINE=1 just build /path/to/parse --input-kind parse --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just build /path/to/reconstruction --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just validate /ssd/audit
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT completion_state, count(*) FROM anonymous_cycle GROUP BY completion_state'
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports --language pt-BR
```

`build --evidence FILE` supplies reviewed reconstruction assertions for snapshot
or parse builds. See [reconstruction](reconstruction.md) for exact anchor requirements;
assertions and checksums are not independent semantic certification. Default parse
builds reconstruct one content object per group with one reused `FrozenParseReader`.
The Python API accepts explicit related object groups for overlap/copy resolution.
Unknown cross-group histories remain unresolved; global eligible totals stay null.

| Python interface | Behavior |
| --- | --- |
| `publication.ResourceConfig` | Validated resource limits |
| `publication.publish_release(shards, store, config=None)` | Publish verified disjoint immutable reconstruction inputs |
| `publication.build_from_parse(parse, store, config=None, evidence=None, object_groups=None)` | Shared reader and bounded reconstruction groups |
| `publication.build_from_snapshot(snapshot, store, config=None, evidence=None)` | Parse frozen snapshot with configured workers, then build |
| `publication.inspect_release(path)` | Verify metadata identity and every file hash/size |
| `publication.open_release(path)` | Verified read-only DuckDB plus temporary relocated fact views |
| `release_tools.validate_release(path)` | Integrity, logical digests, grains/FKs/accounting/lineage/coverage and explicit deferred inputs |
| `release_tools.query_release(path, sql, max_rows=1000)` | Exactly one parsed SELECT, bounded output, external access disabled |
| `release_tools.report_release(path, output, language="both")` | Paired translated Markdown, shared findings ledger and reproducible SQL |

Resources default to parser workers 4, DuckDB threads 4, memory 12 GiB, spill cap
8 GiB and free SSD reserve 10 GiB. CLI flags `--parser-workers`, `--duckdb-threads`,
`--memory-bytes`, `--spill-bytes`, `--reserve-bytes`, `--batch-rows`, `--max-events`
are validated. DuckDB receives actual thread/memory/spill settings; temporary
spill stays in staging. Reserve plus spill budget is checked before/through writes,
with additional batch headroom. Limits are not a promise that a full corpus fits;
exhaustion aborts publication. Parser locks are per content/config key, allowing
independent objects concurrently while parsing identical content once. Each
reconstruction group is bounded (default 100000 events); publication streams 2048
rows at a time. Full frozen population metadata is retained once in memory.

A store contains `releases/DIGEST/audit.duckdb`, `context.json`, `release.json` and
`facts/TABLE/year=YEAR/round=ROUND/uf=UF/*.parquet`. Facts use zstd compression;
compact context, session summaries and marts live in DuckDB. Official section
context supplies partitions; unresolved geography stays `unknown`. Canonical
copied-event and derived-row mappings partition associated evidence/lineage when
known. Shared frozen metadata lineage is preserved once, including original source
observations and objects. Legacy parses without it are explicitly unavailable.
Complete row representations remain in `payload` JSON alongside typed contract
columns or mart grain keys. This preserves uncertainty and versioned summary fields.

Single-writer locking, staging/fsync/atomic release rename and atomic `current`
pointer replacement preserve prior published releases through interruption. Repeated
identical inputs/config verify and reuse their immutable release. Interrupted staging
is never a successful release; a completed release with an old pointer can be reused
on retry. `current` identifies a release digest; passing the release path pins a query.
Relocate the complete store/release: temporary fact views resolve its current path,
and published data remains usable after source/parse/reconstruction removal.

Validation rehashes physical files and recomputes order-independent logical SHA-256
multiset digests with exact counts; it verifies unique primary/alternate keys,
available FKs, original-record lineage, cycle/event/session accounting, disjoint
content partition and expected-member retention. Missing snapshot/objects/location
context in old parses is explicitly deferred, never certified. Each query performs
one full integrity verification. Reports reuse one verified manifest and one query
connection for all calculations, following full validation. Full verification scans
large facts; it is intentional and can be expensive. Query connections are read-only,
with no spill into immutable releases. COPY, writes, multiple statements and external
file reads are rejected. `--sql-file FILE` avoids shell quoting for longer SELECTs;
`--max-rows` bounds returned rows and reports truncation.

Coverage retains expected/member/principal distinctions and unknown strata.
Processing availability uses expected advertised package/type rows, with complete
result population unknown; receipt, processing, generation, publication and client
observation are separate. Missing source is not zero latency or not-published.
HTTP Last-Modified/download timestamps never supply lifecycle times. Domestic
late completion is strictly after 17:00 America/Sao_Paulo on the target date;
equal is not late. Observed late completions and evidenced remaining-open intervals
are separate. Unresolved clocks/context block confident classification, bounded
intervals retain sensitivity limits, and overseas convention stays unavailable.
Session/cycle facts never expand through member/package/lineage joins.

Reports default to `report.en.md` and `report.pt-BR.md`, with `findings.json`,
`lifecycle.sql` and `late.sql`; `--language en|pt-BR|both` selects languages.
Translated labels/explanations share identical values, SQL, formulas and numerical
examples. Findings retain input IDs, calculation, assumptions, exclusions,
uncertainty, reproduction commands and evidence that could challenge them.
Electoral validation is unavailable; reconstructed cycles are not reconciled votes.

Phase 7 extension is implemented through `derivatives.publish_derivative` and a
manifest-driven parent-chain loader. Base `FACTS` remains unchanged; children pin
relative parent identities/hashes, add compact/fact storage and reuse parent Parquet.
See [electoral imports](electoral-results.md) for the normalized contract, the official
BWEB adapter, binary BU verification and query/validation/report integration.
