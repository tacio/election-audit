# Task 9.2 — Bounded frozen real-data pilot

Document-ID: EA-HANDOFF-9.2 · Revision: 1 · Language: en

Prerequisites: [8.3](task-8.3.md), [index](../implementation-index.md), [analysis](../analysis.md), [reproduction](../reproduction.md), [backfill](../backfill.md). Task 7.1 remains partial; no real BU or national validation is claimed.

Objective/files/interfaces: pilot.py selects one index-eligible available principal per AC/AL/DF/ES/PR, using fixed seed diagnostic-geographic-pilot-v1, hashed municipality/zone strata and principal ranks. Query-only SQLite transaction includes committed WAL; metadata pools are bounded at 100000 current log mappings per configured AC–RJ UF, with pool/index hashes, selected-UF rows and exclusions preserved. No raw directory walk, live DB copy/checkpoint, downloader mutation or national acquisition occurred.

Deliverables/acceptance/limits: data/phase9/pilot: five frozen log objects; full five-UF expected denominator 54166, not all AC–RJ. 49235 events; 2328 authorizations, 2327 completions, 177 manual requests, 44403 unknown. All 34 sessions, 2328 cycles and 49235 clocks remain unresolved. 43466 stored unsupported-message diagnostics are capped examples with 2 diagnostic_limit markers, not the unknown-event denominator. Mixed 04/10/2026 and 25/10/2026 dates do not independently identify rounds. Fixed keyword review exports no free text or personal IDs and adds no semantics. Pipeline 162.549 seconds; complete pilot 406.437 seconds; stored files 1084083961 bytes at measurement. Exact inputs, coverage, calculations/SQL, source anchors, safe message review and bilingual reports are retained in pilot-selection.json, pilot-results.json, reproduction.json and reports/operational.

```sh
rtk proxy env UV_OFFLINE=1 just pilot --source /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 --output data/my-pilot
```
