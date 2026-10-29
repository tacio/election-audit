# Task 1.3 — onboarding and local command surface

Document-ID: EA-HANDOFF-1.3 · Revision: 1 · Language: en

Objective: usable just recipes and paired onboarding plus compact documentation
that lets the next phase start with minimal context.

Prerequisites/files/interfaces: tasks 1.1/1.2; the CLI adapter and unchanged script
contracts; uv, just, rtk and Python 3.14. Preserve acquisition state and English
research paths.

Deliverables: `justfile`; `README.md` / `README.pt-BR.md`; paired
`implementation-index.md`, `task-handoff-template.md` and per-task handoffs under
`docs/en/` / `docs/pt-BR/`. The original README acquisition detail is retained below
the new English onboarding; its dated counts are labeled historical. The paired
onboarding has matching commands/examples. Exclusions: long research translation,
future pipeline recipes, acquisition runs, parsing and model fitting.

Acceptance commands (all exit 0):

```sh
rtk proxy env UV_OFFLINE=1 just setup
rtk proxy env UV_OFFLINE=1 just doctor
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just download --help
rtk proxy env UV_OFFLINE=1 just resume --help
rtk proxy env UV_OFFLINE=1 just inspect --help
rtk proxy env UV_OFFLINE=1 just fmt
rtk proxy just --list
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv build --offline --wheel --out-dir /tmp/election-audit-phase1-dist
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv venv --python 3.14 /tmp/election-audit-phase1-wheel-check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv pip install --offline --no-deps --python /tmp/election-audit-phase1-wheel-check/bin/python /tmp/election-audit-phase1-dist/election_audit-0.1.0-py3-none-any.whl
```

Results: locked setup and doctor passed; check validated the lock, formatting,
lint and all 36 tests. Existing SQLite ResourceWarning remained nonfatal. All
three help wrappers retained original flags without opening acquisition data;
format was idempotent. Recipe listing contains only implemented commands. Wheel
build and isolated no-dependency install succeeded; importing `election_audit`,
`scripts.download_tse_logs` and `scripts.inspect_tse_logs` from `/tmp` resolved to
`/tmp/election-audit-phase1-wheel-check/lib/python3.14/site-packages/`, confirming
legacy scripts are included in the distribution.

Documentation QA: an inline stdlib Python check compared each pair's
`Document-ID` / `Revision` and fenced command blocks (README's new onboarding
only), and resolved all relative Markdown links. All 6 pairs passed after this
handoff was created. Commands, identifiers and examples match across new pairs.

Decisions: `just` forwards variadic options through shell positional arguments
(`"$@"`), preserving quoting. `resume` adds `--missing-only`; `check` never acquires
election data. Recipes use `uv --locked`, default the writable cache to
`/tmp/election-audit-uv-cache`, and accept inherited `UV_OFFLINE=1`. Parallel docs
share IDs/revisions; changes increment both revisions. No placeholders for future
commands. The implementation index links current contracts and individual handoffs.

Unresolved: fresh network installation remains untested because PyPI DNS is
unavailable; existing local distributions were used as documented in task 1.1.
Long English research and retained acquisition reference await Phase 2 translation.
The `.git` mount remains empty; no commit is claimed. No data was downloaded,
inspected or modified in this phase.

Exact next task: **Phase 2, first assigned documentation/contracts task**. Read
repository instructions, `docs/en/implementation-index.md`, the assigned task and
only the relevant existing research/interfaces. Retain the parallel-document
convention and create a compact paired handoff after each task.
