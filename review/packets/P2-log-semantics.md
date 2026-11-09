# Packet P2: parsing and log semantics

Scope:

- `election_audit/archive_parsing.py`
- `election_audit/reconstruction.py`
- `election_audit/semantic_pass.py`
- `election_audit/operational_review.py`
- `election_audit/sa_logs.py`
- `election_audit/round1_prefix.py`
- `election_audit/resources/real-log-rules.json` and `real-log-rules-2022.json`.
- Their tests.
- `docs/en/archive-parsing.md`, `docs/en/reconstruction.md`,
  `docs/en/semantic-pass.md`.

Press on:

- The vote-cycle state machine: can a cycle be counted twice, or lost, across a restart,
  a urn replacement, a memory copy of the log, a midnight rollover or a clock jump?
- Sessions and segments: are official, training and test blocks told apart by evidence,
  or by assumptions about order and time?
- Deduplication of memory copies: can it merge two real events, or keep two copies of
  one?
- Encodings, truncated lines and unknown templates: does the parser count, flag or drop
  them?
- Are the rule files (`real-log-rules*.json`) justified by evidence, and could a log
  format change silently turn a rule off?
