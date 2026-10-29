# Task 2.1 — Dimensional contracts

Document-ID: EA-HANDOFF-2.1 · Revision: 1 · Language: en

Objective: define grains, keys, identities, relationships, time semantics and
versioning before transformations, so joins cannot multiply votes.

Prerequisites: task 1.3, repository/RTK instructions, implementation index and task
handoff template. Acquisition remains authoritative and untouched.

Files/interfaces: `election_audit/resources/contracts/schema.json`,
`election_audit/contracts.py`, `tests/test_contracts.py`; paired
`schema-dictionary.md`, `transformation-conventions.md` and `glossary.md` under
`docs/en/` and `docs/pt-BR/`. `load_contract("schema")` loads packaged resources;
`validate_contracts()` checks metadata; `validate_rows(table_name, rows)` checks
single-batch shape/types/keys/null reasons. Explicit `root` allows another checkout.

Deliverables: 30 table contracts covering immutable bytes/observations/packages/
snapshots, election-scoped dimensions, composition, harmonized populations,
separate device/configuration identities, result versions, canonical decisions,
totals separate from choice counts, lifecycle events, anonymous reconstruction,
coverage, issues and original-record lineage. Original locators support nested
archive paths/member occurrence and line/byte/record ranges. Nullable fields
require `field_states`; original missing meanings survive. Exclusions: no manifest
migration, snapshot creation, parser, ETL, signature verifier or model fitting.

Acceptance: the commands below exited 0. The full check passed 43 tests plus lock,
Ruff and registry/docs checks. The documented synthetic DuckDB join was executed
separately and returned `(80, 80)`. A wheel built offline and contract validation
from its ZIP path under `/tmp` passed, proving packaged JSON availability.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv build --wheel --out-dir /tmp/election-audit-phase2-wheel
```

Decisions: namespace/digest IDs retain natural keys and rule versions. Objects,
packages, physical sessions, sections and result versions have distinct identities.
Package lifecycle observations do not require imported BUs. Aggregate choices to
result grain before attaching totals; never expand totals through members,
sessions, witnesses or lineage. Harmonize each round to disjoint common groups
before joining. Unproven splits/transfers remain incomparable.

Unresolved: structural validation does not execute foreign-row, context,
nonnegative-count, category-accounting, composition or canonical-selection rules;
future publication must check them as specified in the conventions. Source-specific
codes/category semantics need validated adapters. No live acquisition or Git
operation was attempted; the inherited mount has no usable Git history. Broad
`data/` ignore initially omitted JSON in a wheel; resources now live under
`election_audit/resources/contracts/`, and the rebuilt wheel probe passed.

Exact next task: **2.2**, feature/readiness contracts; consult only schema dictionary,
research targets and feature registry. Completed in the same Phase 2 agent; its
handoff is [2.2](task-2.2.md).
