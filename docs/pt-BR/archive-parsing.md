# Análise sintática de arquivos congelados

Document-ID: EA-ARCHIVE-PARSING · Revision: 3 · Language: pt-BR

[English](../en/archive-parsing.md) · [Índice de implementação](implementation-index.md)

A Fase 4 lê somente [snapshots](snapshots.md) concluídos. `parse_snapshot` chama
`inspect_snapshot(..., verify_objects=True)` e `snapshot_tables`, depois abre
o `source_object.storage_locator` relativo congelado. Os caminhos originais de
aquisição em `payload.inventory` são evidências, nunca entradas do analisador.
Os bytes da aquisição e do snapshot permanecem intactos. O piloto de cinco regiões
da Fase 9 executou este analisador sobre objetos reais. A passagem nacional do segundo
turno usou o analisador fundido de resumos em
[processamento orientado a features](feature-oriented-processing.md), que mantém as
mesmas proteções e classes de mensagem. Um subconjunto de UFs é cobertura nacional
parcial, e amostras de seções conservam o denominador congelado da UF inteira.

```sh
env UV_OFFLINE=1 just parse /path/to/derived/SNAPSHOT_DIGEST --store /path/to/parsed
env UV_OFFLINE=1 just parse --help
```

O comando imprime o diretório de publicação concluído. `--store` deve ficar fora
do snapshot imutável e da raiz original de aquisição. Nomes de ativos selecionados
terminados em `log.dat`, `.jez` ou `.zip` identificam objetos candidatos; nenhum
filtro por situação do pacote exclui silenciosamente contextos de preparação ou
desconhecidos. Observações ausentes e anúncios históricos sem mapeamento continuam
explícitos. Índices de metadados não são confundidos com arquivos de logs. Estes
comandos são ilustrativos, não uma execução do piloto.

O leitor valida a estrutura do diretório ZIP antes de alocar metadados de
`ZipFile`. Cada membro permitido passa por validação de CRC/tamanho em fluxo antes
da análise, inclusive membros que não são logs. Membros ZIP/JEZ aninhados usam
arquivos temporários privados em disco que permitem reposicionamento; nenhum
caminho de membro é extraído. Arquivos temporários têm limites por membro e de
bytes expandidos cumulativos. Eventos e problemas JSONL são gravados em fluxo,
sem acumular um acervo na memória. ZIP64, arquivos em múltiplos discos e layouts
não padronizados de diretório geram problemas explícitos de formato não suportado
ou inválido; não são relatados como decodificações bem-sucedidas. CRC e SHA-256
não verificam assinaturas.

Cada localizador conserva todo nome original de membro, a ocorrência iniciada em
zero entre nomes iguais no arquivo que o contém e o índice do diretório central
iniciado em zero. Nomes e conteúdos iguais continuam ocorrências separadas,
inclusive duplicatas aninhadas. Os nomes/URLs originais do arquivo externo ficam
nas associações congeladas de observações e ativos de pacote. Intervalos de linhas
iniciados em um são exatos; deslocamentos originais de bytes desconhecidos ficam
nulos. A ordem segue os membros do arquivo e as linhas originais; não há ordenação
por horário.

| Limite / opção da CLI | Padrão | Comportamento no limite |
| --- | --- | --- |
| `--max-archive-bytes` | `536870912` | Rejeitar contêiner ZIP maior |
| `--max-member-bytes` | `134217728` | Ignorar membro maior com problema registrado |
| `--max-total-bytes` | `536870912` | Bytes expandidos cumulativos, incluindo contêineres aninhados |
| `--max-directory-bytes` | `4194304` | Limitar memória do diretório central antes de decodificar o ZIP |
| `--max-members` | `10000` | Contagem global de membros em todos os níveis |
| `--max-depth` | `4` | A raiz tem profundidade zero; cada contêiner aninhado soma um |
| `--max-line-bytes` | `65536` | Bytes físicos incluindo terminador; consumir linha excessiva |
| `--max-lines` | `2000000` | Contagem global de linhas físicas originais |
| `--max-issues` | `10000` | Conservar essa quantidade de diagnósticos mais um marcador `diagnostic_limit` |

Todos os limites devem ser inteiros positivos e fazem parte da identidade do
cache. Um membro ignorado, linha malformada, corrupção ou limite produz `partial`;
eventos preservados continuam utilizáveis como evidência com essa limitação.
`complete` significa conclusão da decodificação estrutural, nunca elegibilidade
eleitoral, completude de sessões ou votos. Ao exceder os diagnósticos,
`issues_seen` continua contando os problemas encontrados; o marcador retido torna
o truncamento explícito. Falhas de recursos/disco interrompem a publicação em vez
de produzir um artefato de sucesso.

Membros `logd.dat` (nome base sem distinção de maiúsculas, com qualquer separador
de caminho) usam Latin-1 e seis colunas separadas por tabulação: horário, nível,
dispositivo, aplicação, mensagem, token. Horários locais válidos do dispositivo
são conservados exatamente, sem inferência de fuso ou turno. Somente a identidade
numérica do dispositivo e a identidade limitada da aplicação são selecionadas.
Registros malformados conservam localizador e motivo estruturado limitado, sem
amostras brutas nem texto de exceções. Identificadores de eleitores/mesários,
corpos de mensagens e tokens sensíveis nunca são selecionados para eventos ou
diagnósticos.

| Mensagem exata de VOTA | `event_kind` |
| --- | --- |
| `O voto do eleitor foi computado` | `completion_message` |
| `Eleitor foi habilitado` | `authorization_message` |
| `Solicitação de dado pessoal do eleitor para habilitação manual` | `manual_request_message` |

Essas são as únicas três classes decodificadas em `jez-structural-v1`. Todas as
outras mensagens/aplicações ficam como `unknown` com evidência
`unsupported_message_class`. Cada evento mantém `selection_state=context_unresolved`,
inclusive contextos de preparação e datas/turnos misturados. A semântica revisada de
mensagens reais fica no adaptador separado da Fase 13, `real-operational-v1`
(`operational_review`), ancorado na evidência original. Uma
solicitação manual não é uma habilitação nem um ciclo concluído. Mensagens de
conclusão não são totais reconciliados de votos.

`source_line_sha256` calcula o hash da linha física original exata, incluindo
seus bytes originais CR/LF quando presentes. Conserva evidência de que mensagens
desconhecidas diferem sem selecionar seus textos. Não é identidade de evento nem
decisão de deduplicação. A identidade do evento inclui objeto original, localizador
completo da ocorrência de membro, linha e versão do analisador/configuração.
Linhas iguais repetidas no mesmo segundo ainda geram eventos separados. Decisões
sobre blocos copiados na Fase 5 exigem evidência explícita e regra de reconstrução;
tipos normalizados e horários sozinhos não estabelecem equivalência.

`cache/KEY/` contém `events.jsonl`, `issues.jsonl`, `artifact.json` e
`artifact.json.sha256`. A chave combina SHA-256 do conteúdo, versão do analisador
e configuração inteira. Cada reutilização verifica a identidade dos metadados e
todos os tamanhos/checksums dos arquivos em fluxo. Objetos com bytes idênticos
reutilizam a análise entre pacotes e snapshots. Caches danificados são movidos
para `.corrupt-*` como evidência e reconstruídos; artefatos concluídos nunca são
remendados. Preparação privada, fsync, travas no armazenamento derivado e renomeação
atômica tornam reinícios seguros. Diretórios `.parse-building-*` abandonados são
ignorados; sua limpeza é uma ação separada.

`parses/PUBLICATION_DIGEST/` contém `parse.json` com checksum. Essa publicação
imutável vincula os hashes do cache ao ID do snapshot, a todas as observações
originais e ativos de pacote correspondentes, às tabelas congeladas de contexto
de eleição/seção/pacote, aos anúncios históricos desconhecidos, aos ativos ausentes
e ao resumo original de cobertura. As associações não participam da identidade
do cache de conteúdo. Bytes iguais, portanto, não apagam testemunhos do publicador
nem implicam uma única sessão operacional.

| API Python em `election_audit.archive_parsing` | Uso |
| --- | --- |
| `parse_snapshot(snapshot, store, config=ParseConfig())` | Verificar entradas congeladas; retornar caminho da publicação |
| `inspect_parse(path)` | Verificar publicação e conteúdo referenciado, independentemente das entradas brutas |
| `inspect_artifact(path)` | Verificar um artefato imutável de conteúdo em cache |
| `iter_event_witnesses(path)` | Transmitir eventos por snapshot/observação de origem, conservando todos os ativos de pacote |
| `iter_lineage(path)` | Transmitir `record_lineage` no formato do contrato para testemunhos de eventos |
| `iter_parsing_issues(path)` | Transmitir linhas do contrato `parsing_issue` vinculadas ao snapshot |
| `parse_object(source, store, config=..., expected_sha256=...)` | API interna/de testes de conteúdo; produção usa a API de snapshot congelado |

`event_id` identifica uma ocorrência de conteúdo; `witness_event_id` também a
delimita por snapshot e observação de origem. A Fase 5 deve selecionar sessões
operacionais com evidência antes de agregar testemunhos. As estruturas JSONL de
eventos/testemunhos são artefatos intermediários, não linhas prematuras dos
contratos `selected_event` ou de sessões de votação. Não há reconstrução de sessões,
conversão de fuso, importações eleitorais, publicação DuckDB/Parquet, ajuste de
modelos de atributos nem rotulação de fraude nesta fase.

A aceitação usou somente fixtures sintéticas isoladas: membros aninhados/duplicados,
corrupção de CRC, logs ausentes, linhas malformadas/excessivas, todos os limites,
mensagens iguais repetidas, contextos misturados, minimização de dados, hashes
distintos de mensagens desconhecidas, cache danificado, interrupção, leitura
exclusiva de congelados e associações de múltiplos pacotes/snapshots. No aceite da Fase 4
passaram as 15 fixtures do analisador e todos os 83 testes do repositório; a ajuda
da receita também passou.

```sh
env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
env UV_OFFLINE=1 just check
env UV_OFFLINE=1 just parse --help
```
