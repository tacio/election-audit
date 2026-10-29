# Task 4.1 — Bounded archive decoding

Document-ID: EA-HANDOFF-4.1 · Revision: 1 · Language: en

Objective: decode frozen JEZ/ZIP members without extracting paths or hiding
duplicate occurrences. Prerequisites: [3.3](task-3.3.md), source/lineage contracts.

Files/interfaces: `election_audit/archive_parsing.py`, `_Parser.archive`,
`ParseConfig`; [paired guide](../archive-parsing.md). Frozen-only production
entry point is `parse_snapshot`; original raw inventory paths are evidence only.

Deliverables: directory preflight before ZIP metadata allocation, streamed
CRC/length validation of all permitted members, bounded disk spooling for nested
archives, full original names/duplicate occurrence/member-index locators, explicit
size/depth/count/format issues. No arbitrary member path extraction. ZIP64,
multi-disk and nonstandard directory layouts remain explicitly unsupported.

Acceptance: commands below exited 0; all 15 parser fixtures passed, including
nested duplicate archives/logs, CRC corruption in selected and other members,
missing logs, lying directory counts and archive/member/expansion/depth guards.
Final repository check passed 83 offline tests, Ruff, lock, contracts and docs.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
```

Decisions: repeated names are legitimate occurrences; root archive names live in
external frozen observation/package associations. CRC failures emit no events
from the damaged member. Limits make artifacts partial, never silently complete.
Unresolved: unsupported archive variants require a versioned adapter; no real
corpus, network or Git operation was attempted. Acquisition remains untouched.

Next: [4.2](task-4.2.md), structural lines/events; read only this handoff, guide
and source-locator/event-identity conventions.
