# Packet P4: integrity rules

Scope:

- `election_audit/integrity_checks.py` (large: follow the subcommands)
- `election_audit/printed_bu.py`
- `election_audit/zeresima.py`
- `election_audit/gedai.py`
- `election_audit/signature_errors.py`
- `election_audit/integrity_documents.py`
- Their tests.
- `docs/en/integrity-checks.md` and `docs/en/observations.md`.

Press on:

- For each rule (I-, Z-, G-, E- and the rest), can it pass when its input is missing,
  empty or unparseable? Is "unavailable" kept apart from "pass" all the way to the
  summary counts?
- Which section-level exclusions exist (zones not published, contexts filtered, copies
  deduplicated)? Are they counted, and could they hide failures?
- Are the decisions recorded in the docs (O17, O18, O19, T11, T12, T13) reasonable, or
  do they explain away anomalies? Is there an alternative reading of the same evidence?
- Clock comparisons between different machines (urn and GEDAI computer) at a
  one-minute grain: can they flip a verdict?
- Do the summary numbers in the docs follow from the code paths, or could they come from
  an earlier version?
