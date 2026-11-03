# Electoral imports and derivative releases

Document-ID: EA-ELECTORAL-RESULTS · Revision: 3 · Language: en

[Português](../pt-BR/electoral-results.md) · [Index](implementation-index.md) · [Publication](publication.md)

The official **tse-bweb-2026-v1** adapter now imports the acquired AC runoff BWEB
CSV using its pinned bundled dictionary, exact 45-column header, Latin-1 encoding
and reviewed candidate/blank/null mapping. The existing **electoral-normalized-v1**
interface remains available for explicitly normalized sources, including other
rounds/history and external references. Original log acquisition and frozen parent
releases are preserved. BU imports use a separate source snapshot; no automatic
linkage to operational sessions or clock conversion is inferred.

The official AC archive, SHA-512 sidecar, catalog and resource API bytes were
acquired on 2026-10-30 UTC. The published checksum matches and ZIP CRCs pass.
The archive has 17622 rows: 8697 presidential rows (election 6258, cargo 1) and
8925 governor rows (election 6260, cargo 3), which are explicitly excluded.
All 2270 presidential principal sections pass both published-vote-sum versus
attendance and attendance plus abstention versus electorate checks; published
presidential choices sum to 453654 votes. These are real source arithmetic checks,
not independent final-result reconciliation. Absent choices remain unknown, not
zero. Apurada is not Totalizado: result status remains unknown, complete choice
ledgers are unavailable and canonical results/ratios remain unavailable. Raw BU
emission/receipt tokens are retained as unresolved processing events. Special and
unresolved categories, signatures and independent final totals remain unverified.

[Official AC resource](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna/resource/4753eb99-062b-484a-b569-04c51d039885).
`election_audit/resources/bweb-2026-layout.json` pins the dictionary and mapping;
`electoral-source-evidence.json` records the earlier failed access and successful
acquisition. The dataset API response listed only first-round resources even though
the separate runoff resource API confirmed this archive. Both responses are kept.

The local acquired directory is `data/official-bu/ac-runoff-2026-10-30/`; it is
ignored by Git. Its `bundle.json` names exactly four local source specs: `archive`,
`checksum`, `resource_metadata`, `catalog_metadata`. Each requires `path`, `sha256`,
`official_url`, `observed_at`. Top-level fields are `adapter`, `verification_status`
(`official_layout_verified`), these four specs, `election` (the exact supported
2026 runoff contract) and `uf` (`ac` for the real validation). Paths are confined,
all source hashes checked, SHA-512 and resource/archive links verified, archive
members and the dictionary edition pinned. Input plus expanded source bytes are
bounded by 64 MiB and input/generated rows by `max_events`; this is a bounded
importer, not national streamed BU processing. Identical retransmissions retain
all source record witnesses; contradictory counts or repeated metadata fail.
Re-observation runs retain separate snapshot/result/event identities and share
original byte objects without conflicting observation keys.

The inspection output must be a new file. The import example uses the existing
frozen pilot's 108350 inherited electoral rows and an explicit 200000-row bound;
new imported facts remain in a separate immutable derivative. The scientific
eligibility blockers for official BU snapshots reflect status/completeness rather
than incorrectly claiming the schema is unverified. Older snapshots retain their
own quality indicators. Other UF/category/dictionary editions require review.

```sh
rtk proxy env UV_OFFLINE=1 uv run --locked python -m election_audit.official_bu --bundle data/official-bu/ac-runoff-2026-10-30/bundle.json --output data/official-bu/ac-runoff-2026-10-30/validation-recheck.json
rtk proxy env UV_OFFLINE=1 just import-results data/phase9/pilot/warehouse/releases/64eafb496f230a6634f3eade0c49cbacd7845d95a1ac73d7a2bbc76070cc998a --bundle data/official-bu/ac-runoff-2026-10-30/bundle.json --store data/official-bu/ac-runoff-2026-10-30/warehouse --max-events 200000
```

Explicit normalized imports are usable now. A local bundle lists only the files
authorized for import, relative to its directory. A source entry has exactly these
fields; replace the illustrative hash and paths with actual inputs. Do not rename
an official CSV into this format: a separately reviewed mapping is required.

```json
{
  "adapter": "electoral-normalized-v1",
  "verification_status": "normalized_only",
  "sources": [{
    "path": "vote_choice_count.jsonl",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "table": "vote_choice_count",
    "format": "jsonl",
    "encoding": "utf-8",
    "official_url": "fixture://replace-with-original-source-locator",
    "observed_at": "2026-10-29T00:00:00+00:00",
    "schema_evidence": ["replace with reviewed schema version and source evidence"]
  }]
}
```

JSONL uses exact contract field names/types and explicit `field_states` for nulls.
CSV uses semicolon delimiter and exact contract field order followed by
`field_states`; extension CSVs use their column order without `field_states`.
Only strict UTF-8 without BOM/NUL is supported. CSV null is `\N`, booleans are
`true`/`false`, integers are canonical decimal tokens; JSON fields contain JSON.
Duplicate JSON keys, unknown fields/categories/statuses, naive normalized instants,
negative electoral counts, hash mismatches and conflicting immutable keys fail.
Identical retransmissions deduplicate facts while retaining every original locator.

Importable contract tables: election, contest, section, location, snapshot,
section_composition, candidacy, vote_choice, result_version, section_contest_totals,
vote_choice_count, processing_event, harmonized_population and harmonized_member.
First-round and historical data use the same explicit contract; no automatic fetch.
Snapshot has no election column: section/contest/composition establish exact election
and round. IDs and zero-padded TSE codes must be supplied, never inferred from names.

| Extension table | Fields and requirements |
| --- | --- |
| `result_evidence` | `result_version_id`, `snapshot_id`, `official_target`, `complete_choices`, `expected_choice_ids`, `status_evidence`, `supersedes`, `supersession_evidence` |
| `electorate_reference` | `snapshot_id`, `principal_section_id`, `eligible_electors`; one independent electorate value per principal |
| `final_result_reference` | `reference_id`, `snapshot_id`, `contest_id`, `level`, `uf`, `municipality_tse`, `zone`, `expected_principals`, `metrics`, `final` |
| `harmonization_evidence` | `population_id`, `composition_reviewed`, `transfers_reviewed`, `electorate_reviewed`, `evidence` |

Extension types and keys are defined in `electoral_imports.EXTENSIONS`. Status
anchors contain `object_sha256` and nonempty `record_locator`, referring to a preserved
source object. `supersedes` is an array of version IDs; `supersession_evidence` maps
each predecessor to an anchor. Anchors attest a supplied normalized assertion,
not independent verification of official status. Completeness requires the exact
expected contest choice set, including explicit zero rows. A missing row is unknown.
Final references use zone/municipality/uf/national levels, an exact principal list,
and nonempty metrics keyed by totals contract fields; unused geography fields are
empty strings. An explicitly national population includes overseas units (ZZ);
its declared list is never inferred from the available records.

```sh
rtk proxy env UV_OFFLINE=1 just import-results /ssd/audit/releases/PARENT_DIGEST --bundle /ssd/normalized/bundle.json --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just validate /ssd/audit
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT selection_state, count(*) FROM canonical_result GROUP BY selection_state'
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql "SELECT result_version_id, json_extract_string(payload, '$.state') FROM result_reconciliation"
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports
```

`publish_derivative(parent, bundle, store, config=None)` uses the existing resource
configuration, lock, reserve/spill guards, staging/fsync/rename and atomic current
pointer. The pilot bounds total normalized source bytes to 64 MiB and row inputs,
inherited electoral context and combined inputs using `max_events` (default 100000).
Incoming publication rows include generated source/lineage witnesses in its bound.
Electoral rows are resident in Python; this is not streamed national BU processing.
Parent operational events/cycles/lineage are reused through Parquet views, never
copied into Python or rewritten. Limits fail publication; no partial success.

Each `derivative-release-v1` pins a checked relative parent release ID and manifest
hash, adds `audit.duckdb`, `import.json`, exact `originals/SHA256` bytes and new facts
partitioned by year/round/UF (unresolved lineage stays unknown). Contract input
tables append without changing their published schema; derived decisions/marts
replace connection-local views and leave historical versions intact. New versions
must use new immutable IDs. The manifest records columns, keys, storage and logical
counts/digests. Loader, validator, query and report include the whole parent chain.
Relocate the entire relative chain together. Missing/corrupt parents fail. Reports
include chain identities, table/file pins, SQL and source assumptions in findings.json.
Each query/report hashes every physical fact file once; validation also recomputes
logical digests, relational checks and electoral derivations. No external reads or
writes are accepted by the SELECT-only query interface.

Canonical selection considers only totalized official-target assertions, with
explicit matching snapshot/principal/contest supersession evidence. No latest-hash
or latest-clock rule is used; surviving conflicts stay unavailable. Received,
rejected and excluded versions are retained but never totalized. Totals are one row
per version, choices separately; member/session joins never expand totals.
Category sums, attendance, electorate accounting and any present external electorate
reference must agree before section ratios are ready. A missing optional reference
remains explicit. Hierarchy findings distinguish missing/extra coverage from numeric
differences; they never compare a partial sum to a full reference as a numeric error.

Four marts: `section_results`, `unanimous_results`, `result_timing`, `round_comparison`.
Mart grain keys are typed columns and full measures remain in JSON `payload`.
Strict unanimity needs complete reconciled positive all-ballot totals, exactly one
candidate with every vote and zero blank/null/special/unresolved categories.
All-valid-only unanimity is separately named. Missing categories/zero ballots are
unavailable, never false zero observations. Candidate votes are never attributed
to log cycles; physical urn contributions are unavailable without isolating source data.
Timing uses verified processing-event endpoints and explicit clock rules; repeated
events retain all endpoint pairs, including negatives. Closing-to-receipt remains
unavailable without an explicit closing anchor. Result-version instants alone do not
certify clock conversion or supply missing publisher events.
Round comparison requires disjoint whole-principal populations, reviewed composition,
transfers and electorate, complete results, same-year presidential contest pair and
exact snapshot linkage. It aggregates each round before joining, preserves separate
candidate IDs and electorate changes, and makes no individual transfer inference.

## Binary BU content verification (Phase 12)

`binary_bu` decodes official binary BUs with the pinned ASN.1 schema, and
`electoral_verification` (CLI `electoral-verify`) streams BWEB records, preserves
the EA18/EA20 objects and matches section, location, urn, emission and choices
exactly between binary BU and BWEB. It writes resumable per-section checkpoints and
a checksummed `evidence.sqlite`. `content_verified` certifies that linkage only:
signature trust and RDV recount stay `not_verified`, and national completeness is
not implied. The official ASN.1 ZIP returned HTTP 403; the reviewed public schema
mirror is pinned by SHA-256. The real run covers the 2270 AC runoff principals in
`data/phase12/ac-round2/`, with UF counts matching EA20. The
[Phase 12 handoff](handoffs/task-12.md) has the compatibility rule for 374 early
records and the remaining gaps.

Phase 8 input: use the pinned derivative path and the four marts plus operational
parent views, checking availability and denominators before analysis. To add new
families, extend normalized/derived schemas and producer with a new versioned rule;
the loader reads manifest columns/keys rather than changing operational `FACTS`.
Never edit the base DB/schema or existing releases. Official layout verification and the remaining final-reconciliation
limits must propagate. No fitting or fraud labels in this phase.
