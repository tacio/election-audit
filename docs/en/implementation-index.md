# Implementation index

Document-ID: EA-IMPLEMENTATION-INDEX · Revision: 11 · Language: en

Read repository instructions (including `/home/tacio/.codex/RTK.md`), this index,
the assigned task handoff and only relevant contracts. Use a separate agent per
phase, with minimal context. Do not reopen all research or carry every prior phase
into the next agent. Record a paired handoff after every numbered task using the
[template](task-handoff-template.md). [Português](../pt-BR/implementation-index.md).

Scope: available 2026 presidential runoff logs, AC–RJ, partial national coverage.
No fitting or fraud labeling. Preserve raw bytes, running acquisition and manifest.
Other rounds/history require explicit imports; successful subsets are not national.

| Task | Complete deliverables | Handoff |
| --- | --- | --- |
| 1.1 | Python 3.14, uv lock, package/CLI, DuckDB/PyArrow | [1.1](handoffs/task-1.1.md) |
| 1.2 | Ruff, mechanical legacy formatting | [1.2](handoffs/task-1.2.md) |
| 1.3 | just recipes, paired onboarding, index/template | [1.3](handoffs/task-1.3.md) |
| 2.1 | 30 dimensional contracts, dictionary, lineage, safe joins | [2.1](handoffs/task-2.1.md) |
| 2.2 | 21 feature/readiness contracts, denominators and blockers | [2.2](handoffs/task-2.2.md) |
| 2.3 | Full paired research/acquisition translations, glossary/diagrams, docs checks | [2.3](handoffs/task-2.3.md) |
| 3.1 | Read-only selected source inventory, WAL isolation, honest historical unknowns | [3.1](handoffs/task-3.1.md) |
| 3.2 | Frozen expected indexes, member/principal coverage and bounded asset selection | [3.2](handoffs/task-3.2.md) |
| 3.3 | Atomic immutable copies, snapshot/inspection CLI, frozen provenance and guide | [3.3](handoffs/task-3.3.md) |
| 4.1 | Bounded nested JEZ/ZIP decoding, CRC and duplicate member locators | [4.1](handoffs/task-4.1.md) |
| 4.2 | Ordered structural events, naive clocks, safe bounded diagnostics | [4.2](handoffs/task-4.2.md) |
| 4.3 | Verified immutable parse cache, all frozen associations, CLI/API and guide | [4.3](handoffs/task-4.3.md) |
| 5.1 | Candidate/official contexts, separate identities, exact copied-block lineage | [5.1](handoffs/task-5.1.md) |
| 5.2 | Anonymous authorization/completion/suspension/cancellation state machine | [5.2](handoffs/task-5.2.md) |
| 5.3 | Evidenced section/overseas clock rules, UTC/corrections and continuity | [5.3](handoffs/task-5.3.md) |
| 5.4 | Operational denominators, immutable bounded shards/shared context, CLI/API | [5.4](handoffs/task-5.4.md) |
| 6.1 | Immutable bounded DuckDB/Parquet releases, resource limits, atomic current | [6.1](handoffs/task-6.1.md) |
| 6.2 | Coverage/session/lifecycle availability/late-voting marts, clock uncertainty | [6.2](handoffs/task-6.2.md) |
| 6.3 | Build/validate/read-only query/bilingual reports; Phase 7 extension seam | [6.3](handoffs/task-6.3.md) |
| 7.1 (partial) | Strict normalized importer/provenance; verified official TSE BU adapter outstanding (source access blocked) | [7.1](handoffs/task-7.1.md) |
| 7.2 | Immutable parent-pinned derivatives, evidenced canonical selection, arithmetic/hierarchy reconciliation | [7.2](handoffs/task-7.2.md) |
| 7.3 | Four electoral marts, bounded SELECT, validation and paired reports; real BU validation unavailable | [7.3](handoffs/task-7.3.md) |
| 8.1 | Versioned 21-contract feature registry, streamed descriptive outputs and explicit scientific blockers | [8.1](handoffs/task-8.1.md) |
| 8.2 | Persisted seeded reviewed stable-location populations, geographic strata and municipal stress holdouts | [8.2](handoffs/task-8.2.md) |
| 8.3 | Immutable protocol/exploration/null/investigation/scenario ledgers, test access history, CLI and paired reports | [8.3](handoffs/task-8.3.md) |
| 9.1 | Production synthetic offline walkthrough, four immutable stages and paired marked reports | [9.1](handoffs/task-9.1.md) |
| 9.2 | Frozen five-region real diagnostic pilot, exact pools/ranks/denominators and unresolved messages/clocks | [9.2](handoffs/task-9.2.md) |
| 9.3 | Relocatable whitelisted review bundles, frozen replay/logical digests, safe command/SQL checks | [9.3](handoffs/task-9.3.md) |
| 9.4 | Verified bounded restart, honest backfill/storage guide and updated bilingual onboarding | [9.4](handoffs/task-9.4.md) |

Acceptance: 166 offline tests passed (160 prior + 6 Phase 9); lock, Ruff,
contracts, paired docs and harmless command/SQL checks pass. Actual frozen pilot:
five principals AC/AL/DF/ES/PR; full five-UF expected denominator 54166;
49235 events, 44403 unknown; all 34 sessions, 2328 cycles and clocks unresolved.
Pipeline 162.549 seconds, full pilot 406.437 seconds; measured run bytes 1084083961.
`data/phase9/` retains demo, pilot, review bundles, fresh reproduction results,
paired reports and verification evidence. No full backfill, model fitting,
candidate attribution, national margin or fraud label. Task 7.1 remains partial:
verified official TSE BU adapter and real BU validation unavailable. Git unavailable.

| Interface | Relevant source / contract |
| --- | --- |
| Runtime | `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked` |
| CLI | `election_audit/cli.py`; legacy `download resume inspect doctor`; `snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill docs-command-check` |
| Acquisition | `scripts/download_tse_logs.py`; `manifest_path(root)` follows `manifest-location.json`; original storage/lock/layout preserved |
| Snapshot/source/coverage | `election_audit/resources/contracts/schema.json`; `source_object`, `source_observation`, `source_package`, `package_observation`, `package_asset`, `snapshot`, `snapshot_observation`, `coverage_ledger`, `record_lineage` |
| Frozen input APIs | `source_inventory.inventory_sources`, `coverage.build_population`, `snapshots.create_snapshot/publish_snapshot/inspect_snapshot/snapshot_tables`; [guide](snapshots.md) |
| Structural parse APIs | `archive_parsing.parse_snapshot/inspect_parse/iter_event_witnesses/iter_lineage/iter_parsing_issues`; [archive guide](archive-parsing.md); version `jez-structural-v1`; exact `source_line_sha256`, unresolved contexts, content cache separate from all publisher witnesses |
| Operational reconstruction | `reconstruction.reconstruct_parse/inspect_reconstruction/iter_reconstruction_rows/load_reconstruction_context`; [guide](reconstruction.md); `operational-v1`; `FrozenParseReader` for bounded groups, shared full population context, explicit uncertainty |
| Operational releases | `publication`, `operational_marts`, `release_tools`; [publication guide](publication.md); immutable DuckDB/Parquet, SELECT-only queries and paired reports |
| Electoral derivatives | `electoral_imports`, `electoral_results`, `derivatives`, `electoral_reports`; [guide](electoral-results.md); normalized-only, partial national; official BU adapter outstanding |
| Analysis foundation | `analysis`, `analysis_partitions`, `analysis_ledgers`, `analysis_reports`; [guide](analysis.md); `analyze`, `validate`, `query`, `report` |
| Structural validator | `election_audit/contracts.py`; `load_contract`, `validate_contracts`, `validate_rows`; packaged resources; semantic/relational checks remain publication work |
| Grains/joins/time | [Dictionary](schema-dictionary.md), [conventions](transformation-conventions.md); separate totals/choices, unique canonical versions, no member/session/witness multiplication |
| Features | `election_audit/resources/contracts/features.json`; [readiness guide](feature-readiness.md); unknown is not zero, AC–RJ partial, after17 Brasilia, strict unanimity |
| Research | `research/analysis-plan.md`, `research/download-sources.md`, linked full `.pt-BR.md` counterparts; [acquisition reference](acquisition-reference.md) |
| Docs check | `scripts/check_docs.py`; `check_docs(root)`; metadata/revisions/local links/fenced parity; safe separate help/command/SQL syntax checks |
| Recipes | `justfile`; `setup doctor fmt lint test contracts-check docs-check check download resume inspect snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill docs-command-check` |

Next: task 7.1 official adapter/real validation, after obtaining accessible
pinned official documentation and original BU data. Use [9.4](handoffs/task-9.4.md),
[reproduction](reproduction.md), [backfill](backfill.md) and
[electoral guide](electoral-results.md). Review actual message/session/clock
evidence before claiming operational eligibility. Preserve unknowns and partial
national coverage; no fitting is authorized.

Pairs under `docs/en/` and `docs/pt-BR/` share Document-ID/Revision; research keeps
English paths plus `.pt-BR.md` counterparts. Bump both revisions together. Code,
commands, SQL, formulas and numerical examples stay identical. Human translation
review complements mechanical parity; Phase 9 extends executable doc validation.
