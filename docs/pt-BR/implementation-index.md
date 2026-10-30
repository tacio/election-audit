# Índice de implementação

Document-ID: EA-IMPLEMENTATION-INDEX · Revision: 12 · Language: pt-BR

Leia instruções do repositório (incluindo `/home/tacio/.codex/RTK.md`), este índice,
handoff atribuído e só contratos relevantes. Use agente separado por fase com
contexto mínimo. Não reabra toda pesquisa nem leve todas as fases anteriores ao
próximo agente. Registre handoff em pares após cada tarefa numerada usando o
[modelo](task-handoff-template.md). [English](../en/implementation-index.md).

Recorte: logs disponíveis do segundo turno presidencial de 2026, AC–RJ, cobertura
nacional parcial. Sem ajuste ou rótulos de fraude. Preserve bytes, aquisição ativa
e manifesto. Outros turnos/histórico exigem importações; subconjunto não é nacional.

| Tarefa | Entregas concluídas | Handoff |
| --- | --- | --- |
| 1.1 | Python 3.14, uv lock, pacote/CLI, DuckDB/PyArrow | [1.1](handoffs/task-1.1.md) |
| 1.2 | Ruff, formatação mecânica dos legados | [1.2](handoffs/task-1.2.md) |
| 1.3 | Receitas just, onboarding em pares, índice/modelo | [1.3](handoffs/task-1.3.md) |
| 2.1 | 30 contratos dimensionais, dicionário, linhagem, uniões seguras | [2.1](handoffs/task-2.1.md) |
| 2.2 | 21 contratos de atributos/prontidão, denominadores e bloqueios | [2.2](handoffs/task-2.2.md) |
| 2.3 | Traduções integrais de pesquisa/aquisição, glossário/diagramas, checagens | [2.3](handoffs/task-2.3.md) |
| 3.1 | Inventário selecionado somente leitura, isolamento WAL, histórico desconhecido explícito | [3.1](handoffs/task-3.1.md) |
| 3.2 | Índices esperados congelados, cobertura membros/principais, seleção limitada | [3.2](handoffs/task-3.2.md) |
| 3.3 | Cópias atômicas imutáveis, CLI/inspeção, proveniência congelada e guia | [3.3](handoffs/task-3.3.md) |
| 4.1 | Decodificação limitada de JEZ/ZIP aninhados, CRC e localizadores de membros duplicados | [4.1](handoffs/task-4.1.md) |
| 4.2 | Eventos estruturais ordenados, relógios locais, diagnósticos seguros limitados | [4.2](handoffs/task-4.2.md) |
| 4.3 | Cache imutável verificado, todas as associações congeladas, CLI/API e guia | [4.3](handoffs/task-4.3.md) |
| 5.1 | Contextos candidatos/oficiais, identidades separadas, linhagem de cópia exata | [5.1](handoffs/task-5.1.md) |
| 5.2 | Máquina de estados anônimos de habilitação/conclusão/suspensão/cancelamento | [5.2](handoffs/task-5.2.md) |
| 5.3 | Regras evidenciadas por seção/exterior, UTC/correções e continuidade | [5.3](handoffs/task-5.3.md) |
| 5.4 | Denominadores operacionais, grupos limitados imutáveis/contexto compartilhado, CLI/API | [5.4](handoffs/task-5.4.md) |
| 6.1 | Publicações limitadas imutáveis DuckDB/Parquet, recursos e current atômico | [6.1](handoffs/task-6.1.md) |
| 6.2 | Marts de cobertura/sessão/disponibilidade de ciclo de vida/votação tardia e incerteza | [6.2](handoffs/task-6.2.md) |
| 6.3 | Construção/validação/consulta somente leitura/relatórios bilíngues; extensão da Fase 7 | [6.3](handoffs/task-6.3.md) |
| 7.1 | Importações normalizadas estritas e adaptador BWEB oficial fixado; leiaute AC real e aritmética das linhas publicadas verificados | [7.1](handoffs/task-7.1.md) |
| 7.2 | Derivadas imutáveis com pai fixado, seleção canônica evidenciada, reconciliação aritmética/hierárquica | [7.2](handoffs/task-7.2.md) |
| 7.3 | Quatro marts eleitorais, SELECT limitado, validação e relatórios em par; reconciliação final real indisponível | [7.3](handoffs/task-7.3.md) |
| 8.1 | Registro versionado dos 21 contratos, saídas descritivas em fluxo e bloqueios científicos explícitos | [8.1](handoffs/task-8.1.md) |
| 8.2 | Populações estáveis de locais revisadas com sementes, estratos geográficos e reservas de estresse municipal | [8.2](handoffs/task-8.2.md) |
| 8.3 | Registros imutáveis de protocolo/exploração/nulos/investigação/cenários, acesso ao teste, CLI e relatórios pareados | [8.3](handoffs/task-8.3.md) |
| 9.1 | Roteiro sintético sem rede de produção, quatro etapas imutáveis e relatórios pareados identificados | [9.1](handoffs/task-9.1.md) |
| 9.2 | Piloto diagnóstico real congelado de cinco regiões, conjuntos/posições/denominadores e mensagens/relógios não resolvidos | [9.2](handoffs/task-9.2.md) |
| 9.3 | Pacotes relocáveis com código permitido, reprodução congelada/resumos lógicos e verificação segura de comandos/SQL | [9.3](handoffs/task-9.3.md) |
| 9.4 | Retomada limitada verificada, guia honesto de processamento/armazenamento e orientação bilíngue atualizada | [9.4](handoffs/task-9.4.md) |

Aceitação: 166 testes sem rede passaram (160 anteriores + 6 da fase 9); lock,
Ruff, contratos, documentos pareados e verificações inofensivas de comandos/SQL.
Piloto real congelado: cinco principais AC/AL/DF/ES/PR; denominador completo
esperado das cinco UFs 54166; 49235 eventos, 44403 desconhecidos; todas as
34 sessões, 2328 ciclos e relógios não resolvidos. Pipeline 162.549 segundos;
piloto completo 406.437 segundos; arquivos medidos 1084083961 bytes.
`data/phase9/` preserva roteiro, piloto, pacotes de revisão, reproduções novas,
relatórios pareados e verificações. Não há processamento completo, ajuste de
modelo, atribuição de candidato, margem nacional ou rótulo de fraude. A tarefa 7.1 agora inclui adaptador BWEB oficial com validação aritmética de linhas reais AC. Situação/completude/hierarquia finais permanecem sem verificação. Repasses anteriores registram aceitação histórica; o repasse atual 7.1 substitui seu bloqueio de acesso à fonte.

Aceitação atual da tarefa 7.1: `rtk just check` passou com 177 testes sem rede. Validação da fonte AC real e relatórios da derivada imutável estão em `data/official-bu/ac-runoff-2026-10-30/`; consulte o [repasse atual](handoffs/task-7.1.md).

| Interface | Fonte / contrato relevante |
| --- | --- |
| Runtime | `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked` |
| CLI | `election_audit/cli.py`; legados `download resume inspect doctor`; `snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill docs-command-check` |
| Aquisição | `scripts/download_tse_logs.py`; `manifest_path(root)` segue `manifest-location.json`; armazenamento/trava/estrutura preservados |
| Snapshot/fontes/cobertura | `election_audit/resources/contracts/schema.json`; `source_object`, `source_observation`, `source_package`, `package_observation`, `package_asset`, `snapshot`, `snapshot_observation`, `coverage_ledger`, `record_lineage` |
| APIs de entradas congeladas | `source_inventory.inventory_sources`, `coverage.build_population`, `snapshots.create_snapshot/publish_snapshot/inspect_snapshot/snapshot_tables`; [guia](snapshots.md) |
| APIs da análise estrutural | `archive_parsing.parse_snapshot/inspect_parse/iter_event_witnesses/iter_lineage/iter_parsing_issues`; [guia de arquivos](archive-parsing.md); versão `jez-structural-v1`; `source_line_sha256` exato, contextos não resolvidos, cache separado de todos os testemunhos do publicador |
| Reconstrução operacional | `reconstruction.reconstruct_parse/inspect_reconstruction/iter_reconstruction_rows/load_reconstruction_context`; [guia](reconstruction.md); `operational-v1`; `FrozenParseReader` para grupos limitados, contexto completo compartilhado, incerteza explícita |
| Publicações operacionais | `publication`, `operational_marts`, `release_tools`; [guia de publicação](publication.md); DuckDB/Parquet imutáveis, consultas somente SELECT e relatórios em par |
| Derivadas eleitorais | `electoral_imports`, `electoral_results`, `derivatives`, `electoral_reports`; [guia](electoral-results.md); importações normalizadas e BWEB oficiais, nacional parcial; reconciliação final indisponível |
| Validador estrutural | `election_audit/contracts.py`; `load_contract`, `validate_contracts`, `validate_rows`; recursos empacotados; semântica/relações ficam para publicação |
| Granularidade/uniões/tempo | [Dicionário](schema-dictionary.md), [convenções](transformation-conventions.md); totais/escolhas separados, versões canônicas únicas, sem multiplicação por integrantes/sessões/evidências |
| Atributos | `election_audit/resources/contracts/features.json`; [prontidão](feature-readiness.md); desconhecido não é zero, AC–RJ parcial, after17 Brasília, unanimidade estrita |
| Pesquisa | `research/analysis-plan.md`, `research/download-sources.md`, pares integrais `.pt-BR.md` vinculados; [referência de aquisição](acquisition-reference.md) |
| Checagem documental | `scripts/check_docs.py`; `check_docs(root)`; metadados/revisões/links locais/blocos; sem executar comandos |
| Receitas | `justfile`; `setup doctor fmt lint test contracts-check docs-check check download resume inspect snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill docs-command-check` |

Próxima: obter vínculo explícito de totalização/supersessão, evidência completa de escolhas e referências finais independentes para resultados reais. Lacuna de importação BWEB oficial resolvida para leiaute AC verificado. Consulte [guia eleitoral](electoral-results.md), [reprodução](reproduction.md) e [processamento](backfill.md). Novos logs exigem novos snapshots; pilotos existentes permanecem parciais. Revise mensagens/sessões/relógios antes de conceder elegibilidade. Nenhum ajuste é autorizado.

Pares sob `docs/en/` e `docs/pt-BR/` compartilham Document-ID/Revision; pesquisa
mantém caminhos ingleses e pares `.pt-BR.md`. Incremente revisões juntas. Código,
comandos, SQL, fórmulas e exemplos numéricos ficam iguais. Revisão humana complementa
paridade mecânica; Fase 9 amplia validação de comandos executáveis.

Fundação analítica: `analysis`, `analysis_partitions`, `analysis_ledgers`, `analysis_reports`; [guia](analysis.md); `analyze`, `validate`, `query`, `report`.
