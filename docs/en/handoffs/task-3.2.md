# Task 3.2 — Population ledger

Document-ID: EA-HANDOFF-3.2 · Revision: 1 · Language: en

Objective: account for expected members, unique principals and every coverage gap.
Prerequisites: [3.1](task-3.1.md), composition/coverage/lineage contracts.

Files/interfaces: `election_audit/coverage.py`, `build_population(inventory)`;
`source_inventory.py` now accepts all official UFs/ZZ explicitly, retaining AC–RJ
as default. Both inventory functions accept optional `section_keys` tuples of
`(uf, municipality, zone, section)` to bound raw reads. Full UF indexes are retained;
unsampled members remain in the ledger with `outside_asset_selection`.

Deliverables: structural contract rows for election, source objects/observations,
current package advertisements/assets, sections, resolved composition, coverage
and original JSON-pointer lineage. Adapter evidence retains historical run rows,
failures and advertisements, index records and unrepresentable package statuses.
Current auxiliary JSON is metadata, not archive parsing. Package status meanings,
installation, BU availability and parsing stay unknown/not attempted.

Acceptance: command below exited 0, 12 isolated tests passed (5 inventory and 7
population). New cases cover member/principal denominators, aggregate members,
missing authoritative indexes, cycles/conflicts/missing principals, unfinished,
interrupted and finished runs, missing advertisements, corrupt metadata, explicit
section sampling and later UF selections. No live acquisition was accessed.
`rtk proxy env UV_OFFLINE=1 just check` exited 0: lock, formatting, lint,
contracts, paired docs and 55 tests passed. An initial import-order lint failure
was corrected; the existing collector ResourceWarning remains non-fatal.

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_snapshots.py -v
```

Decisions: a verified official phase/pleito/UF index defines expected membership;
missing/invalid/duplicate indexes leave denominator null. Manifest-only sections
remain visible without becoming authoritative population. Composition only accepts
direct known principals with self-maps; no chain collapsing. Member accounting is
disjoint; unique principals use their own denominator. Partial acquired versions
are unresolved. A finished run never proves complete population, and running
does not distinguish active from abandoned. Historical byte attribution stays
unknown. Additional states enter through explicit later snapshots without code
changes; national completeness requires all UFs including ZZ and complete assets.

Unresolved: v1 contract cannot represent null raw package status: exact metadata
and explicit issues survive while that normalized advertisement is omitted.
No national denominator is inferred for a subset. No archive/parser or DuckDB work.

Exact next task: **3.3**, atomically copy/reverify frozen inputs and publish immutable
snapshot IDs, provenance, inspection CLI and paired compact guide. Read only this
handoff, inventory/population APIs and snapshot/membership contracts.
