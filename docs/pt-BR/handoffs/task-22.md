# Tarefa 22 — Tabela de atributos por seção v2

Document-ID: EA-HANDOFF-22 · Revision: 1 · Language: pt-BR

Objetivo: uma linha por seção principal e turno, para 2026 e 2022, com o mapeamento
entre turnos, covariáveis do perfil do eleitorado, chaves de local de votação,
modelo e software da urna, regra de relógio, situação de integridade, medidas
operacionais e um registro da população, construída a partir de entradas
congeladas e sem ler resultados ou valores operacionais fora da UF de
desenvolvimento.

Pré-requisitos: [plano de conclusão](../../../research/completion-plan.pt-BR.md)
Fase 22; o [protocolo do estudo](../../../research/analysis-plan.pt-BR.md), seções 2
e 7; as entradas da Fase 19 ([handoff 19](task-19.md)), as versões da Fase 20
([handoff 20](task-20.md)) e a passada semântica da Fase 21 ([handoff 21](task-21.md));
as exclusões de proteção `data/national/phase11-protection-2026-10-31/exclusions.json`.

Arquivos e interfaces: `election_audit/semantic_pass.py` (`session-aggregates-v3`),
`election_audit/section_table.py` (`section-table build`, `section-features-v2`),
`tests/test_section_table.py`, `election_audit/cli.py`, `justfile`;
[tabela por seção](../section-table.md), [passada semântica](../semantic-pass.md#versão-3-fase-22),
[registro de observações](../observations.md). Uma construção grava uma raiz nova
com `release/` (`sections.parquet`, `units.parquet`, `ledger.json`, `manifest.json`
e `restricted/`); a saída precisa ser nova.

Entregas:

- Passada semântica v3, nos dois anos e turnos, em
  `~/data/election-audit-stage/phase22/v3-national-r{1,2}-20261105/` e
  `v3-national-2022-r{1,2}-20261105/`: 1704924, 3393756, 1805887 e 3570943
  sessões, sem erros por objeto.
- Tabelas por seção em `~/data/election-audit-stage/phase22/table-2026-20261106/`
  (998496 linhas, 499248 unidades) e `table-2022-20261106/` (945386 linhas, 472693
  unidades).
- Deduplicação de cópias pela linhagem dos blocos, regras legais de encerramento
  com o Amazonas resolvido pelos encerramentos impressos, estados do relógio,
  unidades harmonizadas e o registro.
- Entrada O11 do registro de observações (ajustes de relógio em Mato Grosso no 2º
  turno).
- Não produzido: nenhuma leitura de resultados ou valores operacionais fora do AC;
  situação de integridade de 2022 (a Fase 20 não rodou para 2022).

Aceitação (5–6 de novembro de 2026):

- Todo shard de sessões das quatro execuções v3 tem as nove colunas novas; toda
  coluna em comum com as versões anteriores (2026 v1, 2022 v2) é igual em todas as
  linhas de sessões, segmentos e objetos, nos dois sentidos.
- As contagens públicas das tabelas estão no
  [guia da tabela por seção](../section-table.md#resultados-nacionais). Toda unidade
  é `same_principal`; o registro conta todas as seções de cada turno.
- A construção por blocos é igual em conteúdo à construção anterior por UF (todo
  arquivo Parquet, nos dois sentidos, e o registro) em SP 2022 e nas duas tabelas
  nacionais; o pico de memória caiu de 5.2 GB para 3.9 GB (2026) e 3.3 GB (2022).
- `UV_OFFLINE=1 just check` passa com 381 testes.

Decisões:

- Cópias de uma sessão são reconhecidas pelo dispositivo, pelo início do bloco e
  pela posição no bloco, nunca pelo texto ou pelo horário; a igualdade das cópias
  como prefixos fica para a Fase 20b.
- Os relógios das urnas são locais. O encerramento esperado vem dos fusos legais;
  no Amazonas, só dos encerramentos impressos unânimes de um município, senão fica
  não resolvido.
- O modelo do lado do BU é comparado com o da última sessão mantida, porque
  sessões anteriores podem ser de uma urna substituída.
- A construção guarda linhas em Python para municípios inteiros de uma UF por vez
  (cerca de 10000 seções), com limite de 1 GB no DuckDB, para caber nos 6 GiB ao
  lado de uma passada em execução.
- A máquina suspendeu duas vezes durante as execuções (5 de novembro 20:58–21:51 e
  23:10–06:56). As passadas retomaram sem erros; um bloqueio de suspensão não
  impediu a segunda, então execuções longas precisam da suspensão automática do
  desktop desligada.

Questões em aberto:

- Oito seções do 1º turno de 2026 cujo modelo do log difere do de quem assinou o
  BU, e 704 seções do Amazonas sem regra de encerramento em 2022 (94 em 2026): Fase
  20b.
- A tabela de 2026 rodou ao lado da passada de 2022 com cerca de 6.9 GB no total,
  acima dos 6 GiB, antes de a construção por blocos corrigir isso; nada falhou, e mais de
  20 GB de RAM ficaram disponíveis.

Próxima tarefa exata: Fase 20b em `../election-audit-20b` (branch
`phase-20b-integrity`): especificações ASN.1 oficiais, cadeias de certificados no
país todo com os seriais revogados, nova execução nacional do I1, releitura por
prefixo do I6, as verificações do DataUrnas-BR e os itens da Fase 22. Perguntar
pela resposta do TSE (protocolo 83529705172533) depois de 25 de novembro de 2026.
