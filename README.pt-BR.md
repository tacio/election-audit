# Auditoria eleitoral — eleição presidencial brasileira de 2026

Document-ID: EA-ONBOARDING · Revision: 11 · Language: pt-BR

[English](README.md)

Ferramentas reprodutíveis de auditoria dos logs e boletins de urna (BUs) do TSE nos
dois turnos da eleição presidencial de 2026. Os bytes originais são preservados,
cada estágio lê só entradas congeladas e grava uma nova saída imutável que fixa seu
pai, e valores desconhecidos ou parciais permanecem explicitamente indisponíveis em
vez de serem estimados. As ferramentas não produzem rótulos de fraude.

## Estado (3 de novembro de 2026)

- **Coleta:** os dois turnos foram baixados do TSE e verificados por SHA-256 (499176
  versões de log do primeiro turno e 499177 do segundo, com lacunas explícitas de
  seções sem log e sem arquivo auxiliar publicado).
- **Processamento estrutural:** todos os 498581 logs elegíveis do segundo turno
  resumidos em uma release Parquet imutável. O primeiro turno ainda não foi processado.
- **Verificação eleitoral, semântica operacional, features, modelos, investigações e
  notebooks:** implementados e exercitados só no Acre (AC).
- **Próximo:** revisão do plano de análise e das definições das fases.

O [índice de implementação](docs/pt-BR/implementation-index.md) traz o estado
completo, os locais dos artefatos e o mapa de interfaces. Comece por ele.

## Instalação e verificações

Instale uv, just e rtk. Python 3.14, DuckDB, PyArrow e Ruff estão fixados no
lockfile. As receitas usam `/tmp/election-audit-uv-cache`; a instalação offline
exige esse cache preenchido. As verificações nunca baixam dados eleitorais.

```sh
rtk proxy just setup
rtk proxy just doctor
rtk proxy env UV_OFFLINE=1 just check
```

## Teste offline

O passo a passo cria originais explicitamente SINTÉTICOS (arquivo com datas
misturadas, histórico de substituição e cópia, solicitação/cancelamento manual,
relógios não resolvidos, conteúdo aninhado malformado) e publica a cadeia completa
operacional → eleitoral → partição → ledger com os dois relatórios. Todo diretório
de saída precisa ser novo.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
```

Um pacote de revisão contém os originais selecionados congelados, a cadeia relativa
completa de releases, configurações exatas, árvore de código, lock de dependências,
SQL, validação e digests lógicos das saídas. Exclui manifestos ativos, raízes de
coleta, ambiente e credenciais. Veja [reprodução](docs/pt-BR/reproduction.md).

## Pipeline

1. **Coleta** (`download`, `resume`, `inspect`): objetos brutos do TSE e um
   manifesto SQLite. Veja a [referência de coleta](docs/pt-BR/acquisition-reference.md).
2. **Snapshot** (`snapshot`): congela objetos selecionados e denominadores de
   cobertura esperada. Veja [snapshots](docs/pt-BR/snapshots.md).
3. **Parse estrutural** (`parse`): decodificação limitada de JEZ/ZIP aninhados em
   eventos ordenados. Veja [parse de arquivos](docs/pt-BR/archive-parsing.md).
4. **Reconstrução operacional** (`reconstruct`, `operational-review`): sessões,
   ciclos de voto anônimos e regras de relógio com incerteza explícita. Veja
   [reconstrução](docs/pt-BR/reconstruction.md).
5. **Releases** (`build`, `validate`, `query`, `report`): DuckDB/Parquet imutáveis.
   Veja [publicação](docs/pt-BR/publication.md).
6. **Resultados eleitorais** (`import-results`, `electoral-verify`): importação e
   verificação de BWEB e BU binário. Veja
   [resultados eleitorais](docs/pt-BR/electoral-results.md).
7. **Análise** (`analyze`, `features`, `research-protocol`, `research-models`,
   `investigations`): features descritivas, partições congeladas, avaliação final
   protegida e ledgers só de acréscimo. Veja [análise](docs/pt-BR/analysis.md) e o
   [plano de análise](research/analysis-plan.pt-BR.md).
8. **Reprodução** (`demo`, `pilot`, `review-bundle`, `reproduce`, `backfill`).

O processamento estrutural em escala nacional usa resumos paralelos com recursos
limitados em vez de materializar todos os eventos; veja
[processamento orientado a features](docs/pt-BR/feature-oriented-processing.md).
Cada comando documenta a si mesmo:

```sh
rtk proxy env UV_OFFLINE=1 just snapshot --help
rtk proxy env UV_OFFLINE=1 just parse --help
rtk proxy env UV_OFFLINE=1 just reconstruct --help
rtk proxy env UV_OFFLINE=1 just build --help
rtk proxy env UV_OFFLINE=1 just import-results --help
rtk proxy env UV_OFFLINE=1 just analyze --help
rtk proxy env UV_OFFLINE=1 just validate --help
rtk proxy env UV_OFFLINE=1 just query --help
rtk proxy env UV_OFFLINE=1 just report --help
rtk proxy env UV_OFFLINE=1 just backfill --help
rtk proxy env UV_OFFLINE=1 just docs-command-check
rtk proxy just resume --help
rtk proxy just inspect --help
```

## Notebooks

O espaço local marimo tem notebooks de cobertura, eleitoral, operacional e de
pesquisa. Instale as dependências opcionais do painel e informe um conjunto de dados
explícito com checksum. Resultados de pesquisa protegidos ficam ocultos até existir
uma avaliação final validada. O conjunto de dados atual cobre só o AC.

```sh
rtk proxy uv sync --locked --extra dashboard
rtk proxy just dashboard --dataset data/dashboard-ac-2026-10-30/dataset.json
```

## Documentação

Documentos em inglês e português compartilham IDs, revisões e comandos, SQL,
fórmulas e números idênticos byte a byte; `just docs-check` verifica isso. Veja
também [trabalhos relacionados](research/related-work.pt-BR.md), o
[plano de conclusão](research/completion-plan.pt-BR.md) e o
[glossário](docs/pt-BR/glossary.md).
