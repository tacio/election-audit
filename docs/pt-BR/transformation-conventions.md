# Convenções de transformação

Document-ID: EA-TRANSFORMATION-CONVENTIONS · Revision: 2 · Language: pt-BR

[English](../en/transformation-conventions.md)

1. **Entradas imutáveis.** Resolva o manifesto autorizado com `manifest_path(root)`
   e `manifest-location.json`. Use transação de leitura consistente ou backup SQLite;
   nunca copie arquivo de banco ativo sem seu WAL confirmado. Preserve objetos
   originais e aquisição ativa. Congele observações URL-objeto, vínculos de execução
   e metadados, tentativas falhas, cobertura esperada e política. Mapeamento histórico
   irrecuperável é explicitamente desconhecido; o mapeamento atual de `files` não
   comprova bytes antigos. Este contrato não inclui downloads nacionais.
2. **Identidade.** Delimite identidades de seção/local/disputa pela eleição. IDs opacos
   usam namespace versionado e resumo de tuplas de chaves naturais em JSON canônico
   (chaves ordenadas, UTF-8, sem espaço insignificante). Preserve chaves naturais e
   versão da regra; nunca identifique dispositivo/sessão/pacote/resultado só pela
   seção. Não una dispositivos desconhecidos por modelo. Mudança principal do contrato
   exige nova publicação; observações/resultados só acrescentados permanecem imutáveis
   e derivações fixam versões de parser, transformação, seleção e esquema.
3. **Registros de origem.** Localizador registra cada segmento de arquivo aninhado,
   nome original do membro e índice de ocorrência (ZIP pode repetir nomes), mais
   intervalo original de bytes/linhas/registros quando conhecido. Identidade do evento
   inclui objeto/ocorrência do membro, linha/sequência original e versão do parser.
   Nunca a derive só de horário e texto. Não invente deslocamento de bytes após
   decodificar. Toda linha derivada aponta para pelo menos um registro original;
   mantenha também evidências duplicadas/conflitantes. Selecione só campos necessários
   à operação. Não exponha IDs de eleitor/mesário nem tokens sensíveis desnecessários
   em eventos/problemas estruturados; bytes originais continuam preservados à parte
   sob seus limites existentes de acesso.
4. **Decodificar antes de selecionar.** Preserve token bruto e ordem original; valide
   codificação, cabeçalhos, larguras e significados por versão. Mantenha eventos de
   preparação, treinamento e outros turnos com motivos de seleção. Reconstrua sessões
   oficiais VOTA, transições, substituições e ciclos antes de extrair atributos.
   Solicitação de dados manuais pode ser cancelada. Ciclos completos, suspensões,
   tentativas e casos não resolvidos são distintos. Ordem do RDV não identifica
   escolhas nos ciclos anônimos.
5. **Relógios.** Preserve separadamente leitura, regra de fuso e evidência, deslocamento,
   ajuste e confiança. Verifique exceções municipais e regras no exterior; nunca
   infira fuso de voto aparentemente cedo/tarde. Horário absoluto não resolvido
   bloqueia atributos absolutos, mas pode permitir contagens ou durações limitadas.
   after17 doméstico significa estritamente após 17:00:00 de Brasília
   (`America/Sao_Paulo`) na data alvo; exterior fica separado. Recebimento,
   processamento, geração, publicação, observação, abertura/fechamento e transmissão
   não se substituem.
6. **Deduplicar com evidência.** Identidade de bytes deduplica objetos, não
   necessariamente sessões/resultados. Blocos copiados/sobrepostos verificados exigem
   linhagem explícita e regra de reconstrução. Mensagem/horário em segundos repetidos
   podem ser legítimos. Sessões de substituição não podem ser somadas por cada pacote
   que as testemunha. Duplicação não resolvida fica indisponível, sem adivinhação.
7. **Unir e somar com segurança.** Selecione um resultado canônico elegível por
   `(snapshot_id, principal_section_id, contest_id)` antes de agregar. Valide unicidade
   à direita de cada união muitos-para-um e preserve contagens de linhas/chaves.
   Agregue escolhas à granularidade de resultado antes de anexar totais. Nunca some
   eleitorado/comparecimento após unir totais a várias escolhas, integrantes,
   sessões, pacotes ou linhagens. Use integrante-principal só para resolver a principal
   analítica única; harmonização histórica agrega cada população disjunta uma vez.
   Correspondências incomparáveis permanecem indisponíveis.
8. **Reconciliar antes de publicar.** Verifique além da estrutura: chaves estrangeiras,
   contexto eleitoral/disputa, autoatribuições/ausência de ciclos da composição,
   estado/identidade canônica, contagens não negativas, completude das escolhas,
   contabilidade de categorias, definições de comparecimento/eleitorado e população
   esperada. Compare município/UF/BR incluindo ZZ em snapshots coerentes. Separe
   lacunas de cobertura de discrepâncias numéricas. Preserve correções/decréscimos
   e resultados concorrentes. SHA-256/CRC não verificam assinatura nem intenção do voto.
9. **Publicar disponibilidade.** Conte integrantes esperadas e principais únicas
   separadamente; registre instaladas/não instaladas, ausentes, falhas, exclusões e
   desconhecidos. Sem descarte silencioso nem conversão de nulo em zero. Prontidão
   é por atributo/unidade; registre denominador e motivo. Um subconjunto de UFs ou uma
   população de desenvolvimento (por exemplo, o AC) é cobertura nacional parcial,
   insuficiente à inferência nacional. Histórico exige importação explícita com
   esquema validado. Estágios do pipeline não ajustam modelos nem produzem rótulos de
   fraude; o ajuste pertence às fases de pesquisa.

Um exemplo sintético fixa a contabilidade. Um resultado tem eleitorado `100`,
comparecimento `80`, candidatos `45` e `30`, branco `3`, nulo `2` e
especial/não resolvido `0`. Há uma linha de totais e quatro de escolhas. Unir
escolhas e somar comparecimento repetido produziria `320`; o correto é `80`.
Duas seções integrantes apontando para essa principal ainda representam `80`,
não `160`. O exemplo é artificial e não descreve dados observados.

```sql
-- Synthetic example only; no acquisition table is queried.
WITH totals(result_version_id, attending_voters) AS (VALUES ('r1', 80)),
choices(result_version_id, vote_count) AS
    (VALUES ('r1', 45), ('r1', 30), ('r1', 3), ('r1', 2)),
choice_totals AS (
    SELECT result_version_id, SUM(vote_count) AS ballots
    FROM choices GROUP BY result_version_id
)
SELECT t.attending_voters, c.ballots
FROM totals t JOIN choice_totals c USING (result_version_id);
```

Resultado esperado: `80`, `80`. Não use `SUM(DISTINCT attending_voters)` para
corrigir união multiplicada: totais iguais em seções diferentes são legítimos.
