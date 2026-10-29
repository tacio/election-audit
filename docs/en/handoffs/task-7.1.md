# Task 7.1 — Explicit electoral imports

Document-ID: EA-HANDOFF-7.1 · Revision: 1 · Language: en

Objective: strict versioned normalized imports with original bytes, source hashes, observations and record locators. Files: `electoral_imports.py`, `tests/test_electoral_imports.py`. CSV uses exact contract headers, semicolon delimiter, strict UTF-8, canonical integers, explicit null states; JSONL rejects duplicate keys. Retransmissions retain witnesses; conflicting immutable keys fail. Location, composition, electorate, final hierarchy, first and second rounds use explicit contracts.

Official evidence inspected on 2026-10-29: TSE technical page, EA16 revision 2026-05-22, EA18 revision 2026-05-22, EA20 revision 2026-10-13 and AC runoff BU resource 4753eb99-062b-484a-b569-04c51d039885. These identify official formats/resources but do not verify a BU CSV header/encoding/category mapping. No real BU was supplied/imported. Exact blocker: missing pinned real BU bytes and its bundled dictionary/header plus reviewed normalized mapping. The implemented adapter is normalized_only; no official BU compatibility or signature certification.

Acceptance: four normalized importer fixtures passed, exit 0. No raw corpus read or acquisition change. Git unavailable; no commit claim. Next: task 7.2 canonical selection, append-only evidence and arithmetic/hierarchy reconciliation. Read this handoff and the electoral contracts only.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_electoral_imports.py -v
```

Verified official TSE adapter remains outstanding: this is a partial task 7.1 delivery. Bounded AC ZIP range access additionally failed DNS (curl exit 6, zero bytes); web rejected ZIP/sidecar binary content. See [guide](../electoral-results.md) for exact resource links and pinned discovery evidence.
