# Tarefa 4.3 — Cache imutável e publicação da análise

Document-ID: EA-HANDOFF-4.3 · Revision: 1 · Language: pt-BR

Objetivo: analisar conteúdo idêntico uma vez, conservando toda associação congelada
de origem, pacote e snapshot. Pré-requisitos: [4.2](task-4.2.md), [guia de
snapshots](../snapshots.md), contratos relevantes de origem/linhagem/problemas.

Arquivos/interfaces: `election_audit/archive_parsing.py`, CLI `parse`, receita `just
parse`, [guia bilíngue](../archive-parsing.md), `tests/test_archive_parsing.py`.
`parse_snapshot(snapshot, store, config=ParseConfig())` retorna o caminho da publicação.

Entregas: identidade de cache por conteúdo/analisador/configuração, artefatos e
diagnósticos imutáveis com checksum em fluxo, reutilizações verificadas, publicação
atômica/fsync/travas derivadas, recuperação de interrupção e quarentena de caches
corrompidos. A publicação imutável separada
`parses/PUBLICATION_DIGEST/parse.json` conserva snapshot, observações, ativos de
pacote, tabelas de contexto, histórico desconhecido, ativos ausentes e cobertura
completa. `cache/KEY/` contém eventos/problemas e `artifact.json` com checksum.

Aceitação: os comandos abaixo terminaram com código 0: 15 fixtures do analisador;
83 testes do repositório, lock, Ruff, contratos e documentação bilíngue; ajuda da
receita utilizável. A análise sintética pela CLI passou também após remover os
objetos brutos originais. Vários pacotes e um segundo snapshot reutilizam um
artefato de conteúdo com todas as associações preservadas; fixtures de corrupção
e interrupção se recuperam. ResourceWarnings existentes do coletor não são fatais.
Sem acervo real, rede ou operação Git; aquisição intacta.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just parse --help
```

Decisões: `iter_event_witnesses(path)` transmite `witness_event_id` por
snapshot/observação, `event_id` de conteúdo compartilhado e todos os ativos de
pacote; `iter_lineage(path)` e `iter_parsing_issues(path)` emitem linhas no formato
dos contratos. `inspect_parse(path)` verifica publicação e cache independentemente
das entradas brutas. `source_line_sha256` é evidência exata da linha física original,
incluindo terminadores, não regra de equivalência. Todos usam
`selection_state=context_unresolved`.

Pendente: somente três classes exatas VOTA são decodificadas em `jez-structural-v1`;
extensões exigem adaptador versionado. Variantes ZIP não suportadas e artefatos
parciais limitados continuam explícitos. Sem sessões, ciclos, conversão de fuso
ou construção DuckDB.

Próxima: **Fase 5**, reconstrução operacional. Passar somente esta passagem,
[índice](../implementation-index.md), guia de arquivos, contratos relevantes de
sessão/dispositivo/evento/ciclo/linhagem e referências de formato necessárias.
Ler testemunhos da publicação e `context_tables` congeladas; conservar limites de
origem/analisador e denominadores dos índices completos. Nunca somar testemunhos
de pacotes nem deduplicar apenas por horário/tipo. Acervo real permanece na Fase 9.
