# Packet P0: open review

Scope: the whole checkout. There is no file list. Spend your effort where you think the
project is most likely to be wrong, or most likely to mislead a reader of its results.

Start with:

- `CLAUDE.md`
- `README.md`
- `docs/en/implementation-index.md`
- `research/analysis-plan.md`
- `research/completion-plan.md`

Press on:

- If you had to defend the opposite conclusion from whatever this project ends up
  reporting, which design choice, check or number would you attack first?
- Which claims in the README or the index are stronger than the code supports?
- Where does "unknown is not zero" quietly fail, so that missing data becomes a pass, a
  zero or an exclusion that nobody counts?
- What would an adversary who had read this repository do to stay undetected?
