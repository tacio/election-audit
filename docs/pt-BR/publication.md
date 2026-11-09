# Publicação operacional e relatórios iniciais

Document-ID: EA-PUBLICATION · Revision: 4 · Language: pt-BR

[English](../en/publication.md) · [Índice de implementação](implementation-index.md)

O pipeline lê somente artefatos congelados. Uma release cobre exatamente o snapshot
de que foi construída; um subconjunto de UFs é cobertura nacional parcial. A aceitação
usou fixtures sintéticas e o piloto real de cinco regiões da Fase 9; nenhuma regra
autoritativa de relógio foi certificada. A semântica revisada de mensagens reais é um
adaptador separado da Fase 13 (`operational_review`), fora destas releases. Coleta
original, manifestos e bytes foram preservados.

Etapas: snapshot congelado → parse/cache estrutural → grupos limitados de
reconstrução operacional → publicação imutável DuckDB/Parquet → validação → consultas
somente leitura e relatórios iniciais. Selecione exatamente um snapshot/parse ou um
ou mais fragmentos disjuntos de reconstrução. Não são produzidos importação BU,
atribuição a candidatos, ajuste de modelos ou rótulos de fraude.

```sh
env UV_OFFLINE=1 just build /path/to/snapshot --input-kind snapshot --store /ssd/audit --parser-workers 4
env UV_OFFLINE=1 just build /path/to/parse --input-kind parse --store /ssd/audit
env UV_OFFLINE=1 just build /path/to/reconstruction --store /ssd/audit
env UV_OFFLINE=1 just validate /ssd/audit
env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT completion_state, count(*) FROM anonymous_cycle GROUP BY completion_state'
env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports
env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports --language pt-BR
```

`build --evidence FILE` fornece alegações revisadas de reconstrução para construções
a partir de snapshot ou parse. Veja [reconstrução](reconstruction.md) para requisitos
de âncoras exatas; alegações e hashes não são certificação semântica independente.
Por padrão, construções de parse reconstroem um objeto de conteúdo por grupo com um
`FrozenParseReader` reutilizado. A API Python aceita grupos explícitos de objetos
relacionados para resolução de cópias/sobreposições. Históricos desconhecidos entre
grupos permanecem indefinidos; totais globais elegíveis continuam nulos.

| Interface Python | Comportamento |
| --- | --- |
| `publication.ResourceConfig` | Limites validados de recursos |
| `publication.publish_release(shards, store, config=None)` | Publicar entradas imutáveis disjuntas e verificadas de reconstrução |
| `publication.build_from_parse(parse, store, config=None, evidence=None, object_groups=None)` | Leitor compartilhado e grupos limitados de reconstrução |
| `publication.build_from_snapshot(snapshot, store, config=None, evidence=None)` | Analisar snapshot congelado com trabalhadores configurados e construir |
| `publication.inspect_release(path)` | Verificar identidade de metadados e hash/tamanho de cada arquivo |
| `publication.open_release(path)` | DuckDB verificado somente leitura e visões temporárias realocadas dos fatos |
| `release_tools.validate_release(path)` | Integridade, digests lógicos, grãos/FKs/contabilização/linhagem/cobertura e entradas explicitamente adiadas |
| `release_tools.query_release(path, sql, max_rows=1000)` | Exatamente um SELECT analisado, saída limitada, acesso externo desativado |
| `release_tools.report_release(path, output, language="both")` | Markdown traduzido em par, registro compartilhado de achados e SQL reproduzível |

Recursos padrão: 4 trabalhadores do parser, 4 threads DuckDB, memória 12 GiB, limite
de spill 8 GiB e reserva livre SSD 10 GiB. As opções CLI `--parser-workers`,
`--duckdb-threads`, `--memory-bytes`, `--spill-bytes`, `--reserve-bytes`, `--batch-rows`,
`--max-events` são validadas. DuckDB recebe configurações efetivas de threads/memória/
spill; spill temporário fica no staging. Reserva mais orçamento de spill são
verificados antes/durante escritas, com folga adicional por lote. Os limites não
prometem que um corpus completo cabe; esgotamento aborta a publicação. Travas do
parser são por chave de conteúdo/configuração, permitindo objetos independentes
simultâneos e análise única de conteúdo idêntico. Cada grupo de reconstrução é
limitado (padrão 100000 eventos); a publicação transmite 2048 linhas por vez.
Metadados completos da população congelada ficam uma vez na memória.

O armazenamento contém `releases/DIGEST/audit.duckdb`, `context.json`, `release.json`
e `facts/TABLE/year=YEAR/round=ROUND/uf=UF/*.parquet`. Fatos usam compressão zstd;
contexto compacto, resumos de sessão e marts ficam no DuckDB. Contexto oficial de
seção fornece partições; geografia indefinida fica `unknown`. Mapeamentos de evento
canônico copiado e linha derivada particionam evidências/linhagem associadas quando
conhecidos. Linhagem compartilhada de metadados congelados é preservada uma vez,
incluindo observações e objetos originais. Parses antigos sem ela ficam explicitamente
indisponíveis. Representações completas permanecem em JSON `payload` junto a colunas
tipadas do contrato ou chaves do grão do mart. Isso preserva incerteza e campos
versionados dos resumos.

Trava exclusiva, staging/fsync/renomeação atômica e substituição atômica do ponteiro
`current` preservam publicações anteriores diante de interrupção. Entradas/configurações
idênticas verificam e reutilizam a publicação imutável. Staging interrompido nunca
é publicação bem-sucedida; publicação completa com ponteiro antigo pode ser reutilizada
na repetição. `current` identifica um digest; fornecer o caminho da publicação fixa
a consulta. Realocar armazenamento/publicação completos funciona: visões temporárias
resolvem o caminho atual e dados continuam utilizáveis após remoção de origem/parse/
reconstrução.

A validação recalcula hashes físicos e digests lógicos de multiconjunto SHA-256
independentes da ordem, com contagens exatas; verifica chaves primárias/alternativas,
FKs disponíveis, linhagem original, contabilização ciclo/evento/sessão, partição
disjunta e membros esperados preservados. Ausência de contexto de snapshot/objetos/
localização em parses antigos é explicitamente adiada, nunca certificada. Cada consulta
faz uma verificação completa de integridade. Relatórios reutilizam um manifesto
verificado e uma conexão de consulta para todos os cálculos, após validação completa.
Verificação completa lê fatos grandes; isso é intencional e pode ser caro. Conexões
de consulta são somente leitura, sem spill nas publicações imutáveis. COPY, escritas,
múltiplas instruções e leitura de arquivos externos são rejeitados. `--sql-file FILE`
evita problemas de aspas para SELECTs maiores; `--max-rows` limita linhas retornadas
e informa truncamento.

Cobertura preserva distinções entre esperados/membros/principais e estratos desconhecidos.
Disponibilidade de processamento usa linhas de pacote/tipo esperado anunciado, com
população completa de resultados desconhecida; recebimento, processamento, geração,
publicação e observação do cliente são separados. Origem ausente não é latência zero
nem não publicado. Last-Modified HTTP/download nunca fornecem tempos de ciclo de vida.
Conclusão doméstica tardia ocorre estritamente após 17:00 America/Sao_Paulo na data-alvo;
igual não é tardia. Conclusões tardias observadas e intervalos comprovados de permanência
aberta são separados. Relógios/contexto indefinidos impedem classificação confiável,
intervalos limitados preservam sensibilidade e convenção exterior permanece indisponível.
Fatos de sessão/ciclo nunca se expandem por junções de membros/pacotes/linhagem.

Relatórios padrão: `report.en.md` e `report.pt-BR.md`, com `findings.json`,
`lifecycle.sql` e `late.sql`; `--language en|pt-BR|both` seleciona idiomas.
Rótulos/explicações traduzidos compartilham valores, SQL, fórmulas e exemplos numéricos
idênticos. Achados preservam IDs de entrada, cálculo, premissas, exclusões, incerteza,
comandos de reprodução e evidência que pode contestá-los. Validação eleitoral está
indisponível; ciclos reconstruídos não são votos reconciliados.

A extensão da Fase 7 está implementada por `derivatives.publish_derivative` e
carregador de cadeia de pais orientado pelo manifesto. `FACTS` base permanece igual;
filhos fixam identidades/hashes relativos do pai, acrescentam armazenamento compacto/
fatos e reutilizam Parquet do pai. Consulte [importações eleitorais](electoral-results.md)
para o contrato normalizado, o adaptador oficial BWEB, a verificação de BU binário e a
integração de consulta/validação/relatório.
