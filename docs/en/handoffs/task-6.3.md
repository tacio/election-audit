# Task 6.3 — Build, validation, read-only query and paired initial reports

Document-ID: EA-HANDOFF-6.3 · Revision: 1 · Language: en

Objective: make the frozen operational release pipeline reviewable through APIs/CLI/recipes and English/Portuguese reports.
Prerequisites: [6.2](task-6.2.md), [index](../implementation-index.md), [publication guide](../publication.md), relevant operational contracts only.

Files/interfaces: `publication.py`, `operational_marts.py`, `release_tools.py`; CLI/recipes `build`, `validate`, `query`, `report`. `build --input-kind snapshot|parse|reconstruction` reaches atomic releases from frozen inputs. New parse contexts retain full coverage/source dimensions and metadata lineage once. `open_release` attaches temporary fact views, `query_release` permits exactly one parsed SELECT with restricted external access and bounded results; `--sql-file` supports reproducible longer queries. Internal verified-manifest reuse avoids repeated corpus hashing within an operation.

Deliverables: physical hashes, manifest/locator checks, logical SHA-256 multiset digests plus exact counts, grain/FK/cardinality/event-cycle-session accounting/lineage/coverage/resource validation. Reports default to BOTH languages, with translated labels/explanations and identical calculations/SQL/formulas/examples; `--language en|pt-BR|both`. Shared findings identify inputs, calculations, assumptions, exclusions, uncertainty, reproduction commands and challenging evidence. Report outputs are separate from immutable releases. Static operational fact loader and explicit parent/child extension route for Phase 7 are documented; no electoral logic added.

Acceptance: final command below exited 0: lock, Ruff, contracts, paired documentation and **126 offline tests**. Phase 6 contributes 20 fixtures: six publication/concurrency/resource failures, five operational clock/lifecycle/coverage tests and nine release interface/integrity/report tests. Includes full synthetic snapshot→release after source/parse/reconstruction deletion, bounded disjoint groups, partitioned evidence/lineage, SELECT write/COPY/external-read rejection, report manifest reuse and both languages. No real corpus/network/Git operation or acquisition change; Git state unavailable, no commit/hash claim.

Decisions: `operational-release-v1`, `operational-marts-v1`. Full integrity verification reads all fact bytes once per query/report operation; validation also recomputes logical content. Report calculations share a verified manifest/connection. Unknown lifecycle times, overseas convention, cross-shard copied histories and unavailable electoral validation remain explicit; no confident global eligible cycle total, candidate attribution, model fitting or fraud labels.

Unresolved: no authoritative real-message adapter/pilot or publisher lifecycle feed; old parses can lack metadata lineage/source dimensions and defer relevant checks. Full frozen metadata remains resident once. Existing `FACTS` is limited to seven operational families. Phase 7 must implement a derivative manifest loader/API that pins and verifies a relative parent release, adds a separate compact database/new partitioned facts and reuses parent Parquet without copying or editing the parent. See guide for exact seam.

Next: **Phase 7**, electoral imports as a new immutable derivative. Read this handoff, index, publication guide, relevant electoral contracts, existing frozen provenance APIs only. Preserve base releases, original inputs and partial national scope. No real corpus pilot until Phase 9.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just build --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
```
