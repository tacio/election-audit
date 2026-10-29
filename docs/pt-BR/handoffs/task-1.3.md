# Tarefa 1.3 — onboarding e comandos locais

Document-ID: EA-HANDOFF-1.3 · Revision: 1 · Language: pt-BR

Objetivo: receitas just utilizáveis, onboarding em pares e documentação compacta
para iniciar a próxima fase com contexto mínimo.

Pré-requisitos/arquivos/interfaces: tarefas 1.1/1.2; adaptador CLI e contratos
inalterados dos scripts; uv, just, rtk e Python 3.14. Preservar estado da aquisição
e caminhos da pesquisa em inglês.

Entregas: `justfile`; `README.md` / `README.pt-BR.md`; pares de
`implementation-index.md`, `task-handoff-template.md` e handoffs por tarefa em
`docs/en/` / `docs/pt-BR/`. O detalhamento original de aquisição foi preservado abaixo
do novo onboarding em inglês; suas contagens datadas estão identificadas como
históricas. O onboarding em pares mantém comandos/exemplos iguais. Exclusões:
tradução da pesquisa longa, receitas futuras, aquisição, parsing e ajuste de modelos.

Comandos de aceitação (todos com saída 0):

```sh
rtk proxy env UV_OFFLINE=1 just setup
rtk proxy env UV_OFFLINE=1 just doctor
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just download --help
rtk proxy env UV_OFFLINE=1 just resume --help
rtk proxy env UV_OFFLINE=1 just inspect --help
rtk proxy env UV_OFFLINE=1 just fmt
rtk proxy just --list
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv build --offline --wheel --out-dir /tmp/election-audit-phase1-dist
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv venv --python 3.14 /tmp/election-audit-phase1-wheel-check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache uv pip install --offline --no-deps --python /tmp/election-audit-phase1-wheel-check/bin/python /tmp/election-audit-phase1-dist/election_audit-0.1.0-py3-none-any.whl
```

Resultados: instalação travada e doctor aprovados; check validou lock, formatação,
lint e todos os 36 testes. O ResourceWarning de SQLite existente continuou sem
falha. As três ajudas preservaram as opções originais sem abrir dados de aquisição;
formatação idempotente. A listagem contém somente comandos implementados. Geração
de wheel e instalação isolada sem dependências aprovadas; importar `election_audit`,
`scripts.download_tse_logs` e `scripts.inspect_tse_logs` a partir de `/tmp` resolveu
para `/tmp/election-audit-phase1-wheel-check/lib/python3.14/site-packages/`, confirmando
a inclusão dos scripts legados na distribuição.

QA documental: uma verificação inline em Python padrão comparou `Document-ID` /
`Revision` e blocos de comandos de cada par (somente o novo onboarding do README),
e resolveu todos os links Markdown relativos. Todos os 6 pares passaram após a
criação deste handoff. Comandos, identificadores e exemplos correspondem nos pares.

Decisões: `just` repassa opções variáveis pelos argumentos posicionais do shell
(`"$@"`), preservando as aspas. `resume` adiciona `--missing-only`; `check` nunca
adquire dados eleitorais. Receitas usam `uv --locked`, cache gravável padrão em
`/tmp/election-audit-uv-cache` e aceitam `UV_OFFLINE=1` herdado. Documentos paralelos
compartilham IDs/revisões; mudanças incrementam ambas. Sem comandos futuros vazios.
O índice vincula contratos atuais e handoffs individuais.

Pendências: instalação limpa pela rede continua sem teste porque o DNS do PyPI está
indisponível; foram usadas distribuições locais como documentado na tarefa 1.1.
Pesquisa longa e referência de aquisição em inglês aguardam tradução na Fase 2.
A montagem `.git` continua vazia; nenhum commit é alegado. Nenhum dado foi baixado,
inspecionado ou modificado nesta fase.

Próxima tarefa exata: **Fase 2, primeira tarefa atribuída de documentação/contratos**.
Ler instruções do repositório, `docs/en/implementation-index.md`, tarefa atribuída
e somente pesquisa/interfaces relevantes. Manter a convenção documental paralela
e criar handoff compacto em pares após cada tarefa.
