# Task 9.4 — Processamento retomável e orientação final

Document-ID: EA-HANDOFF-9.4 · Revision: 1 · Language: pt-BR

Pré-requisitos: [8.3](task-8.3.md), [índice](../implementation-index.md), [análise](../analysis.md), [reprodução](../reproduction.md), [processamento](../backfill.md). Tarefa 7.1 permanece parcial; nenhuma validação BU real ou nacional é alegada.

Objetivo/arquivos/interfaces: backfill reutiliza análise/cache/contexto/fragmentos por objeto e publicações verificadas; nenhuma aquisição é executada. Guia pareado documenta comandos explícitos para todo AC–RJ disponível, UFs/ZZ posteriores e importações separadas de turnos/histórico. Retomada limitada do piloto e interrupção antes da renomeação são verificadas; processamento de toda a população não foi executado. README agora descreve etapas implementadas, comandos de demonstração/piloto/reprodução/relatórios e próxima ação da tarefa 7.1.

Entregas/aceitação/limites: Padrões permanecem 4 trabalhadores estruturais, 4 threads DuckDB, memória 12 GiB, temporários 8 GiB, reserva 10 GiB. SSD livre inicial de aproximadamente 31.6 GB deixa aproximadamente 12.3 GB após reserva/temporários, antes de derivados/folga. Parquet e DuckDB ficam juntos; metadados completos das UFs são relevantes mesmo com cinco principais. Não há promessa de que todo processamento cabe. Seis testes novos mais 160 existentes passaram (166 totais); saída final fica em data/phase9/verification. Git indisponível: nenhuma alegação de commit. Preserve coletor/bytes originais ativos e publicações imutáveis. Menor tarefa restante: obter documentação BU oficial TSE/dados originais acessíveis, implementar adaptador verificado e validar dados reais para tarefa parcial 7.1; revisar evidência de mensagens/relógios/sessões antes de conceder elegibilidade operacional. Nenhum ajuste de modelo, permutabilidade avaliada, margem nacional coerente ou rótulo de fraude.

```sh
rtk proxy env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
rtk proxy env UV_OFFLINE=1 just check
```
