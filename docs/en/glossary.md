# Glossary

Document-ID: EA-GLOSSARY · Revision: 1 · Language: en

[Português](../pt-BR/glossary.md)

| English | Português | Meaning |
| --- | --- | --- |
| election | eleição | Official year/pleito/election/round scope. |
| contest | disputa | Office/cargo and jurisdiction within election. |
| registered section | seção registrada | Administrative member before aggregation. |
| principal section | seção principal | Terminal section responsible for a composed electorate. |
| composition crosswalk | correspondência de composição | Snapshot-specific member-to-principal assignment; not a vote multiplier. |
| polling location | local de votação | Election-scoped place; a cluster for splits/peers. |
| candidacy | candidatura | Official contest-specific candidate identity. |
| vote choice | escolha de voto | Candidate or blank/null/special/unresolved category. |
| physical device | dispositivo físico | Evidenced hardware identity, separate from model/software. |
| software configuration | configuração de software | Observed version/build/configuration identity. |
| source object | objeto de origem | Exact original bytes identified by local SHA-256. |
| source observation | observação de origem | Immutable attempt to observe URL-to-object mapping. |
| source package | pacote de origem | Official package context; its ID is not assumed a byte digest. |
| snapshot | snapshot | Frozen input inventory, expected population and policy. |
| result version | versão de resultado | Immutable BU/result observation, including conflicts/corrections. |
| canonical result | resultado canônico | One eligible selected version per snapshot/principal/contest. |
| voting session | sessão de votação | Reconstructed physical operational session; may span packages. |
| anonymous cycle | ciclo anônimo | Operational voter cycle without candidate or voter identity. |
| lineage | linhagem | Derived-row links to original object/member/record evidence. |
| readiness | prontidão | Feature/unit availability after validating inputs and denominator. |
| receipt / processing | recebimento / processamento | Distinct publisher lifecycle events. |
| generation / publication | geração / publicação | Artifact creation and public availability; distinct events. |
| observation | observação | Client retrieval/observation time, not source event time. |
| device time | horário do dispositivo | Original naive clock reading before validated conversion. |
| after17 | after17 | Domestic completion strictly after 17:00:00 Brasilia; overseas separate. |
| strict unanimity | unanimidade estrita | Positive total, all ballots one candidate, no other categories. |
| exchangeability | permutabilidade | Sampling assumption needed for rank calibration; not implied by clusters. |
| FDR | FDR | Expected fraction of false rejections among rejections, zero if none; not fraud probability. |
| conditional impact bound | limite condicional de impacto | Arithmetic range under explicit mechanism/population/cap. |

Code/table/field identifiers are identical in both languages; translations describe
their meaning without renaming public interfaces. See the [dictionary](schema-dictionary.md).
