# Statistical audit of the 2026 presidential election: study protocol

Document-ID: EA-ANALYSIS-PLAN · Revision: 11 · Language: en

[Português](analysis-plan.pt-BR.md) · [Completion plan](completion-plan.md) · [Related work](related-work.md)

**Status: draft protocol, 3 November 2026.** This document says what the audit will
claim, how each claim is tested and how sensitive each test is. It is not yet
frozen. It will be frozen and publicly pre-registered (OSF registration plus a
signed git tag) in Phase 23, before any confirmatory analysis. After the freeze,
every change is a recorded deviation and its results are labelled exploratory.
No fraud finding, national margin or fitted national model exists today.

## 1. Questions and the claims they allow

The audit answers three separate questions:

1. **Integrity.** Do the published artifacts agree with each other, with their
   signatures and with independent copies? Answered by deterministic checks
   (section 5). A discrepancy is a fact about artifacts, not about intent.
2. **Unusualness.** Do some places, device groups or the whole distribution of
   results depart from what comparable sections and the same sections' first round
   predict? Answered by a small, prespecified family of statistical tests (section
   7). A rejection says "this pattern is unlikely under the stated model", not
   "these votes are fraudulent".
3. **Outcome sensitivity.** Under an explicit mechanism, population and cap, how
   much could the national margin move? Answered by arithmetic bounds (section 8).
   These are conditional statements, not estimates of what happened.

**Results always come with their power.** The headline of the statistical part is
the *minimum detectable manipulation*: for each mechanism, the smallest change
to the national margin that the tests would detect with 80% probability. A null
result without that number would be uninterpretable, so it is never reported
alone.

The audit does **not** claim:

- that any section, person or party committed fraud;
- that the absence of signals proves the absence of fraud;
- that any vote, late cycle or manual authorization belongs to a candidate (the
  RDV is shuffled; see section 6);
- a corrected winner, or the result of removing flagged sections.

## 2. What has already been seen

Pre-registration is only meaningful if it discloses what the authors saw before
writing it. As of this revision:

- **Acre (AC):** runoff BWEB and binary BUs (2270 sections, content-verified);
  section features; one turnout model fitted and evaluated on calibration data;
  126 development case packets. AC is development data.
- **Five-UF structural pilot (AC, AL, DF, ES, PR):** frozen logs, with sessions,
  cycles and clocks all left unresolved. Development data.
- **National runoff structural summaries (Phase 11):** per-log counts of lines,
  structural events, authorizations, completions and manual requests for 498581
  logs. No electoral result was joined to them and no ranking was computed. Each
  runoff log spans setup (September), the first round and the runoff, so these
  counts mix rounds and are not runoff measures.
- **Inspection registries:** every location listed in
  `data/phase15/inspection.sqlite`, `data/national/phase11-protection-2026-10-31/`,
  `$EA_STAGE/inspection/phase20b-national-20261109.sqlite` (the 7824 polling places of the 12016 sections whose integrity rows were
  seen in Phases 20 and 20b, registered on 9 November 2026)
  and the Phase 11 tranche registries is development data.
- **National semantic pass (Phase 21):** per-session aggregates of every eligible log
  of both 2026 rounds and of both 2022 rounds, computed by code. Seen: object,
  session and segment counts, the population ledgers, the AC equivalence samples and
  individual clock-fault sessions of 2022 (four restarts at 01/01/2009, one at
  23/08/1933). No session measure was joined to results, ranked or summarized by area.
- **Integrity checks (Phase 20):** I1–I9 compare artifacts section by section. Seen:
  match and mismatch counts per check, and the values of rows that disagree. AC and
  ZZ outputs were inspected while the checks were built, and I5 compared AC completed
  cycles with BU attendance. Values of agreeing rows stay in the check outputs
  (`restricted/` and per-contest digests) and are neither reported nor queried before
  the freeze. The logs of the 596 protected/stress sections are hashed with SHA-512
  for I1. Five of them (four test, one municipal stress) were structurally parsed,
  without any values being read, in the Phase 11 stratified sample before the
  exclusions existed (`data/national/phase11-protection-2026-10-31/impact.json`).
- **Integrity reconciliation (Phase 20b):** the I6 prefix re-read (line-by-line
  content of the 113 differing round-1 block pairs, as digit-masked templates); for
  the 121 sections that failed I5, their BU attendance, their log sessions and the
  raw election-day lines of their logs, compared case by case with DataUrnas-BR; the
  RDV blocks of the two MG sections that failed I3. National counts of sessions
  started before election day, without their measures. In the 8 November 2026
  reconciliation: DataUrnas-BR's round-1 per-section log counts for those sections,
  the BU attendance of es/57932/0009/0112 (whose urn's log is in the package of
  section 0085), and the national total of completed cycles in official sessions
  per semantic-pass run, compared between versions 3 and 4 and not reported.
- **Checks added from DataUrnas-BR (Phase 20b, 8–9 November 2026):** pass and
  failure counts of the Ed521 cross-check and of Z1–Z5, G1–G3, H1–H2, E1–E2 and
  J1–J4 (section 5), and the rows that fail or are unavailable. For the GEDAI
  failures outside sp/0176 (13 and 70 sections): their BU load codes, urn numbers,
  load-media serials and load times, and every GEDAI log line naming them. For the
  signature errors: their digit-masked templates and the votes counted before and
  after each; the raw lines around the two signing errors followed by a vote (about
  ten lines each, voter-related lines excluded). National counts of late urn loads
  by date and GEDAI match status, without results.
- **Not seen:** section-level electoral results or operational measures outside AC,
  beyond the counts and disagreeing rows above; the contents of the 596
  protected/stress runoff logs.

## 3. Threat model: from mechanism to observable

Each mechanism leaves traces in specific artifacts, or none. The audit is designed
around this table; a test that does not appear here does not belong to the
confirmatory family.

| Mechanism | Where it would leave traces | Checks and tests | What the audit cannot see |
| --- | --- | --- | --- |
| Altered or substituted results after the urn (transmission, totalization, publication) | BU signature; binary BU vs BWEB vs hierarchical totals; printed BU copies | I1, I2, I4, I8 | Nothing within the electronic chain if the signing keys themselves were compromised; printed copies are the out-of-band check |
| Software that alters votes inside the urn, with BU, RDV and log all consistent | No log trace; aggregate result patterns only | TSE election-day integrity tests (external evidence, section 4); C1, C2, C4, C6 | A switch spread evenly across sections looks like ordinary swing at any size, and the swing model absorbs it, so these data cannot identify it (section 7.5); this threat rests on the external evidence of section 4 and on printed BUs (I8) |
| Ballot stuffing or impersonation by poll workers | Non-biometric authorizations, cycles outside normal hours, bursts of fast cycles; turnout and share spikes | I5; C2, C3, C5 | Stuffing spread thinly over many sections at normal times and with biometric authorizations |
| Suppression or obstruction of voters | Turnout drop from round 1 to round 2 relative to peers; long gaps, suspensions, late opening, urn replacement | C1 (turnout), C4, C5 | Causes outside the polling place; legitimate causes (transport, weather) produce the same signal |
| Tampered, copied or fabricated logs | Block hashes; the round-1 segment inside each runoff log vs the round-1 log; clock discontinuities | I6, I7 | A complete, consistently re-signed artifact chain |
| An urn not prepared through the official chain, or carrying unofficial software | GEDAI load records; zerésima before votes; package signature checks at start-up and their failures | G1–G3, Z1–Z5, H1–H2, E1–E2 | The logs record checks by name and result only, not program hashes; a compromised verifier would log success |
| Altered results after publication | TSE's JWS signature on each published result file | J1–J4 | A change made before signing |
| Errors in publication or in this pipeline | Any reconciliation failure | I1–I9 | — |

Benign processes produce several of these signals: regional political swings,
age and accessibility of the electorate, biometric enrolment rates, transport,
urn replacements and administrative practice. Each test therefore has a stated
benign alternative and a control (section 7.6).

## 4. Data and frozen provenance

| Input | Use | Status |
| --- | --- | --- |
| Section logs, both rounds | Sessions, cycles, authorization mix, timing | Acquired; manifests pinned by the SHA-256 migration certificates |
| Phase 11 runoff structural release `55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` | Block hashes, member structure, object index | Complete for 498581 eligible logs; structural only |
| BWEB, 27 UFs and ZZ, both rounds | Section results | To acquire (AC done); TSE publishes SHA-512 checksums |
| Binary BUs, RDVs and signatures (totalized packages) | I1–I3 | To acquire (AC done for BUs) |
| Hierarchical results (EA20) | I4 | To acquire |
| Voter profile by section (age, sex, schooling) and polling places | Covariates, location keys | To acquire |
| 2022 presidential BWEB, BUs and logs, both rounds, with voter profile | Negative control (section 7.6) | To acquire |
| TSE election-day integrity test reports, both rounds | External evidence about in-urn software | To collect |
| Independent printed BU copies (QR codes) | I8 | Collected in Phase 20b (CMInd and Arvor, 518 sections); selection is not random |
| GEDAI-UE preparation logs, both rounds (two exports each, with SHA-512 files) | G1–G3 | Acquired; some zones' logs not published (T11) |
| TSE urn hash lists (`path1u13/15/20/22`) and JWS manual (key in appendix B) | H1–H2, J1–J4 | Downloaded in a browser and frozen (`tse-www-20261108/`, `tse-jws-key-20261108/`) |
| Signed result files (`-u.jws`) for every EA20 node | J1–J4 | Fetched for both rounds (5786 files each) |
| Revocation lists of `AC DIVULGACAO` and `AC TOTALIZACAO` | J1–J4 (key status) | Downloaded in a browser on 9 November 2026 and frozen (`tse-jws-crls-20261109/`); current on election day, none revoked |
| DataUrnas-BR's Ed521 verifier and the `ed521rs` vectors | Ed521 cross-check | Frozen at fixed commits (`ed521-crosscheck-refs-20261108/`) |

Rules that apply to every table:

- Analyses read the **frozen, certified manifest copies** in
  `migration-2026-11-01/manifest-r{1,2}.sqlite`, identified by hash, not the live
  manifests in `.local-state/`. Paths in the manifests are relative to the object
  root.
- One canonical result per principal section after resolving retransmissions,
  with competing versions kept. Aggregated sections join their principal section
  exactly once. Keys stay zero-padded text; counts stay integers.
- A population ledger records expected, aggregated, installed, not-installed,
  BU-available, log-available, reconciled, failed and excluded sections, by UF and
  device model. Unknown is never zero; nothing is dropped silently.
- `Recebido` (received, not totalized) packages are never added to totalized
  votes.

## 5. Tier 1: deterministic integrity checks

These checks need no statistical model. They are reported first, as counts with
complete discrepancy tables and the source hashes needed to verify each row.

| ID | Check | Unit | A failure means |
| --- | --- | --- | --- |
| I1 | BU signature verification against TSE trust material | BU | The artifact is not the one signed by the urn |
| I2 | Binary BU content equals the BWEB row | Section × choice | Publication differs from the signed artifact |
| I3 | RDV recount equals the BU | Section | Ballot record and count disagree |
| I4 | Section sums equal published municipality, UF, ZZ and national totals | Hierarchy node | Totalization differs from sections |
| I5 | Completed cycles in the identified runoff session equal BU attendance | Section | Log and count disagree (often a parsing or session problem; investigated) |
| I6 | Round-1 blocks inside each runoff log equal the round-1 log of the same urn | Urn | One of the two published histories changed |
| I7 | Log clock continuity and session structure pass the reconstruction rules | Session | History is incomplete or out of order |
| I8 | Independent printed BU copies equal the published BU | Section (sample) | Publication differs from the printed record |
| I9 | Package status, aggregation and round identity are consistent | Package | Population is mis-specified |

If the RDV archive does not cover every section, I3 uses a prespecified uniform
random sample. To claim, with 95% confidence, that the discrepancy rate is below
`p` when the sample shows none, the sample size is:

```
n = ceil(ln(0.05) / ln(1 - p))        # p = 0.001 gives n = 2995
```

Independent printed copies (I8) come from third-party collections whose selection
is not random. Their agreement corroborates the sections they cover; it does not
extend to other sections.

**Known gap: I2 for the municipal elections held with the runoff.** Ten municipal
elections ran with the 2026 runoff (elections 6282–6293: supplementary mayoral
elections and three local consultations, 871 contests in 13 municipalities of MT,
PR, RJ, RS, SP and TO). Their contests are in the signed BUs (I1) and are recounted
from the RDV (I3), but the national BWEB carries only the presidential runoff, so
they have no I2 counterpart. They stay unverified against a published section-level
table until TSE publishes one or another source is added; the gap is to be closed in
a later revision, not before the freeze. The impact is low: no claim of this study
rests on these contests. The presidential runoff, the subject of C1–C6 and of the
outcome sensitivity, is covered by I2 in every section with a BU, and the municipal
contests are a small fraction of the round's contests (871 of 539819).

**Supplementary checks (Phase 20b).** These come from the checks DataUrnas-BR runs
and were added before the freeze. They test the urn's preparation and start-up and
the published files, not the count; a failure is investigated like an I-check
failure. Definitions are in the integrity checks guide.

| ID | Check | Unit | A failure means |
| --- | --- | --- | --- |
| Ed521 cross-check | An independent Ed521 verifier (DataUrnas-BR's) gives the same verdict on every urn and CA signature | Signature | One of the two verifiers is wrong, so I1 rests on one implementation |
| Z1–Z5 | Every voting urn printed a zerésima on election day, before any vote and before declaring itself ready, and none after votes | Section | Votes may predate the zero report |
| G1–G3 | The BU's (section, load code, urn) and its load medium are in TSE's GEDAI preparation logs | Section | The urn's load is not recorded by the official preparation system, or its records are not published |
| H1–H2 | Every program package verified in a log is named in TSE's hash lists, and every verification succeeded | Path × model | A package outside the published software, or a failed start-up check |
| E1–E2 | No vote in the session of a signature verification error; after a signing error, only the vote in flight | Section | An urn kept voting after it failed to verify its software |
| J1–J4 | Each published result file carries TSE's signature with the official key, over the same bytes as the plain file and the EA20 snapshot | Result file | The published result differs from what TSE signed |

**Known gaps of the supplementary checks**, which stay open at the freeze unless TSE
answers: G1 cannot be applied in three zones and G3 in three others whose
preparation logs are not published (482 and 284 sections, T11); sp/0176 has the
correspondences of only 169 of 437 sections; 13 and 70 late loads outside it have no
published correspondence (T13), and these stay G1 failures; the GEDAI logs' own
signature files are not verified; the hash lists do not name the files of the load
media and the load (T12), and the logs carry names and results, not hashes, so H1
shows that the verified names are published, not that the bytes match; the CA
certificate chains stop at the intermediate CAs because the roots are not published
(T1); the JWS key's revocation status is known as of the lists read on
9 November 2026, which TSE serves only to browsers.

Agreement among artifacts produced by the same software chain (I1–I4) shows
consistency, not voter intent. The TSE integrity tests and printed copies are the
only out-of-band evidence, and they are reported with that caveat.

## 6. Log semantics (rules before any operational measure)

- A runoff log file is not a runoff event filter. A `logd.dat` contains setup,
  first-round and runoff events. Identify official voting sessions, round
  transitions, urn identity, restarts, suspensions and clock changes in line order
  before selecting a session.
- Count completed voter cycles, not messages. A request for manual data can be
  cancelled; it is not a completed manual vote. Unresolved cycles stay unknown.
- Split authorization as biometric versus non-biometric. A biometric match is the
  only path where the urn checks the voter against an enrolled fingerprint; manual,
  no-biometrics and undetermined methods all rest on the poll worker and are
  pooled. The biometric marker is identical in 2026 and 2022, so the split is
  measured the same way in both years; the 2022 logs have no explicit manual
  marker.
- Timestamps are naive device-clock readings. Keep the original reading, the
  assigned offset, adjustments, the conversion rule and its confidence. Do not
  infer a timezone from an early or late first vote. Unresolved clocks block
  absolute-time claims but not count checks.
- A voting session belongs to the round when it runs in that round's official
  context. An urn switched on before election day and left running opens its session
  then; the session becomes official at its first voting event on election day and
  is flagged. A restart line that names the round in effect keeps that round's
  context, because the urn does not repeat the official-round marker after a
  mid-day restart (session rules `sessions-v2`).
- Deduplicate copied histories by verified block lineage, never by identical
  message text and second-resolution time, which repeat legitimately.
- The RDV is shuffled by design
  ([TSE](https://www.tse.jus.br/comunicacao/noticias/2021/Julho/registro-digital-do-voto-permite-recontagem-e-amplia-transparencia-do-processo-eleitoral)),
  so log cycles cannot be joined to ballot choices. No operational event is ever
  attributed to a candidate.
- Message semantics come from the official
  [log guide](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema)
  as exact reviewed templates (`real-log-rules.json`); messages outside them stay
  unknown and are counted in a published template vocabulary.

## 7. Tier 2: statistical analysis

### 7.1 Units and outcomes

The unit is the principal section, harmonized across rounds; sections whose
composition changed between rounds are matched only through an explicit
crosswalk, or marked incomparable. Outcomes:

- runoff turnout (attendance / eligible electorate);
- candidate A share of valid votes, `A / (A + B)`, undefined when valid votes are
  zero; every test runs in both directions (A and B), with A and B fixed from
  official candidacy identifiers;
- blank and null shares, with their own denominators;
- operational measures: non-biometric share of completed cycles (expected level
  from biometric enrolment and electorate profile), share of
  cycles after the official closing time, and cycle cadence (completed cycles per
  active minute).

### 7.2 Primary model: round-1 to round-2 swing

Each section's runoff outcome is predicted from its own first-round vector
(candidate shares, blank, null, turnout), its voter profile (age bands, sex,
schooling), its size and its location (UF, municipality, polling place).
Predicting change rather than level removes most stable local structure, which is
the main source of false alarms in cross-sectional models.

- **Size-aware noise.** Counts are modelled with an overdispersed binomial
  (beta-binomial) likelihood, so small sections are not flagged for being noisy.
  Each section receives a predictive tail probability for its observed count,
  using mid-p for discreteness. A funnel plot of residual against size is
  published for every outcome.
- **Cross-fitting.** Every section is scored by a model that never saw its polling
  place: 10 folds grouped by polling place and stratified by UF
  ([Chernozhukov et al. 2018](https://doi.org/10.1111/ectj.12097)). This gives an
  honest score for every section instead of a small held-out test set.
- **Within-location contrast.** Sections in the same polling place share
  neighbourhood, staff and logistics. The difference between a section and the
  other sections at its location is reported as a primary, model-light statistic.
- **Flexible comparator.** A quantile regression forest
  ([Meinshausen 2006](https://www.jmlr.org/papers/v7/meinshausen06a.html)) is
  compared against the beta-binomial swing model on development data using held-out
  quantile loss and interval coverage. The model is chosen before the freeze; the
  choice and the losing model's results are both published.
- **Without round 1.** The models are also fitted without the first-round vector,
  because the first round could itself be affected.

### 7.3 Confirmatory family

Confirmatory tests act only at global or cluster level, where 500,000 sections
give power rather than an impossible multiple-testing burden. Each test is
two-sided or run in both candidate directions, and each has a simulation-based
null drawn from the fitted model with whole-location resampling. A test run in both
directions counts as two members of the family. Before the freeze, a table fixes for
each test its statistic, unit, direction or directions, null and threshold, and so
the family size.

| ID | Test | Detects | Benign alternative |
| --- | --- | --- | --- |
| C1 | Calibration of swing residuals: excess of extreme predictive tail probabilities, signed, for share and turnout | Widespread manipulation beyond ordinary swing | Model misspecification (checked on 2022 and development data) |
| C2 | Turnout × share joint distribution compared with the model-implied null, in the spirit of [Klimek et al. 2012](https://doi.org/10.1073/pnas.1210722109) | Stuffing that raises turnout and one candidate together | Strongly mobilized homogeneous communities |
| C3 | Excess of integer percentages relative to a size-aware null ([Kobak et al. 2016](https://doi.org/10.1214/16-AOAS904); [Rozenas 2017](https://doi.org/10.1017/pan.2016.9)) | Fabricated or rounded results | Small sections; tested against the exact discrete null |
| C4 | Scan statistic over polling places and municipalities on residuals ([Kulldorff 1997](https://doi.org/10.1080/03610929708831995)) | Geographically concentrated manipulation | Local political events; reviewed with source evidence |
| C5 | Association between operational excess (non-biometric share, late cycles, cadence) and share residual, adjusted for the voter profile (age bands, schooling, biometric enrolment, size) and compared within polling place, both directions | Stuffing or impersonation linked to one candidate | Low biometric enrolment, accessibility, queues |
| C6 | Swing residual by device model and software version, within location | Device-specific software manipulation | Composition of places using older devices (the 2022 Instituto Voto Legal error; section 7.6) |

Age and rurality drive both operational measures and vote shares, so the unadjusted
C5 association is reported as descriptive only.

Multiplicity is controlled across this family with Benjamini–Yekutieli at 5% FDR
([Benjamini and Yekutieli 2001](https://doi.org/10.1214/aos/1013699998)). The
family, statistics, nulls, seeds and thresholds are frozen in the pre-registration.
Mixture-model forensics such as Mebane's eforensics are run as a secondary,
exploratory analysis; their known sensitivity to strategic voting and
administration is reported with them.

### 7.4 Section rankings are triage only

Section and location scores are published as ranked predictive tail
probabilities for investigation (section 9). With 500,000 sections, the smallest
attainable rank p-value and the multiple-testing threshold make individual
confirmatory claims unreachable, so rankings carry no significance label.

### 7.5 Power and minimum detectable manipulation

Before the freeze, synthetic manipulations are injected into copies of the
development data and the 2022 data, then the full pipeline (fit, scoring, tests)
is rerun:

- mechanisms: vote switching, ballot stuffing (turnout increase with one-sided
  share), suppression (turnout decrease), fabricated round results, copied or
  missing log segments, clock errors;
- magnitudes: from 0.1% to 10% of affected sections' votes;
- concentration: spread uniformly, concentrated in municipalities, concentrated
  in a UF, concentrated in one device model.

For each mechanism and concentration the protocol reports power curves and the
**minimum detectable manipulation**: the smallest national margin shift detected
with 80% power by the family. Benign injected disturbances (clock errors, copied
logs) measure false alarms. These numbers are part of the pre-registration and of
the headline results. The minimum detectable manipulation is a power statement for
the named injection patterns, not a bound: after a null result it does not limit
manipulation of other patterns, and a switch spread evenly across sections is not
identifiable at any size, because the round-1 to round-2 model absorbs it as swing.

### 7.6 Negative controls

- **2022 presidential election, both rounds,** through the same pipeline. 2022 is
  not certified clean, but a method that flags 2022 as strongly as it would flag a
  manipulated election is not informative, and the comparison is published either
  way.
- **The 2022 device-model claim.** In November 2022 a report by Instituto Voto
  Legal argued that votes from older urn models should be discarded; the TSE
  rejected it and fined the coalition that filed it
  ([TSE decision](https://www.tse.jus.br/comunicacao/arquivos/voto-alexandre-de-moraes)).
  C6 is required to show how a naive device-model contrast arises from where older
  devices were deployed, and that the within-location contrast removes it.
- **Placebos:** permuted candidate labels within location, randomized location
  labels, and the first round predicted from itself, which must produce null
  results.

### 7.7 Development, confirmatory and holdout data

- **Development:** the data listed in section 2. Used to build and tune everything.
- **Sealed holdout:** at the freeze, a random 10% of polling places, stratified by
  UF, is drawn with a seed published in the pre-registration and its list hashed.
  The holdout is not opened until the confirmatory run on the rest is published.
  It then replicates C1–C6 once, and concordance is reported.
- **Confirmatory:** every other location. Its tests are run once, after the
  freeze. The 596 protected/stress runoff logs stay unread until the freeze and are
  then allocated by the same random draw as every other location.
- **Development UFs** are reported descriptively, never as confirmatory evidence.

## 8. Outcome sensitivity

Let `M = total_A - total_B > 0` be the official national margin, taken from
reconciled final data. The arithmetic thresholds are:

| Mechanism assumed and corroborated | Largest margin change per affected ballot |
| --- | --- |
| Remove an invalid vote counted for A | 1 vote |
| Correct a vote counted for A that should have been B | 2 votes |
| Restore a suppressed additional vote for B | 1 vote |

A strict B win needs at least `floor(M/2) + 1` A-to-B switches, or `M + 1`
removals or additional B votes. For an anonymous subset of `r` completed ballots
removed from a section with `a` A votes, `b` B votes and `c` other ballots:

```
d_max = min(r, a) - max(0, r - a - c)
d_min = max(0, r - b - c) - min(r, b)
corrected national margin in [M - d_max, M - d_min]
```

Bounds add over disjoint sections; overlapping detectors are deduplicated first.
`r` counts presidential ballots, not authorizations or messages. With a validated
cap `q_i` on switched ballots, the largest adverse correction is `2 * min(q_i, a_i)`
per section. If the total stays below `M`, that mechanism, within that population
and cap, cannot reverse the result; nothing follows about mechanisms outside it.

A model-based counterfactual `2 * sum(a_i - n_valid_i * p_hat_i)` is labelled
**excess relative to the baseline**, never stolen votes. Its uncertainty comes
from geographic block resampling of the full fit, selection and estimation
pipeline. The minimum detectable manipulation (section 7.5) is reported alongside
it, so readers can compare what could be hidden with what was seen.

## 9. Investigation protocol

Ranked locations and a random sample of unflagged locations receive the same case
packet: source hashes, keys, observed and expected values, peer definition, score,
integrity results, alternative explanations, corroboration sought and
affected-vote bounds. Reviewers of operational evidence are blinded to candidate
direction where feasible. Corroboration is sought from polling-station minutes,
incident records and printed BU copies. Investigation results are reported for
flagged and unflagged cases alike, so the false-alarm rate of the triage is
visible.

## 10. Guardrails against selective inference

- An append-only analysis ledger records every outcome, subgroup, geography, time
  window, device comparison and model variant examined, including null and failed
  specifications.
- Selecting subgroups after seeing results is itself selection; correcting only
  the displayed list does not account for the search
  ([xkcd 882](https://xkcd.com/882/)).
- The protected evaluation is used once per protocol and partition: a final
  evaluation needs the protocol's shared access registry, which refuses a second
  model and any repeat, whichever model directory asks.
- Once inspected, data becomes development data. Renewed confirmatory claims need
  new held-out evidence.
- Monitoring results as they arrive is descriptive; there is no sequential
  stopping rule.
- A small p-value is not the probability of fraud; a non-significant test is not
  proof of its absence; a 5% FDR is not a bound on the share of fraudulent votes
  ([ASA statement](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf)).
- Benford-style digit tests are not used as evidence
  ([Deckert, Myagkov and Ordeshook 2011](https://authors.library.caltech.edu/records/5jbtk-8wn05)).
- Exchangeability is assumed only where stated and checked within strata; where it
  fails, scores are descriptive ranks
  ([Bates et al. 2023](https://doi.org/10.1214/22-AOS2244);
  [Barber et al. 2023](https://arxiv.org/abs/2202.13415)).

## 11. Reproducibility and how to challenge the results

The results should be checkable by someone who does not trust the authors.

- **Pre-registration.** The frozen protocol, confirmatory family, seeds, holdout
  hash and power results are registered on OSF and in a signed git tag before the
  confirmatory run.
- **Claims register.** Every number in the findings report links to the query that
  produces it, the hashes of its input releases and the command that rebuilds it.
- **Replication kit.** The released Parquet tables and scripts recompute every
  headline number on a laptop in under an hour, without the raw logs.
- **Forensic replay.** The review bundle rebuilds any release from the original
  TSE bytes, verified by hash, on a clean machine.
- **Explorer.** Bilingual marimo notebooks over the released tables let readers
  inspect coverage, integrity results, residual maps, funnel plots and case
  packets, with every view exportable with its provenance.
- **Alternative specifications.** Documented switches (peer definition, covariate
  set, with or without round 1, model family) let a reviewer rerun the family under
  their own choices and compare.
- **Deviations and errata** are published in the same repository, dated and
  never rewritten.

## 12. Historical data

History improves peer definition and stress-tests the method; it is not a clean
control group. Harmonize section splits and mergers, electorate changes, timezone
rules, device generations, biometric workflows and number of contests. Do not
concatenate years as if they were independent observations. 2022 is in scope as a
negative control (section 7.6); 2018 remains a later stress test.

## References

- Barber, R. F. et al. (2023). [Conformal prediction beyond exchangeability](https://arxiv.org/abs/2202.13415).
- Bates, S. et al. (2023). [Testing for outliers with conformal p-values](https://doi.org/10.1214/22-AOS2244). *Annals of Statistics*.
- Benjamini, Y. and Yekutieli, D. (2001). [The control of the false discovery rate in multiple testing under dependency](https://doi.org/10.1214/aos/1013699998). *Annals of Statistics*.
- Chernozhukov, V. et al. (2018). [Double/debiased machine learning for treatment and structural parameters](https://doi.org/10.1111/ectj.12097). *Econometrics Journal*.
- Deckert, J., Myagkov, M. and Ordeshook, P. (2011). [Benford's Law and the detection of election fraud](https://authors.library.caltech.edu/records/5jbtk-8wn05). *Political Analysis*.
- Klimek, P., Yegorov, Y., Hanel, R. and Thurner, S. (2012). [Statistical detection of systematic election irregularities](https://doi.org/10.1073/pnas.1210722109). *PNAS*.
- Kobak, D., Shpilkin, S. and Pshenichnikov, M. (2016). [Integer percentages as electoral falsification fingerprints](https://doi.org/10.1214/16-AOAS904). *Annals of Applied Statistics*.
- Kulldorff, M. (1997). [A spatial scan statistic](https://doi.org/10.1080/03610929708831995). *Communications in Statistics: Theory and Methods*.
- Mebane, W. R. Jr. [Election forensics working papers](https://public.websites.umich.edu/~wmebane/), including the eforensics finite-mixture model (Ferrari, Mebane, McAlister and Wu 2019, and later papers).
- Meinshausen, N. (2006). [Quantile regression forests](https://www.jmlr.org/papers/v7/meinshausen06a.html). *JMLR*.
- Rozenas, A. (2017). [Detecting election fraud from irregularities in vote-share distributions](https://doi.org/10.1017/pan.2016.9). *Political Analysis*.
- Wasserstein, R. and Lazar, N. (2016). [The ASA statement on p-values](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf).
