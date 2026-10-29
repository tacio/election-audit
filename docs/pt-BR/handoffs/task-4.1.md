# Tarefa 4.1 — Decodificação limitada de arquivos

Document-ID: EA-HANDOFF-4.1 · Revision: 1 · Language: pt-BR

Objetivo: decodificar membros JEZ/ZIP congelados sem extrair caminhos nem ocultar
ocorrências duplicadas. Pré-requisitos: [3.3](task-3.3.md), contratos de origem/linhagem.

Arquivos/interfaces: `election_audit/archive_parsing.py`, `_Parser.archive`,
`ParseConfig`; [guia bilíngue](../archive-parsing.md). A entrada de produção
exclusiva de congelados é `parse_snapshot`; caminhos brutos originais no inventário
são somente evidência.

Entregas: verificação do diretório antes da alocação de metadados ZIP, validação
em fluxo de CRC/tamanho de todos os membros permitidos, arquivos temporários
limitados em disco para arquivos aninhados, localizadores com nomes originais,
ocorrências duplicadas e índices de membros, problemas explícitos de tamanho,
profundidade, contagem e formato. Nenhum caminho arbitrário de membro é extraído.
ZIP64, múltiplos discos e layouts não padronizados continuam explicitamente não
suportados.

Aceitação: os comandos abaixo terminaram com código 0; passaram todas as 15
fixtures do analisador, incluindo arquivos/logs aninhados duplicados, corrupção
de CRC em membros selecionados e outros, logs ausentes, contagens falsas no
diretório e limites de arquivo/membro/expansão/profundidade. A verificação final
passou 83 testes offline, Ruff, lock, contratos e documentação.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
```

Decisões: nomes repetidos são ocorrências legítimas; nomes do arquivo externo
ficam nas associações congeladas de observações/pacotes. Falhas de CRC não emitem
eventos do membro danificado. Limites tornam artefatos parciais, nunca completos
silenciosamente. Pendente: variantes não suportadas exigem adaptador versionado;
não houve operação no acervo real, de rede ou Git. A aquisição permanece intacta.

Próxima: [4.2](task-4.2.md), linhas/eventos estruturais; ler somente esta passagem,
o guia e as convenções de localizadores/identidade de eventos.
