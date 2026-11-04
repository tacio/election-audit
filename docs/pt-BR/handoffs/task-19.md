# Tarefa 19 — Entradas nacionais

Document-ID: EA-HANDOFF-19 · Revision: 1 · Language: pt-BR

Objetivo: obter e congelar, com somas de verificação e manifestos imutáveis, todas
as entradas nacionais que as Fases 20–26 revisadas leem: BWEB dos dois turnos de
2026 e de 2022; BUs binários, RDVs, assinaturas e logs; os resultados hierárquicos
EA20; perfil do eleitorado e locais de votação; correspondências de mídias; logs de
preparação GEDAI; os relatórios do teste de integridade do dia da eleição; e os
manifestos certificados fixados.

Pré-requisitos: Fase 19 do [plano de conclusão](../../../research/completion-plan.pt-BR.md);
a coleta e a migração certificada da Fase 10 ([handoff 10](task-10.md)); a
[referência de aquisição](../acquisition-reference.md).

Arquivos e interfaces: `bulk_acquisition` (`bulk-download fetch|verify`),
`sa_logs` (`sa-logs fetch|summarize`), `results_hierarchy`
(`results-hierarchy fetch`, `results-hierarchy-v1`), `integrity_documents`
(`integrity-docs ingest`, `integrity-documents-v1`), o arquivo de hashes fixados
`election_audit/resources/pins/certified-manifests-2026.json` e as receitas
correspondentes do `justfile`. Cada coleta grava numa raiz nova, guarda os corpos
endereçados por conteúdo e somente leitura, e mantém URL de origem, ETag e
Last-Modified.

Entregas:

- Dados abertos (CKAN): BWEB, resultados, perfil do eleitorado e locais de
  votação, e correspondências de mídias de 2026 e 2022, além dos logs GEDAI de
  2026. Os 12 conjuntos pequenos estão completos, com todo `.sha512` publicado
  coincidindo.
- Arquivos em massa de BU/RDV/log: 56 por ano (2026: 219.2 GB, 2022: 168.5 GB),
  com hashes recalculados contra seus manifestos em 2026-11-04.
- Logs de contingência SA: todos os 60 (31 e 29), idênticos byte a byte aos
  arquivos em massa.
- EA20: 5815 arquivos por turno (BR, 27 UFs e ZZ, 5757 municípios e arquivos de
  andamento), todo arquivo unificado final. O segundo turno foi gerado em
  2026-10-25. O primeiro foi gerado em 2026-10-05, exceto todo o ZZ (186 cidades e
  o total do ZZ), regerado em 2026-10-24.
- Manifestos certificados: hashes fixados; as duas cópias de cada manifesto e os
  dois certificados conferem em 2026-11-04. O manifesto obsoleto de antes da
  separação continua documentado na
  [referência de aquisição](../acquisition-reference.md).
- Documentos do teste de integridade: amostra de dez tribunais coletada no
  navegador (SP, AC, AL, DF, ES, PR, MG, RJ, BA, RS), com 125 documentos
  arquivados por SHA-256 e um link quebrado registrado como não servido.

Aceitação: `just check` passa com 348 testes. Execuções reais:
`results-hierarchy fetch` nos dois turnos (5815 arquivos cada, 0 não finais);
`integrity-docs ingest` (125 arquivados, 0 faltando, 1 não servido); o SHA-256 das
duas cópias dos manifestos e dos certificados é igual aos hashes fixados.

Decisões:

- EA20 e os relatórios de totalização mudam após retotalizações, então toda coleta
  é um retrato datado. Cada linha EA20 guarda o carimbo de geração do próprio
  arquivo.
- Documentos de integridade são associados aos registros por SHA-256, nunca pelo
  nome, porque navegadores renomeiam downloads.
- Os sites dos TREs recusam requisições automatizadas. Eles foram lidos no próprio
  navegador do usuário, sem alterar a identidade das requisições.
- Os documentos de integridade são uma amostra. Os tribunais publicam coisas
  diferentes: SP, DF, ES, MG, RJ e BA publicam atas dos testes; AC, AL, PR e RS
  publicam só as listas de urnas sorteadas.

Pendências:

- Documentos de integridade dos outros 17 tribunais. O TCU acompanhou os testes
  nas 27 UFs e deve enviar ao TSE um relatório consolidado em até 30 dias após o
  segundo turno; arquivá-lo como fonte nacional quando for publicado.
- A regeração do ZZ do primeiro turno em 2026-10-24 não está explicada. A Fase 20
  precisa compará-la com os resultados SA do ZZ (`busa.dat`).
- Quatro documentos da amostra são um ZIP, um RTF, um CSV e uma planilha
  OpenDocument. Seus tipos de mídia estão registrados; o conteúdo não é
  interpretado.

Próxima tarefa exata: Fase 21 de 2022 (revisão das regras, equivalência, execução
nacional) e depois a Fase 20. A Fase 20 lê os arquivos em massa de BU/RDV
(incluindo `busa.dat`), as raízes EA20 em
`~/data/election-audit-stage/results-hierarchy/`, as correspondências e os
manifestos fixados.
