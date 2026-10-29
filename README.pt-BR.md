# Auditoria eleitoral — segundo turno presidencial de 2026

Document-ID: EA-ONBOARDING · Revision: 4 · Language: pt-BR

[English](README.md)

Este projeto preserva os bytes originais da aquisição e publica snapshots congelados → análises estruturais → reconstrução operacional → publicações imutáveis DuckDB/Parquet → importações eleitorais normalizadas → atributos descritivos, partições e registros imutáveis de análise. Logs disponíveis AC–RJ formam uma população nacional parcial. Nenhum modelo é ajustado e nenhum rótulo de fraude é produzido.

Instale uv, just e rtk. Python 3.14, DuckDB 1.5.3, PyArrow 24.0.0 e Ruff estão fixados no arquivo de dependências. As receitas usam `/tmp/election-audit-uv-cache`; instalação sem rede exige cache previamente preenchido. As verificações nunca adquirem dados eleitorais.

```sh
rtk proxy just setup
rtk proxy just doctor
rtk proxy env UV_OFFLINE=1 just check
```

O pequeno roteiro sem rede cria originais explicitamente SINTÉTICOS, arquivo com datas mistas, substituição/histórico copiado, solicitação manual/cancelamento, relógios não resolvidos e conteúdo aninhado malformado. Publica toda a cadeia operacional → eleitoral normalizada → partição → registro de resultado nulo e ambos os relatórios. Cada diretório de saída abaixo deve ser novo.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
```

O pacote de revisão contém originais selecionados congelados, cadeia relativa completa de publicações-pais, configurações exatas, código e dependências fixadas, SQL, validação e resumos criptográficos lógicos. Exclui manifesto ativo, raiz da aquisição, ambiente e credenciais. Reprodução sem rede exige dependências fixadas já instaladas ou em cache; distribuições/cache não são incluídos. Bytes dos contêineres e tempos de criação podem diferir; identidades das entradas congeladas e conteúdo lógico normalizado são verificados.

Use o [guia de reprodução e revisão por pares](docs/pt-BR/reproduction.md) para piloto real limitado, revisão de evidências e limites de reprodutibilidade; use o [guia de processamento retroativo](docs/pt-BR/backfill.md) para planejamento de recursos e retomada. Comandos operam sobre entradas congeladas, exceto quando se invoca explicitamente um comando de aquisição.

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

A tarefa 7.1 permanece PARCIAL: implementar o adaptador BU oficial TSE 2026 somente após obter e verificar documentação oficial e dados BU originais, e então executar validação real de compatibilidade/aritmética. O importador normalizado e comparecimento sintético 10/20 não satisfazem essa tarefa. BU real ausente não impede diagnósticos operacionais. Atributos numéricos continuam cientificamente inelegíveis; permutabilidade, atribuição de candidatos e margem nacional final estão indisponíveis.

Opções do coletor legado, estrutura de objetos, `manifest-location.json` autoritativo e comportamento WAL ativo foram preservados. Mantenha um coletor por raiz original. Nova captura de snapshot observa o estado confirmado atual; reproduza um snapshot congelado existente para preservar identidades de observação. UFs/ZZ adicionais e turnos/histórico exigem snapshots/importações explícitos.

Trabalho posterior começa pelo [índice de implementação](docs/pt-BR/implementation-index.md). Veja [snapshots](docs/pt-BR/snapshots.md), [arquivos](docs/pt-BR/archive-parsing.md), [reconstrução](docs/pt-BR/reconstruction.md), [publicação](docs/pt-BR/publication.md), [importações eleitorais](docs/pt-BR/electoral-results.md), [análise](docs/pt-BR/analysis.md), [protocolo de pesquisa](research/analysis-plan.pt-BR.md) e [referência da aquisição](docs/pt-BR/acquisition-reference.md). Documentos em inglês e português compartilham IDs/revisões e comandos, SQL, fórmulas e exemplos numéricos exatos. Verificações mecânicas complementam revisão humana da tradução.
