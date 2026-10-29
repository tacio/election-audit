# Statistical audit of the 2026 presidential runoff

Document-ID: EA-ANALYSIS-PLAN · Revision: 1 · Language: en

[Português](analysis-plan.pt-BR.md)

Working protocol, 29 October 2026. This is a proposed analysis design, not a fraud
finding, a fitted national model, or a preregistration made before seeing any data.
Initial inspection has covered the acquisition manifest and a few AC/AL/AM logs.
Freeze the protocol and data snapshot before inspecting candidate-specific anomaly
rankings; record subsequent changes as exploratory analyses.

## Recommendation

Use a conditional, non-parametric baseline for turnout and candidate vote share,
with a separate operational model for log behavior. Start with matched empirical
comparisons; use quantile regression forests as the principal flexible predictor.
Calibrate scores on held-out voting locations, investigate spatial clusters, and
apply multiplicity controls only where their assumptions are defensible. Treat
findings as relative anomalies requiring investigation. A reference population
assembled from official returns is not independently certified fraud-free.

There are three distinct questions:

1. **Integrity:** do source versions, counts and independent records reconcile?
2. **Unusualness:** which sections or clusters differ from comparable peers?
3. **Outcome:** under an explicit mechanism and affected population, how much
   could the national margin change?

A model residual answers the second question. It does not, by itself, identify
fraudulent votes or a causal effect on the result. Fraud can also look ordinary or
affect a whole reference population, so failure to find outliers cannot certify
the absence of fraud.

## Repository review

Reviewed browser-accessible files on the named branches, not every file or a
security audit of either project. Pin commit hashes before adopting code.

| Source | Useful practices | Limits for this project |
| --- | --- | --- |
| [Turicas / eleicoes-brasil](https://github.com/turicas/eleicoes-brasil), `develop` | Explicit historical schemas, original-to-normalized header mappings and raw/derived separation. | Historical ETL is not a validated 2026 section-log parser. |
| [INEMA / eleicoes2026](https://github.com/inematds/eleicoes2026), `main` | Provenance, immutable publication versions, accounting checks, handling asynchronous result updates. | Its live dashboard and aggregate estimates do not establish section-level fraud or identify individual vote transfers. |

Turicas' [extractor implementation](https://raw.githubusercontent.com/turicas/eleicoes-brasil/develop/extractors.py)
uses Latin-1 input and validates observed CSV headers against a declared schema.
Its inspected `VotacaoZonaExtractor.get_headers()` rejects years after 2018. Adopt
the schema discipline; do not assume this path supports the current election.
Preserve original missing-value codes alongside normalized nulls rather than
losing their distinct meanings.

INEMA's [data contract](https://github.com/inematds/eleicoes2026/blob/main/contrato/README.md)
distinguishes eligible electors in counted sections from the entire electorate,
and valid votes from total votes. Its
[collector](https://raw.githubusercontent.com/inematds/eleicoes2026/main/coleta/coletor.py)
keeps raw responses and treats national/state differences during asynchronous
publication differently from final discrepancies. Adopt these checks. Our audit
should also retain decreases and corrections as versioned observations rather
than discard them because totals were expected to increase.

Its [failure history](https://github.com/inematds/eleicoes2026/blob/main/FALHAS.md)
records timezone and stale-CDN problems. The
[normalization code](https://raw.githubusercontent.com/inematds/eleicoes2026/main/coleta/nucleo.py)
uses a UF-level time adjustment. That is insufficient as a general section-clock
rule: municipality exceptions and overseas locations need explicit treatment.

An additional implementation to examine is
[DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR): its documented
handling of replacement urns, copied logs, timezone exceptions and Parquet output
is relevant. Independently validate its parsers and findings against TSE originals
before reuse; its published conclusions are not ground truth for our model.

## Data required before fitting

The current downloader collects logs and auxiliary metadata. Logs alone do not
provide the candidate totals, electorate denominators and location attributes
needed for the proposed electoral model.

| Input | Purpose | Validation / source |
| --- | --- | --- |
| Second-round BUs, preferably the published CSV plus selected binary BUs | Candidate totals, eligible electors, turnout, blank/null votes, voting location, urn/version identifiers | [TSE BU dataset](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna); reconcile CSV against binary samples and final totals. |
| First-round BUs and section details | First-round preference vector and turnout baseline | Same dataset, correct round and cargo; aggregate changed section compositions before joining. |
| Second-round logs, auxiliary files and section indexes | Sessions, voting events, operational history, aggregation and publication status | [TSE technical documentation](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados). |
| Final federal result at BR/UF/municipality levels | Final reporting margin and hierarchical reconciliation | Election 6258, cargo 1; use a coherent final snapshot. |
| Selected RDVs and signature envelopes | Recompute counts and validate signed artifacts | [TSE format links](https://www.tse.jus.br/eleicoes/eleicoes-2026/eleicoes-2026); these are additional downloads. |
| Section/locality register, historical results, temporary transfers, polling-place information | Stable joins and peer selection | Verify each year's schema, TSE-versus-IBGE code mapping and denominator definitions. |
| Occurrence records, polling-station minutes, independent BU copies or other corroboration | Resolve specific suspicious cases and study access/suppression mechanisms | Obtain for identified cases; official electronic artifacts share parts of the same production chain. |

TSE publishes BUs by UF and round, with separate checksum resources, in the
[BU catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna).
Do not confuse a catalog example or a dashboard simulation with an observed final
result. No final margin is asserted in this plan.

## Canonical tables and integrity checks

Use a principal-section key `(year, round, election, UF, municipality_TSE, zone,
section)` and separate `physical_urn`, `source_package` and `voting_session` keys.
Keep codes as zero-padded text and vote counts as integers. A physical urn can
serve multiple historical sessions; a section can use replacement hardware.

Produce append-only source snapshots, a section-composition crosswalk, section
results, session summaries, parsing issues and candidate-independent anomaly
features. Use Parquet for large derived tables when the analysis dependencies are
installed; retain SQLite for manifest queries. Keep the running downloader's
manifest read-only during analysis. Its current `files` table records the latest
URL mapping: before analysis, add/freeze per-run URL-to-object provenance so later
metadata updates cannot silently change the analysis inputs.
If `manifest-location.json` exists, resolve it with the downloader's
`manifest_path()` helper; an HDD-local `manifest.sqlite` may be a pre-migration
snapshot rather than the authoritative database.

Required checks include:

- Correct date, round, cargo, official phase and package status; downloaded
  received/rejected/excluded versions must not be added to totalized votes.
- One canonical result per principal section after resolving retransmissions;
  preserve competing versions and conflicts. Do not sum all hashes.
- Aggregate sections into their principal electorate exactly once. For historical
  comparisons, harmonize changed compositions or mark them incomparable.
- Candidate votes + blank + applicable null categories = presidential votes;
  check turnout/abstention against the appropriate electorate, documenting any
  transfers or exceptional categories. Repeated BU rows must not multiply a
  section's electorate or turnout.
- Sum results to municipality, UF and BR, including ZZ, using the same final
  population and version. Separate publication gaps from numerical discrepancies.
- Compare log completion and suspension events against BU totals after decoding
  session semantics; a raw message-count mismatch is an investigation item.
- Verify digital signatures using TSE's schema and trust material separately from
  checking transport hashes or ZIP CRCs. Agreement among artifacts generated by
  the same software is a consistency check, not independent proof of voter intent.

Maintain a population ledger: expected sections, aggregated sections, installed
and non-installed sections, available BUs, available logs, reconciled records,
parser failures and exclusions. Report coverage by UF, location, model/version
and candidate support; do not silently drop unusual records. Alphabetical download
order makes the current partial collection unsuitable for national inference.

## Log semantics: checks before computing features

Direct inspection of three saved AC/AL/AM files found setup dates, 4 October and
25 October events in the same `logd.dat`. A second-round filename is not a filter
for second-round events. Preserve line order and identify official VOTA sessions,
turn transitions, urn identity, restarts, suspensions and clock changes before
selecting the target session. Date filtering is a useful diagnostic, not a full
replacement for session reconstruction.

The [official log guide](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema)
shows successful voting, partial/full suspensions and registration workflows.
Count completed voter cycles rather than every message mentioning a vote or a
manual authorization. A request for manual data may be cancelled and is not
automatically a completed manual vote. Keep unresolved cycles explicitly unknown.

Log timestamps are naive device-clock readings. Preserve the original reading,
assigned timezone/offset, clock adjustments, conversion rule and confidence.
Verify municipality-level mappings and overseas conventions against BU/session
records; do not infer timezone from an unusually early/late first vote. Opening,
closing, transmission and download times are different quantities. Evaluate
sensitivity to plausible clock errors; unresolved clocks exclude absolute-time
claims but need not exclude result-count checks.

Deduplicate copied files and verified overlapping event blocks across replacement
packages, retaining lineage. Do not deduplicate solely on identical messages or
second-resolution timestamps, which can legitimately repeat. Do not sum the same
physical session through multiple section/package references.

TSE explains that RDV entries are shuffled to prevent reconstructing voter order:
[official RDV explanation](https://www.tse.jus.br/comunicacao/noticias/2021/Julho/registro-digital-do-voto-permite-recontagem-e-amplia-transparencia-do-processo-eleitoral).
Therefore, log timestamps cannot be joined by row number to RDV choices. We cannot
attribute late, fast or manually authorized voting cycles to a candidate.

## Non-parametric model specification

### Targets and controls

Fit separate conditional distributions for:

- Turnout: completed voters / eligible electorate in the harmonized section.
- Candidate A share: A / (A + B), undefined if valid votes are zero.
- Blank/null proportions with their correct denominators.
- Operational measures: distributions of completed-cycle durations, within-session
  gaps, failed authorizations, outages/restarts and within-day intensity changes.

Use a prespecified first-round preference vector, electorate/size, geography,
historical voting patterns where comparable, and relevant pre-election polling
place characteristics. Check whether a state also voted for governor: the number
of contests changes voting duration. Candidate A/B definitions are fixed from
official identifiers and the tests run symmetrically in both directions.

Maintain two model specifications: one adjusts operational comparisons for device
model/version and known logistics; another examines those factors as possible
mechanisms. Do not automatically control away turnout, manual authorization or
outages when those are the hypothesized effects of manipulation. Repeat electoral
models without the current first-round baseline, which itself may be affected.

### Predictors and scores

Start with interpretable matched-peer medians, empirical conditional quantiles
and median absolute deviations. Compare within polling place where possible, then
within zone/municipality with size and historical-preference matching. Sections
are not randomly assigned voters: within-school permutations are not automatically
exact randomization tests. Require overlap and flag out-of-support cases rather
than force a prediction.

The main nonlinear predictor is a **quantile regression forest**, which estimates
conditional outcome quantiles without a fixed normal-error model:
[Meinshausen (2006)](https://www.jmlr.org/papers/v7/meinshausen06a.html).
Compare it against the matched empirical baseline using held-out quantile loss
and interval coverage. Flexibility alone does not establish robustness to bad
data, confounding or contaminated training populations.

For an interval `[L_j(x), U_j(x)]`, a possible component score is
`s_ij = max(L_j(x_i) - y_ij, y_ij - U_j(x_i), 0) / scale_j(x_i)`.
Specify scale floors and discrete/zero-denominator handling using training data.
Prespecify a joint maximum score across components, then calibrate that joint
score; do not add separate p-values without justification. Keep signed residuals
for interpretation and absolute scores for symmetric detection.

### Calibration, geography and multiplicity

Split by whole polling locations into training, calibration and test sets, with
fixed seeds and geographic strata. Use municipal holdouts as a stronger stress
test. Same-location peer diagnostics form a separate descriptive layer; using
neighbors to train and test would otherwise exaggerate generalization.

For a frozen score and an exchangeable reference, a conservative rank p-value is
`p_i = (1 + number of calibration scores >= s_i) / (n_cal + 1)`.
[Bates et al. (2023)](https://doi.org/10.1214/22-AOS2244) develop conformal outlier
testing under stated sampling assumptions. Election sections share environments
and are not independent random draws; splitting into clusters alone does not
prove exchangeability. Examine calibration within prespecified strata and use
whole-cluster scores for confirmatory geographic tests. Where assumptions remain
unsupported, publish empirical tail ranks as descriptive scores, not valid fraud
p-values. [Barber et al. (2023)](https://arxiv.org/abs/2202.13415) discuss the impact
of departures from exchangeability.

Primary inferential units should initially be polling-location/municipality
clusters; section rankings guide investigation. For valid p-values, use a
prespecified testing family and a dependence-aware procedure, such as
[Benjamini–Yekutieli](https://doi.org/10.1214/aos/1013699998), at a proposed 5% FDR.
This controls a testing error criterion under its assumptions, not the percentage
of accusations that constitute fraud. It cannot repair invalid input p-values.
Define families across outcomes, geographic scales and model variants before
testing; label additional searches exploratory.

Check resolution and power before committing: with 20,000 calibration units, the
minimum rank p-value is about 0.00005. For 500,000 tests the first BH threshold at
5% is 0.0000001, and BY is more stringent. Such a design cannot detect an isolated
outlier at that threshold. Do not invent tiny p-values by extrapolating an
unsupported tail distribution. Coarser cluster tests, prespecified global tests,
or a larger valid reference may be necessary. State the undetectable effect range.

### Guardrails against selective testing and repeated inspection

The [xkcd Significant comic](https://xkcd.com/882/) illustrates testing many
subgroups and selectively reporting one low p-value. With 20 independent true-null
tests at 5%, the probability of at least one false rejection is
`1 - 0.95**20`, about 64%; the expected number is one. Dependence changes the first
calculation, but does not make unadjusted exploratory searches confirmatory.

Keep an analysis ledger containing every outcome, subgroup, geographic scale,
time window, hardware comparison, model variant and historical-election comparison
examined, including null results and unsuccessful specifications. Freeze the
confirmatory family and the joint score before examining test-set rankings.
Selecting interesting subgroups after seeing their results is itself selection;
correcting only the final displayed list does not account for the preceding search.

Reserve a genuinely untouched test partition. Choose features, peer definitions,
hyperparameters and thresholds using development data and historical backtests.
Once inspected, a test partition becomes development data for subsequent changes;
use new held-out evidence or a justified selection-adjusted analysis for renewed
confirmatory claims. Statistical multiplicity correction alone does not fix
training/test leakage or adaptive model selection.

Treat monitoring while downloads arrive as descriptive. Confirmatory testing uses
a frozen population and snapshot. Repeatedly inspecting p-values and stopping
when a threshold is crossed is not covered by the present fixed-family helpers;
sequential claims would require a separately specified valid sequential method.

Report effect sizes and conditional vote-margin bounds alongside uncertainty.
A non-significant test does not prove absence of fraud; a small p-value does not
give the probability of fraud. A 5% FDR target concerns the expected fraction of
false null rejections among rejections, with zero when none are rejected; it is
neither a per-case probability nor a bound on the share of fraudulent votes. These
interpretation safeguards follow the
[ASA's p-value statement](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf).
Non-parametric modeling does not remove any of these design requirements.

## Historical elections: acquisition priority and validation

Historical data can improve peer definition, expose persistent local behavior
and stress-test generalization. It is not a certified clean control group. A
pattern recurring across elections can be ordinary structure, a recurrent data
artifact or a persistent irregularity; recurrence alone cannot distinguish them.

Prioritize:

1. **2026 first-round results and section composition:** the closest electorate
   baseline for the runoff. Distinguish actual change from aggregation and
   transfers, and allow the first-round data themselves to be contaminated.
2. **2022 presidential results, both rounds, plus comparable logs:** a prior cycle
   for turnout/preferences and operational validation. TSE lists presidential
   section results and section details in its
   [2022 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2022), and
   [documents public online logs from 2022](https://www.justicaeleitoral.jus.br/fato-ou-boato/checagens/2022/logs-das-urnas-eletronicas-sao-dados-publicos-e-nao-revelam-votos-de-eleitores).
   Check current file availability and year-specific formats before bulk retrieval.
3. **2018 presidential results, both rounds:** another cycle to assess stability
   and temporal sensitivity. TSE's
   [2018 catalog](https://dadosabertos.tse.jus.br/dataset/resultados-2018) includes
   presidential section votes and section details. Do not presume the same online
   log coverage as 2022 or identical meanings across schemas.

Use chronological development/backtests where feasible: for example, develop
using 2018 data and perform a frozen retrospective check on 2022 before the final
2026 evaluation. If 2022 results inform another revision, label the earlier check
as development and preserve a fresh final test. Compare historical-assisted and
current-cycle-only models under the same held-out evaluation; retain history only
where it improves calibration, prediction or investigation quality.

Harmonize section splits/mergers, electorate changes, locations, timezone rules,
device/software generations, biometric workflows and numbers of contests. Do not
equate different candidates' raw shares or assume voter preferences remain fixed.
Municipal-election data may help validate parsing and some operational mechanisms,
but do not automatically belong in a presidential-turnout/vote-share reference.
Use history as context and as a stress test, rather than simply concatenating all
rows and claiming a larger independent calibration sample. Repeated observations
of the same places and year-to-year distribution shifts violate that shortcut.

## Validation and investigation protocol

Before applying anomaly labels:

1. Validate parser and count reconciliation across hardware, software, geography,
   normal/replacement sessions and exceptional BU types.
2. Use held-out geography and independent historical elections as stress tests,
   not as assumed fraud-free training labels. First- and second-round differences
   can reflect legitimate vote transfers and different contest counts.
3. Inject documented synthetic mechanisms into separate validation copies:
   added votes, switched votes, reduced turnout, duplicated histories, missing
   segments and clock errors, at multiple geographic concentrations and magnitudes.
   Refit/calibrate where appropriate so contamination effects are tested too.
4. Report detection power, localization, false alarms under benign simulated
   mechanisms, and coverage by stratum. Simulations assess the implemented
   detector against specified mechanisms, not all possible fraud.
5. Investigate ranked cases with source evidence, plus a random sample of
   unflagged cases. Seek independent BU copies, minutes, incident explanations and
   corroborating evidence. Analysts reviewing operational logs should initially
   be blinded to candidate identity where feasible.

Inspect coherent regional and model/version shifts as well as isolated extremes:
a widespread alteration could be absorbed by a flexible baseline. Conversely,
regional political preferences, age, accessibility, transport and administration
can generate coherent differences without fraud. First-round aggregate changes
cannot identify individual vote transfers (an ecological identification problem).

Use operational and result evidence jointly, with explicit alternative
explanations. Neither high support, low biometric use, fast voting, late closure,
late transmission nor a particular device model is sufficient alone. Do not use
Benford conformity as the primary test: [Deckert, Myagkov and Ordeshook
(2011)](https://authors.library.caltech.edu/records/5jbtk-8wn05) show that this can
misclassify election data. Do not delete flagged sections and declare the
remaining sum the true outcome.

## Estimating outcome impact

Let `M = total_A - total_B > 0` be the frozen official national margin. Obtain it
from reconciled final data, not the incomplete local logs. Distinguish:

| Mechanism assumed and corroborated | Largest margin change per affected ballot |
| --- | --- |
| Remove an invalid vote counted for A | 1 vote |
| Correct a vote counted for A that should have been B | 2 votes |
| Restore a suppressed additional vote for B | 1 vote |

For a strict B win, at least `floor(M/2) + 1` A-to-B switches are required, if that
many A votes are eligible for correction. At least `M + 1` A removals or additional
B votes are required under the corresponding one-vote mechanism. These are
arithmetic thresholds, not estimates of what happened.

For an anonymous flagged subset of `r` completed ballots in a section with
`a` A votes, `b` B votes and `c` other ballots, assume all `r` are removed. Its
removed A-minus-B contribution has sharp feasible bounds:

```
d_max = min(r, a) - max(0, r - a - c)
d_min = max(0, r - b - c) - min(r, b)
corrected national margin in [M - d_max, M - d_min]
```

Sum these contribution bounds over disjoint affected sections/subsets. They use
only anonymous subset size and BU counts; they do not allocate late/manual votes
to a candidate. Overlapping detectors must be deduplicated before adding bounds.
The removal assumption itself needs justification, and `r` must count presidential
ballots, not authorization attempts or generic log messages. If “at most r” are
affected, include the zero-removal case as well.

For a two-candidate switching scenario with a validated cap `q_i` on affected
ballots, the maximum adverse margin correction is `2 * min(q_i, a_i)` per section.
This assumes at most that many currently A ballots can be switched to B; different
mechanisms, changed electorates and blank/null conversions require different
constraints. If the resulting total bound is smaller than M, that *specified
mechanism within that specified population and cap* cannot reverse the result.
This says nothing about undetected manipulation outside the population.

A model-based counterfactual can estimate expected A votes as `n_valid_i * p_hat_i`
with valid turnout held fixed. The implied two-candidate margin difference is
`2 * sum(a_i - n_valid_i * p_hat_i)`. Label it **excess relative to the baseline**,
not stolen votes. To study turnout manipulation, model participation separately
and vary absent voters' hypothetical choices; these are not observed in the logs.
Use geographic block resampling of the full fit/selection/estimation pipeline,
report signed effects and sensitivity to matching, contamination and omitted
factors. A simple bootstrap of selected residuals ignores selection bias.
Prediction intervals for sections cannot simply be added as a national confidence
interval, and predictive uncertainty does not identify causal uncertainty.

Every reported case should include source hashes, section/session/package keys,
observed and expected features, peer definition, score/assumptions, multiplicity
status, alternative explanations, corroboration, affected-vote bounds and the
conditional national-margin implications. “Real impact” remains unidentified
without defensible evidence about the mechanism and counterfactual.

## Execution order

1. Let acquisition continue; inspect a small, reproducible read-only log sample.
2. Obtain BUs for both rounds, final totals, a section crosswalk and the required
   schema documentation; add targeted RDV/signature checks.
3. Freeze a coverage/provenance snapshot; build and reconcile session/result tables.
4. Freeze targets, null assumptions, splits, testing families and validation
   simulations; implement and compare the conditional empirical and forest models.
5. Produce a candidate-symmetric investigation table, then conditional impact
   bounds and sensitivity analyses. Publish neither fraud counts nor a corrected
   winner from statistical residuals alone.

`scripts/audit_statistics.py` contains tested rank-calibration, multiplicity and
impact-bound primitives. It does not fit the proposed model. The log-inspection
utility is a parser diagnostic, with no timezone conversion or fraud classifier.
