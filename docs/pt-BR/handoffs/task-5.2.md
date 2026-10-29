# Tarefa 5.2 — Ciclos operacionais anônimos

Document-ID: EA-HANDOFF-5.2 · Revision: 1 · Language: pt-BR

Objetivo: Implementar transições anônimas explícitas sem transformar solicitações, repetições ou históricos parciais em votos.
Pré-requisitos: [5.1](task-5.1.md), [índice de implementação](../implementation-index.md),
[guia de reconstrução](../reconstruction.md), contratos relevantes de sessão/dispositivo/evento/ciclo/linhagem e atributos operacionais.

Arquivos/interfaces e entregas: `reconstruct_cycles`; seis testes de ciclos. Habilitação/conclusão básicas reconstroem ciclos concluídos com método desconhecido. Habilitação repetida, órfãos, eventos intermediários desconhecidos e históricos incompletos permanecem não resolvidos. Solicitações nunca estabelecem método manual. Regras revisadas de suspensão total/parcial, retomada, tentativa/falha, método, cancelamento e abandono preservam estados distintos e evidência original. Sem associação candidato/RDV.

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

Próxima: **5.3**, relógios evidenciados. Repassar somente este registro, índice,
guia de reconstrução e contratos relevantes. Na Fase 6 usar
`reconstruct_parse(..., object_sha256=[...], reader=reader)` e então
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
manter o diretório compartilhado `contexts` ao transferir o armazenamento.
