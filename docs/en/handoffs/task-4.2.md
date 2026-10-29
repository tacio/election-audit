# Task 4.2 — Structural events and safe diagnostics

Document-ID: EA-HANDOFF-4.2 · Revision: 1 · Language: en

Objective: retain ordered operational message evidence without inventing sessions
or persisting sensitive message/token fields. Prerequisites: [4.1](task-4.1.md),
source-locator/event-identity conventions and `parsing_issue` contract.

Files/interfaces: `_Parser.lines` in `election_audit/archive_parsing.py`,
`events.jsonl`, `issues.jsonl`; [guide](../archive-parsing.md).

Deliverables: Latin-1 six-column decoder, validated raw naive device timestamps,
device/application identity, source sequence/line locators, exact physical-line
SHA-256 including original line endings, three exact VOTA message classes and
explicit unknown classes. Malformed/oversized records produce bounded diagnostics
without raw samples. Original bytes remain separately frozen; no voter/mesario
IDs, raw messages or sensitive tokens are selected. Repeated identical messages
remain distinct events, and all contexts stay unresolved.

Acceptance: commands below exited 0; all 15 parser fixtures and 83 total offline
tests passed. Fixtures verify malformed/oversized lines, original line numbers,
diagnostic truncation, equal-second repeated messages, mixed dates/setup apps,
redaction and distinct exact-line fingerprints for unknown texts/line endings.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
```

Decisions: `completion_message` is evidence, not votes; no filename-derived round
or timezone conversion. Unknown byte offsets remain null. Unresolved: only three
VOTA classes are decoded; further semantics require versioned adapter extensions,
never kind/timestamp-only deduplication. No live corpus or acquisition changes.

Next: [4.3](task-4.3.md), reusable content artifacts and frozen associations.
