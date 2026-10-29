# Importações eleitorais e publicações derivadas

Document-ID: EA-ELECTORAL-RESULTS · Revision: 1 · Language: pt-BR

[English](../en/electoral-results.md) · [Índice](implementation-index.md) · [Publicação](publication.md)

Logs disponíveis AC–RJ do segundo turno presidencial de 2026 continuam com cobertura
nacional parcial. O importador utilizável é **electoral-normalized-v1**, não um
decodificador BU oficial TSE verificado. O adaptador oficial verificado da tarefa 7.1
continua pendente. Nenhum BU real foi fornecido/importado; verificações aritméticas
sintéticas não constituem validação eleitoral real ou certificação de assinatura.
Aquisição e publicações base foram preservadas.

Evidência primária inspecionada em 2026-10-29: [índice técnico oficial](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados),
[metadados BU AC segundo turno](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna/resource/4753eb99-062b-484a-b569-04c51d039885),
[EA16](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea16-arquivo-de-configuracao-de-secoes-eleitorais)
(2026-05-22), [EA18](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
(2026-05-22), [EA20](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado)
(2026-10-13). Essas especificações JSON são distintas do dicionário CSV BU.
A ferramenta web rejeitou o ZIP BU AC e o arquivo de hash como conteúdo binário
não suportado. Requisição CLI limitada por intervalo falhou no DNS, saída 6, zero
bytes baixados. Bloqueio exato: bytes fixados BU e dicionário/cabeçalho/codificação/
mapeamento de categorias não puderam ser obtidos. Evidência de descoberta e digest
do schema normalizado ficam fixados na identidade/proveniência de cada derivada;
descoberta não certifica schema de origem. Nenhum download nacional é tentado.

```sh
rtk proxy curl --range 0-65535 --max-time 20 --max-filesize 1048576 --fail --show-error --silent --dump-header /tmp/election-audit-bu-range.headers --output /tmp/election-audit-bu-range.bin https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AC_261020260742.zip
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
Nunca editar banco/schema base ou publicações existentes. Propagar pendência do
adaptador oficial BU e situação de validação real. Sem ajuste ou rótulos de fraude
nesta fase.
