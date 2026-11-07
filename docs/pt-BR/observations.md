# Observações de transparência e de operação

Document-ID: EA-OBSERVATIONS · Revision: 3 · Language: pt-BR

[English](../en/observations.md) · [Índice de implementação](implementation-index.md)

Este registro guarda dois tipos de constatação que não são resultados de
integridade:

- **Observações de transparência**: o que o TSE publica, como e em que estado.
- **Observações de operação**: como a eleição foi conduzida, na medida em que os
  artefatos auditados revelam procedimentos internos.

As duas importam para a auditoria. A primeira define o que pode ser verificado de
forma independente. A segunda define o que os dados significam: um procedimento
operacional explica sinais que, de outro modo, poderiam ser tomados por anomalias.

Uma observação é um fato datado e com fonte. Não é uma constatação sobre a contagem
dos votos nem evidência de intenção. Cada entrada declara seu efeito sobre a
auditoria. Entradas nunca são reescritas: uma resposta ou correção posterior é
acrescentada como resolução, com sua data.

## Transparência

| ID | Visto em | Observação | Evidência | Efeito sobre a auditoria | Situação |
| --- | --- | --- | --- | --- | --- |
| T1 | 2026-11-05 | Os certificados raiz (`AC RAIZ UE`, `AC RAIZ UE v2`) e o da `AC URNA v2` não são publicados, embora seus SHA-512 constem do resumo de software HOLOCRON do TSE (segundo cópia de terceiros) | Nenhuma cópia pública encontrada; o DataUrnas-BR relata o mesmo | As cadeias de certificados são verificadas só até as ACs intermediárias | Pedido ao TSE, protocolo 83529705172533 (2026-11-05), resposta devida até 2026-11-25 |
| T2 | 2026-11-05 | O certificado publicado da `AC URNA` venceu em 2026-07-18; sua chave assinou a lista de revogados da `AC URNA` em 2026-09-27; o certificado renovado não é publicado | `tse-format-docs-20261105/ca/acurna.der`; `tse-crls-20261105-complete/acurna.crl` | A emissora das urnas ECDSA é verificada pela chave, não por um certificado válido no dia da eleição | Pedido (protocolo de T1) |
| T3 | 2026-11-05 | A lista de revogados da raiz (`acraizue.crl`, número 16) foi emitida em 2024-10-04, com próxima atualização prevista para 2024-11-03, e não foi atualizada desde então | `tse-crls-20261105-complete/acraizue.crl` | Não é possível estabelecer se a `AC URNA` foi revogada em 2026 | Pedido (protocolo de T1) |
| T4 | 2026-11-05 | O documento de política citado nos certificados das urnas UE2020 (`http://dpc.acue2020.tse.jus.br/DPC-PC-ACUE2020.PDF`) retorna 404; o índice de políticas retorna 403; `dpc.acue2022.tse.jus.br` não resolve | Verificações com navegador e `curl` em 2026-11-05 | As práticas de certificação das ACs não podem ser lidas | Pedido (protocolo de T1) |
| T5 | 2026-11-05 | Documentos oficiais e listas de revogados retornam HTTP 403 a clientes que não são navegadores; as listas baixam em um navegador, que as marca como perigosas | Verificações com `curl` e navegador em 2026-11-05 | A coleta não pode ser totalmente automatizada, o que enfraquece a reprodutibilidade | Contornado por download manual e congelamento |
| T6 | 2026-11-05 | Não há vetores de teste publicados para o Ed521 (o DOC-ICP-01.01 do ITI traz só os parâmetros); o pacote de formatos de 2026 do TSE traz um verificador de referência | `tse-format-docs-20261105` (`python/lib/mr_util.py`) | A construção foi confirmada pelo código do próprio TSE, não por vetores | Resolvido pelo código de referência |
| T7 | 2026-11-05 | As especificações espelhadas por terceiros diferem do pacote de 2026 do TSE: rótulos de enumerações do BU e estrutura do arquivo de assinatura | Comparação com `election_audit/resources/*-mirrored.asn1` | A decodificação anterior usou as especificações espelhadas; os valores não mudam, rótulos e estrutura são corrigidos na Fase 20b | Pacote oficial congelado (SHA-256 `b5ac413e81121d53de2bb1657af611f84a45fdc84388e9d9821872994bbfbafd`) |
| T8 | 2026-11-05 | O relatório do teste de integridade do 2º turno ainda não foi publicado; o relatório consolidado do TCU é esperado por volta de 2026-11-24 | [Handoff da Fase 19](handoffs/task-19.md) | A evidência externa sobre o software dentro da urna está incompleta | Pendente |
| T9 | 2026-11-04 | A CDN pode servir cópias antigas em cache de arquivos de dados abertos a requisições HEAD e GET; o hash dos arquivos compactados muda a cada recompactação mesmo sem mudança de conteúdo | [Índice de implementação](implementation-index.md), Fase 19 | A identidade de um arquivo precisa vir do ETag, do tamanho e do conteúdo, nunca só da URL | `bulk-download` revalida e exige ETag e tamanho iguais |
| T10 | 2026-11-06 | Nenhum conjunto de dados do TSE informa o fuso horário de cada município; a lei (Decreto 2.784/1913, alterado pela Lei 12.876/2013) define uma linha de Tabatinga a Porto Acre, e os municípios do Amazonas a oeste dela só são nomeados em notícias do TRE-AM, cujo site retorna HTTP 403 a clientes que não são navegadores | [Notícia do TRE-AM de 2026-09-25](https://www.tre-am.jus.br/comunicacao/noticias/2026/Setembro/eleitorado-do-amazonas-deve-ficar-atento-aos-horarios-de-votacao-nas-eleicoes-2026), lida em navegador | A lista é fixada à mão (`resources/am-acre-time-municipalities.json`) e conferida com os encerramentos impressos pelas urnas | Contornado ([O12](#operação)) |

## Operação

| ID | Observação | Evidência | Efeito sobre a auditoria |
| --- | --- | --- | --- |
| O1 | Quando uma urna é substituída, seu pacote pode trazer o mesmo log duas vezes, da memória interna (`…MI.jez`) e da externa (`…ME.jez`) | Fase 22, casos de I5 do 1º turno com mais votos concluídos que comparecimento | As sessões são deduplicadas pela linhagem dos blocos ([tabela por seção](section-table.md#regras)) |
| O2 | O log do segundo turno contém toda a história da urna: preparação em setembro, 1º turno e 2º turno | Fase 21 | As sessões são selecionadas pelo turno, nunca pelo arquivo |
| O3 | Os relógios das urnas marcam a hora local; a votação termina às 17:00 de Brasília, então a leitura configurada de encerramento é 15:00 no AC; as urnas a imprimem quando alguém tenta encerrar antes da hora | Fase 22, AC 2026 e 2022 | O horário de encerramento é uma regra por município, não uma hora nacional |
| O4 | Operadores ajustam o relógio das urnas com o aplicativo ADH; as urnas registram ajustes de fuso na carga, e uma mensagem de ajuste de horário de verão aparece 7313 vezes no vocabulário do 2º turno de 2026, embora o Brasil não tenha horário de verão | Vocabulário da Fase 21; colunas v3 da Fase 22 | A evidência de relógio é registrada por sessão; medidas de horário exigem relógio resolvido |
| O5 | Na apuração de contingência (SA), o RDV é produzido pelo sistema de apuração, não pela urna; duas seções de SA de MG mostram 20 eleitores a menos no RDV que no BU (40 para senador) no 1º turno | I3 da Fase 20; DataUrnas-BR | A recontagem pelo RDV não é independente nas seções de SA; a conciliar com o DataUrnas-BR |
| O6 | A urna prevista difere da efetivamente usada em 3060 (1º turno) e 2721 (2º turno) seções; em todos os casos a urna efetiva confere com o BU | I9 da Fase 20 | Substituição de urna é comum e documentada pelos arquivos de correspondência |
| O7 | Dez eleições municipais realizadas com o 2º turno (871 disputas em 13 municípios) aparecem nos BUs mas não no BWEB | I2 da Fase 20 | Sua verificação I2 precisa de outra fonte (Fase 20b) |
| O8 | Os resultados EA20 do 1º turno do ZZ (186 cidades e o total do ZZ) foram regerados em 2026-10-24, depois da geração do 1º turno em 2026-10-05 | [Handoff da Fase 19](handoffs/task-19.md) | As verificações de hierarquia usam a regeração final |
| O9 | As autoridades certificadoras emitiram suas listas de revogados em 2026-09-27 com validade de 90 dias; a `AC URNA` revogou três certificados de urna em 2025-05-16 | `tse-crls-20261105-complete/` | A Fase 20b verifica que nenhuma assinatura de 2026 usa um certificado revogado |
| O10 | Os 29 pacotes de relatórios de totalização (`Relatorio_Resultado_Totalizacao_2026_<UF>.zip`: 27 UFs, BR, ZZ) são recompactados por uma rotina agendada a cada poucas horas (visto em 2026-11-03 às 11:30, 19:30 e 22:30 GMT, e em 2026-11-04 às 08:30 GMT) com membros inalterados; os PDFs dentro mudam após decisões judiciais: 18 PDFs do 1º turno foram regerados entre 2026-10-07 e 2026-10-24, inclusive RJ após a retotalização de governador e MS após a de deputado; todo relatório diz "sujeito a modificações" | [Referência de aquisição](acquisition-reference.md#relatórios-de-totalização-mudam-com-o-tempo) | Resultados publicados são retratos de um momento: a auditoria lê a hora do resultado impressa em cada PDF, compara retratos pelo CRC dos membros, não pelo hash do arquivo, e espera retotalizações por meses |
| O11 | No 2º turno de 2026, operadores atrasaram em cerca de uma hora o relógio das urnas com o ADH antes da votação em 82 seções de Mato Grosso (deslocamentos perto de −3600 s; três municípios, a maioria na zona 0053); nenhuma seção de Mato Grosso teve esse ajuste no 1º turno. A causa provável, urnas carregadas no horário de Brasília, não está confirmada | [Tabela por seção](section-table.md#resultados-nacionais), `clock_adh_shift_s` | Essas sessões são `adjusted`: suas leituras seguem o ajuste, e as medidas de horário as mantêm |
| O12 | Onze municípios do Amazonas seguem o horário do Acre (UTC−5) e encerram a votação às 15:00 locais: Amaturá, Atalaia do Norte, Benjamin Constant, Eirunepé, Envira, Guajará, Ipixuna, Itamarati, Jutaí, São Paulo de Olivença e Tabatinga; os outros 51 encerram às 16:00 locais. Em 2022 e em 2026, todo município do Amazonas cujas urnas imprimiram encerramento configurado às 15:00 está na lista, e nenhum da lista imprimiu 16:00 (10 dos 11 imprimiram em 2026, 9 em 2022). O DataUrnas-BR usa a mesma lista | Notícias do TRE-AM de [2024-08-26](https://www.tre-am.jus.br/comunicacao/noticias/2024/Agosto/onze-municipios-terao-horario-diferenciado-nas-eleicoes) (citando o art. 231 da Resolução TSE 23.736/2024) e de [2026-09-25](https://www.tre-am.jus.br/comunicacao/noticias/2026/Setembro/eleitorado-do-amazonas-deve-ficar-atento-aos-horarios-de-votacao-nas-eleicoes-2026); códigos do TSE, nomes e zonas em `eleitorado_local_votacao` de 2022 e 2026; Fase 20b | Seções do Amazonas sem encerramento impresso recebem a regra `am_list` ([tabela por seção](section-table.md#regras)); uma impressão que contradiz a lista continua `unresolved` |
| O13 | Em 17 seções o arquivo de assinatura foi assinado por uma urna diferente da indicada no BU: 14 no 1º turno (al/27057/0022/0581, ba/38857/0108/0148, es/56472/0024/0100, es/56995/0053/0028, es/57053/0001/0046, es/57053/0001/0413, ms/91570/0031/0007, pr/75280/0133/0034, pr/76236/0093/0083, rn/18813/0009/0144, se/31054/0001/0346, se/32417/0022/0133, sp/71072/0418/0073, sp/71072/0418/0418) e 3 no 2º turno (es/57932/0009/0085, rj/58696/0027/0139, sp/64777/0393/0312). Toda assinatura nelas confere com o certificado da própria urna signatária, emitido por uma AC do TSE e não revogado; em es/57932/0009/0085 a urna signatária é a urna do BU da seção 0112 da mesma zona. O procedimento que produziu isso não é documentado no material publicado | Seções de integridade v2 nacionais da Fase 20b, `cert_subject` contra `urn_serial`; seis das oito divergências de modelo do I9 da Fase 20 são essas seções | Os arquivos são saída autêntica de urna, mas o vínculo entre signatária e urna do BU não é; o I9 relata essas seções em vez de tratá-las como assinaturas com falha |

## Fontes

As entradas congeladas citadas acima ficam em `~/data/election-audit-stage/inputs/`:

| Diretório | Conteúdo |
| --- | --- |
| `tse-format-docs-20261105/` | O pacote de formatos de 2026 do TSE: o ZIP original, os arquivos extraídos com hashes e os certificados das ACs em `ca/` |
| `tse-crls-20261105-complete/` | As cinco listas de revogados, com `SHA256SUMS` |

O [DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) é comparado nos
[trabalhos relacionados](../../research/related-work.pt-BR.md).
