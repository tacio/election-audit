# Tarefa 3.3 — CLI de snapshots imutáveis

Document-ID: EA-HANDOFF-3.3 · Revision: 1 · Language: pt-BR

Objetivo: congelar entradas revisáveis e reiniciáveis que downloads não alterem.
Pré-requisitos: [3.2](task-3.2.md), contratos de fontes/snapshot/cobertura/linhagem.

Arquivos/interfaces: `election_audit/snapshots.py`; `create_snapshot`,
`publish_snapshot`, `inspect_snapshot`, `snapshot_tables`. Adaptadores CLI em
`election_audit/cli.py`; receitas utilizáveis `just snapshot` e `just snapshot-inspect`.
O [guia em pares](../snapshots.md) define opções, saída e identidade. `--source`
segue marcador; `--store` fica fora da raiz original. `--section` opcional repetido
limita arquivos, mantendo denominadores completos das UFs selecionadas.

Entregas: cópias independentes verificadas por SHA-256, publicação atômica por
diretório temporário/rename com fsync e trava separada, reserva de espaço,
identidade imutável, JSON com checksum, esquema/runtime/implementação/seleção
congelados, inspeção independente e validação de linhas/chaves estrangeiras,
preservando falhas e desconhecidos. A mesma captura/implementação republica
idempotentemente; nova captura tem novo horário e pode receber novo ID. `inspect`
legado e aquisição ficam inalterados. Sem arquivos compactados, DuckDB/Parquet,
importação de BU, resultados canônicos, reconstrução eleitoral ou ajuste.

Aceitação: comando completo final abaixo terminou com código 0: lock, Ruff
format/lint, metadados dos contratos, documentos em pares e 66 testes offline,
incluindo 23 específicos de inventário/população/snapshots. `--help` das duas novas
receitas terminou com código 0. Sem acervo real, inventário nacional, rede ou Git.
ResourceWarning existente do coletor permanece não fatal.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just snapshot --help
rtk proxy env UV_OFFLINE=1 just snapshot-inspect --help
```

Decisões: consumidores chamam `inspect_snapshot(path, verify_objects=True)` e
`snapshot_tables(document)`. `source_object.storage_locator` é relativo ao diretório
concluído; não reabrir caminhos originais em `payload.inventory`. Contrato congelado:
`payload.schema`; tabelas normalizadas: `payload.tables`. `snapshot_tables` inclui
as linhas do envelope de snapshot/participação. Linhagem por ponteiro JSON indica
registros originais exatos, sem intervalos inventados. Identidade `snapshot:v1:`
resume o digest canônico de inventário; chaves de snapshot usam `pending-snapshot`
no cálculo desse digest para evitar circularidade. O guia especifica o formato.

Metadados atuais verificados emitem observações/arquivos de pacotes. `Totalizado`
vira exatamente `totalized` na versão `tse-package-status-exact-v1`; outros rótulos,
variantes e códigos numéricos ficam deliberadamente desconhecidos. Estados brutos
e mapeamento/versão são congelados. Estado nulo/não textual gera problemas
explícitos, sem inventar linhas. Associações históricas de execução/log mantêm
atribuição nula de bytes; objetos atuais não provam conteúdo histórico.

Pendências: sem histórico Git utilizável; nenhum commit inventado. `running` não
prova processo ativo; argumentos de execução e mapeamentos históricos ausentes
são irrecuperáveis. Reconciliação/publicação geral e outros adaptadores de estados
validados ficam para depois. Diretórios temporários abandonados são ignorados,
não removidos silenciosamente. Instalação e prontidão de BU/parser permanecem
desconhecidas. AC–RJ continua nacionalmente parcial.

Próxima tarefa exata: **Fase 4**, decodificação/parsing somente de snapshots
congelados. Repassar este registro, índice, guia de snapshots, contratos de fontes/
linhagem/parsing-issue e referências específicas do parser. Preservar ocorrências
duplicadas e localizadores aninhados; escrever derivados separadamente, nunca
alterar snapshots. Não inventariar/verificar hashes do acervo real ainda; piloto
real limitado pertence à Fase 9.
