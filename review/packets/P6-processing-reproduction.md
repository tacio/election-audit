# Packet P6: national processing, releases and reproduction

Scope:

- `election_audit/national*.py`
- `election_audit/publication.py`
- `election_audit/operational_marts.py`
- `election_audit/release_tools.py`
- `election_audit/reproduction.py`
- `election_audit/pilot.py`
- `election_audit/walkthrough.py`
- Their tests.
- `docs/en/national-processing.md`, `docs/en/feature-oriented-processing.md`,
  `docs/en/publication.md`, `docs/en/reproduction.md`, `docs/en/backfill.md`.

Press on:

- Parallel workers and shards: can a failed or retried shard be counted twice or not at
  all, and still give a summary that looks complete?
- Content addressing and version pins: can two different inputs or code versions produce
  the same release ID, or one input produce two IDs?
- Can an independent person reproduce a release from the documented commands alone?
  Which inputs, environment details or manual steps are undocumented?
- Do resource limits (memory, workers) change results, for example through spilling,
  ordering or float summation?
- Is `query` really bounded and read-only?
