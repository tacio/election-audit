# Transparency and operational observations

Document-ID: EA-OBSERVATIONS · Revision: 4 · Language: en

[Português](../pt-BR/observations.md) · [Implementation index](implementation-index.md)

This register records two kinds of finding that are not integrity results:

- **Transparency observations**: what TSE publishes, how and in what state.
- **Operational observations**: how the election was run, as far as the audited
  artifacts reveal internal procedures.

Both matter to the audit. The first sets what can be verified independently. The
second sets what the data mean: an operational procedure explains signals that
could otherwise be mistaken for anomalies.

An observation is a dated, sourced fact. It is neither a finding about the vote
count nor evidence of intent. Each entry states its effect on the audit. Entries
are never rewritten: a later answer or correction is added as a resolution, with
its date.

## Transparency

| ID | Seen | Observation | Evidence | Effect on the audit | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | 2026-11-05 | The root certificates (`AC RAIZ UE`, `AC RAIZ UE v2`) and `AC URNA v2` are not published, though their SHA-512 values appear in TSE's HOLOCRON software summary (as cited from a third-party copy) | No public copy found; DataUrnas-BR reports the same | Certificate chains are verified up to the intermediate CAs only | Requested from TSE, protocol 83529705172533 (2026-11-05), reply due 2026-11-25 |
| T2 | 2026-11-05 | The published `AC URNA` certificate expired on 2026-07-18; its key signed the `AC URNA` revocation list on 2026-09-27; the renewed certificate is not published | `tse-format-docs-20261105/ca/acurna.der`; `tse-crls-20261105-complete/acurna.crl` | The ECDSA urns' issuer is verified by key, not by a certificate valid on election day | Requested (T1 protocol) |
| T3 | 2026-11-05 | The root's revocation list (`acraizue.crl`, number 16) was issued on 2024-10-04 with its next update due on 2024-11-03, and has not been updated since | `tse-crls-20261105-complete/acraizue.crl` | Whether `AC URNA` was revoked cannot be established for 2026 | Requested (T1 protocol) |
| T4 | 2026-11-05 | The policy document named in UE2020 urn certificates (`http://dpc.acue2020.tse.jus.br/DPC-PC-ACUE2020.PDF`) returns 404; the policy index returns 403; `dpc.acue2022.tse.jus.br` does not resolve | Browser and `curl` checks on 2026-11-05 | The CAs' certification practices cannot be read | Requested (T1 protocol) |
| T5 | 2026-11-05 | Official documents and certificate-revocation lists return HTTP 403 to non-browser clients; the revocation lists download in a browser, which flags them as dangerous | `curl` and browser checks on 2026-11-05 | Collection cannot be fully automated, which weakens reproducibility | Worked around by manual download and freezing |
| T6 | 2026-11-05 | No test vectors are published for Ed521 (ITI DOC-ICP-01.01 gives parameters only); TSE's 2026 format package contains a reference verifier | `tse-format-docs-20261105` (`python/lib/mr_util.py`) | The construction was confirmed from TSE's own code, not from vectors | Resolved by the reference code |
| T7 | 2026-11-05 | The specifications mirrored by third parties differ from TSE's 2026 package: BU enumeration labels and the signature-file structure | Comparison with `election_audit/resources/*-mirrored.asn1` | Earlier decoding used the mirrored specifications; values are unaffected, labels and structure are corrected in Phase 20b | Official package frozen (SHA-256 `b5ac413e81121d53de2bb1657af611f84a45fdc84388e9d9821872994bbfbafd`) |
| T8 | 2026-11-05 | The integrity test report for round 2 is not yet published; the TCU consolidated report is expected around 2026-11-24 | [Phase 19 handoff](handoffs/task-19.md) | External evidence about in-urn software is incomplete | Pending |
| T9 | 2026-11-04 | The CDN can serve stale cached copies of open-data files to HEAD and GET requests; archive hashes change on every re-zip even when contents do not | [Implementation index](implementation-index.md), Phase 19 | A file's identity must come from its ETag, length and contents, never from the URL alone | `bulk-download` revalidates and requires matching ETag and length |
| T10 | 2026-11-06 | No TSE dataset gives each municipality's time zone; the law (Decreto 2.784/1913 as amended by Lei 12.876/2013) defines a line from Tabatinga to Porto Acre, and the Amazonas municipalities west of it are named only in TRE-AM press notices, whose site returns HTTP 403 to non-browser clients | [TRE-AM notice of 2026-09-25](https://www.tre-am.jus.br/comunicacao/noticias/2026/Setembro/eleitorado-do-amazonas-deve-ficar-atento-aos-horarios-de-votacao-nas-eleicoes-2026), read in a browser | The list is pinned by hand (`resources/am-acre-time-municipalities.json`) and checked against the urns' printed closes | Worked around ([O12](#operations)) |

## Operations

| ID | Observation | Evidence | Effect on the audit |
| --- | --- | --- | --- |
| O1 | When an urn is replaced, its package can hold the same log twice, from internal (`…MI.jez`) and external (`…ME.jez`) memory | Phase 22, round-1 I5 cases with more completions than attendance | Sessions are deduplicated by block lineage ([section table](section-table.md#rules)) |
| O2 | A runoff log contains the urn's whole history: setup in September, round 1 and the runoff | Phase 21 | Sessions are selected by round, never by file |
| O3 | Urn clocks run on local time; voting closes at 17:00 Brasília time, so the configured closing reading is 15:00 in AC; urns print it when someone tries to close early | Phase 22, AC 2026 and 2022 | The closing time is a per-municipality rule, not one national hour |
| O4 | Operators set urn clocks with the ADH application; urns log time-zone adjustments when loaded, and a daylight-saving adjustment message appears 7313 times in the 2026 runoff vocabulary although Brazil has no daylight saving | Phase 21 vocabulary; Phase 22 v3 columns | Clock evidence is recorded per session; time-of-day measures need a resolved clock |
| O5 | In contingency counting (SA) the RDV is produced by the counting system, not by the urn; two MG SA sections show 20 fewer voters in the RDV than in the BU (40 for senate) in round 1 | Phase 20 I3; DataUrnas-BR | The RDV recount is not independent in SA sections; to be reconciled with DataUrnas-BR |
| O6 | The expected urn differs from the urn effectively used in 3060 (round 1) and 2721 (round 2) sections; in every case the effective urn matches the BU | Phase 20 I9 | Urn replacement is common and documented by the correspondence files |
| O7 | Ten municipal elections held with the runoff (871 contests in 13 municipalities) appear in the BUs but not in BWEB | Phase 20 I2 | Their I2 check needs another source (Phase 20b) |
| O8 | The EA20 round-1 results for ZZ (186 cities and the ZZ total) were regenerated on 2026-10-24, after the round-1 generation on 2026-10-05 | [Phase 19 handoff](handoffs/task-19.md) | Hierarchy checks use the final regeneration |
| O9 | The certificate authorities issued their revocation lists on 2026-09-27 with 90-day validity; `AC URNA` revoked three urn certificates on 2025-05-16 | `tse-crls-20261105-complete/` | Phase 20b checks that no 2026 signature uses a revoked certificate |
| O10 | The 29 totalization report packages (`Relatorio_Resultado_Totalizacao_2026_<UF>.zip`: 27 UFs, BR, ZZ) are re-zipped by a scheduled job every few hours (seen 2026-11-03 at 11:30, 19:30 and 22:30 GMT, and 2026-11-04 at 08:30 GMT) with unchanged members; the PDFs inside change after court decisions: 18 round-1 PDFs were regenerated between 2026-10-07 and 2026-10-24, including RJ after the governor retotalization and MS after the deputy retotalization; every report says "sujeito a modificações" | [Acquisition reference](acquisition-reference.md#totalization-reports-are-a-moving-target) | Published results are point-in-time snapshots: the audit reads the result time printed in each PDF, compares snapshots by member CRC, not by archive hash, and expects retotalizations for months |
| O11 | In 2026 round 2, operators set urn clocks back by about one hour with ADH before voting in 82 Mato Grosso sections (shifts near −3600 s; three municipalities, mostly zone 0053); no Mato Grosso section had such a setting in round 1. The likely cause, urns loaded on Brasília time, is not confirmed | [Section table](section-table.md#national-results), `clock_adh_shift_s` | These sessions are `adjusted`: their readings follow the setting, and time-of-day measures keep them |
| O12 | Eleven Amazonas municipalities keep Acre time (UTC−5) and close voting at 15:00 local: Amaturá, Atalaia do Norte, Benjamin Constant, Eirunepé, Envira, Guajará, Ipixuna, Itamarati, Jutaí, São Paulo de Olivença and Tabatinga; the other 51 close at 16:00 local. In both 2022 and 2026, every Amazonas municipality whose urns printed a configured close of 15:00 is on this list and none on it printed 16:00 (10 of the 11 printed in 2026, 9 in 2022). DataUrnas-BR uses the same list | TRE-AM notices of [2024-08-26](https://www.tre-am.jus.br/comunicacao/noticias/2024/Agosto/onze-municipios-terao-horario-diferenciado-nas-eleicoes) (citing Art. 231 of Resolução TSE 23.736/2024) and [2026-09-25](https://www.tre-am.jus.br/comunicacao/noticias/2026/Setembro/eleitorado-do-amazonas-deve-ficar-atento-aos-horarios-de-votacao-nas-eleicoes-2026); TSE codes, names and zones in `eleitorado_local_votacao` 2022 and 2026; Phase 20b | Amazonas sections without a printed close get the `am_list` rule ([section table](section-table.md#rules)); a print that contradicts the list stays `unresolved` |
| O13 | In 17 sections the signature file was signed by a different urn from the one named in the BU: 14 in round 1 (al/27057/0022/0581, ba/38857/0108/0148, es/56472/0024/0100, es/56995/0053/0028, es/57053/0001/0046, es/57053/0001/0413, ms/91570/0031/0007, pr/75280/0133/0034, pr/76236/0093/0083, rn/18813/0009/0144, se/31054/0001/0346, se/32417/0022/0133, sp/71072/0418/0073, sp/71072/0418/0418) and 3 in round 2 (es/57932/0009/0085, rj/58696/0027/0139, sp/64777/0393/0312). Every signature in them verifies with the signing urn's own certificate, issued by a TSE CA, not revoked; in es/57932/0009/0085 the signing urn is the BU urn of section 0112 of the same zone. The procedure that produced this is not documented in the published material | Phase 20b national integrity sections v2, `cert_subject` against `urn_serial`; six of the eight I9 model mismatches of Phase 20 are these sections | The files are authentic urn output, but the binding between signer and BU urn is not; I9 reports these sections instead of treating them as failed signatures |
| O14 | When an urn restarts, its first lines (`Início das operações do logd`, `Urna ligada em …`, `Estrutura de diretórios da ME: OK`, `Iniciando aplicação - #º turno`, the software version and the urn model) are written before `Iniciando registro do log na MI e na ME`, and some copies of a log lack them: in 97 round-1 block pairs the copy in the runoff log lacks these lines at one restart, and in 3 the round-1 log does | Phase 20b I6 prefix re-read (`integrity-round1-prefix-v1`), `differences.jsonl` | Copies of one urn's log are compared line by line, not by block fingerprint alone; these pairs are not content changes |
| O15 | The three copies of the 2026-10-04 log of urn 01760983 (rj/60011/0008/0061) disagree: the published round-1 log has 311 computed votes, equal to the BU attendance, and ends at 18:03:25; the external-memory copy carried in the runoff log has 305, ends at 18:25:46 and has corrupted bytes (`eleitmr digitadm`, `YDeputadm Dedepal]`); the internal-memory copy has 303 and ends at 18:12:33. In the round-1 log one line at 09:32:45 carries urn identifier 01740981 | Phase 20b I6 prefix re-read; Phase 20 I5 (log 36 completed, BU 311) | The published round-1 log is the copy that agrees with the BU; the I5 difference of this section comes from the broken stream, not from missing votes |

## Sources

The frozen inputs named above are under `~/data/election-audit-stage/inputs/`:

| Directory | Content |
| --- | --- |
| `tse-format-docs-20261105/` | TSE's 2026 format package: the original ZIP, extracted files with hashes, and the CA certificates in `ca/` |
| `tse-crls-20261105-complete/` | The five revocation lists, with `SHA256SUMS` |

[DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) is compared in
[related work](../../research/related-work.md).
