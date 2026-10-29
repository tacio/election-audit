# Tarefa 1.1 — base instalável

Document-ID: EA-HANDOFF-1.1 · Revision: 1 · Language: pt-BR

Objetivo: `election_audit` instalável, resolução reproduzível com uv, runtime
declarado e CLI que preserva os scripts originais.

Pré-requisitos/arquivos/interfaces: Python 3.14, uv; `scripts/download_tse_logs.py`,
`scripts/inspect_tse_logs.py`, `scripts/audit_statistics.py`; suas opções, imports,
estrutura de dados e marcador do manifesto continuam sendo os contratos vigentes.

Entregas: `pyproject.toml`, `uv.lock`, `.python-version`, `election_audit/`,
`scripts/__init__.py`, `tests/test_cli.py`, regras de exclusão. Dependências de execução:
DuckDB 1.5.3 e PyArrow 24.0.0; Ruff 0.17.0 para desenvolvimento. Exclusões: parsing,
snapshots, migração de esquema, aquisição, tradução da pesquisa e ajuste de modelos.

Comandos de aceitação (todos com saída 0):

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv lock --offline --check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv sync --locked --offline
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -v
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked election-audit doctor
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked election-audit resume --help
```

Resultados: verificação do lock e instalação offline travada aprovadas; 36 testes
aprovados (34 originais e 2 dos adaptadores CLI); doctor informou Python 3.14.5,
SQLite 3.50.4 e as versões acima; a ajuda de resume preservou as opções originais.
Um ResourceWarning de SQLite legado apareceu no Python 3.14; os testes passaram.

Decisões: Python 3.14 é o runtime do projeto, compatível com as distribuições Linux
locais autênticas disponíveis; os scripts independentes continuam funcionando nas
versões anteriores de Python. Dependências e corte do resolvedor fixados em
`2026-10-29T00:00:00Z`; Hatchling 1.32.4 fixado e sua dependência de compilação
Pluggy limitada a 1.6.0. A CLI delega às funções `main()` existentes; `resume` insere
`--missing-only` e restaura os argumentos do processo mesmo em caso de erro.

Evidência do ambiente: o DNS do PyPI falhou. Os registros autênticos de lock de
DuckDB/PyArrow vieram de `oss-viz/uv.lock`, vizinho somente para leitura; os de Ruff,
do resolvedor com cache do uv. `uv lock --offline` normalizou e validou este lock.
A `.venv` ignorada recebeu os arquivos Linux instalados das mesmas versões de
DuckDB/PyArrow de `oss-viz/.venv`; ferramentas de compilação e Ruff vieram de uma
cópia do cache uv em `/tmp/election-audit-uv-cache`. Nenhum hash foi inventado.
A instalação travada foi testada com esses artefatos; uma instalação limpa com
download não foi testada.

Pendências: instalação limpa exige acesso ao PyPI ou os wheels correspondentes
em cache; não houve aquisição ao vivo nem verificação de assinaturas. Não há commit
Git porque a `.git` montada está vazia. Os dados de aquisição não foram alterados.

Próxima tarefa exata: **1.2**, configurar Ruff e aplicar somente formatação e
organização mecânica dos imports, comparar a AST e executar todos os testes.
