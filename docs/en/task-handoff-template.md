# Task handoff template

Document-ID: EA-HANDOFF-TEMPLATE · Revision: 1 · Language: en

Copy into `docs/en/handoffs/task-<ID>.md` and its `docs/pt-BR/` counterpart.
Replace all placeholders. Keep the same document ID/revision and exact commands,
identifiers, formulas and examples in both languages. Update the implementation
index after completing the task; send only this compact handoff to the next agent.

- Document-ID: `EA-HANDOFF-<ID>`; Revision: `<N>`; Language: `en` / `pt-BR`.
- Objective: one concrete task and its completion condition.
- Prerequisites: exact instructions, previous task IDs and relevant contract paths.
- Files/interfaces: changed paths; schemas, APIs, CLI flags and invariants relied on.
- Deliverables: what is now usable; explicit exclusions and preserved behavior.
- Acceptance: exact commands, exit codes, counts/results, artifacts and limits;
  distinguish checks run from checks blocked or not attempted.
- Decisions: choices needed by the next task, with brief reasons.
- Unresolved issues: actual blockers, data/environment gaps, risks and owner/action.
- Exact next task: phase/task ID and the minimal files/contracts the next agent needs.

Preserve acquisition state and original bytes. Never claim full national coverage
from AC–RJ or a passing subset. Never fit a model as part of this pipeline scope.
Record unavailable Git state and network access without inventing commit IDs,
download checks, hashes or acceptance results.
