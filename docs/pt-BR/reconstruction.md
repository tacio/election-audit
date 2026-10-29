# Reconstrução operacional

Document-ID: EA-RECONSTRUCTION · Revision: 1 · Language: pt-BR

[English](../en/reconstruction.md) · [Índice de implementação](implementation-index.md)

A Fase 5 lê [publicações de análise](archive-parsing.md) congeladas e verificadas,
nunca a aquisição ativa. `operational-v1` produz sessões candidatas, eventos em
ordem original, ciclos anônimos, linhagem, problemas originais da análise e resumos
operacionais. Preserva todas as testemunhas do publicador sem multiplicar eventos
do conteúdo. As contagens são ciclos anônimos reconstruídos, nunca votos
reconciliados nem associações com candidatos/RDV. A aceitação é inteiramente
sintética; nenhum adaptador de mensagens reais ou piloto ativo foi validado. O
analisador estrutural de três classes permanece `jez-structural-v1`.

```sh
rtk proxy env UV_OFFLINE=1 just reconstruct /path/to/parsed/parses/PARSE_DIGEST --store /path/to/operations
rtk proxy env UV_OFFLINE=1 just reconstruct --help
rtk proxy env UV_OFFLINE=1 just reconstruct /path/to/parsed/parses/PARSE_DIGEST --store /path/to/operations --object-sha256 OBJECT_SHA256 --max-events 100000
```

## Observações automáticas e afirmações revisadas

Sem evidências adicionais, a ocorrência do membro, a ordem original das linhas,
mudanças na coluna do dispositivo e na data civil ingênua geram limites
conservadores de sessões candidatas. `session_kind=unresolved`, seleção do alvo e
identidade física continuam não resolvidos. A coluna do dispositivo é uma leitura
observada, não automaticamente um número de série oficial. Dispositivos
desconhecidos nunca se fundem por seção/modelo. Seções anunciadas pelos pacotes e
atribuições revisadas à seção principal permanecem separadas; conflitos com a
composição congelada ou com os pacotes impedem a seleção. Registros de preparação,
treinamento e outras datas permanecem visíveis.

O JSON opcional de evidências contém `version=operational-evidence-v1` e listas
`segments`, `copies`, `semantics`, `clocks`. Cada afirmação exige `rule_id`,
`review_state` (`reviewed` ou `unverified`) e entradas `evidence` com `event_id` e
`source_line_sha256` exatos. Identificadores de regras são limitados, sem texto
livre. As evidências não contêm identificadores de eleitores/mesários, mensagens
ou tokens. Campos desconhecidos são rejeitados. A correspondência de evento/hash
valida a proveniência, mas não demonstra que a interpretação humana está correta.
`reviewed` é uma afirmação de revisão fornecida, não um certificado criptográfico.
Afirmações não verificadas são preservadas nos metadados sem alterar seleção,
semântica ou relógios. A Fase 9 deve revisar o significado das fontes e criar
adaptadores reais testados e versionados.

| Lista de afirmações | Campos além da revisão/âncoras comuns | Significado |
| --- | --- | --- |
| `segments` | `event_ids`, `session_kind`, `principal_section_id`, `election_id`, `serial`, `software_version`, `software_build`, `start_reason`, `end_reason`, `distinct_history` | Linhas físicas originais consecutivas de um membro/dispositivo; contexto revisado oficial/preparação/treinamento/outro/não resolvido, evidências independentes opcionais de equipamento/programa e limites |
| `copies` | `canonical_event_ids`, `copied_event_ids` | Intervalos distintos consecutivos com pelo menos duas linhas originais, hashes exatos iguais incluindo quebras de linha; decisão explícita revisada de cópia, sem cadeias |
| `semantics` | `event_id`, `kind` | Interpretação operacional revisada ancorada naquele evento original; a classe original permanece em `event_evidence` |
| `clocks` | `event_ids`, `section_id`, `election_id`, `timezone`, `clock_adjustment_seconds`, `continuity` | Geografia exata de seção/eleição, fuso IANA opcional, correção com sinal e continuidade verificada/desconhecida em um intervalo consecutivo |

Os motivos de limites de sessão aceitos são `unknown`, `opening`, `closing`,
`restart`, `replacement`, `truncated`. Segmentos distintos de substituição nunca
se fundem apenas por compartilharem a seção principal. `distinct_history=true` é
uma afirmação revisada de que históricos repetidos entre fluxos são
operacionalmente distintos. Sem essa afirmação ou regra verificada de cópia,
possíveis históricos iguais entre fluxos permanecem com impedimento de prontidão.
Igualdade de classe/horário ou linhas repetidas no mesmo fluxo original nunca
acionam deduplicação automática. A linhagem da cópia preserva ambos os objetos,
todos os localizadores e observações.

Este exemplo sintético mostra a interface; âncoras reais devem vir de uma análise
verificada. Os identificadores ilustrativos não afirmam fatos sobre as fontes.

```python
from election_audit.reconstruction import reconstruct_parse

evidence = {
    "version": "operational-evidence-v1",
    "segments": [
        {
            "event_ids": ["EVENT_A", "EVENT_B"],
            "session_kind": "official_vota",
            "principal_section_id": "SECTION_ID",
            "election_id": "ELECTION_ID",
            "rule_id": "reviewed-format-reference-v1",
            "review_state": "reviewed",
            "evidence": [{"event_id": "EVENT_A", "source_line_sha256": "EXACT_LINE_SHA256"}],
        }
    ],
}
path = reconstruct_parse("/path/to/parse", "/path/to/operations", evidence=evidence)
```

## Transições anônimas

A habilitação básica seguida de conclusão reconstrói um ciclo concluído com
método desconhecido. Uma solicitação de dados para habilitação manual cria um
histórico pendente; nunca estabelece habilitação bem-sucedida nem método manual.
Solicitação → habilitação → conclusão ainda tem método desconhecido. Apenas
evidência explícita do método e conclusão bem-sucedida após habilitação estabelecem
um ciclo manual concluído.

| Entrada durante o acompanhamento de um ciclo | Resultado |
| --- | --- |
| Habilitação repetida ou nova tentativa explícita | Preserva o histórico anterior não resolvido e inicia outro |
| Conclusão sem habilitação ativa | Órfão não resolvido ou conclusão sem habilitação |
| Evento intermediário desconhecido ou linhas físicas ausentes | Preserva transições não resolvidas |
| Suspensão total | Encerra um histórico suspenso |
| Suspensão parcial/retomada | Preserva um ciclo interrompido; duração ativa sem suporte fica nula |
| Cancelamento, abandono, falha de habilitação | Encerra histórico cancelado com motivo distinto |
| Histórico aberto ao final | Histórico parcial não resolvido ou suspenso |

As classes adicionais revisadas são `authorization_attempt`,
`authorization_failed`, `authorization_manual`, `authorization_biometric`,
`authorization_other`, `suspension_full`, `suspension_partial`, `resumption`,
`cancellation`, `abandonment`, `session_opening`, `session_closing`, `clock_change`.
Texto real desconhecido nunca recebe essas classes por frase presumida ou
expressão regular abrangente.

## Tempo e elegibilidade

Leitura original, regra explícita de fuso, deslocamento UTC, correção com sinal,
instante UTC, confiança e evidência permanecem separados. Exceções municipais e
locais no exterior usam regras evidenciadas de seção/eleição exatas. Nenhum padrão
por UF, horário aparentemente precoce/tardio ou horário de recepção/publicação
fornece fuso. Fusos ausentes continuam nulos; horários locais IANA ambíguos ou
inexistentes permanecem não resolvidos. O instante UTC é a leitura local corrigida
menos o deslocamento evidenciado. Correções e reversões permanecem visíveis na
ordem original.

Durações exigem um único intervalo contínuo revisado, todos os registros
intermediários, leituras corrigidas monotônicas e nenhum evento intermediário ou
mudança de relógio sem suporte. Um intervalo verificado sem fuso pode sustentar
tempo local decorrido limitado enquanto UTC continua indisponível. Mudanças de
intervalo de regra invalidam duração sem suporte, mesmo quando os identificadores
das regras coincidem. A duração do ciclo concluído começa na habilitação
bem-sucedida e exclui solicitação anterior; a latência de habilitação é separada.
Ciclos interrompidos não têm duração ativa. Intervalos entre ciclos usam ciclos
concluídos adjacentes na mesma sessão, sem saltar históricos não resolvidos ou
atravessar substituições. Nas fases seguintes, after17 doméstico significa
estritamente após `17:00:00` em `America/Sao_Paulo` na data-alvo; a Fase 5 não faz
essa classificação. O exterior permanece separado.

Os resumos incluem ciclos observados por estado, ciclos concluídos elegíveis,
denominadores de métodos conhecidos/desconhecidos, solicitações manuais observadas,
denominadores explícitos de tentativas/falhas, contagens elegíveis de durações e
intervalos, latência de habilitação, interrupções e evidência de abertura/fechamento.
Totais elegíveis ausentes continuam nulos. `known_completed_manual_cycles` conta
conclusões manuais observadas com método conhecido; `completed_manual_cycles`
continua nulo se algum método concluído é desconhecido. A proporção manual aplica-se
apenas a ciclos concluídos com método conhecido. A taxa de falha usa tentativas
explícitas observadas; a população completa de tentativas continua desconhecida.
Prontidão específica de duração, método e exposição permanece separada.

A amplitude observada não é automaticamente exposição. A exposição exige
abertura/fechamento únicos evidenciados nos limites do intervalo, relógios contínuos
com suporte e intervalos de interrupção resolvidos; subtraem-se os segundos de
interrupção sustentados. Limites desconhecidos, problemas de análise, históricos
copiados ambíguos ou contexto operacional impedem prontidão de exposição/contagem
do alvo. Cobertura original completa e ativos ausentes do snapshot permanecem na
publicação. AC–RJ e qualquer amostra de objetos/seções continuam com cobertura
nacional parcial e denominador congelado do índice completo.

## Interface imutável e grupos limitados

`reconstructions/DIGEST/` contém `reconstruction.json` com soma de verificação e
arquivos JSONL das oito tabelas contratuais de sessão/dispositivo/evento/ciclo/
linhagem/problema, além de `event_evidence`, `session_summaries`, `cycle_gaps`,
`interruptions`. Preparação privada, fsync, bloqueio derivado e renomeação atômica
impedem publicação parcial bem-sucedida. Reexecuções verificam artefatos imutáveis;
corrupção falha explicitamente. A inspeção funciona após remover os insumos
originais, snapshots e análises, desde que o contexto compartilhado da
reconstrução seja mantido. As entradas originais nunca são alteradas. Os metadados
completos da população ficam uma única vez em `contexts/PARSE_ID/parse.json`; os
grupos referenciam seu localizador relativo validado e SHA-256. Transfira o
armazenamento completo, incluindo `contexts`.

| API Python em `election_audit.reconstruction` | Finalidade |
| --- | --- |
| `reconstruct_parse(parse, store, evidence=None, object_sha256=None, max_events=1000000, reader=None)` | Verificar análise/grupo e publicar reconstrução imutável |
| `inspect_reconstruction(path)` | Verificar identidade dos metadados e somas de todos os arquivos de linhas |
| `load_reconstruction_context(path)` | Verificar/carregar população completa e contexto congelado compartilhados |
| `iter_reconstruction_rows(path, table)` | Verificar e transmitir uma tabela contratual/intermediária |
| `reconstruct_sessions`, `reconstruct_cycles`, `normalize_clocks`, `summarize_operations` | Unidades limitadas em memória para testes/adaptadores |

O limite padrão conta eventos únicos de conteúdo e no máximo dez vezes esse
número de testemunhas do publicador; exceder qualquer limite aborta a publicação.
Use `--object-sha256` repetido ou a lista Python para pequenos grupos relacionados.
O argumento opcional `object_sha256` em `inspect_parse`, `iter_event_witnesses` e
`iter_parsing_issues` verifica/lê apenas conteúdos selecionados, sempre verificando
a identidade completa dos metadados da publicação. Omiti-lo preserva a verificação
completa. Todas as testemunhas dos conteúdos selecionados permanecem. Os próprios
metadados/contexto da publicação de análise permanecem em memória; portanto, isto
não é um mecanismo nacional de metadados inteiramente em fluxo.

Para processamento completo, reutilize `FrozenParseReader` para verificar/carregar
os metadados da análise e indexar associações uma única vez.
`reader.group(object_sha256)` verifica apenas o conteúdo daquele grupo e retorna
iteradores de testemunhas e problemas. Passar o leitor à reconstrução também
reutiliza a publicação de contexto compartilhado entre grupos. Seu `document` é
imutável por convenção. Problemas estruturais em um grupo permanecem impedimentos
conservadores nos resumos operacionais do alvo.

```python
from election_audit.archive_parsing import FrozenParseReader
from election_audit.reconstruction import reconstruct_parse

reader = FrozenParseReader("/path/to/parsed/parses/PARSE_DIGEST")
for object_sha256 in sorted(reader.artifacts):
    path = reconstruct_parse(
        reader.path,
        "/path/to/operations",
        object_sha256=[object_sha256],
        reader=reader,
    )
```

Grupos independentes preservam identidade de sessão/ciclo quando as evidências
não mudam. Inclua históricos de substituição/cópia juntos quando necessário; a
sobreposição entre grupos não é resolvida. A Fase 6 deve registrar uma partição
disjunta dos objetos de conteúdo, rejeitar chaves repetidas de evento/sessão/ciclo
ao reunir grupos, preservar `overlap_resolution_scope=selected_object_group_only`
de cada grupo e não pode afirmar que grupos independentes demonstram ausência de
históricos copiados. Cópias ou mudanças de contexto exigem nova reconstrução
evidenciada e substituição da publicação afetada. Não há publicação DuckDB/Parquet,
importações eleitorais, ajuste de modelos ou rótulos de fraude.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_reconstruction.py -v
rtk proxy env UV_OFFLINE=1 just check
```
