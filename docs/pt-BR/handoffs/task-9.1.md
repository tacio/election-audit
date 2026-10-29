# Task 9.1 — Roteiro sintético sem rede

Document-ID: EA-HANDOFF-9.1 · Revision: 1 · Language: pt-BR

Pré-requisitos: [8.3](task-8.3.md), [índice](../implementation-index.md), [análise](../analysis.md), [reprodução](../reproduction.md), [processamento](../backfill.md). Tarefa 7.1 permanece parcial; nenhuma validação BU real ou nacional é alegada.

Objetivo/arquivos/interfaces: walkthrough.py e reproduction.demo de produção são incluídos na distribuição sem importar testes. Bytes ZIP determinísticos contêm datas mistas, histórico copiado exato, substituição, solicitação manual/cancelamento, relógios não resolvidos e conteúdo aninhado malformado. Asserções com hashes são somente sintéticas. Denominadores conhecidos de membros/principais são 3/2; comparecimento normalizado é 10/20 = 0.5. Quatro etapas imutáveis preservam partições e cinco registros, incluindo resultado nulo completo registrado. Identidade desconhecida e elegibilidade científica permanecem indisponíveis.

Entregas/aceitação/limites: data/phase9/demo; reports/operational, reports/electoral e reports/analysis contêm relatórios pareados visivelmente SYNTHETIC/SINTÉTICO com IDs/revisões correspondentes. Observações congeladas preservam tempo real da captura; tempos sintéticos são valores explícitos da fixture. Novas capturas podem ter identidades diferentes.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
```
