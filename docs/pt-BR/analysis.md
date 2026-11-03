# Fundação de análise estatística

Document-ID: EA-ANALYSIS · Revision: 3 · Language: pt-BR

[English](../en/analysis.md) · [Índice](implementation-index.md) · [Pai eleitoral](electoral-results.md)

A fase 8 publica fundamentos descritivos a partir de uma release derivada operacional ou eleitoral imutável. Não ajusta modelos nem aplica rótulos automáticos de fraude. Qualquer subconjunto de UFs, incluindo o snapshot padrão AC–RJ, é cobertura nacional parcial. Cada variável numérica preserva seus bloqueios de qualidade da fonte (vínculo de totalização final, evidência completa de escolhas e referências finais independentes continuam indisponíveis), disponibilidade temporal desconhecida e elegibilidade científica indisponível. Não se afirma permutabilidade ou margem nacional final coerente. O ajuste de modelos ocorre só no caminho de pesquisa posterior (`features`, `research_protocol`, `research_models`, `investigations`; Fases 14–17), documentado em seus handoffs.

Use configuração local explícita, com até 8 MiB. Os campos opcionais candidate_a/candidate_b devem ser IDs oficiais de candidatura da disputa, distintos e fixados juntos; nenhum é inferido. Vínculos vazios preservam cada local desconhecido como inelegível. Os bytes da configuração são preservados e fixados no novo filho.

```json
{
  "version": "audit-analysis-v1",
  "cutoff_at": "2026-10-29T00:00:00+00:00",
  "partition": {
    "version": "location-partition-v1",
    "seed": "reviewed-protocol-v1",
    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
    "links": [],
    "municipal_holdout": []
  },
  "records": []
}
```

```sh
rtk proxy env UV_OFFLINE=1 just analyze /ssd/audit/releases/PARENT_DIGEST --bundle /ssd/design/analysis.json --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just validate /ssd/audit
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT partition_id, payload FROM partition_plan'
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT feature_id, count(*) FROM training_features GROUP BY feature_id'
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports --language both
```

`analysis.publish_analysis(parent, bundle, store, config=None)` usa bloqueio, limites de recursos, transação de staging/fsync/rename/ponteiro atual e cadeia relativa de pais verificada existentes. Fatos operacionais do pai são reutilizados, sem cópia ou reescrita. O registro longo `audit_features` transmite lotes limitados de SQL. Populações compactas de vínculos, catálogos de evidências e registros analíticos herdados/atuais são limitados por max_events; esta é uma fundação, não treinamento nacional de modelos em fluxo. Falha de publicação preserva o artefato atual anterior; chamadas idênticas retomam. Preserve toda a cadeia relativa de pais ao mover.

Os 21 contratos aparecem em `audit_feature_registry`, com entradas exigidas exatas, definições, componentes, tabelas de origem, unidades, descrições de numeradores/denominadores, regra temporal, papéis, especificações e bloqueios. Cada principal esperado e seção congelada não resolvida preserva linhas em `audit_features`; cada valor tem chaves do pai/origem, versão de transformação, numerador, denominador, corte e indicadores de qualidade. Comparecimento, proporções separadas de brancos/nulos e A/(A+B), B/(A+B) simétricos podem ser calculados de contagens normalizadas completas e reconciliadas; eleitorado é contexto descritivo. Denominadores ausentes/zero e A/B/categorias não resolvidos ficam indisponíveis. Outros componentes operacionais, temporais, históricos, de integridade, inferenciais e contrafactuais nomeiam explicitamente bloqueios e marts de origem. Não se presume linha de base do primeiro turno disponível.

A especificação operational_adjusted trata equipamento/modelo/versão/logística como ajustes possíveis; mechanism os preserva como mecanismos possíveis. no_first_round usa apenas contexto do ciclo atual; history_assisted exige histórico comparável. Comparecimento, autorização manual e interrupções nunca são controles automáticos. Datas de disponibilidade da origem atualmente permanecem desconhecidas, impedindo elegibilidade preditiva mesmo quando a aritmética retrospectiva está disponível.

Partições exigem vínculos estáveis de locais de votação revisados entre observações relacionadas, incluindo turnos e histórico. Mesmo nome de escola, código de seção ou ID de local limitado à eleição nunca estabelece identidade estável. Um vínculo tem exatamente estes campos; substitua o digest ilustrativo por hash real de source_object congelado. A publicação rejeita âncoras que não resolvem no catálogo verificado do pai. Localizadores e verified=true expressam alegações de revisão fornecidas; integridade dos bytes não certifica independentemente a identidade alegada.

```json
{
  "location_id": "election-scoped-id",
  "stable_location_id": "reviewed-cross-round-id",
  "verified": true,
  "evidence": {
    "object_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "record_locator": "exact preserved register/review record locator"
  }
}
```

`partition_plan` fixa população/hash exatos ordenados, semente/versão, frações, estratos geográficos UF/município, âncoras originais, regra e lista de reserva municipal (UF:municipality_tse). `location_partition` preserva cada observação. Um local estável recebe uma atribuição por limiar de probabilidade SHA256 no estrato, portanto estratos pequenos não precisam realizar frações exatas. Todas as observações relacionadas ficam juntas. Identidade desconhecida permanece indisponível, sem alternativa adivinhada. Designações de estresse municipal reservam municípios inteiros. Mudanças de população/semente/versão criam novos IDs; vínculos e atribuições publicados obsoletos/conflitantes falham. Planos e atribuições são acrescentados sem modificar publicações anteriores.

Primeiro publique a partição, leia seu partition_id exato e depois publique um filho com registros. Cada registro usa o envelope versionado exato abaixo; conflitos de record_id imutável falham, retransmissões idênticas são deduplicadas e novas versões usam novos IDs. Referências genéricas e tipadas são validadas antes da publicação atômica. A API aceita qualquer ordem de entrada.

```json
{
  "record_id": "protocol-v1",
  "version": "analysis-ledger-v1",
  "record_kind": "protocol",
  "analysis_run_id": null,
  "created_at": "2026-10-29T00:00:00+00:00",
  "references": [],
  "payload": {
    "state": "frozen",
    "question": "conditional_unusualness",
    "partition_id": "replace-with-persisted-partition-id",
    "family": [{
      "outcome": "turnout",
      "subgroup": "all",
      "window": "election_day",
      "scale": "location",
      "model_variant": "no_first_round",
      "historical_comparison": "none"
    }]
  }
}
```

Tipos em `analysis_ledger`: protocol fixa ou marca exploratória cada família de resultado/subgrupo/janela/escala/modelo/histórico; analysis_run fixa protocolo, snapshots, configuração de origem e IDs de configuração de modelo; model_config armazena estimador/hiperparâmetros/sementes com fitted=false; exploration preserva situação da família, result e null_result; analysis_snapshot lista o histórico e não pode ser completo omitindo membro registrado ou resultado explorado/nulo. O histórico fornecido atesta o trabalho registrado; o pipeline não descobre buscas externas não relatadas.

calibration registra população exata de locais persistidos de calibração, n_cal, configuração de escore e premissas não validadas. Unidades desconhecidas/de teste/treinamento não entram nessa população. score registra escore descritivo finito, referências correspondentes de configuração/calibração e unidade conhecida; interpretation deve ser descriptive_only. Não se produzem escores ajustados, valores-p válidos de fraude ou garantias de FDR. investigation preserva referências de escore/unidade, explicações alternativas, corroboração independente, cegamento ao candidato e conclusão não resolvida/benigna/requer revisão. Conclusões automáticas de fraude são rejeitadas. Âncoras originais devem resolver em objetos congelados.

Resultados de teste não inspecionados são reservados pela interface de consulta. Metadados e `training_features` continuam consultáveis; a última inclui unidades vinculadas de treinamento/calibração e exclui qualquer local reservado por população de teste intocada. Outras consultas de resultados e funções dinâmicas de tabela são bloqueadas enquanto houver local de teste intocado. Publique registro test_access com execução/protocolo/partição correspondentes, finalidade e inspection=true antes de inspecionar. `test_partition_status` marca esses locais como development_inspected para análises futuras, inclusive sementes/populações posteriores. Protocolo futuro fixado não pode reutilizar local de teste inspecionado. Carregadores internos apoiam validação; usá-los para inspecionar resultados também exige registrar acesso. Relatórios agregados de disponibilidade não revelam resultados individuais de teste.

Registros impact exigem um único snapshot/eleição/disputa e IDs distintos de candidatos, mecanismo explícito (removal_exact/removal_at_most/switching_cap), populações de principais afetadas, limites de cédulas concluídas e âncoras, tratamento de sobreposição, final_margin e margin_assumptions. Contagens publicadas devem corresponder ao alvo canônico normalizado fixado; isso não é validação independente de BU real. Contagens de turnos/disputas diferentes não podem ser somadas. Apenas principais disjuntos ou união deduplicada corroborada por principal são somados. Sobreposição, margem ausente ou limites sem suporte ficam indisponíveis. Escolhas do subconjunto anônimo permanecem desconhecidas. Limites são aritmética condicional sob margem/mecanismo declarados; não estabelecem votos roubados, atribuição a candidato, causalidade ou intervalo nacional de confiança. Margem assumida empatada exige uma troca para vitória estrita. O auxiliar puro aceita premissas explícitas de contagens; o publicador acrescenta validação de origem/alvo.

Relatórios usam en e pt-BR por padrão, compartilham cálculos idênticos em findings.json e incluem disponibilidade de variáveis, resumos de partição/acesso, contagens de registros, limites condicionais, SQL exato, configuração, validação e fixações de arquivos/tabelas de toda a cadeia de pais. `--language en|pt-BR|both` muda somente rótulos humanos. Relatórios devem ficar fora de cada pai e filho imutável.

O caminho de pesquisa se apoia nesses ledgers: a Fase 14 publica releases de features, a Fase 15 congela protocolos e o diário protegido de avaliação final, a Fase 16 ajusta modelos e a Fase 17 monta pacotes de investigação. Veja seus [handoffs](implementation-index.md#estado-das-fases). A aceitação desta fundação não autoriza ajuste de modelos nem rotulagem de fraude.
