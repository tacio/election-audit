# Task 7.3 — Marts eleitorais, relatórios e extensão da Fase 8

Document-ID: EA-HANDOFF-7.3 · Revision: 1 · Language: pt-BR

Objetivo: quatro marts eleitorais com disponibilidade/denominadores precisos, consulta/validação somente leitura de derivadas e relatórios em par. Pré-requisitos: [7.2](task-7.2.md), [índice](../implementation-index.md), [guia](../electoral-results.md), apenas os quatro contratos relevantes de atributos.

Arquivos/interfaces: `electoral_imports.py`, `electoral_results.py`, `derivatives.py`, `electoral_reports.py`; `publication.inspect_release/open_release`, `release_tools.validate_release/query_release/report_release`; CLI/receita `import-results PARENT --bundle FILE --store STORE`. Build/aquisição/schema base e sete famílias operacionais FACTS permanecem iguais. Manifestos derivados fixam pais relativos verificados e evidência de descoberta de origem/schema; carregador orientado por tabelas/colunas/chaves. Parquet do pai é reutilizado. Consulta/relatório verificam arquivos físicos uma vez por operação. Validação recalcula grãos/FKs, digests lógicos e decisões/marts eleitorais. Pacotes de achados incluem identidades/arquivos/tabelas dos pais e SQL de reprodução.

Marts: section_results preserva disponibilidade canônica, totais únicos por resultado, denominadores de comparecimento/todas as cédulas/válidos e contagens exatas por candidato. unanimous_results separa unanimidade estrita de todas as cédulas daquela apenas entre válidos; estrita exige cédulas positivas completas reconciliadas e zero categorias excepcionais. result_timing preserva pares de extremos conhecidos/ausentes/negativos/repetidos; encerramento-até-recebimento fica indisponível sem âncora explícita e observação do cliente nunca substitui publicação. round_comparison exige populações disjuntas de principais inteiros/composições/transferências/eleitorados revisados, agrega turnos antes da junção e preserva IDs contextualizados de candidatos e diferenças de eleitorado. Sem atribuição ciclo-candidato ou atribuição não sustentada a urna física.

Aceitação: just check completo saiu com 0, 144 testes offline (18 da Fase 7: 4 importação, 10 semântica/marts, 4 integração de derivadas). Pipeline sintético congelado pai→importação→filho→validação/consulta/relatório passou, incluindo conflitos somente de acréscimo, preservação imutável do pai, realocação da cadeia relativa, ausência de cópias dos fatos operacionais, uma passagem de hashes físicos Parquet por relatório, restrições SELECT/leitura externa e falha com pai corrompido. Ajuda da receita passou. Relatórios usam ambos os idiomas por padrão e preservam cálculos. Sem leitura do corpus real ou alteração da aquisição. Git indisponível; sem alegação de commit/hash.

Pendência da tarefa 7.1: adaptador BU oficial TSE verificado e validação de BU real continuam indisponíveis. Metadados oficiais 2026 e documentos EA16/18/20 inspecionados; ZIP/cabeçalho/dicionário indisponíveis via análise binária web e curl limitado ao intervalo AC falhou no DNS, saída 6, zero bytes. Evidência exata de acesso fixada em resources/electoral-source-evidence.json. Verificações de schema normalizado e aritmética sintética não provam compatibilidade oficial ou assinaturas. Piloto limitado a 64 MiB de bytes e max_events linhas eleitorais de entrada/herdadas/combinadas; residem em Python, não é processador nacional em fluxo. Propagar nacional parcial e desconhecidos. Sem ajuste de modelos ou rótulos de fraude.

Próxima: agente da Fase 8 recebe apenas este repasse, índice, guia eleitoral, contratos relevantes e APIs derivadas orientadas pelo manifesto. Consultar quatro marts mais visões operacionais herdadas por caminho fixado do filho. Acrescentar schemas normalizados/derivados versionados e tabelas do produtor; carregador aceita colunas/chaves do manifesto sem editar FACTS operacional ou publicações anteriores. Preservar cadeia relativa completa ao mover/empacotar. Não reabrir pesquisa integral. Sem piloto real até a Fase 9.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just import-results --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
```
