# Task 9.2 — Piloto real congelado limitado

Document-ID: EA-HANDOFF-9.2 · Revision: 1 · Language: pt-BR

Pré-requisitos: [8.3](task-8.3.md), [índice](../implementation-index.md), [análise](../analysis.md), [reprodução](../reproduction.md), [processamento](../backfill.md). Tarefa 7.1 permanece parcial; nenhuma validação BU real ou nacional é alegada.

Objetivo/arquivos/interfaces: pilot.py seleciona um principal disponível elegível no índice por AC/AL/DF/ES/PR, usando semente fixa diagnostic-geographic-pilot-v1, estratos município/zona e posições por hash. Transação SQLite somente de consulta inclui WAL confirmado; conjuntos são limitados a 100000 mapeamentos atuais de logs por UF AC–RJ configurada, com hashes dos conjuntos/índices, linhas das UFs selecionadas e exclusões preservados. Não houve percurso de diretórios originais, cópia/checkpoint do banco ativo, alteração do coletor ou aquisição nacional.

Entregas/aceitação/limites: data/phase9/pilot: cinco objetos de logs congelados; denominador completo das cinco UFs 54166, não todo AC–RJ. 49235 eventos; 2328 habilitações, 2327 conclusões, 177 solicitações manuais, 44403 desconhecidos. Todas as 34 sessões, 2328 ciclos e 49235 relógios permanecem não resolvidos. 43466 diagnósticos armazenados de mensagem não suportada são exemplos limitados com 2 marcadores diagnostic_limit, não o denominador de eventos desconhecidos. Datas mistas 04/10/2026 e 25/10/2026 não identificam turnos independentemente. Revisão de palavras fixas não exporta texto livre/identificadores e não acrescenta semântica. Pipeline 162.549 segundos; piloto completo 406.437 segundos; arquivos 1084083961 bytes na medição. Entradas, cobertura, cálculos/SQL, âncoras, revisão segura e relatórios bilíngues estão em pilot-selection.json, pilot-results.json, reproduction.json e reports/operational.

```sh
rtk proxy env UV_OFFLINE=1 just pilot --source /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 --output data/my-pilot
```
