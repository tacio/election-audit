# Tarefa 20b — Conclusão da integridade: verificações trazidas do DataUrnas-BR

Document-ID: EA-HANDOFF-20B · Revision: 4 · Language: pt-BR

Objetivo: executar nacionalmente, para 2026 e nos dois turnos, as verificações que o
DataUrnas-BR faz e que faltavam a este projeto: uma comparação do Ed521 com o
verificador do DataUrnas-BR, a zerésima em todo log, as cargas de urna contra os logs
de preparação do GEDAI, os nomes de pacotes nos logs contra as listas de hash do TSE e
as assinaturas JWS do TSE nos resultados publicados. Os itens anteriores da Fase 20b
(Ed521, certificados, prefixo do I6, I8, I3/I5) estão registrados no
[índice de implementação](../implementation-index.md) e no
[guia das verificações de integridade](../integrity-checks.md).

Pré-requisitos: [plano de conclusão](../../../research/completion-plan.pt-BR.md) Fase
20b; as passadas por seção `integrity-sections-v4`
(`phase20/national-r{1,2}-sections-v4-20261107`); os logs de 2026 copiados para o SSD
e as exclusões de proteção; as raízes de entrada do GEDAI; os snapshots EA20
`results-hierarchy/ea20-r{1,2}-20261104`.

Arquivos e interfaces:

- `election_audit/ed521.py` (gancho `observer`), `urn_pki.py` (vereditos das ACs
  observados), `ed521_crosscheck.py` (`ed521-crosscheck-v1`).
- `semantic_pass.py` (`session-aggregates-v5`: `markers.parquet`,
  `packages.parquet`).
- `zeresima.py` (`integrity-zeresima-v2`), `gedai.py` (`integrity-gedai-v3`),
  `hash_lists.py` (`integrity-hash-lists-v1`), `signature_errors.py`
  (`integrity-signature-errors-v1`), `signed_results.py`
  (`signed-results-fetch-v1`, `integrity-jws-v1`).
- CLI: `integrity-check ed521-crosscheck|zeresima|gedai|hash-lists|signature-errors|jws`
  e `results-hierarchy fetch-signed`.
- Testes: `tests/test_ed521_crosscheck.py`, `test_zeresima.py`, `test_gedai.py`,
  `test_hash_lists.py`, `test_signature_errors.py`, `test_signed_results.py` e os testes de marcadores e pacotes
  em `test_semantic_pass.py`.

Entregas:

- Releases em `~/data/election-audit-stage/`: `phase20b-ed521/national-r{1,2}-20261108`,
  `phase20b-zeresima/v5-national-r{1,2}-20261108` e
  `national-r{1,2}-zeresima-v2-20261109`, `phase20b-gedai/national-r{1,2}-gedai-v3-20261109`,
  `phase20b-hash-lists/national-v1-20261109`,
  `phase20b-signature-errors/national-r{1,2}-signature-errors-v1-20261109`,
  `phase20b-jws/signed-r{1,2}-20261108` e `national-r{1,2}-jws-v2-20261109` (a v1
  sem as listas de revogação). Os
  releases anteriores de zerésima e do GEDAI ficam como registro das primeiras regras.
- Entradas congeladas: `inputs/ed521-crosscheck-refs-20261108/`,
  `inputs/tse-www-20261108/` (listas de hash e manual JWS, baixados pelo usuário num
  navegador), `inputs/tse-jws-key-20261108/` e `inputs/tse-jws-crls-20261109/` (as
  duas listas de revogação, baixadas pelo usuário num navegador).
- Observações T11, T12, T13, O18 e O19 (resolvida pela verificação de erros de
  assinatura).

Aceitação (9 de novembro de 2026):

- Comparação do Ed521: 3193786 e 2827813 assinaturas (de urna e de AC), 0
  divergências, 0 erros de seção; 53 vetores, o DataUrnas-BR igual ao modo estrito em
  todos.
- Passe semântico v5: sessões, segmentos, objetos e vocabulário iguais aos da v4 linha
  a linha nos dois turnos; 5197232 e 10312157 marcadores.
- Zerésima v2: 498579 e 498580 seções aprovadas; uma reprovação em Z1 por turno, as
  duas seções da O17.
- GEDAI v2: 498444 e 498388 seções casadas, G2 nunca reprova; 482 (G1) e 284 (G3)
  seções ficam `zone_unpublished` (T11); 281 e 337 reprovações em G1, 268 e 267 delas
  em sp/0176; uma reprovação em G3 no 2º turno. O GEDAI v3 é igual ao v2 linha a linha
  e acrescenta `absent_detail`: das 13 e 70 seções isoladas em G1, a mídia não foi lida
  de volta depois da carga em 9 e 55, foi lida depois sem ela em 4 e 10, e nunca em 0
  e 5 (T13); os 112 arquivos `.sha512` dos arquivos do GEDAI conferem.
- Listas de hash: sete caminhos de programa não listados (T12); 86 linhas `ERRO` na
  inicialização (O19).
- Erros de assinatura: 0 reprovações nos dois turnos; 181 e 307 seções com erros em
  blocos oficiais; nenhum voto na sessão de um erro de verificação; um voto em curso
  depois de um erro de assinatura em uma seção por turno, lido nos logs.
- JWS: verificações da chave todas verdadeiras; 5786 arquivos por turno verificados,
  iguais aos arquivos simples e ao snapshot EA20; toda cópia alterada recusada.
- `UV_OFFLINE=1 just check` passa com 437 testes.
- JWS v2: as duas listas de revogação assinadas pelos emissores, vigentes no dia da
  eleição (25 de agosto a 23 de novembro de 2026) e vazias; resultados por arquivo
  iguais aos da v1.
- A Revisão 9 do protocolo registra as verificações suplementares e suas lacunas.
- Não feito: os arquivos de assinatura dos logs do GEDAI.

Decisões:

- A Z4 da zerésima reprova uma zerésima impressa depois de votos no seu fluxo, não uma
  segunda zerésima: reinícios e substituições imprimem novas (O18). A Z1 se aplica só a
  seções cujos blocos oficiais têm votos.
- As regras do GEDAI não são aplicadas numa zona cujos logs publicados não têm nada
  para casar; essas seções ficam indisponíveis, não reprovadas. Uma zona com algum
  casamento mantém suas reprovações, então sp/0176 continua reprovada.
- Um erro de assinatura é `verification` ou `signing` pelo seu modelo. Votos depois de
  um reinício são contados, não reprovados, porque um reinício repete as verificações
  de inicialização; depois de um erro de assinatura o único voto em curso é permitido
  (E2).
- Uma reprovação em G1 do GEDAI continua reprovada, diga o que disser
  `absent_detail`: o detalhe descreve a publicação, com dois relógios diferentes, e
  não prova por que falta uma carga.
- As listas de hash são comparadas por nome e resultado; o ano do modelo num nome é
  relatado como `model_suffix`, não como casamento.
- A chave JWS vem do manual do TSE (apêndice B), não dos arquivos `.jws` nem do
  DataUrnas-BR, que só a confirma.
- O host www do TSE recusa downloads automatizados; seus arquivos são baixados pelo
  usuário num navegador e congelados, nunca obtidos com um cliente disfarçado.

Questões em aberto:

- GEDAI: sp/0176 (169 de 437 seções casadas, sem mídias de carga; 192 das suas
  reprovações têm uma mídia nunca lida de volta) e as 13 e 70 seções isoladas em G1
  (T13): por que faltam as correspondências das cargas tardias não está estabelecido.
  Os dois casos podem ir ao TSE no próximo pedido.
- As assinaturas dos logs do GEDAI (`.vsc`) não são verificadas: formato não revisto.
- A memória agregada dos seis workers da comparação do Ed521 não foi medida.

Próxima tarefa exata: a Fase 23 do [plano de conclusão](../../../research/completion-plan.pt-BR.md),
só com dados de desenvolvimento. Antes do seu congelamento, acrescentar ao
[protocolo do estudo](../../../research/analysis-plan.pt-BR.md) a resposta do TSE
sobre os certificados raiz (devida até 25 de novembro de 2026) e o relatório do TCU.
