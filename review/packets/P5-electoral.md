# Packet P5: electoral results and joins

Scope:

- `election_audit/electoral_imports.py`
- `election_audit/electoral_results.py`
- `election_audit/electoral_references.py`
- `election_audit/official_bu.py`
- `election_audit/binary_bu.py`
- `election_audit/derivatives.py`
- `election_audit/results_hierarchy.py`
- `election_audit/section_table.py`
- `election_audit/elections.py`
- Their tests.
- `docs/en/electoral-results.md`, `docs/en/section-table.md`,
  `docs/en/transformation-conventions.md`, `docs/en/schema-dictionary.md`.

Press on:

- Join multiplicity: can any join multiply or drop rows (aggregated sections, urn
  replacements, sections present in one round only, BWEB versus binary BU)?
- Canonical selection of one result per `(snapshot_id, principal_section_id,
  contest_id)`: is the rule deterministic, and is it right when sources disagree?
- Are nulls, blank and null votes, and abstentions kept distinct from zero?
- Do the totals reconcile with official totals at every level, and is a reconciliation
  failure reported or absorbed?
- Round 1 versus round 2 identity of a section: what is assumed, and what changes
  (merges, transfers, new sections)?
