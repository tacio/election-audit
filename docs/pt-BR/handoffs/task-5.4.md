# Tarefa 5.4 — Resumos operacionais e grupos imutáveis

Document-ID: EA-HANDOFF-5.4 · Revision: 1 · Language: pt-BR

Objetivo: Publicar artefatos limitados de reconstrução seguros a reinício e denominadores operacionais explícitos para a Fase 6.
Pré-requisitos: [5.3](task-5.3.md), [índice de implementação](../implementation-index.md),
[guia de reconstrução](../reconstruction.md), contratos relevantes de sessão/dispositivo/evento/ciclo/linhagem e atributos operacionais.

Arquivos/interfaces e entregas: `summarize_operations`, `reconstruct_parse`, `inspect_reconstruction`, `iter_reconstruction_rows`, `load_reconstruction_context`; CLI/receita `reconstruct`; sete testes de resumo/publicação. Separar ciclos observados, contagens elegíveis do alvo, métodos desconhecidos, tentativas explícitas, durações/intervalos sustentados, latência, interrupções e exposição evidenciada. Grupos atômicos com somas compartilham metadados completos uma vez em `contexts/PARSE_ID/parse.json`. `FrozenParseReader` verifica metadados/indexa associações uma vez e então verifica grupos selecionados; passe `reader=` para reutilizar contexto. Todas as testemunhas são mantidas. Testam-se transferência do armazenamento completo e inspeção após remover fontes/análise.

Aceitação: os comandos abaixo terminaram com código 0: 23 testes de reconstrução
(seis de sessão, seis de ciclos, quatro de relógios e sete de resumo/publicação),
106 testes totais, lock, Ruff, contratos e documentação em pares; ajuda da receita
e CLI sintética passaram. Sem leitura real do acervo, rede/Git ou mudança na aquisição.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_reconstruction.py -v
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just reconstruct --help
```

Decisões: `operational-v1` e `operational-evidence-v1`; o analisador estrutural
permanece `jez-structural-v1`. Afirmações revisadas preservam âncoras exatas, mas
não certificam independentemente o significado das mensagens. Entradas não
verificadas nunca selecionam contexto oficial. Ausências continuam desconhecidas;
AC–RJ e amostras mantêm recorte nacional parcial e cobertura congelada do índice completo.

Pendências: nenhum adaptador operacional real ou regra oficial de relógio/identidade
foi validado; a Fase 9 deve revisar o significado das fontes. Grupos resolvem
sobreposição apenas internamente. A Fase 6 deve manter partição disjunta de objetos,
rejeitar chaves repetidas de evento/sessão/ciclo e preservar incerteza entre grupos.
Metadados completos da análise permanecem em memória uma vez por leitor; eventos/
testemunhas são limitados por grupo. Sem publicação DuckDB, importação eleitoral,
ajuste de modelos ou rótulos de fraude nesta fase.

Próxima: **6**, publicação DuckDB/Parquet. Repassar somente este registro, índice,
guia de reconstrução e contratos relevantes. Na Fase 6 usar
`reconstruct_parse(..., object_sha256=[...], reader=reader)` e então
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
manter o diretório compartilhado `contexts` ao transferir o armazenamento.
