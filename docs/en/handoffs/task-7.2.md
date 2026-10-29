# Task 7.2 — Canonical results and reconciliation

Document-ID: EA-HANDOFF-7.2 · Revision: 1 · Language: en

Objective: append-only competing result versions with evidence-driven canonical selection and explicit arithmetic/coverage findings. Prerequisites: [7.1](task-7.1.md), electoral contracts, immutable publication seam.

Files/interfaces: `electoral_results.py`, `derivatives.py`, `publication.py`, `release_tools.py`; `publish_derivative(parent, bundle, store)`, `validate_release`, `query_release`. A child pins a relative parent release and manifest digest, stores original normalized inputs, compact additions and partitioned new result facts. Parent databases/facts remain immutable. Loader supports layered manifest schemas, checked parent chains, relocation and SELECT-only restricted queries. Parent lineage remains queryable; imported rows retain original source bytes/hashes/locators.

Selection uses totalized official-target assertions plus original-record status and supersession anchors. Multiple surviving eligible versions remain conflict; received/rejected/excluded do not totalize. Totals occur once per version, choices separately. Composition is terminal, same-election and many-to-one; repeated sessions never multiply results. Reconciliation distinguishes missing choices, category/attendance/electorate mismatch, present external-electorate mismatch, unknown semantics, missing hierarchy coverage and exact numeric differences. National reference populations explicitly include ZZ where supplied. Corrections retain all earlier immutable releases/versions.

Acceptance: ten synthetic selection/reconciliation/mart fixtures and four derivative integration fixtures passed, exit 0. These include conflicts, supersession, duplicate candidate semantics, repeated totals, aggregation, sessions, zero/missing/exception categories, external electorate mismatch, hierarchy ZZ coverage, clocks and reviewed disjoint round populations. Verified official TSE BU adapter remains outstanding, not complete task 7.1 delivery. No real BU validation.

Limits: normalized pilot inputs only, 64 MiB total source bytes; input/inherited/combined electoral rows bounded by max_events. Electoral rows are resident for reconciliation, not a streamed national BU processor. Parent operational event/cycle/lineage facts are not loaded into Python. No signature certification, fitting or fraud labels. Git unavailable; no commit claim.

Next: task 7.3 four electoral marts and bilingual reports; read this handoff, features section_results/unanimous_results/result_timing/round_comparison and the derivative extension module.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_electoral_results.py -v
```
