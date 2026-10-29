# Task 1.1 — installable foundation

Document-ID: EA-HANDOFF-1.1 · Revision: 1 · Language: en

Objective: installable `election_audit`, reproducible uv dependency resolution,
a declared runtime, and a CLI that preserves the original scripts.

Prerequisites/files/interfaces: Python 3.14, uv; `scripts/download_tse_logs.py`,
`scripts/inspect_tse_logs.py`, `scripts/audit_statistics.py`; their command flags,
imports, data layout and manifest marker remain authoritative.

Deliverables: `pyproject.toml`, `uv.lock`, `.python-version`, `election_audit/`,
`scripts/__init__.py`, `tests/test_cli.py`, ignore rules. Runtime dependencies:
DuckDB 1.5.3 and PyArrow 24.0.0; development Ruff 0.17.0. Exclusions: parsing,
snapshots, schema migration, data acquisition, research translation and model fitting.

Acceptance commands (all exit 0):

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv lock --offline --check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv sync --locked --offline
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -v
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked election-audit doctor
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked election-audit resume --help
```

Results: lock check and locked offline setup passed; 36 tests passed (34 original
plus 2 CLI adapter tests); doctor reported Python 3.14.5, SQLite 3.50.4 and the
versions above; resume help retained the original downloader options. A legacy
SQLite ResourceWarning appeared under Python 3.14; tests still passed.

Decisions: Python 3.14 is the project runtime, matching available genuine local
Linux dependency distributions; original standalone scripts still work on their
previous Python versions. Pin dependencies and the resolver cutoff
`2026-10-29T00:00:00Z`; pin Hatchling 1.32.4 and constrain its build dependency
Pluggy 1.6.0. CLI delegates to the existing `main()` functions; `resume` inserts
`--missing-only` and restores process arguments even on errors.

Environment evidence: PyPI DNS failed. Genuine DuckDB/PyArrow lock records came
from the read-only neighboring `oss-viz/uv.lock`, Ruff records from uv's cached
resolver, then `uv lock --offline` normalized and validated this project's lock.
The ignored `.venv` was seeded with the matching installed Linux DuckDB/PyArrow
files from `oss-viz/.venv`; build tools and Ruff came from a copied uv cache in
`/tmp/election-audit-uv-cache`. No hashes were invented. Locked setup was tested
with those existing artifacts; a clean download/install was not tested.

Unresolved: clean installation requires accessible PyPI or the matching cached
wheels; no live acquisition or signature verification was attempted. No Git commit
is available because the mounted `.git` is empty. Acquisition data was untouched.

Exact next task: **1.2**, configure Ruff and apply only mechanical formatting/import
cleanup to the legacy sources, then compare their AST and rerun all tests.
