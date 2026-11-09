# Packet P1: acquisition, snapshots and coverage

Scope:

- `scripts/download_tse_logs.py`
- `scripts/inspect_tse_logs.py`
- `election_audit/source_inventory.py`
- `election_audit/coverage.py`
- `election_audit/snapshots.py`
- `election_audit/source_staging.py`
- `election_audit/bulk_acquisition.py`
- `election_audit/sevenzip.py`
- Their tests.
- `docs/en/acquisition-reference.md`, `docs/en/snapshots.md`,
  `research/download-sources.md`.

Press on:

- Can a truncated, partial or duplicate download be counted as complete, or a missing
  object vanish from a denominator?
- Is the SQLite manifest, which runs in WAL mode, read consistently while a downloader
  may still be writing? Can a snapshot mix two states?
- Do the hashes cover the bytes that later stages read? Can a stage read something that
  no frozen hash pins?
- Is the expected-coverage denominator independent of what was downloaded?
- Is the 7z/ZIP/JEZ decoding bounded against hostile archives (size, nesting, path
  traversal)?
