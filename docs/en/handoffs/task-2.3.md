# Task 2.3 — Bilingual research and documentation checks

Document-ID: EA-HANDOFF-2.3 · Revision: 2 · Language: en

Objective: preserve complete research/acquisition references in English and
Brazilian Portuguese, and mechanically check pairing, revision, links and examples.

Prerequisites: tasks 2.1/2.2, English research sources and original acquisition
README. Local source contents were authoritative; no linked sources were refetched.

Files/interfaces: `research/analysis-plan.md`, `research/download-sources.md` and
linked `*.pt-BR.md` counterparts; `docs/en/acquisition-reference.md` and its full
Portuguese pair. README onboarding pair now Revision 2 points to them. Paired
schema dictionary, feature readiness, glossary, transformation conventions,
three task handoffs and implementation index. `scripts/check_docs.py` exposes
`check_docs(root)`; `just docs-check` and `just contracts-check` are included in
`just check`. Tests exercise deliberate revision/example/link failures.

Deliverables: full protocol translation preserving design/assumptions, source
caveats, references, formulas and numerical examples; source/mirror notes and
historical acquisition reference translated. The reference was still embedded
in README after Phase 1, so it was extracted intact, with local links adjusted.
Historical acquisition counts remain dated observations, not current coverage.
Code identifiers, formulas and code examples remain identical across languages.
Mermaid IDs/structure remain identical; human labels are translated.
Exclusions: commands in documentation are not executed by docs-check; full command
validation belongs to Phase 9. No website, rendered artifacts or live acquisition.

Acceptance: `rtk proxy env UV_OFFLINE=1 just check` exited 0; 43 tests passed,
including docs checks; 16 document pairs validate metadata/revision/local links/
fenced examples. Manual review compared every protocol section, source caveat,
external-reference set, formula and numerical example. Both languages' synthetic
SQL fences are identical and the example returned `(80, 80)` in DuckDB. No external
link freshness or clean network installation is claimed. Legacy SQLite
ResourceWarning may appear under Python 3.14; all tests pass.

Decisions: English research paths remain stable; Portuguese uses `*.pt-BR.md`.
Parallel guides share Document-ID/Revision, and revisions are bumped together.
The checker discovers docs/research/README pairs by metadata, checks exact code
blocks without executing commands, checks Mermaid structure while allowing translated
labels, and reports missing local paths/anchors.
Translation meaning requires human review; mechanical parity cannot certify it.

Unresolved: upstream specifications/URLs may change; this phase translated supplied
sources rather than browsing again. Parser details, real data readiness, official
signature verification and full executable doc examples remain later work.

Exact next task: **3.1**, implement a read-only authoritative source locator and
immutable snapshot/coverage inventory without disturbing acquisition. Read only
implementation index, task 2.1 handoff, schema dictionary/conventions and the
source/snapshot/coverage/lineage subsets of
`election_audit/resources/contracts/schema.json`; consult acquisition helper
`manifest_path(root)` in `scripts/download_tse_logs.py`. Freeze current URL-to-byte
observations honestly; retain unavailable historical mappings explicitly unknown.

Review correction: Portuguese schema/readiness diagram labels are now translated;
paired guide revisions are 2. Mermaid comparison preserves diagram kind/direction,
entity/node IDs, edges, arrow/cardinality and supported shape declarations. Only
recognized human labels may differ; unsupported diagram syntax stays exact.
Targeted tests allow translated labels and reject changed IDs, arrows, direction,
cardinality or removed relationships; executable/code fences remain exact.
Focused acceptance is recorded below; no implementation index or other phase was
changed for this correction.

Correction acceptance: all commands below exited 0; 4 focused documentation tests
passed, all current document pairs passed, and changed Python files passed lint
and format checks. No full-suite rerun was needed for this isolated correction.

```sh
rtk proxy env UV_OFFLINE=1 just docs-check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_docs.py -v
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked ruff check scripts/check_docs.py tests/test_docs.py
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked ruff format --check scripts/check_docs.py tests/test_docs.py
```
