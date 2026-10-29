# Tarefa 6.1 — Publicações operacionais imutáveis

Document-ID: EA-HANDOFF-6.1 · Revision: 1 · Language: pt-BR

Objetivo: publicar fragmentos limitados de reconstrução congelada como fatos Parquet comprimidos e dimensões compactas DuckDB.
Pré-requisitos: [5.4](task-5.4.md), [índice](../implementation-index.md), contratos operacionais.

Arquivos/interfaces: `election_audit/publication.py`: `ResourceConfig`, `publish_release`, `inspect_release`, `open_release`, `build_from_parse`, `build_from_snapshot`. `parse_snapshot(..., workers=4)` e `parse --workers` aplicam concorrência limitada ao parser. A aquisição existente foi preservada.

Entregas: trava exclusiva não bloqueante; `releases/DIGEST` imutáveis, contexto/proveniência com hashes, `current` atômico; fatos Parquet zstd particionados por ano/turno/UF comprovados (desconhecido preservado), dimensões DuckDB em SSD. Configurações efetivas de threads/memória/spill e verificações da reserva livre; lotes limitados de linhas e reconstrução por objeto/grupo. Entradas imutáveis idênticas retomam com segurança; objetos compartilhados e chaves repetidas de evento/sessão/ciclo falham. Conexões somente leitura anexam visões temporárias dos fatos e sobrevivem à realocação do armazenamento.

Aceitação: cinco fixtures de publicação passaram (interrupção em três etapas, escritor concorrente, limites de recurso/sobreposição, falha PK/FK, realocação/configurações, corrupção); verificação completa saiu com 0 e 111 testes offline. Apenas dados sintéticos; nenhuma operação no corpus real/rede/Git.

Decisões: padrões de 4 trabalhadores do parser, 4 threads DuckDB, memória 12 GiB, limite de spill 8 GiB, reserva livre 10 GiB. Exige reserva mais orçamento de spill antes/durante a publicação. Ausência do contexto completo de snapshot/objetos/localização é explicitamente adiada, nunca certificada silenciosamente. Seleção oficial desconhecida mantém partição desconhecida. Sobreposição de cópias entre fragmentos continua indefinida; total global elegível permanece nulo.

Pendências: nenhum adaptador operacional real/piloto; metadados do parser ficam residentes uma vez. Marts de ciclo de vida e validação completa da publicação vêm a seguir; sem importação eleitoral ou ajuste.

Próxima: **6.2**, marts operacionais de cobertura/sessão/disponibilidade de processamento/votação tardia, usando apenas interfaces de publicação e reconstrução.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_publication.py -v
rtk proxy env UV_OFFLINE=1 just check
```
