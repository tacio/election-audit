# Task 9.3 — Offline reproduction and review bundle

Document-ID: EA-HANDOFF-9.3 · Revision: 1 · Language: en

Prerequisites: [8.3](task-8.3.md), [index](../implementation-index.md), [analysis](../analysis.md), [reproduction](../reproduction.md), [backfill](../backfill.md). Task 7.1 remains partial; no real BU or national validation is claimed.

Objective/files/interfaces: reproduction.py exposes review_bundle/verify_bundle/reproduce and matching CLI/recipes. Export includes frozen originals/inventory, complete relative parent chain, configurations, SQL/reports/nulls/limitations, exact source whitelist and lock/runtime versions. No live manifest, raw root, .local-state, .git, .aws, .codex, .agents or environment is copied. Symlinks are rejected before dereferencing. Complete file hashes detect changes/removals/additions; wrapper checksum is not an authenticated signature. Installed implementation must match bundled code before replay; offline dependencies must already be installed/cached.

Deliverables/acceptance/limits: Four-stage synthetic relocated replay, tampering, source symlink refusal, paired report metadata/calculation fences and harmless command/flag/SQL checks have focused acceptance tests. Exact original manifests retain physical/logical pins. Fresh containers and derivative IDs can differ; reproduction maps only parent_release_id provenance to stage aliases and checks every other payload field and parse identity exactly. Stable artifacts: data/phase9/demo-review, demo-reproduced, pilot-review and pilot-reproduced; reproduction-result.json records actual stage matches/runtime differences. scripts/check_doc_commands.py never executes documented acquisition/backfill/SQL; scripts/check_docs.py retains metadata/revision/link/fence/Mermaid checks. Translation meaning remains human review.

```sh
rtk proxy env UV_OFFLINE=1 just review-bundle data/phase9/demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
rtk proxy env UV_OFFLINE=1 just docs-command-check
```
