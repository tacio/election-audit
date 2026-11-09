# Packet P7: research design and statistics

Scope:

- `research/analysis-plan.md` (the study protocol, still before its freeze)
- `research/completion-plan.md`
- `research/related-work.md`
- `election_audit/features.py`
- `election_audit/research_protocol.py`
- `election_audit/research_models.py`
- `election_audit/research_evaluation.py`
- `election_audit/analysis*.py`
- `election_audit/investigations.py`
- Their tests.
- `docs/en/analysis.md`, `docs/en/feature-readiness.md`, `docs/en/observations.md`.

This packet matters most for bias and unstated assumptions. No results exist yet: the
protocol is to be frozen before the confirmatory data is used. Findings here can still
change the design.

Press on:

- Questions and claims: does the protocol allow conclusions that its tests cannot
  support, in either direction ("no evidence of manipulation" versus "manipulation")?
  Is absence of evidence ever presented as evidence of absence?
- The threat model: which plausible mechanisms of manipulation or error would produce
  no observable signal in these data? Is that blind spot stated?
- Model choice: the round-1 to round-2 swing model, its covariates, and the hidden
  assumptions in them (stable electorate, comparable sections, no differential
  turnout). Ecological fallacy. Spatial dependence.
- Forking paths: which choices are still free and could be tuned after seeing data?
  Are the confirmatory family, the thresholds and the multiple-comparison correction
  fixed?
- Leakage: can development, calibration or holdout data influence each other through
  features, partitions, normalization or the analyst's own exposure?
- Power: is the minimum detectable effect realistic, and is a null result framed by it?
- Negative controls and sensitivity analyses: do they test what they say they test?
- Political neutrality: is any choice asymmetric between candidates or regions?
