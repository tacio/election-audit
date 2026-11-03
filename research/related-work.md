# Related work

Document-ID: EA-RELATED-WORK · Revision: 2 · Language: en

[Português](related-work.pt-BR.md) · [Research protocol](analysis-plan.md) · [README](../README.md)

## Scope and evidence

This project sits at the intersection of electoral-data engineering, reconciliation
of published election artifacts, and statistical election forensics. This focused
review compares relevant Brazilian open-data projects and methodological work;
it is not a systematic literature review or a claim of priority. Public project
pages and selected source files were consulted on 30 October 2026. Their reported
results are attributed to their authors and have not been independently reproduced
here. Branch links are mutable; adopting external code requires a pinned revision,
license review and validation against preserved TSE originals.

## Brazilian electoral-data infrastructure

[Turicas' eleicoes-brasil](https://github.com/turicas/eleicoes-brasil/tree/develop)
provides extraction and normalization of TSE electoral datasets. Its
[extractors](https://github.com/turicas/eleicoes-brasil/blob/develop/extractors.py)
illustrate declared headers and source-specific transformations. Our pipeline
shares this emphasis on explicit schemas, while adding frozen original-byte
snapshots, record witnesses and immutable parent-linked releases. Historical ETL
support does not establish compatibility with the current BWEB layout. Our
verified adapter is itself restricted to the reviewed 2026 presidential-runoff
layout and real AC validation; broader compatibility remains to be established.

[INEMA's eleicoes2026](https://github.com/inematds/eleicoes2026) addresses live
result dissemination. Its [data contract](https://github.com/inematds/eleicoes2026/blob/main/contrato/README.md)
separates collection from presentation and distinguishes result denominators.
These concerns also matter in an audit: intermediate responses can describe
different publication states. Our analyses instead operate on explicitly frozen
populations and retain source versions, corrections and unknown states. This
supports reproducibility after live feeds change. It does not establish that
our current partial derived population represents the country.

## Reconciliation of published returns

[Multiverso Digital's BWEB conference](https://www.multiversodigital.com.br/eleicoes2026/metodo.php)
describes importing the 28 UF/overseas archives, checking published SHA-512
checksums, and comparing aggregated BWEB votes with official result JSON. It
emphasizes equal geographic scope, aggregated sections and candidate-status
reclassification. Our AC adapter already checks source checksums and section
accounting, but does not yet perform final hierarchical reconciliation. Its
national coverage and reconciliation are useful implementation precedents,
not capabilities we can claim from our AC checks.

[AnaliseEleicoes](https://github.com/radzki/AnaliseEleicoes) combines statistical
comparisons with historical elections and reconciliation against separate TSE
publications. The authors report runoff agreement across 6,292 municipality–zone
units and with the totalization report at national, UF and overseas levels.
Our next reconciliation should similarly compare candidate and accounting
metrics over an explicit common population. Agreement at aggregate levels alone
cannot identify which competing BU version was included, nor rule out offsetting
section-level discrepancies. Section/version linkage remains a separate check.

Both examples motivate a distinction in our terminology: a separately published
TSE result is an external reconciliation reference relative to our BU import,
but not an independent measurement of voter intent. Summing the same imported
BWEB rows again would not supply an external reference. Even agreement between
separate TSE products checks consistency within a partly shared production chain.

## Binary artifacts and zero-vote sections

[DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) describes decoding
binary BUs, logs and signature artifacts, parallel totalization, UF-level result
reconciliation, and Parquet publication. It is the closest engineering comparison
among the projects reviewed. We share the need to reconstruct operational history
and preserve exceptional cases, but our implemented evidence currently covers
structural/log processing and a verified AC CSV import. Binary-BU decoding,
cryptographic certification and final-result linkage remain gaps in our pipeline.
External parsers are candidates for validated reuse, rather than substitutes for
checking their schemas, trust assumptions and behavior on exceptional files.

[Wesley Cota's zero-vote analysis](https://g.wcota.me/eleicoes2026/) links section
results to historical context and individual TSE urn artifacts. Its method states
that the section-voting CSV omits a candidate row when the candidate has no votes.
This is directly relevant to our incomplete choice ledgers, but the observation
concerns a particular dataset: it does not by itself prove identical omission
semantics in every BWEB edition or establish that a missing section has zero votes.
Our derived ledger can record a zero once the applicable sparse-format rule and
complete contest/section coverage have been verified, retaining the original
absence and the evidence used. Until then, missing choices remain unknown.

TSE's [EA18 specification](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
distinguishes section status from received-file hash status, including totalized,
rejected and excluded versions. Its [EA20 specification](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado)
provides hierarchical results and distinguishes completed counting from final
totalization. These official contracts offer a concrete path to resolving our
status and reference gaps. They still require acquired bytes and a verified
mapping between the selected binary BU and the CSV result record.

## Statistical election forensics

[Klimek et al. (2012)](https://doi.org/10.1073/pnas.1210722109) study turnout–vote
patterns using a parametric model of systematic irregularities. Their work
connects a statistical pattern to a proposed mechanism. Applying such an approach
to another election requires validating its baseline and assumptions; an extreme
turnout/share combination is not, by itself, a count of fraudulent ballots.
AnaliseEleicoes and DataUrnas-BR illustrate the practical interest in statistical
screening alongside integrity checks. Our design separates integrity, conditional
unusualness and possible outcome impact, so a screening result cannot silently
become a causal or national-impact claim.

The proposed conditional model draws on [Meinshausen's quantile regression
forests (2006)](https://www.jmlr.org/papers/v7/meinshausen06a.html), which estimate
conditional outcome quantiles. The [research protocol](analysis-plan.md) proposes
matched empirical baselines and geography-aware evaluation before interpreting
such estimates. [Bates et al. (2023)](https://doi.org/10.1214/22-AOS2244) provide
conformal outlier-testing methods under stated assumptions. Our election data do
not automatically satisfy those assumptions: geographic dependence, repeated
locations and adaptive inspection require explicit treatment. The implemented
analysis foundation records partitions, access and exploratory/null results;
it has not fitted the proposed model or established valid fraud p-values.

## Position of this project and remaining work

The intended contribution is an auditable connection from frozen source bytes,
through operational and electoral evidence, to explicitly qualified analysis.
The implemented emphasis is traceability, versioned populations and unavailable
states when an interpretation lacks evidence. This is a design emphasis relative
to the reviewed work, not a demonstrated unique feature or superior detector.

| Dimension | Relevant precedent | Current position here |
| --- | --- | --- |
| Schema-aware electoral ETL | Turicas | Pinned official AC BWEB adapter; normalized import contracts. |
| Publication versions and denominators | INEMA | Frozen inputs and immutable derivatives; partial derived populations. |
| Hierarchical result reconciliation | Multiverso Digital; AnaliseEleicoes | AC published-row arithmetic and UF totals match; national BR/UF/municipal/ZZ reconciliation pending. |
| Binary BU/log/signature integration | DataUrnas-BR | Log pipeline and national runoff structural summaries done; AC binary BU content verified against BWEB; signatures and RDV pending. |
| Omitted zero-vote choices | Cota | Explicit unknowns; evidence-backed sparse-to-complete normalization pending. |
| Conditional statistical screening | Klimek et al.; Meinshausen; Bates et al. | Research design, protected protocol and one AC development turnout fit; no national model or validated fraud inference. |

The AC reconciliation pilot is done for the runoff: all 2270 AC sections are
content-verified between binary BU and BWEB, with UF totals matching EA20. The next
steps are national: the same verification for every UF and both rounds, signature
and RDV checks, and hierarchy reconciliation including ZZ. Eligibility should follow
the evidence for each result and measure. Unresolved clocks can block timing claims
without blocking independently verified count arithmetic. National inference and
independent corroboration of voter intent remain separate research requirements.
