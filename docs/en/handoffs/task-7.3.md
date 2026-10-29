# Task 7.3 — Electoral marts, reports and Phase 8 extension

Document-ID: EA-HANDOFF-7.3 · Revision: 1 · Language: en

Objective: four electoral marts with precise availability/denominators, read-only derivative query/validation and paired reports. Prerequisites: [7.2](task-7.2.md), [index](../implementation-index.md), [guide](../electoral-results.md), relevant four feature contracts only.

Files/interfaces: `electoral_imports.py`, `electoral_results.py`, `derivatives.py`, `electoral_reports.py`; `publication.inspect_release/open_release`, `release_tools.validate_release/query_release/report_release`; CLI/recipe `import-results PARENT --bundle FILE --store STORE`. Existing build/acquisition/base schema and seven operational FACTS families remain unchanged. Derivative manifests pin checked relative parents and original source/schema discovery evidence; loader is table/column/key driven. Parent Parquet is reused. Query/report verify physical files once per operation. Validation recomputes input grains/FKs, logical digests and derived electoral decisions/marts. Findings bundles include parent identities/files/tables and reproduction SQL.

Marts: section_results retains canonical availability, once-per-result totals, turnout/all-ballot/valid denominators and exact candidate counts. unanimous_results separates strict all-ballot unanimity from all-valid-only; complete reconciled positive ballots and zero exceptional categories are required for strict unanimity. result_timing retains known/missing/negative/repeated endpoint pairs; closing-to-receipt is unavailable without an explicit closing anchor, and client observation never substitutes publication. round_comparison requires reviewed disjoint whole-principal populations/compositions/transfers/electorates, aggregates rounds before joining and retains scoped candidate IDs and electorate differences. No cycle-candidate attribution or unsupported physical-urn attribution.

Acceptance: full just check exited 0, 144 offline tests (18 Phase 7 tests: 4 import, 10 semantics/marts, 4 derivative integration). Synthetic frozen parent→import→child→validate/query/report passed, including append-only conflicts, immutable parent preservation, relative-chain relocation, no operational fact copies, one physical Parquet hash pass per report, SELECT/external-read guards and parent corruption failure. Recipe help passed. Reports default to both languages and preserve calculations. No real corpus read or acquisition change. Git unavailable; no commit/hash claim.

Outstanding task 7.1: verified official TSE BU adapter and real BU validation remain unavailable. Primary official 2026 metadata and EA16/18/20 documentation inspected; ZIP/header/dictionary unavailable through web binary parsing, and bounded AC range curl failed DNS with exit 6 and zero bytes. Exact access evidence is pinned in resources/electoral-source-evidence.json. Normalized schema checks and synthetic arithmetic do not prove official compatibility or signatures. Pilot is bounded to 64 MiB input bytes and max_events input/inherited/combined electoral rows; these electoral inputs reside in Python, not a streamed national processor. Propagate partial national and unknowns. No model fitting or fraud labels.

Next: Phase 8 agent gets only this handoff, index, electoral guide, relevant feature contracts and manifest-driven derivative APIs. Query four marts plus inherited operational views by pinned child path. Add new versioned normalized/derived schemas and producer tables; loader accepts manifest columns/keys without editing operational FACTS or prior releases. Preserve complete relative parent chain when relocating/bundling. Do not reopen full research. No real-corpus pilot until Phase 9.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just import-results --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
```
