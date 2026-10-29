# Task 6.2 — Honest operational marts

Document-ID: EA-HANDOFF-6.2 · Revision: 1 · Language: en

Objective: publish operational coverage, session summaries, processing-event availability and late-voting diagnostics without electoral inputs.
Prerequisites: [6.1](task-6.1.md), [index](../implementation-index.md), operational feature contracts.

Interfaces: `operational_marts.coverage_rows`, `processing_availability_rows`, `late_session_row`, `materialize_marts`; publication materializes compact marts before atomic release. Rows retain exact calculation inputs in `payload` JSON and explicit unique grain columns. Session summaries preserve Phase 5 denominators/readiness. Full expected ledger and source/context dimensions are now retained once in new parse contexts; older contexts honestly expose unavailable fields.

Acceptance: five focused operational fixtures passed: strict 17:00 boundary, equal Brasilia instants from different offsets, unknown clocks/context, missing closing evidence, completed-after versus remaining-open, overseas, bounded sensitivity, lifecycle absence/repeats and retained expected members. Publication has six fixtures including actual independent-key parser concurrency and identical-key parse-once behavior. Full check: exit 0, 117 offline tests. Acquisition/raw and real corpus untouched.

Decisions: domestic completion means strictly after 17:00 America/Sao_Paulo on target date; overseas convention unavailable. Remaining open needs evidenced continuous opening/closing interval and is separate from observed late completions. Unknowns never become zero rates. Bounded clock intervals retain lower/upper counts; unsupported absolute clocks stay unclassifiable. Cross-shard eligible totals remain null. Receipt, processing, generation, publication and client observation remain separate; HTTP/download timestamps never fill publisher fields. Expected package population comes from frozen advertisements; complete result population remains unknown. No join expands cycles through member/package/lineage witnesses.

Concurrency refinement: replace global parser cache lock with per-content/config-key locks; independent objects parse concurrently, same-key callers share one verified immutable result. This makes configured parser workers effective while preserving atomic parsing.

Unresolved: authoritative real lifecycle feed, clock rules and overseas convention unavailable; no candidate attribution, BU import or real pilot. Exact next: **6.3**, build/validate/query/report APIs, CLI/recipes and bilingual reports, then Phase 7 extension only.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_operational_marts.py -v
rtk proxy env UV_OFFLINE=1 just check
```
