# Tarefa 3.1 — Inventário de fontes

Document-ID: EA-HANDOFF-3.1 · Revision: 1 · Language: pt-BR

Objetivo: congelar uma visão fiel de aquisição somente para leitura antes da
seleção de cobertura. Pré-requisitos: tarefa 2.1, índice, dicionário e convenções.

Arquivos/interfaces: `election_audit/source_inventory.py` oferece
`read_manifest(root, ufs=DEFAULT_UFS)` e `inventory_sources(root, ufs=DEFAULT_UFS)`.
`manifest_path(root)` do coletor resolve o marcador de localização. Uma transação
SQLite `mode=ro` inclui o WAL confirmado; nenhum bloqueio do coletor é adquirido.
`canonical`, `digest` e `identity` oferecem identidades JSON canônicas versionadas.

Entregas: linhas originais selecionadas de execução/seção/log/arquivo, metadados,
detalhes, horários de busca, validadores, URLs, caminhos e estados de pacotes;
linhas atuais verificadas de `source_object`/`source_observation` e todas as falhas
de objetos. Localizadores identificam tabela e chave primária; intervalos de bytes
desconhecidos permanecem nulos. Exclusões: rede, alteração dos originais, varredura
de diretórios, interpretação de arquivos compactados ou inferência histórica.

Aceitação: o comando de fixtures isoladas abaixo terminou com código 0; 5 testes
passaram. Cobrem marcador, WAL confirmado, isolamento entre tabelas durante
confirmação concorrente, objetos corrompidos/ausentes/fora da raiz, manifesto
ausente e atualizações posteriores de URLs. Nenhum inventário nacional ou do
acervo real foi executado.
`rtk proxy env UV_OFFLINE=1 just check` também terminou com código 0: lock, Ruff,
contratos, documentos em pares e 48 testes offline passaram. Um ResourceWarning
legado do coletor não causou falha na suíte.

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_snapshots.py -v
```

Decisões: mapeamentos atuais viram novas observações locais do inventário com
execução sintética e horário de captura. São leituras locais, não tentativas HTTP;
estado HTTP permanece desconhecido. Horários originais de busca ficam intactos
em `manifest_rows`. Todo anúncio histórico mantém identidade de objeto nula e
`historical_mapping_unknown`, mesmo com a URL atual verificada. O manifesto não
registra tentativas por execução nem mapeamentos históricos confiáveis de bytes.

Pendências: sem histórico Git utilizável/acesso à rede; sem alegações de commits,
hashes ou downloads. Bytes podem mudar após a captura: a publicação deverá copiá-los
e verificá-los novamente atomicamente. Running indica execução inacabada na
captura, sem afirmar que o processo está ativo. Escopo padrão: 19 UFs alfabéticas
AC–RJ, pleito 3221/eleição 6258, nacionalmente parcial.

Próxima tarefa exata: **3.2**, população a partir de índices de UF verificados e
evidências do manifesto. Ler este registro, API e contratos de cobertura/composição;
preservar denominadores desconhecidos e composição não resolvida.
