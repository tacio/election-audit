# Phase 18 — Portable marimo exploration

Document-ID: EA-HANDOFF-18 · Revision: 1 · Language: en

Four packaged notebooks cover coverage/integrity, electoral returns, operations and model/investigation evidence. `dashboard_main` launches the local gallery; `dashboard_export_main` exports immutable-release marts to a new portable directory. Both are in `election_audit.dashboard`.

`AuditDataset.open(uri)` accepts local and HTTPS manifests with checksummed relative Parquet references; bounded pages, filters, CSV and provenance downloads retain zero versus unknown. Remote files use a bounded verified cache; loopback HTTP is explicitly test-only. `publish_dataset` accepts already access-filtered row streams in 2048-row batches. Protected releases export only development features and redacted coverage metadata. Mere test inspection does not authorize outcome export: the future producer must supply `research_evaluation.final_evaluation_complete(db, document)` validating final evaluation and its immutable references.

Acceptance: six dashboard tests pass, Ruff checks/format pass, and marimo checks all four reactive graphs. The real AC release exported to `data/dashboard-ac-2026-10-30/dataset.json`; 54166 coverage rows, 2270 reconciliation rows and current unresolved result marts retain their original populations. The coverage notebook executed successfully to HTML. This dataset is explicitly exploratory and unpartitioned, not final-result certification.

Limits: source marts lack many eligible electoral/operational measures, model runs and verified geographic coordinates. Pages show unavailable states; maps require supplied verified latitude/longitude rather than invented locations. Charts describe the selected bounded page, not a national distribution. Full browser interaction QA remains for integration. No notebook action performs acquisition, reconstruction or fitting. No public hosting occurred.

Dependencies are optional `dashboard`: marimo 0.25.0 and Altair 6.3.0. Root owns CLI/recipe integration and dependency pins. Phase 14 should populate the portable schema; Phases 15–16 must implement validated final-evaluation evidence. Existing releases and raw inputs were not modified.
