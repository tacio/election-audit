# Plano de conclusão da auditoria de 2026

Document-ID: EA-COMPLETION-PLAN · Revision: 9 · Language: pt-BR

[English](completion-plan.md)

Escopo aprovado: fluxo completo de pesquisa dos dois turnos presidenciais de 2026. Cada fase numerada é atribuída a um novo subagente; integração e aceitação são coordenadas pelo agente principal. O escopo autoriza ajuste nas fases 15–17 e substitui restrições históricas da fundação para novos artefatos; publicações anteriores preservam seu significado.

Estado de execução (3 de novembro de 2026): as fases são executadas uma por vez, cada uma atribuída a um novo subagente e revisada antes do despacho da seguinte. As Fases 10 e 11 estão concluídas; as Fases 12–18 existem só como artefatos de desenvolvimento do Acre (AC). Este plano e o plano de análise estão em revisão após a revisão metodológica de 3 de novembro de 2026; nenhuma nova fase é despachada até essa revisão ser incorporada. A Fase 18 (notebooks/dashboard marimo) continua por último. Estado atual, artefatos e pendências estão no [índice de implementação](../docs/pt-BR/implementation-index.md).

| Fase | Entrega |
| --- | --- |
| 10 | Verificar identidades dos dois turnos; corrigir coleta explícita por turno; preservar manifestos e bytes originais. |
| 11 | Processar a população nacional em partições limitadas em disco, com checkpoints verificados e limites de capacidade; medir antes de expandir. |
| 12 | Decodificar BUs binários oficiais, vincular pacotes EA18 totalizados ao BWEB, estabelecer completude das escolhas e reconciliar hierarquias finais incluindo ZZ. |
| 13 | Validar mensagens reais, sessões, históricos copiados e relógios; publicar medidas operacionais elegíveis com incerteza. |
| 14 | Harmonizar turnos e locais; produzir as 21 famílias de atributos e registros explícitos de disponibilidade. |
| 15 | Congelar famílias de pesquisa e partições agrupadas; proteger resultados de teste e preservar histórico de inspeção. |
| 16 | Ajustar referências empíricas e florestas quantílicas, simular mecanismos e executar uma avaliação final registrada. |
| 17 | Investigar sinais simétricos e controles não sinalizados; calcular limites condicionais e sensibilidades relativas à referência. |
| 18 | Entregar quatro notebooks marimo bilíngues e interface portátil de dados locais/HTTPS com checksums. |

Padrões: somente 2026; registrar validação histórica de 2022 e teste de estresse de 2018 como fases futuras. Somente a máquina atual: armazenamento durável no HDD e no volume de saída adicionado, temporários limitados no SSD, no máximo metade da CPU disponível, paralelismo real medido, uma thread de biblioteca por processo, 4 GiB de memória de trabalho agregada da Fase 11, orçamento temporário total por objeto de 8 GiB, reserva de 10 GiB no SSD e piso de 20 GiB no HDD. Usar partições por local estável de 60/20/20 e holdout municipal adicional de 10%. Proteger resultados até a avaliação final congelada. Locais já inspecionados continuam como desenvolvimento. Os manifestos originalmente fornecidos contêm somente URLs do segundo turno. A coleta corrigida do primeiro turno usou `.local-state/tse-2026-t1-verified.sqlite` e `turno-1-verified`; terminou em 31 de outubro de 2026, e os dois turnos foram copiados para o volume de saída e verificados por SHA-256 em 1º de novembro de 2026.

Dashboard: cobertura/integridade, comparações eleitorais, operações e modelos/investigações. Usar controles marimo e Altair, leitor AuditDataset compartilhado, consultas limitadas e sob demanda, estados indisponíveis explícitos e exportações com proveniência. Mudanças reativas de controles nunca iniciam coleta ou ajuste. Servir em loopback por padrão; hospedagem remota efetiva é futura.

A aceitação exige regressões, exemplos reais redigidos, reconciliação de populações equivalentes, retomada após interrupção, medições de recursos, proteção de resultados, ajustes e simulações reproduzíveis, verificações de notebook/navegador, equivalência local/HTTP, documentação pareada e handoffs compactos. Cada fase deve distinguir ferramentas implementadas, execuções reais e evidências pendentes. Fontes, relógios, assinaturas ou permutabilidade ausentes nunca viram fatos inventados. Sem classificação automática de fraude nem atribuição de ciclos anônimos a candidatos.

## Registro de execução

Benchmarks medidos, estudos de ajuste, parcelas, revisões de capacidade, mudança para o volume de saída adicionado, migração das cópias de origem e a execução final orientada a features do segundo turno na Fase 11 estão registrados no [handoff da Fase 11](../docs/pt-BR/handoffs/task-11.md) e no [guia de processamento orientado a features](../docs/pt-BR/feature-oriented-processing.md). As evidências salvas estão em `data/national/`.
