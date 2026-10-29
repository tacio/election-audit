# Task 1.2 — mechanical Ruff adoption

Document-ID: EA-HANDOFF-1.2 · Revision: 1 · Language: en

Objective: consistent formatting and linting without changing acquisition,
inspection or statistical behavior.

Prerequisites/files/interfaces: task 1.1; `pyproject.toml`, legacy `scripts/*.py`
and `tests/*.py`, the package CLI. Legacy function names, signatures, CLI flags,
output schemas and acquisition behavior are preserved.

Deliverables: Ruff target `py314`, line length 100, lint rules `E4`, `E7`, `E9`,
`F`, `I`; mechanical formatting and import ordering. No behavioral changes or new
pipeline functionality. The existing downloader callback has a narrow `E731`
per-file exception to preserve its implementation.

Acceptance commands (all exit 0):

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff check . --fix
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff format .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff format --check .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff check .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline python -m unittest discover -s tests -v
```

Results: Ruff fixed 6 import blocks; formatting changed 7 files; final formatting
and lint passed; all 36 tests passed. Before/after `ast.parse` trees for all 3
original scripts and all 3 original test files were compared after removing only
Import/ImportFrom nodes: equal. Imports were sorted by Ruff; no other AST changes.
Baseline copies are temporary in `/tmp/election-audit-phase1-original`.

Decisions: no broad lint suppression, unsafe fixes or source-interface migration.
Formatting remains a separate task from the new CLI behavior in 1.1.

Unresolved: the existing SQLite ResourceWarning remains visible on Python 3.14;
no test failed. Installation/network limitations are in task 1.1. No raw data was
read or changed and no live request was made.

Exact next task: **1.3**, add usable just recipes, paired onboarding, a compact
implementation index and the reusable handoff template.
