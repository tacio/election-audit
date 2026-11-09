# Snapshots congelados e cobertura

Document-ID: EA-SNAPSHOTS · Revision: 3 · Language: pt-BR

[English](../en/snapshots.md) · [Índice de implementação](implementation-index.md)

`snapshot` cria uma população local de entradas independente. Lê o manifesto
autorizado por `manifest_path(root)` e seu marcador, usando uma transação SQLite
somente para leitura que inclui WAL confirmado. Aquisição e originais permanecem
inalterados. Não há rede, varredura de diretórios, interpretação de arquivos
compactados, importação eleitoral ou publicação DuckDB.

Seleção padrão: segundo turno presidencial federal de 2026, pleito `3221`, eleição
`6258`, turno `2`, data `2026-10-25` e as 19 UFs alfabéticas AC–RJ. A cobertura
nacional é **parcial**. `--ufs` permite selecionar explicitamente qualquer UF,
incluindo ZZ, em snapshot posterior. `--round 1` seleciona o primeiro turno (pleito
`3220`, eleição `6257`, `2026-10-04`); `--source-manifest` substitui o manifesto
encontrado pelo marcador de localização da raiz. Histórico exige adaptadores de
importação explícitos. Índices ausentes e UFs indisponíveis nunca viram população zero.

Para piloto limitado, selecione seções explicitamente. Somente seus objetos e os
objetos de índice/configuração das UFs selecionadas são lidos para hash/cópia;
diretórios de objetos originais não são percorridos. Índices completos das UFs
mantêm o denominador. Integrantes fora da seleção continuam como `not_selected`,
com `outside_asset_selection`; agregação não expande automaticamente a amostra.
Caminhos e seção abaixo são ilustrativos; o comando não foi executado no acervo real.

```sh
env UV_OFFLINE=1 just snapshot --source /path/to/raw --store /path/to/derived --ufs ac --section ac/01120/0001/0001 --reserve-gib 10
env UV_OFFLINE=1 just snapshot-inspect /path/to/derived/SNAPSHOT_DIGEST --verify-objects
```

Repita `--section UF/MUNICIPALITY/ZONE/SECTION` para incluir arquivos; códigos têm
larguras `2/5/4/4`, com UF minúscula. Omita `--section` somente para congelar todos
os arquivos das UFs selecionadas intencionalmente. `--source` e `--store` são
obrigatórios. O armazenamento deve ficar fora da raiz de aquisição. Reserva padrão
de espaço livre: `10` GiB; espaço insuficiente falha antes da cópia. A CLI imprime
o diretório concluído. `inspect` mantém o diagnóstico original de mensagens brutas.

Diretório concluído contém `snapshot.json`, `snapshot.sha256` e cópias independentes
em `objects/`, endereçadas por SHA-256. Localizadores nas tabelas dos contratos são
relativos a esse diretório. `payload.inventory` mantém caminhos originais como
evidência; parsers devem usar os caminhos congelados das tabelas emitidas.
Metadados são JSON UTF-8 canônico. `inventory_sha256` resume o conteúdo substituindo
chaves de snapshot pelo sentinela `pending-snapshot`, evitando identidade circular;
`snapshot_id` usa `snapshot:v1:` e o digest JSON canônico desse digest de inventário.
Checksum de arquivo protege o envelope inteiro, incluindo criação. Esquema, hashes
de implementação, runtime/pacotes, seleção e política de normalização são congelados.

A publicação copia e verifica cada objeto em diretório privado temporário,
sincroniza arquivos/diretórios e renomeia atomicamente. Mudanças durante a cópia
abortam a publicação. Entradas ausentes/falhas ainda podem gerar snapshot parcial
fiel, com objetos nulos e checagens preservadas. Snapshots existentes são validados
e nunca sobrescritos. Republicar a mesma captura e implementação é idempotente;
nova captura CLI registra novo horário e pode criar novo ID. Diretórios
`.snapshot-building-*` interrompidos são ignorados; limpeza é separada dos artefatos
concluídos.

A inspeção verifica checksum, identidade, formato/chaves/nulos pelo esquema
congelado, chaves estrangeiras emitidas e existência/tamanho dos objetos.
`--verify-objects` também verifica hashes das cópias. Nunca relê manifesto/raiz
originais; downloads posteriores ou exclusões dos originais não alteram snapshots.
Reconciliação eleitoral geral, assinaturas e resultados canônicos ficam para depois;
disponibilidade não determina elegibilidade eleitoral.

`files` legado contém apenas o mapeamento atual de URLs. Linhas atuais viram novas
observações locais com execução sintética e horário de captura; não são requisições
HTTP e o estado HTTP fica desconhecido. `fetched_at`, ETag e Last-Modified originais
ficam intactos em `manifest_rows`. Linhas históricas de `logs` preservam execução,
seção/pacote/estado/nome/URL originais, mapeamento de objeto nulo e
`historical_mapping_unknown`. Nunca recebem bytes atuais como fato histórico.
O manifesto legado não recupera toda tentativa nem os índices históricos.

Índices congelados verificados fornecem **integrantes** registrados esperados,
incluindo agregados. Índice duplicado/inválido/ausente mantém contagens nulas;
seções só do manifesto continuam visíveis como apenas observadas. Principais
terminais diretos com automapeamento estabelecem denominador separado. Conflitos,
principais ausentes e cadeias/ciclos ficam não resolvidos. Cada seção retida aparece
uma vez na contabilização disjunta: acquired, aggregated, missing, failed,
unresolved, not_published ou not_selected. Falhas históricas continuam explícitas
mesmo com bytes atuais disponíveis. Execução finalizada não prova cobertura;
linhas inacabadas não distinguem processos ativos de abandonados.

`Totalizado` vira exatamente `totalized` em `tse-package-status-exact-v1`, baseado
na [referência de aquisição](acquisition-reference.md) fornecida. Outros rótulos,
variantes de caixa e códigos numéricos ficam deliberadamente `unknown` até validação;
valores brutos são preservados. Estado nulo/não textual não cabe no contrato v1:
bytes auxiliares exatos e problema explícito permanecem, sem inventar rótulo.
Instalação, disponibilidade de BU, horários do publicador não validados, parsing
e reconciliação ficam desconhecidos/não tentados. Linhagem JSON usa ponteiros
originais e segmentos de arquivo `[]`; intervalos desconhecidos ficam nulos.

| Interface Python | Artefato retornado / uso |
| --- | --- |
| `source_inventory.read_manifest(root, ufs, section_keys=...)` | Linhas originais selecionadas consistentes e digest |
| `source_inventory.inventory_sources(root, ufs, section_keys=...)` | Objetos/observações atuais verificados, falhas e anúncios históricos desconhecidos |
| `coverage.build_population(inventory)` | Subconjunto dos contratos, resumo e evidências explícitas |
| `snapshots.publish_snapshot(inventory, population, store, reserve_bytes=0)` | Materializar uma captura idempotentemente |
| `snapshots.create_snapshot(root, store, ufs, section_keys=..., reserve_bytes=0)` | Capturar e publicar nova entrada imutável |
| `snapshots.inspect_snapshot(path, verify_objects=False)` | Documento validado independente da aquisição |
| `snapshots.snapshot_tables(document)` | Tabelas incluindo snapshot/participação |

`section_keys` é `None` ou sequência não vazia de tuplas de quatro strings.
`ufs` usa AC–RJ por padrão. Módulos ficam em `election_audit/`. Consumidores usam
`document["payload"]["tables"]` para fontes/seções/cobertura/linhagem e
`snapshot_tables` para incluir `snapshot`/`snapshot_observation`. Esquema congelado:
`document["payload"]["schema"]`. Essas linhas JSON não são publicação DuckDB ou
Parquet. O [analisador estrutural](archive-parsing.md) lê somente localizadores de
objetos congelados e preserva ocorrências de membros aninhados; veja o
[registro 3.3](handoffs/task-3.3.md) para detalhes do aceite.
