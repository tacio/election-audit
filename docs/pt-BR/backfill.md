# Processamento retroativo retomável e planejamento de armazenamento

Document-ID: EA-BACKFILL · Revision: 4 · Language: pt-BR

O processamento retroativo é operação derivada explícita sobre um snapshot imutável, com um grupo limitado de reconstrução por objeto de conteúdo. Não invoca aquisição. Repetir entrada congelada, saída e configuração de recursos idênticas verifica/reutiliza cache estrutural, contexto compartilhado, fragmentos concluídos e publicação; restaura current somente para publicação verificada. Downloads posteriores exigem novo snapshot e não ampliam silenciosamente processamento existente.

Os comandos abaixo para toda a população disponível estão documentados e suas receitas/opções verificadas, mas o processamento completo AC–RJ NÃO foi executado; a passagem estrutural nacional usou o caminho de resumos em [processamento orientado a features](feature-oriented-processing.md). Substitua /large-volume por armazenamento provisionado e SNAPSHOT_DIGEST pelo diretório congelado real. Entradas ausentes/não publicadas ficam explícitas; AC–RJ nunca vira completude nacional. Manifestos de coleta e raízes brutas nunca são modificados.

```sh
rtk proxy env UV_OFFLINE=1 just snapshot --source /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/raw/2026/turno-2 --store /large-volume/audit/snapshots --ufs ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj --reserve-gib 10
rtk proxy env UV_OFFLINE=1 just backfill /large-volume/audit/snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/backfill --max-events 100000
rtk proxy env UV_OFFLINE=1 just backfill /large-volume/audit/snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/backfill --max-events 100000
rtk proxy env UV_OFFLINE=1 just validate /large-volume/audit/backfill/warehouse
rtk proxy env UV_OFFLINE=1 just report /large-volume/audit/backfill/warehouse --output /large-volume/audit/reports --language both
```

Padrões: 4 trabalhadores de análise estrutural, 4 threads DuckDB, 12 GiB de memória, limite de temporários de 8 GiB, reserva livre de 10 GiB, lotes de 2048 linhas e 100000 eventos por grupo. Durante a Fase 9 o SSD tinha aproximadamente 31.6 GB livres (decimal): reserva mais temporários potenciais consomem aproximadamente 19.3 GB, restando cerca de 12.3 GB antes de snapshots, cache, contexto JSON compartilhado, arquivos de reconstrução, banco/fatos, área temporária, pacotes e folga. Proteções de espaço são aplicadas, mas não garantem capacidade.

Fatos e audit.duckdb ficam juntos no armazenamento da publicação; a implementação não coloca Parquet no HDD e somente DuckDB no SSD por opção de armazenamento separado. O contexto populacional de snapshot/análise/reconstrução também mantém índices completos das UFs selecionadas, mesmo com cinco principais. Não alegue que todo o processamento cabe no SSD atual. Provisione armazenamento maior, ou selecione/revise explicitamente populações geográficas administráveis e mantenha denominadores separados. Populações compactas de análise nacional também são limitadas por max_events; não é treinador de modelos nacionais.

Nenhuma estimativa nacional de tamanho/desempenho é inferida multiplicando amostra de cinco principais. Meça inventários congelados e cada etapa antes de ampliar: bytes selecionados, metadados completos das UFs, expansão, duplicação de contexto entre armazenamentos, tamanhos DB/Parquet, temporários, cópias de revisão e espaço livre. Recuse ampliação quando reserva/temporários/folga não couberem. Limites de arquivo/membro/linha/evento podem interromper objetos grandes; mantenha-os para revisão posterior explícita em vez de elevar limites sem critério.

A receita exata de retomada limitada do piloto abaixo é executada duas vezes na aceitação, e fixture sintética interrompível lança erro imediatamente antes da renomeação, verifica ausência do marcador current e então retoma com sucesso. Artefatos concluídos ficam imutáveis; área temporária falha não é sucesso. Retomada limitada evidencia reinício, não execução de toda a população.

```sh
rtk proxy env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
rtk proxy env UV_OFFLINE=1 just backfill data/phase9/pilot/snapshots/0d098eceab46aa73914794ec35a2ae578be3aa6eebcbf168bd00fd38afb0bf71 --output data/phase9/pilot
```

UFs adicionais do segundo turno, incluindo ZZ, devem ser explícitas. A raiz original precisa conter originais/índices disponíveis dessas UFs; ausentes ficam indisponíveis. Outros turnos/histórico usam pacotes normalizados explícitos documentados separadamente, com hashes originais, contratos exatos de eleição/turno e harmonização revisada. `snapshot --round 1` seleciona o primeiro turno, pleito 3220/eleição 6257 (o padrão é o turno 2), e `--source-manifest` substitui o manifesto encontrado pelo marcador de localização da raiz. Não renomeie bytes do segundo turno como primeiro turno. Importações oficiais de BU estão descritas no [guia eleitoral](electoral-results.md).

```sh
rtk proxy env UV_OFFLINE=1 just snapshot --source /explicit/additional-runoff-root --store /large-volume/audit/additional-snapshots --ufs rn ro rr rs sc se sp to zz --reserve-gib 10
rtk proxy env UV_OFFLINE=1 just backfill /large-volume/audit/additional-snapshots/SNAPSHOT_DIGEST --output /large-volume/audit/additional-backfill
rtk proxy env UV_OFFLINE=1 just import-results /large-volume/audit/backfill/warehouse/releases/PARENT_DIGEST --bundle /reviewed/explicit-round-import/bundle.json --store /large-volume/audit/round-imports
```

Use [reprodução](reproduction.md) para pacote de revisão sem rede, amostragem diagnóstica, distinção das identidades de origem/derivadas, artefatos temporais reais e relatórios bilíngues. Handoffs da tarefa 9 registram resultados exatos medidos e menor tarefa restante.
