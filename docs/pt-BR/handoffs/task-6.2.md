# Tarefa 6.2 — Marts operacionais transparentes

Document-ID: EA-HANDOFF-6.2 · Revision: 1 · Language: pt-BR

Objetivo: publicar cobertura operacional, resumos de sessão, disponibilidade de eventos de processamento e diagnósticos de votação tardia sem dados eleitorais.
Pré-requisitos: [6.1](task-6.1.md), [índice](../implementation-index.md), contratos de atributos operacionais.

Interfaces: `operational_marts.coverage_rows`, `processing_availability_rows`, `late_session_row`, `materialize_marts`; a publicação materializa marts compactos antes da liberação atômica. Linhas preservam as entradas exatas do cálculo em JSON `payload` e colunas explícitas do grão único. Resumos de sessão preservam denominadores/prontidão da Fase 5. O registro completo esperado e dimensões de origem/contexto agora ficam uma vez nos novos contextos de parse; contextos antigos indicam campos indisponíveis.

Aceitação: cinco fixtures operacionais específicas passaram: limite estrito de 17:00, instantes de Brasília iguais com offsets diferentes, relógios/contexto desconhecidos, encerramento ausente, conclusão tardia versus permanência aberta, exterior, sensibilidade limitada, ausência/repetição de ciclo de vida e membros esperados preservados. Publicação tem seis fixtures, incluindo concorrência efetiva entre chaves independentes do parser e parse único por chave idêntica. Verificação completa: saída 0, 117 testes offline. Aquisição/dados brutos e corpus real intocados.

Decisões: conclusão doméstica significa estritamente após 17:00 America/Sao_Paulo na data-alvo; convenção exterior indisponível. Permanência aberta exige intervalo contínuo comprovado de abertura/encerramento e é separada das conclusões tardias observadas. Desconhecidos nunca viram taxas zero. Intervalos limitados de relógio preservam contagens inferior/superior; relógios absolutos sem suporte ficam não classificáveis. Totais elegíveis entre fragmentos permanecem nulos. Recebimento, processamento, geração, publicação e observação do cliente continuam separados; timestamps HTTP/download nunca preenchem campos do publicador. População esperada de pacotes vem de anúncios congelados; população completa de resultados continua desconhecida. Nenhuma junção expande ciclos por testemunhas de membros/pacotes/linhagem.

Refinamento de concorrência: substituir trava global do cache do parser por travas por chave de conteúdo/configuração; objetos independentes são analisados simultaneamente, chamadas da mesma chave compartilham um resultado imutável verificado. Isso torna efetivos os trabalhadores configurados, preservando análise atômica.

Pendências: fonte real autoritativa de ciclo de vida, regras de relógio e convenção exterior indisponíveis; sem atribuição a candidatos, importação BU ou piloto real. Próxima exata: **6.3**, APIs de construção/validação/consulta/relatório, CLI/receitas e relatórios bilíngues; depois somente extensão da Fase 7.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_operational_marts.py -v
rtk proxy env UV_OFFLINE=1 just check
```
