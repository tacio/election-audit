# Tarefa 6.3 — Construção, validação, consulta somente leitura e relatórios iniciais em par

Document-ID: EA-HANDOFF-6.3 · Revision: 1 · Language: pt-BR

Objetivo: tornar revisável o pipeline de publicação operacional congelada por APIs/CLI/receitas e relatórios em inglês/português.
Pré-requisitos: [6.2](task-6.2.md), [índice](../implementation-index.md), [guia de publicação](../publication.md), somente contratos operacionais relevantes.

Arquivos/interfaces: `publication.py`, `operational_marts.py`, `release_tools.py`; CLI/receitas `build`, `validate`, `query`, `report`. `build --input-kind snapshot|parse|reconstruction` chega a publicações atômicas por entradas congeladas. Novos contextos de parse preservam dimensões completas de cobertura/origem e linhagem de metadados uma vez. `open_release` anexa visões temporárias de fatos, `query_release` permite exatamente um SELECT analisado com acesso externo restrito e resultados limitados; `--sql-file` suporta consultas maiores reproduzíveis. Reutilização interna do manifesto verificado evita recalcular hashes do corpus na mesma operação.

Entregas: hashes físicos, verificações de manifesto/localizador, digests lógicos de multiconjunto SHA-256 e contagens exatas, validação de grão/FK/cardinalidade/contabilização evento-ciclo-sessão/linhagem/cobertura/recursos. Relatórios padrão nos DOIS idiomas, com rótulos/explicações traduzidos e cálculos/SQL/fórmulas/exemplos idênticos; `--language en|pt-BR|both`. Achados compartilhados identificam entradas, cálculos, premissas, exclusões, incerteza, comandos de reprodução e evidência que pode contestá-los. Saídas do relatório ficam separadas das publicações imutáveis. Carregador estático de fatos operacionais e rota explícita de extensão pai/filho para a Fase 7 documentados; nenhuma lógica eleitoral acrescentada.

Aceitação: comando final abaixo saiu com 0: lock, Ruff, contratos, documentação em par e **126 testes offline**. A Fase 6 acrescenta 20 fixtures: seis de publicação/concorrência/falhas de recursos, cinco operacionais de relógio/ciclo de vida/cobertura e nove de interfaces/integridade/relatórios. Inclui snapshot→publicação sintético completo após apagar origem/parse/reconstrução, grupos disjuntos limitados, evidência/linhagem particionadas, rejeição de escrita/COPY/leitura externa em SELECT, reutilização de manifesto pelo relatório e ambos os idiomas. Nenhuma operação no corpus real/rede/Git ou alteração de aquisição; estado Git indisponível, sem alegação de commit/hash.

Decisões: `operational-release-v1`, `operational-marts-v1`. Verificação completa de integridade lê todos os bytes dos fatos uma vez por operação de consulta/relatório; validação também recalcula conteúdo lógico. Cálculos dos relatórios compartilham manifesto/conexão verificados. Tempos desconhecidos de ciclo de vida, convenção exterior, históricos copiados entre fragmentos e validação eleitoral indisponível continuam explícitos; sem total global elegível confiável, atribuição a candidatos, ajuste de modelos ou rótulos de fraude.

Pendências: nenhum adaptador autoritativo de mensagens reais/piloto ou fonte de ciclo de vida do publicador; parses antigos podem não ter linhagem de metadados/dimensões de origem, adiando verificações relevantes. Metadados congelados completos ficam residentes uma vez. `FACTS` atual limita-se a sete famílias operacionais. A Fase 7 deve implementar carregador/API de manifesto derivado que fixe e verifique uma publicação-pai relativa, acrescente banco compacto separado/novos fatos particionados e reutilize Parquet do pai sem copiá-lo ou editá-lo. Veja o ponto exato de extensão no guia.

Próxima: **Fase 7**, importações eleitorais como nova derivação imutável. Ler somente este registro, índice, guia de publicação, contratos eleitorais relevantes e APIs existentes de proveniência congelada. Preservar publicações-base, entradas originais e escopo nacional parcial. Sem piloto do corpus real até a Fase 9.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just build --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
```
