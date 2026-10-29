# Tarefa 5.3 — Relógios e tempo decorrido evidenciados

Document-ID: EA-HANDOFF-5.3 · Revision: 1 · Language: pt-BR

Objetivo: Preservar leituras originais e aplicar somente evidência explícita de fuso, correção e continuidade por seção/eleição.
Pré-requisitos: [5.2](task-5.2.md), [índice de implementação](../implementation-index.md),
[guia de reconstrução](../reconstruction.md), contratos relevantes de sessão/dispositivo/evento/ciclo/linhagem e atributos operacionais.

Arquivos/interfaces e entregas: `normalize_clocks`, `elapsed_seconds`; quatro testes de relógios. Leitura original, deslocamento, correção, UTC, confiança e evidência ficam separados. Fusos desconhecidos continuam nulos; continuidade local explícita pode sustentar tempo decorrido. Regras municipais/exterior usam contexto exato de seção/eleição. Reversões, mudanças de intervalo, eventos de mudança do relógio e horários locais ambíguos/inexistentes invalidam durações sem suporte. Sem padrão por UF nem classificação after17.

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

Próxima: **5.4**, resumos e publicação imutável. Repassar somente este registro, índice,
guia de reconstrução e contratos relevantes. Na Fase 6 usar
`reconstruct_parse(..., object_sha256=[...], reader=reader)` e então
`inspect_reconstruction`, `load_reconstruction_context`, `iter_reconstruction_rows`;
manter o diretório compartilhado `contexts` ao transferir o armazenamento.
