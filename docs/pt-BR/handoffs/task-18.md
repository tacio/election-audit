# Fase 18 — Exploração portátil com marimo

Document-ID: EA-HANDOFF-18 · Revision: 1 · Language: pt-BR

Quatro notebooks empacotados cobrem cobertura/integridade, resultados eleitorais, operações e evidências de modelos/investigação. `dashboard_main` inicia a galeria local; `dashboard_export_main` exporta marts de publicações imutáveis para novo diretório portátil. Ambos ficam em `election_audit.dashboard`.

`AuditDataset.open(uri)` aceita manifestos locais e HTTPS com referências relativas Parquet e checksums; páginas limitadas, filtros, CSV e downloads de proveniência preservam zero versus desconhecido. Arquivos remotos usam cache verificado limitado; HTTP local é explicitamente restrito a testes. `publish_dataset` recebe fluxos de linhas já filtrados por acesso em lotes de 2048. Publicações protegidas exportam somente atributos de desenvolvimento e metadados de cobertura reduzidos. Inspeção do teste não autoriza exportar resultados: o produtor futuro deve fornecer `research_evaluation.final_evaluation_complete(db, document)` validando avaliação final e referências imutáveis.

Aceitação: seis testes do painel passam, verificações/formatação Ruff passam e marimo verifica os quatro grafos reativos. A publicação real AC foi exportada para `data/dashboard-ac-2026-10-30/dataset.json`; 54166 linhas de cobertura, 2270 de reconciliação e marts atualmente não resolvidos mantêm populações originais. O notebook de cobertura executou com sucesso para HTML. O conjunto é explicitamente exploratório e sem partição, não certificação de resultado final.

Limites: faltam nos marts muitas medidas eleitorais/operacionais elegíveis, ajustes de modelos e coordenadas verificadas. Páginas exibem indisponibilidade; mapas exigem latitude/longitude verificadas fornecidas, sem inventar locais. Gráficos descrevem a página limitada selecionada, não distribuição nacional. Testes completos de interação no navegador permanecem para integração. Ações dos notebooks não adquirem dados, reconstroem nem ajustam modelos. Não houve hospedagem pública.

Dependências opcionais `dashboard`: marimo 0.25.0 e Altair 6.3.0. O agente principal integra CLI/receitas e fixa dependências. A Fase 14 deve preencher o esquema portátil; Fases 15–16 devem implementar evidência validada da avaliação final. Publicações e originais existentes não foram alterados.
