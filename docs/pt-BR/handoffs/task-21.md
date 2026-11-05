# Tarefa 21 — Passada semântica nacional dos logs

Document-ID: EA-HANDOFF-21 · Revision: 1 · Language: pt-BR

Objetivo: uma passada em fluxo por turno sobre todos os logs de urna elegíveis de
2026 e 2022, aplicando regras de mensagens revisadas e gravando agregados por
sessão, impressões digitais de segmentos de contexto e um vocabulário de modelos de
mensagem, com teste de equivalência contra o adaptador por evento do AC antes de
cada execução nacional.

Pré-requisitos: Fase 21 do [plano de conclusão](../../../research/completion-plan.pt-BR.md);
o [protocolo do estudo](../../../research/analysis-plan.pt-BR.md) (Revisão 3); as
entradas da Fase 19 ([handoff 19](task-19.md)); a cópia no SSD e as exclusões de
proteção `data/national/phase11-protection-2026-10-31/exclusions.json`.

Arquivos e interfaces: `election_audit/semantic_pass.py` (`semantic-pass run|equivalence`,
`session-aggregates-v2`), `election_audit/sevenzip.py`, `election_audit/sa_logs.py`
(`sa-logs fetch|summarize`), `election_audit/resources/real-log-rules.json` e
`real-log-rules-2022.json`, `election_audit/elections.py` (descritores de 2022),
`archive_parsing` e `operational_review` (7z e regras por ano). Cada execução grava
uma raiz nova com `binding.json`, `status.json`, shards e um `release/` com somas de
verificação; `--resume` exige um vínculo idêntico.

Entregas:

- 2026, dois turnos: 498580 e 498581 objetos, sem erros, 1704924 e 3393756
  sessões, em `~/data/election-audit-stage/phase21/national-r{1,2}-20261103/`
  (`session-aggregates-v1`). Os registros conciliam as 499207 seções por turno; os
  596 logs protegidos/de estresse continuam não lidos.
- 2022, dois turnos: 471859 e 471983 objetos, sem erros, 1805887 e 3570943
  sessões, em `~/data/election-audit-stage/phase21/national-2022-r{1,2}-v2-20261104/`.
  Os registros contabilizam 472024 e 472027 seções a partir dos nomes dos membros.
- Um leitor 7z só com a biblioteca padrão (codificadores LZMA, LZMA2 e cópia, todo
  CRC conferido, o resto recusado) e um modo em massa que lê os membros dos arquivos
  de 2022 em ordem física; o modo em massa recusa 2026.
- Regras de 2022: semântica exata de 2026 só onde o texto de 2022 é idêntico;
  marcadores de sessão, turno e software de 2022 lidos dos logs; mensagens sem par
  ficam desconhecidas.
- Os 60 logs de apuração de contingência SA, atribuídos às suas seções.

Aceitação (tudo em 4 de novembro de 2026, salvo indicação):

- Equivalência com o adaptador: AC 2026, 400 de 400 objetos (3 de novembro); AC
  2022, 200 de 200 por turno.
- Reprodução: uma execução v2 do AC 2026 (1674 objetos por turno) é igual às linhas
  nacionais v1 em todas as linhas de objetos, sessões e segmentos depois de converter
  as quatro colunas de segundos para `int64`.
- `UV_OFFLINE=1 just check` passa com 359 testes.
- Não tentado: conferir o registro de 2022 com o BWEB de 2022.

Decisões:

- O método de habilitação é analisado como biométrico contra todos os outros
  (manual, sem biometria e desconhecido juntos): só a biometria verifica o eleitor, o
  resto depende do mesário. O texto do marcador biométrico é idêntico em 2022 e 2026.
- A v2 ampliou as colunas de segundos para `int64` depois que o relógio de uma urna
  de 2022 reiniciou em 23/08/1933 e estourou o int32. As versões de 2026 continuam
  v1; leia-as com a conversão.
- A execução de 2022 do segundo turno falhou primeiro em um objeto (um 7z vazio
  aninhado); a correção do leitor só afeta objetos que antes falhavam, então o shard
  00844 foi refeito sob o mesmo vínculo.
- A primeira execução v1 do primeiro turno de 2022, que falhou, foi apagada.

Pendências:

- Falhas de relógio estão registradas mas não interpretadas: quatro sessões de 2022
  do primeiro turno reiniciam em 01/01/2009 (BA 39799/0106/0049 no meio de um voto) e
  PE 25097/0091/0032 em 23/08/1933 antes de um operador acertar a data (ADH). Regras
  de relógio e uma contagem de reinícios e correções ADH por seção são trabalho da
  Fase 22.
- Sessões com várias execuções oficiais por objeto ficam como observadas; agrupá-las
  é trabalho da Fase 22. As impressões digitais comparam segmentos inteiros; a
  comparação de blocos do primeiro turno (I6) precisa de comparação por prefixo.
- Seções de 2022 sem log: 54 seções do ZZ só com BU no primeiro turno, e as seções
  com BU e RDV MG 51390/0244/0091, RN 16918/0054/0090 (primeiro turno) e cinco
  seções do PA na zona 04650/0006 (segundo turno). A Fase 20 deve examiná-las com os
  arquivos de BU.

Próxima tarefa exata: verificações de integridade I1–I9 da Fase 20 sobre os arquivos
em massa de BU/RDV (incluindo `busa.dat`), assinaturas, correspondências e a
hierarquia EA20, e então a Fase 22. Arquivar o relatório consolidado do TCU sobre o
teste de integridade quando for publicado (por volta de 24 de novembro de 2026).
