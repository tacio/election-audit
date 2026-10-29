# Tarefa 1.2 — adoção mecânica do Ruff

Document-ID: EA-HANDOFF-1.2 · Revision: 1 · Language: pt-BR

Objetivo: formatação e lint consistentes sem alterar o comportamento de aquisição,
inspeção ou estatística.

Pré-requisitos/arquivos/interfaces: tarefa 1.1; `pyproject.toml`, `scripts/*.py`
e `tests/*.py` legados, CLI do pacote. Nomes de funções, assinaturas, opções CLI,
esquemas de saída e comportamento da aquisição foram preservados.

Entregas: alvo Ruff `py314`, linhas de 100 caracteres, regras `E4`, `E7`, `E9`,
`F`, `I`; formatação mecânica e organização dos imports. Sem alterações de
comportamento nem novas funções do pipeline. O callback existente do downloader
tem uma exceção pontual de `E731` por arquivo para preservar sua implementação.

Comandos de aceitação (todos com saída 0):

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff check . --fix
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff format .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff format --check .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline ruff check .
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked --offline python -m unittest discover -s tests -v
```

Resultados: Ruff corrigiu 6 blocos de imports; a formatação alterou 7 arquivos;
verificações finais de formatação e lint aprovadas; todos os 36 testes passaram.
As árvores `ast.parse` antes/depois dos 3 scripts e 3 arquivos de teste originais
foram comparadas removendo somente Import/ImportFrom: iguais. Ruff ordenou os
imports; não houve outras alterações de AST. As cópias temporárias da base estão
em `/tmp/election-audit-phase1-original`.

Decisões: sem supressão ampla de lint, correções inseguras ou migração de interfaces.
A formatação é uma tarefa separada do novo comportamento CLI da 1.1.

Pendências: o ResourceWarning de SQLite existente continua visível no Python 3.14;
nenhum teste falhou. Limitações de instalação/rede estão na tarefa 1.1. Nenhum dado
bruto foi lido ou alterado e nenhuma requisição ao vivo foi feita.

Próxima tarefa exata: **1.3**, adicionar receitas just utilizáveis, onboarding em
pares, índice compacto de implementação e modelo reutilizável de handoff.
