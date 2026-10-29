# Tarefa 8.2 — Partições fixadas por local estável

Document-ID: EA-HANDOFF-8.2 · Revision: 1 · Language: pt-BR

Objetivo: persistir populações exatas, sementes, estratos geográficos e atribuições de treinamento/calibração/teste. `analysis_partitions.assign_partitions` e `partition_tables` exigem vínculos estáveis entre turnos verificados com âncoras dos registros originais. Mesmo código de seção, ID de local limitado à eleição ou nome de escola não estabelece identidade. Vínculos desconhecidos preservam linhas inelegíveis.

Artefatos: `partition_plan` fixa hash da população exata ordenada, frações, semente/versão, vínculos e regra; `location_partition` preserva cada observação e evidência de identidade. Limiares SHA256 operam nos estratos UF/município; estratos pequenos não precisam realizar contagens exatas solicitadas. Uma lista de estresse municipal reserva municípios inteiros. Mudanças de população/semente/versão criam novas identidades; artefatos dos pais são imutáveis.

Aceitação: três testes focados passaram (código 0): agrupamento verificado entre turnos/sem sobreposição/desconhecidos; estabilidade à ordem/retomada, mudança de semente/população e estresse municipal; rejeição de vínculos obsoletos/conflitantes/não verificados, geografia e frações inválidas. Integração persistida com derivado/relatório incluída nas verificações finais da tarefa 8.3.

Próxima: tarefa 8.3, registros imutáveis de protocolo/exploração/investigação, cenários condicionais e histórico de acesso ao teste. Identidade do local é uma alegação com evidência, não vínculo certificado de corpus real. Sem leitura de dados reais ou aquisição.
