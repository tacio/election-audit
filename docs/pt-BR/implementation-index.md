# Índice de implementação

Document-ID: EA-IMPLEMENTATION-INDEX · Revision: 24 · Language: pt-BR

[English](../en/implementation-index.md)

Este é o único ponto de entrada sobre o estado atual. Ele diz o que existe, o que
de fato foi executado, onde estão os resultados e qual é o próximo passo. Os guias
em `docs/pt-BR/` descrevem o comportamento de cada ferramenta. Os handoffs em
`docs/pt-BR/handoffs/` são registros datados do que cada tarefa fez na época;
leia-os para detalhes, não para saber o estado. Os planos ficam em `research/`.
O estado abaixo é de **3 de novembro de 2026**.

## Estado atual

**Coleta (Fase 10): concluída nos dois turnos.** O coletor baixou todas as versões
de log anunciadas pelos endpoints por seção do TSE.

| Turno | Pleito / eleição / data | Execução concluída (UTC) | Versões de log | Agregadas | Sem log listado | Arquivo auxiliar não publicado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3220 / 6257 / 2026-10-04 | 2026-10-31 23:27 | 499176 | 17931 | 31 | 41 |
| 2 | 3221 / 6258 / 2026-10-25 | 2026-10-29 22:56 | 499177 | 17931 | 30 | 41 |

Os pacotes do primeiro turno estão todos `Totalizado`; o segundo turno tem 488333
`Totalizado` e 10844 `Recebido`. Por causa das seções sem log e sem arquivo auxiliar,
nenhuma das execuções atende ao critério `national_coverage` do coletor; essas seções
permanecem lacunas explícitas. Em 1º de novembro os dois acervos brutos (53722200971
e 90643145031 bytes) foram copiados para o volume de saída, e cada objeto foi
verificado por SHA-256. As cópias são os originais de referência para o
processamento derivado; os manifestos em `.local-state/` foram preservados sem
alteração. Em 3 de novembro os metadados das raízes do HDD antigo foram arquivados
com hashes e seus objetos brutos, duplicatas das cópias certificadas, foram
liberados para exclusão.

A mudança de disco não exigiu reescrever manifestos: os caminhos nos manifestos são
relativos à raiz de objetos (`objects/xx/<sha>.<ext>`), e o `manifest-location.json`
de cada nova raiz aponta para seu manifesto no SSD (`.local-state/tse-2026.sqlite`
no segundo turno, `.local-state/tse-2026-t1-verified.sqlite` no primeiro). As cópias
certificadas `migration-2026-11-01/manifest-r{1,2}.sqlite` batem com os hashes dos
certificados e, em 3 de novembro, suas linhas de files, logs, sections e runs se
mostraram idênticas às dos manifestos vivos no SSD. As análises fixam as cópias
certificadas. Sobras a ignorar: `raw/2026/turno-2/manifest.sqlite` é o banco obsoleto de
antes da separação; `.local-state/tse-2026-t1.sqlite` é um manifesto do primeiro
turno superado; e `migration-2026-11-01/status.json` mostra `FAILED_STOPPED` porque
o job encadeado depois da cópia verificada foi parado, não porque a cópia falhou.

**Processamento estrutural (Fase 11): concluído no escopo elegível do segundo
turno.** O job de resumos orientados a features processou todos os 498581 objetos
elegíveis (499177 observações menos 596 observações protegidas/de estresse e seus
aliases de conteúdo), com 0 falhas, em 35992 segundos, com três trabalhadores
dentro do orçamento de 4 GiB / metade da CPU. 498575 objetos foram analisados por
completo e 6 parcialmente (190 erros retidos). Foram percorridos 5032537448 eventos
estruturais; cerca de 90% estão em classes de mensagem que o parser estrutural deixa
como `unknown`. A release publicada
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88`
(`source-summary-analysis-release-v1`, 546,6 MB de Parquet) guarda contagens por
log, estrutura de membros e hashes de blocos; os 68,8 GB de checkpoints agrupados
ficam só para recuperação e evidência.

Para que ela não serve: cada `logd.dat` do segundo turno vai da preparação em
setembro, passando pelo primeiro turno, até o segundo turno, então as contagens de
habilitações e conclusões por log (252940011 e 252882361 no total) misturam turnos e
não são medidas do segundo turno. Não há sessões, relógios nem tempos. Os 596 logs
protegidos/de estresse e todo o primeiro turno não foram processados. Toda medida
operacional precisa da passada semântica da Fase 21.

A Fase 11 leu 91.5 GB de objetos pequenos a cerca de 2.5 MB/s com 94% de pressão
de E/S, enquanto gravava checkpoints no mesmo disco. O benchmark de 3 de novembro
(`stage-sources benchmark`, janelas de 2000 objetos, os dois turnos) achou a causa:
a ordem de leitura. As cópias certificadas foram gravadas em ordem de caminho, então
a ordem de seção (URL do manifesto) lê a 1.9–3.5 MB/s, a ordem de caminho a
41–61 MB/s e a ordem física (FIEMAP) a 73–92 MB/s.

**Cópia para o SSD (3 de novembro): concluída nos dois turnos.** Todo objeto bruto
foi copiado em ordem física para `~/data/election-audit-stage/2026/turno-1/` e
`turno-2/` (998412 e 998413 objetos, 53722200971 e 90643145031 bytes); cada corpo de
origem foi conferido com o SHA-256 do manifesto certificado e depois cada corpo
copiado foi recalculado no SSD. As cópias levaram 931 s e 1587 s (cerca de
57 MB/s), as reverificações 954 s e 1431 s; 86 minutos no total. Cada raiz guarda
sua cópia do manifesto, um ledger e um `staging-certificate.json` vinculado ao hash
do manifesto certificado. O diretório home é eCryptfs, então um único leitor
reverifica a apenas 56–63 MB/s. O
[plano de conclusão](../../research/completion-plan.pt-BR.md#regras-de-recursos-e-es)
define as regras de E/S para a próxima passada.

**Fase 19 (entradas nacionais): em andamento.** `bulk-download` baixou, com
SHA-256/SHA-512 e o JSON do catálogo do TSE, o BWEB de 2026 e de 2022 (112
arquivos por ano, todos os 56 por ano coincidindo com o `.sha512` publicado).
Resultados por seção, perfil do eleitorado e locais de votação, correspondências de
mídias e logs GEDAI de 2026 estão sendo baixados para
`~/data/election-audit-stage/inputs/`; os arquivos em massa de BU/RDV/log (2026:
219.2 GB, 2022: 168.5 GB) para `bulk/` no volume de saída. Veja `status.json` em
cada raiz.

**Fase 21 (passada semântica): execuções nacionais de 2026 em andamento.**
`semantic-pass` coincidiu com o adaptador por evento em 400 de 400 objetos do AC
amostrados (84469 ciclos concluídos) e rodou em todos os 1674 objetos não
protegidos do segundo turno do AC em cerca de 60 s, sem erros. As execuções
nacionais dos dois turnos (6 workers, a partir da cópia no SSD) gravam em
`~/data/election-audit-stage/phase21/`. Os logs de 2022 precisam antes de regras de
2022 revisadas. Veja o [guia da passada semântica](semantic-pass.md).

**Fases 12–18: encerradas como pilotos de desenvolvimento do Acre (AC).** A revisão
metodológica de 3 de novembro substituiu suas definições; o trabalho revisado são as
Fases 19–26. Suas ferramentas existem, foram exercitadas com dados reais do AC e são
reutilizadas, mas nada foi executado em escala nacional:

- Fase 12: 2270 seções do segundo turno no AC com conteúdo verificado entre BU binário
  e BWEB; os totais da UF batem. Assinaturas, recontagem de RDV e hierarquia nacional
  não foram feitas.
- Fase 13: adaptador de mensagens reais (`real-operational-v1`) executado em um log
  do AC por turno. Relógios absolutos e conciliação de comparecimento não foram feitos.
- Fase 14: 2270 unidades do AC, 54480 linhas de features, 668 grupos de locais no
  mesmo turno. Sem identidade entre turnos e sem features eleitorais do primeiro turno.
- Fase 15: protocolo do AC congelado (treino 1259, calibração 399, teste protegido
  340, estresse municipal 256, inspecionadas em desenvolvimento 16).
- Fase 16: um ajuste de comparecimento no AC (variante `no_first_round`) avaliado só
  com dados de calibração. O conjunto de teste protegido não foi aberto.
- Fase 17: 126 pacotes de casos de desenvolvimento do AC (20 + 20 ranqueados, 86
  controles não sinalizados).
- Fase 18: quatro notebooks marimo sobre a exportação do AC; QA no navegador não feito.

Não existe resultado eleitoral nacional, margem nacional, modelo nacional ajustado
nem rótulo de fraude.

**Verificações.** A verificação offline completa `just check` passa (lock, formato,
lint, contratos, documentos, comandos documentados e todos os 330 testes).

## Próximo passo

Concluir a Fase 19 (downloads em andamento) e a Fase 21 (execuções nacionais em
andamento; revisão das regras de 2022 pendente) e então as verificações de
integridade da Fase 20 sobre BU, RDV, assinaturas e correspondências baixados. O
[protocolo do estudo](../../research/analysis-plan.pt-BR.md) (Revisão 2) define as
afirmações, o mapa de ameaças e observáveis, as verificações de integridade I1–I9, os
testes confirmatórios C1–C6, o estudo de poder e a política de dados; o
[plano de conclusão](../../research/completion-plan.pt-BR.md) (Revisão 11) define as
Fases 19–26. O protocolo é um rascunho até ser congelado e pré-registrado
publicamente na Fase 23.

## Regras de trabalho

Leia o `CLAUDE.md` do repositório, este índice, o handoff atribuído e só os
contratos relevantes. Execute uma fase por vez. Após cada tarefa numerada, escreva
um handoff em pares a partir do [modelo](task-handoff-template.md) e atualize este
índice nos dois idiomas. Mantenha o processamento dentro de metade da CPU, 4 GiB de
RAM agregada e uma thread de biblioteca por processo.

As 596 observações protegidas/de estresse do segundo turno ficam excluídas antes de
qualquer acesso semântico ou a cache. Os históricos de inspeção em
`data/phase15/inspection.sqlite`, `data/national/phase11-protection-2026-10-31/` e
nos registros das parcelas da Fase 11 continuam vinculantes: qualquer local listado
neles é dado de desenvolvimento, nunca teste intocado. Identidade ausente entre
turnos permanece indisponível.

## Estado das fases

As tarefas de fundação 1.1–9.4 estão concluídas. Aceite (29 de outubro de 2026):
166 testes offline, lock, Ruff, contratos e verificação de documentos em pares; um
piloto real congelado em cinco regiões (AC/AL/DF/ES/PR) com todas as sessões, ciclos
e relógios não resolvidos. A tarefa 7.1 depois acrescentou o adaptador oficial BWEB
com verificações aritméticas reais do AC (177 testes).

| Tarefa | Entregas | Handoff |
| --- | --- | --- |
| 1.1 | Python 3.14, uv lock, pacote/CLI, DuckDB/PyArrow | [1.1](handoffs/task-1.1.md) |
| 1.2 | Ruff, formatação mecânica dos legados | [1.2](handoffs/task-1.2.md) |
| 1.3 | Receitas just, onboarding em pares, índice/modelo | [1.3](handoffs/task-1.3.md) |
| 2.1 | 30 contratos dimensionais, dicionário, linhagem, uniões seguras | [2.1](handoffs/task-2.1.md) |
| 2.2 | 21 contratos de features/prontidão, denominadores e bloqueios | [2.2](handoffs/task-2.2.md) |
| 2.3 | Traduções em pares de pesquisa/coleta, glossário/diagramas, verificação de docs | [2.3](handoffs/task-2.3.md) |
| 3.1 | Inventário de origem somente leitura, isolamento do WAL, desconhecidos históricos explícitos | [3.1](handoffs/task-3.1.md) |
| 3.2 | Índices esperados congelados, cobertura de membros/principais e seleção limitada | [3.2](handoffs/task-3.2.md) |
| 3.3 | Cópias imutáveis atômicas, CLI de snapshot/inspeção, proveniência congelada e guia | [3.3](handoffs/task-3.3.md) |
| 4.1 | Decodificação limitada de JEZ/ZIP aninhados, CRC e localizadores de membros duplicados | [4.1](handoffs/task-4.1.md) |
| 4.2 | Eventos estruturais ordenados, relógios ingênuos, diagnósticos limitados e seguros | [4.2](handoffs/task-4.2.md) |
| 4.3 | Cache de parse imutável verificado, associações congeladas, CLI/API e guia | [4.3](handoffs/task-4.3.md) |
| 5.1 | Contextos candidatos/oficiais, identidades separadas, linhagem exata de blocos copiados | [5.1](handoffs/task-5.1.md) |
| 5.2 | Máquina de estados anônima de habilitação/conclusão/suspensão/cancelamento | [5.2](handoffs/task-5.2.md) |
| 5.3 | Regras de relógio por seção/exterior com evidência, UTC/correções e continuidade | [5.3](handoffs/task-5.3.md) |
| 5.4 | Denominadores operacionais, shards imutáveis limitados/contexto compartilhado, CLI/API | [5.4](handoffs/task-5.4.md) |
| 6.1 | Releases DuckDB/Parquet imutáveis e limitadas, limites de recursos, current atômico | [6.1](handoffs/task-6.1.md) |
| 6.2 | Marts de cobertura/sessão/disponibilidade/voto tardio, incerteza de relógio | [6.2](handoffs/task-6.2.md) |
| 6.3 | Build/validação/consulta somente leitura/relatórios bilíngues | [6.3](handoffs/task-6.3.md) |
| 7.1 | Importações normalizadas e adaptador oficial BWEB fixado; aritmética real do AC verificada | [7.1](handoffs/task-7.1.md) |
| 7.2 | Derivados imutáveis presos ao pai, seleção canônica com evidência, conciliação | [7.2](handoffs/task-7.2.md) |
| 7.3 | Quatro marts eleitorais, SELECT limitado, validação e relatórios em pares | [7.3](handoffs/task-7.3.md) |
| 8.1 | Registro versionado de 21 contratos de features e saídas descritivas em fluxo | [8.1](handoffs/task-8.1.md) |
| 8.2 | Partições de locais estáveis revisados com semente, estratos e reservas municipais | [8.2](handoffs/task-8.2.md) |
| 8.3 | Ledgers imutáveis de protocolo/exploração/investigação/cenário e histórico de acesso ao teste | [8.3](handoffs/task-8.3.md) |
| 9.1 | Passo a passo sintético offline, quatro estágios imutáveis e relatórios em pares | [9.1](handoffs/task-9.1.md) |
| 9.2 | Piloto diagnóstico real congelado em cinco regiões | [9.2](handoffs/task-9.2.md) |
| 9.3 | Pacotes de revisão relocáveis, releitura congelada/digests lógicos | [9.3](handoffs/task-9.3.md) |
| 9.4 | Reinício limitado verificado e guia de backfill/armazenamento | [9.4](handoffs/task-9.4.md) |

| Fase | Estado | Pendências | Handoff |
| --- | --- | --- | --- |
| 10 | Concluída: dois turnos coletados, copiados e verificados por SHA-256 | Seções com lacuna continuam explícitas; BWEB, cadastros e fontes de RDV/assinatura de outras UFs são importações separadas | [10](handoffs/task-10.md) |
| 11 | Concluída no escopo elegível do segundo turno (498581 objetos, 0 falhas) | Passada semântica dos dois turnos e de 2022 (Fase 21); logs protegidos lidos só depois do congelamento da Fase 23 | [11](handoffs/task-11.md) |
| 12 | Só AC: 2270 seções com conteúdo verificado, totais da UF batem | Outras UFs, dois turnos, assinaturas, RDV, hierarquia BR/UF/municipal/ZZ | [12](handoffs/task-12.md) |
| 13 | Amostra do AC: um log por turno | Sessões, relógios, históricos copiados e conciliação de comparecimento nacionais | [13](handoffs/task-13.md) |
| 14 | Só AC: 54480 linhas de features | Features nacionais, identidade entre turnos, resultados do primeiro turno | [14](handoffs/task-14.md) |
| 15 | Protocolo do AC congelado | Substituída pelo congelamento e pré-registro da Fase 23 | [15](handoffs/task-15.md) |
| 16 | Ajuste de desenvolvimento de comparecimento no AC | Família completa de alvos/variantes, simulações com reajuste, avaliação final | [16](handoffs/task-16.md) |
| 17 | Pacotes de casos de desenvolvimento do AC | Casos nacionais, corroboração, limites de impacto, sensibilidade do pipeline completo | [17](handoffs/task-17.md) |
| 18 | Notebooks sobre a exportação do AC | QA no navegador, conjuntos de dados nacionais | [18](handoffs/task-18.md) |
| 19–26 | Não iniciadas; definidas no [plano de conclusão](../../research/completion-plan.pt-BR.md#fases-revisadas) | Todas | — |

## Onde estão os resultados

Caminhos em `data/` são relativos ao repositório e ignorados pelo Git. Caminhos
absolutos ficam no volume de saída da máquina de referência
`/media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/`.

| Artefato | Local |
| --- | --- |
| Originais brutos dos dois turnos (cópias de referência) | `raw/2026/turno-1/`, `raw/2026/turno-2/` no volume de saída |
| Certificados de cópia, cópias certificadas dos manifestos (entradas da análise), ledgers de verificação | `2026/migration-2026-11-01/` no volume de saída |
| Cópia verificada por hash dos dois turnos no SSD (leia estas nas passadas de logs), com certificados | `~/data/election-audit-stage/2026/turno-1/`, `~/data/election-audit-stage/2026/turno-2/` |
| Benchmarks de ordem de leitura | `~/data/election-audit-stage/benchmarks/` |
| Entradas pequenas da Fase 19 (BWEB, resultados, perfil do eleitorado, correspondências, GEDAI), cada uma com catálogo, manifesto e estado | `~/data/election-audit-stage/inputs/<dataset>/` |
| Arquivos em massa de BU/RDV/log da Fase 19, 2026 e 2022 | `bulk/2026-arqurnatot/`, `bulk/2022-arqurnatot/` no volume de saída |
| Relatórios de equivalência, passada de desenvolvimento do AC e passadas nacionais da Fase 21 | `~/data/election-audit-stage/phase21/` |
| Manifestos originais da coleta (vivos) | `.local-state/` |
| Metadados da coleta no HDD antigo (cobertura, marcadores, manifesto obsoleto anterior à divisão) e o store por evento inicial da Fase 11 do AC, verificados por hash; os objetos brutos do HDD antigo duplicavam as cópias certificadas e foram liberados para exclusão em 3 de novembro de 2026 | `archive/old-hdd-2026-11-03/` no volume de saída |
| Logs de execução e registros de lançamento da coleta | `data/phase10/` |
| Release de resumos do segundo turno da Fase 11 | `2026/runoff-summary-analysis-full-20261102/` no volume de saída |
| Configuração, progresso e benchmarks do job da Fase 11 | `data/national/phase11-feature-oriented-2026-11-02/`, ponteiro `data/national/current-phase11.json` |
| Job em nível de evento substituído (parado em 2 de novembro com 15425 objetos) | `data/national/phase11-overnight-2026-11-01/`; não retome |
| Ajustes, parcelas, capacidade e revisões de proteção anteriores da Fase 11 | `data/national/phase11-*-2026-10-31/` |
| Demo, piloto e pacotes de revisão da fundação | `data/phase9/` |
| Importação oficial BWEB do AC | `data/official-bu/ac-runoff-2026-10-30/` |
| Artefatos de desenvolvimento do AC, Fases 12–17 | `data/phase12/` … `data/phase17/` |
| Conjuntos de dados dos painéis | `data/dashboard-ac-2026-10-30/`, `data/dashboard-development-2026-10-30/` |

## Mapa de interfaces

| Área | Módulos e guias |
| --- | --- |
| Ambiente | `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked` |
| CLI | `election_audit/cli.py`. Legados: `download resume inspect doctor`. Pipeline: `snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill`. Extensões: `national electoral-verify operational-review features research-protocol research-models investigations dashboard dashboard-export stage-sources bulk-download semantic-pass` |
| Receitas | `justfile`; uma receita por comando da CLI, mais `setup doctor fmt lint test contracts-check docs-check docs-command-check check` |
| Coleta | `scripts/download_tse_logs.py` (`--round 1` ou `--round 2`), `election_audit/elections.py`; cópia para SSD `source_staging` (`stage-sources`); arquivos de dados abertos `bulk_acquisition` (`bulk-download`); [referência de coleta](acquisition-reference.md) |
| Snapshot/origem/cobertura | `source_inventory`, `coverage`, `snapshots`; [snapshots](snapshots.md) |
| Parse estrutural | `archive_parsing` (`jez-structural-v1`); [parse de arquivos](archive-parsing.md) |
| Reconstrução operacional | `reconstruction` (`operational-v1`), `operational_review` (`real-operational-v1`, Fase 13), `semantic_pass` (`session-aggregates-v1`, Fase 21); [reconstrução](reconstruction.md), [passada semântica](semantic-pass.md) |
| Releases operacionais | `publication`, `operational_marts`, `release_tools`; [publicação](publication.md) |
| Processamento estrutural nacional | Caminho de resumos: `national_parallel`, `national_summary`, `national_summary_release`, `national_summary_tools`, `national_summary_tuning`, `national_resources`; [processamento orientado a features](feature-oriented-processing.md). Caminho em nível de evento: `national_benchmark`, `national_tuning`, `national_workload`, `national`, `national_storage`, `national_relocation`, `national_migration`, `national_overnight`; [processamento nacional](national-processing.md) |
| Importação e verificação eleitoral | `electoral_imports`, `electoral_results`, `derivatives`, `electoral_reports`, `official_bu`; `binary_bu` e `electoral_verification` (Fase 12); [resultados eleitorais](electoral-results.md). `electoral_references` é um protótipo sem integração na CLI e sem testes para conjuntos de referência oficiais |
| Fundação analítica | `analysis`, `analysis_partitions`, `analysis_ledgers`, `analysis_reports`; [análise](analysis.md) |
| Caminho de pesquisa | `features` (Fase 14), `research_protocol` e `research_evaluation` (Fase 15), `research_models` (Fase 16), `investigations` (Fase 17); veja seus handoffs |
| Painel | `dashboard`, `dashboard_data`, `dashboard_ui`, `dashboard_development`, `election_audit/notebooks/` (Fase 18) |
| Reprodução | `reproduction`, `pilot`, `walkthrough`; [reprodução](reproduction.md), [backfill](backfill.md) |
| Contratos | `election_audit/resources/contracts/schema.json` e `features.json`; `contracts.py`; [dicionário do esquema](schema-dictionary.md), [prontidão de features](feature-readiness.md), [convenções de transformação](transformation-conventions.md) |
| Documentos de pesquisa | [protocolo do estudo](../../research/analysis-plan.pt-BR.md), [plano de conclusão](../../research/completion-plan.pt-BR.md), [fontes de download](../../research/download-sources.pt-BR.md), [trabalhos relacionados](../../research/related-work.pt-BR.md) |
| Verificação de documentação | `scripts/check_docs.py` (pares, revisões, links, paridade de blocos), `scripts/check_doc_commands.py` (flags via `--help`, sintaxe SQL) |

Pares em `docs/en/` e `docs/pt-BR/` compartilham Document-ID e Revision; documentos
de pesquisa mantêm caminhos em inglês com equivalentes `.pt-BR.md`. Incremente as
duas revisões juntas. Código, comandos, SQL, fórmulas e números permanecem idênticos
byte a byte.
