# Tarefa 3.2 — Registro de população

Document-ID: EA-HANDOFF-3.2 · Revision: 1 · Language: pt-BR

Objetivo: contabilizar integrantes esperados, principais únicos e todas as lacunas.
Pré-requisitos: [3.1](task-3.1.md), contratos de composição/cobertura/linhagem.

Arquivos/interfaces: `election_audit/coverage.py`, `build_population(inventory)`;
`source_inventory.py` aceita todas as UFs/ZZ explicitamente, mantendo AC–RJ como
padrão. As duas funções de inventário aceitam `section_keys` opcional com tuplas
`(uf, municipality, zone, section)` para limitar leitura de bytes. Índices completos
das UFs são preservados; integrantes fora da amostra continuam no registro com
`outside_asset_selection`.

Entregas: linhas dos contratos de eleição, objetos/observações de fontes, anúncios
e arquivos atuais de pacotes, seções, composição resolvida, cobertura e linhagem
por ponteiros JSON originais. Evidências preservam execuções históricas, falhas,
anúncios, registros do índice e estados de pacotes não representáveis. JSON auxiliar
é metadado, sem interpretação de arquivos compactados. Semântica dos estados,
instalação, disponibilidade de BU e parsing continuam desconhecidos/não tentados.

Aceitação: comando abaixo terminou com código 0; 12 testes isolados passaram
(5 de inventário e 7 de população). Novos casos cobrem denominadores, agregação,
índices ausentes, ciclos/conflitos/principais ausentes, execuções inacabadas,
interrompidas e finalizadas, anúncios sem bytes, metadados corrompidos, seleção de
seções e novas UFs. A aquisição real não foi acessada.
`rtk proxy env UV_OFFLINE=1 just check` terminou com código 0: lock, formatação,
lint, contratos, documentos em pares e 55 testes passaram. Uma falha inicial de
ordenação de imports foi corrigida; ResourceWarning legado permanece não fatal.

```sh
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_snapshots.py -v
```

Decisões: índice verificado de fase/pleito/UF define integrantes esperados; índice
ausente/inválido/duplicado mantém denominador nulo. Seções só do manifesto continuam
visíveis sem se tornarem população autorizada. Composição aceita somente principal
direto conhecido com automapeamento; sem colapsar cadeias. Contabilização de membros
é disjunta; principais únicos têm denominador próprio. Versões parcialmente
adquiridas ficam não resolvidas. Execução finalizada não prova cobertura e running
não distingue processo ativo de abandonado. Atribuição histórica de bytes continua
desconhecida. Novas UFs entram em snapshots explícitos sem mudar código; completude
nacional exige todas as UFs incluindo ZZ e arquivos completos.

Pendências: contrato v1 não representa estado bruto nulo de pacote: metadados exatos
e problemas explícitos são preservados, omitindo esse anúncio normalizado. Não se
infere denominador nacional de um subconjunto. Sem parser de arquivos ou DuckDB.

Próxima tarefa exata: **3.3**, copiar/verificar entradas congeladas atomicamente e
publicar IDs imutáveis, proveniência, CLI de inspeção e guia compacto em pares.
Ler somente este registro, APIs e contratos de snapshot/participação.
