# Electoral imports and derivative releases

Document-ID: EA-ELECTORAL-RESULTS · Revision: 1 · Language: en

[Português](../pt-BR/electoral-results.md) · [Index](implementation-index.md) · [Publication](publication.md)

Available AC–RJ 2026 presidential runoff logs remain partial national coverage.
The usable importer is **electoral-normalized-v1**, not a verified official TSE BU
decoder. Task 7.1's verified official adapter remains outstanding. No real BU was
provided/imported; synthetic arithmetic checks do not constitute real electoral
validation or signature certification. Acquisition and base releases are unchanged.

Primary evidence inspected on 2026-10-29: [official technical index](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados),
[AC runoff BU metadata](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna/resource/4753eb99-062b-484a-b569-04c51d039885),
[EA16](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea16-arquivo-de-configuracao-de-secoes-eleitorais)
(2026-05-22), [EA18](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
(2026-05-22), [EA20](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado)
(2026-10-13). These JSON specifications are distinct from the BU CSV dictionary.
The web tool rejected the AC BU ZIP and sidecar as unsupported binary content.
A bounded CLI range request failed DNS, exit 6, with zero bytes downloaded.
Exact blocker: pinned BU bytes and bundled dictionary/header/encoding/category
mapping could not be obtained. Discovery evidence and the normalized schema digest
are pinned in each derivative's identity/import provenance; discovery does not
certify a source schema. No national download is attempted.

```sh
rtk proxy curl --range 0-65535 --max-time 20 --max-filesize 1048576 --fail --show-error --silent --dump-header /tmp/election-audit-bu-range.headers --output /tmp/election-audit-bu-range.bin https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AC_261020260742.zip
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
its declared list is not inferred from this partial corpus.

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

Phase 8 input: use the pinned derivative path and the four marts plus operational
parent views, checking availability and denominators before analysis. To add new
families, extend normalized/derived schemas and producer with a new versioned rule;
the loader reads manifest columns/keys rather than changing operational `FACTS`.
Never edit the base DB/schema or existing releases. Outstanding official BU adapter
and real-validation status must propagate. No fitting or fraud labels in this phase.
