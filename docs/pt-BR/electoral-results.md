# Importações eleitorais e publicações derivadas

Document-ID: EA-ELECTORAL-RESULTS · Revision: 2 · Language: pt-BR

[English](../en/electoral-results.md) · [Índice](implementation-index.md) · [Publicação](publication.md)

O adaptador oficial **tse-bweb-2026-v1** agora importa o CSV BWEB adquirido do
segundo turno no AC com dicionário incluído fixado, cabeçalho exato de 45 colunas,
codificação Latin-1 e mapeamento revisado de nominal/branco/nulo. A interface
**electoral-normalized-v1** permanece disponível para fontes normalizadas
explicitamente, incluindo outros turnos/histórico e referências externas. A
coleta de logs originais e publicações pais congeladas são preservadas. BUs usam
snapshot de origem separado; nenhum vínculo automático com sessões operacionais
ou conversão de relógio é inferido.

O ZIP oficial AC, arquivo SHA-512 e bytes das APIs do catálogo e do recurso foram
obtidos em 2026-10-30 UTC. O hash publicado confere e os CRCs do ZIP passam.
O arquivo tem 17622 linhas: 8697 presidenciais (eleição 6258, cargo 1) e 8925
para governador (eleição 6260, cargo 3), excluídas explicitamente. Todas as 2270
seções principais presidenciais passam nas verificações soma dos votos publicados
versus comparecimento e comparecimento mais abstenção versus eleitorado; escolhas
presidenciais publicadas somam 453654 votos. São verificações aritméticas reais,
não reconciliação independente do resultado final. Escolhas ausentes permanecem
desconhecidas, não zero. Apurada não é Totalizado: situação permanece desconhecida,
listas completas de escolhas não estão disponíveis e resultados canônicos/razões
ficam indisponíveis. Tokens originais de emissão/recebimento são preservados como
eventos de processamento não resolvidos. Categorias especiais/não resolvidas,
assinaturas e totais finais independentes permanecem sem verificação.

[Recurso oficial AC](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna/resource/4753eb99-062b-484a-b569-04c51d039885).
`election_audit/resources/bweb-2026-layout.json` fixa dicionário e mapeamento;
`electoral-source-evidence.json` registra a falha anterior e aquisição bem-sucedida.
A API do conjunto listou apenas recursos do primeiro turno, embora a API separada
do recurso confirmasse este arquivo do segundo turno. Ambas foram preservadas.

O diretório local adquirido é `data/official-bu/ac-runoff-2026-10-30/`; é ignorado
pelo Git. Seu `bundle.json` declara exatamente quatro fontes locais: `archive`,
`checksum`, `resource_metadata`, `catalog_metadata`. Cada uma exige `path`, `sha256`,
`official_url`, `observed_at`. Campos superiores são `adapter`, `verification_status`
(`official_layout_verified`), essas quatro fontes, `election` (contrato exato de
segundo turno de 2026 suportado) e `uf` (`ac` na validação real). Caminhos são
confinados, hashes conferidos, SHA-512 e vínculos recurso/arquivo verificados,
membros e edição do dicionário fixados. Bytes de entrada mais descompactados têm
limite de 64 MiB; linhas de entrada/geradas, `max_events`. É importador limitado,
não processamento nacional em fluxo. Retransmissões idênticas preservam todas as
testemunhas de registros; contagens ou metadados repetidos contraditórios falham.
Novas observações preservam identidades próprias de snapshot/resultado/evento e
compartilham objetos originais sem conflitar chaves de observação.

A saída de inspeção exige arquivo novo. O exemplo usa as 108350 linhas eleitorais
herdadas do piloto congelado existente e limite explícito de 200000 linhas;
novos fatos ficam em derivada imutável separada. Bloqueios científicos de snapshots
BU oficiais refletem situação/completude, sem alegar incorretamente schema não
verificado. Snapshots anteriores mantêm seus indicadores. Outras UFs/categorias/
edições do dicionário exigem revisão.

```sh
rtk proxy env UV_OFFLINE=1 uv run --locked python -m election_audit.official_bu --bundle data/official-bu/ac-runoff-2026-10-30/bundle.json --output data/official-bu/ac-runoff-2026-10-30/validation-recheck.json
rtk proxy env UV_OFFLINE=1 just import-results data/phase9/pilot/warehouse/releases/64eafb496f230a6634f3eade0c49cbacd7845d95a1ac73d7a2bbc76070cc998a --bundle data/official-bu/ac-runoff-2026-10-30/bundle.json --store data/official-bu/ac-runoff-2026-10-30/warehouse --max-events 200000
```

Importações normalizadas explícitas já são utilizáveis. Um pacote local lista apenas
arquivos autorizados para importação, relativos ao seu diretório. Uma entrada de
fonte tem exatamente estes campos; substitua hash e caminhos ilustrativos pelos
reais. Não renomeie um CSV oficial para este formato: exige mapeamento revisado.

```json
{
  "adapter": "electoral-normalized-v1",
  "verification_status": "normalized_only",
  "sources": [{
    "path": "vote_choice_count.jsonl",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "table": "vote_choice_count",
    "format": "jsonl",
    "encoding": "utf-8",
    "official_url": "fixture://replace-with-original-source-locator",
    "observed_at": "2026-10-29T00:00:00+00:00",
    "schema_evidence": ["replace with reviewed schema version and source evidence"]
  }]
}
```

JSONL usa nomes/tipos exatos do contrato e `field_states` explícitos para nulos.
CSV usa ponto e vírgula e ordem exata dos campos seguida por `field_states`;
CSVs de extensões usam sua ordem de colunas sem `field_states`. Apenas UTF-8
estrito sem BOM/NUL é suportado. Nulo CSV é `\N`, booleanos `true`/`false`, inteiros
decimais canônicos; campos JSON contêm JSON. Chaves JSON repetidas, campos/categorias/
situações desconhecidos, instantes normalizados sem fuso, contagens eleitorais
negativas, hashes divergentes e conflitos de chaves imutáveis falham. Retransmissões
idênticas deduplicam fatos preservando cada localizador original.

Tabelas importáveis: election, contest, section, location, snapshot,
section_composition, candidacy, vote_choice, result_version, section_contest_totals,
vote_choice_count, processing_event, harmonized_population e harmonized_member.
Primeiro turno e histórico usam o mesmo contrato explícito; sem busca automática.
Snapshot não tem coluna de eleição: seção/disputa/composição estabelecem eleição
e turno exatos. IDs e códigos TSE com zeros devem ser fornecidos, nunca inferidos
de nomes.

| Tabela de extensão | Campos e requisitos |
| --- | --- |
| `result_evidence` | `result_version_id`, `snapshot_id`, `official_target`, `complete_choices`, `expected_choice_ids`, `status_evidence`, `supersedes`, `supersession_evidence` |
| `electorate_reference` | `snapshot_id`, `principal_section_id`, `eligible_electors`; um eleitorado independente por principal |
| `final_result_reference` | `reference_id`, `snapshot_id`, `contest_id`, `level`, `uf`, `municipality_tse`, `zone`, `expected_principals`, `metrics`, `final` |
| `harmonization_evidence` | `population_id`, `composition_reviewed`, `transfers_reviewed`, `electorate_reviewed`, `evidence` |

Tipos e chaves das extensões estão em `electoral_imports.EXTENSIONS`. Âncoras de
situação contêm `object_sha256` e `record_locator` não vazio de objeto preservado.
`supersedes` é lista de IDs de versões; `supersession_evidence` associa cada
predecessor a uma âncora. Âncoras atestam alegação normalizada fornecida, sem verificar
independentemente situação oficial. Completude exige conjunto exato de escolhas
da disputa, incluindo linhas zero explícitas. Linha ausente é desconhecida.
Referências finais usam níveis zone/municipality/uf/national, lista exata de
principais e métricas não vazias de campos do contrato de totais; geografia não usada
fica como string vazia. População explicitamente nacional inclui exterior (ZZ);
sua lista declarada não é inferida deste corpus parcial.

```sh
rtk proxy env UV_OFFLINE=1 just import-results /ssd/audit/releases/PARENT_DIGEST --bundle /ssd/normalized/bundle.json --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just validate /ssd/audit
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT selection_state, count(*) FROM canonical_result GROUP BY selection_state'
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql "SELECT result_version_id, json_extract_string(payload, '$.state') FROM result_reconciliation"
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports
```

`publish_derivative(parent, bundle, store, config=None)` usa configuração existente
de recursos, bloqueio, proteção de reserva/spill, staging/fsync/rename e ponteiro
current atômico. O piloto limita bytes totais normalizados a 64 MiB e linhas de
entrada, contexto eleitoral herdado e entradas combinadas por `max_events` (padrão
100000). Linhas de publicação recebidas incluem testemunhas de fontes/linhagem no
limite. Linhas eleitorais residem em Python; não é processamento nacional BU em
fluxo. Eventos/ciclos/linhagem operacionais do pai são reutilizados por visões
Parquet, nunca copiados para Python ou reescritos. Exceder limites falha a publicação;
não há sucesso parcial.

Cada `derivative-release-v1` fixa ID relativo do pai e hash de manifesto verificados,
acrescenta `audit.duckdb`, `import.json`, bytes exatos `originals/SHA256` e fatos
particionados por ano/turno/UF (linhagem não resolvida fica unknown). Tabelas de
entrada acrescentam sem mudar schema publicado; decisões/marts derivados substituem
visões locais da conexão preservando versões históricas. Novas versões exigem novos
IDs imutáveis. O manifesto registra colunas, chaves, armazenamento, contagens e
digests lógicos. Carregador, validador, consulta e relatório incluem toda a cadeia.
Mova toda a cadeia relativa junta. Pais ausentes/corrompidos falham. Relatórios
incluem identidades da cadeia, tabelas/arquivos fixados, SQL e premissas de origem
em findings.json. Cada consulta/relatório calcula hashes físicos dos fatos uma vez;
validação também recalcula digests lógicos, relações e derivações eleitorais.
A interface restrita a SELECT não aceita leituras externas ou escritas.

Seleção canônica considera apenas alegações totalizadas de alvo oficial, com
evidência explícita de supersessão no mesmo snapshot/principal/disputa. Não usa
hash/relógio mais recente; conflitos sobreviventes ficam indisponíveis. Versões
recebidas, rejeitadas e excluídas são preservadas sem totalizar. Totais ficam uma
linha por versão, escolhas separadamente; junções de membros/sessões não expandem
totais. Somas de categorias, comparecimento, contabilidade do eleitorado e qualquer
referência externa presente devem concordar para disponibilizar razões por seção.
Referência opcional ausente fica explícita. Achados hierárquicos distinguem cobertura
ausente/extra de diferenças numéricas; não tratam soma parcial como erro numérico
contra referência completa.

Quatro marts: `section_results`, `unanimous_results`, `result_timing`, `round_comparison`.
Chaves de grão são colunas tipadas e medidas completas ficam no JSON `payload`.
Unanimidade estrita exige totais positivos completos reconciliados de todas as
cédulas, exatamente um candidato com todos os votos e zero brancos/nulos/especiais/
não resolvidos. Unanimidade apenas entre válidos tem nome separado. Categorias
ausentes/zero cédulas ficam indisponíveis, nunca observações falsas de zero.
Votos não são atribuídos a ciclos dos logs; contribuições de urnas físicas ficam
indisponíveis sem dados de origem que as isolem. Tempos usam extremos de eventos
de processamento verificados e regras explícitas de relógio; eventos repetidos
preservam todos os pares, inclusive negativos. Encerramento-até-recebimento permanece
indisponível sem âncora explícita de encerramento. Instantes da versão sozinhos não
certificam conversão de relógio nem suprem eventos ausentes do publicador.
Comparação de turnos exige populações disjuntas de principais inteiros, composição,
transferências e eleitorado revisados, resultados completos, par presidencial do
mesmo ano e ligação exata ao snapshot. Agrega cada turno antes de juntar, preserva
IDs separados de candidatos e mudanças de eleitorado, sem inferir transferência individual.

Entrada da Fase 8: usar caminho fixado da derivada e quatro marts mais visões
operacionais do pai, verificando disponibilidade e denominadores antes de analisar.
Para novas famílias, ampliar schemas normalizados/derivados e produtor com regra
versionada; carregador lê colunas/chaves do manifesto sem mudar `FACTS` operacional.
Nunca editar banco/schema base ou publicações existentes. Propagar verificação de leiaute oficial e os limites restantes
de reconciliação final. Sem ajuste ou rótulos de fraude
nesta fase.
