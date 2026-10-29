# Task 7.2 — Resultados canônicos e reconciliação

Document-ID: EA-HANDOFF-7.2 · Revision: 1 · Language: pt-BR

Objetivo: versões concorrentes somente de acréscimo, seleção canônica baseada em evidência e achados explícitos de aritmética/cobertura. Pré-requisitos: [7.1](task-7.1.md), contratos eleitorais, extensão imutável da publicação.

Arquivos/interfaces: `electoral_results.py`, `derivatives.py`, `publication.py`, `release_tools.py`; `publish_derivative(parent, bundle, store)`, `validate_release`, `query_release`. O filho fixa publicação pai relativa e digest do manifesto, preserva entradas normalizadas originais, acréscimos compactos e novos fatos particionados. Bancos/fatos do pai permanecem imutáveis. O carregador oferece schemas em camadas por manifesto, cadeia de pais verificada, realocação e consultas restritas somente SELECT. Linhagem do pai permanece consultável; linhas importadas preservam bytes/hashes/localizadores originais.

Seleção usa alegações de alvo oficial totalizado e âncoras originais de situação/supersessão. Múltiplas versões elegíveis sobreviventes permanecem em conflito; recebidas/rejeitadas/excluídas não totalizam. Totais ocorrem uma vez por versão, escolhas separadamente. Composição é terminal, da mesma eleição e muitos-para-um; sessões repetidas não multiplicam resultados. Reconciliação distingue escolhas ausentes, divergências de categoria/comparecimento/eleitorado, divergência presente de referência externa do eleitorado, semântica desconhecida, cobertura hierárquica ausente e diferenças numéricas exatas. Populações de referência nacional incluem ZZ explicitamente quando fornecido. Correções preservam publicações/versões imutáveis anteriores.

Aceitação: dez fixtures sintéticas de seleção/reconciliação/marts e quatro de integração de derivadas passaram, saída 0. Incluem conflitos, supersessão, semântica duplicada de candidato, totais repetidos, agregação, sessões, categorias zero/ausentes/excepcionais, divergência de eleitorado externo, cobertura hierárquica ZZ, relógios e populações disjuntas revisadas entre turnos. Adaptador BU oficial TSE verificado continua pendente, não constitui entrega completa da tarefa 7.1. Sem validação de BU real.

Limites: entradas de piloto normalizado somente, 64 MiB de bytes totais das fontes; linhas eleitorais de entrada/herdadas/combinadas limitadas por max_events. Linhas eleitorais residem em memória para reconciliação, não é processador nacional de BU em fluxo. Fatos operacionais de eventos/ciclos/linhagem do pai não são carregados em Python. Sem certificação de assinatura, ajuste ou rótulos de fraude. Git indisponível; sem alegação de commit.

Próxima: tarefa 7.3 quatro marts eleitorais e relatórios bilíngues; ler este repasse, features section_results/unanimous_results/result_timing/round_comparison e o módulo de extensão derivada.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_electoral_results.py -v
```
