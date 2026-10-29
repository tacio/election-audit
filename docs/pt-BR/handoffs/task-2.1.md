# Tarefa 2.1 — Contratos dimensionais

Document-ID: EA-HANDOFF-2.1 · Revision: 1 · Language: pt-BR

Objetivo: definir granularidades, chaves, identidades, relações, semântica temporal
e versões antes das transformações, impedindo multiplicação de votos nas uniões.

Pré-requisitos: tarefa 1.3, instruções do repositório/RTK, índice e modelo de handoff.
Aquisição continua sendo autoridade e permanece intacta.

Arquivos/interfaces: `election_audit/resources/contracts/schema.json`,
`election_audit/contracts.py`, `tests/test_contracts.py`; pares de
`schema-dictionary.md`, `transformation-conventions.md` e `glossary.md` sob
`docs/en/` e `docs/pt-BR/`. `load_contract("schema")` lê recursos empacotados;
`validate_contracts()` verifica metadados; `validate_rows(table_name, rows)` verifica
estrutura/tipos/chaves/motivos de nulo em um lote. `root` explícito permite outro checkout.

Entregas: 30 contratos cobrindo bytes/observações/pacotes/snapshots imutáveis,
dimensões por eleição, composição, populações harmonizadas, dispositivo/configuração
separados, versões/decisões canônicas de resultado, totais separados de escolhas,
eventos de ciclo, reconstrução anônima, cobertura, problemas e linhagem original.
Localizadores suportam arquivos aninhados/ocorrência de membro e intervalos de
linhas/bytes/registros. Campos anuláveis exigem `field_states`; significados de
ausência são preservados. Exclusões: sem migração de manifesto, criação de snapshot,
parser, ETL, verificador de assinatura ou ajuste de modelo.

Aceitação: comandos abaixo terminaram com 0. Verificação completa passou 43 testes,
lock, Ruff e registros/documentos. A união sintética documentada foi executada no
DuckDB separadamente e retornou `(80, 80)`. Wheel construído offline e validação
por caminho ZIP em `/tmp` passaram, comprovando recursos JSON empacotados.

```sh
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv build --wheel --out-dir /tmp/election-audit-phase2-wheel
```

Decisões: IDs com namespace/resumo retêm chaves naturais e versão da regra.
Objetos, pacotes, sessões físicas, seções e versões de resultado têm identidades
distintas. Eventos de pacote não exigem BUs importados. Agregar escolhas à versão
antes dos totais; nunca expandir totais por integrantes, sessões, evidências ou
linhagem. Harmonizar cada turno em grupos comuns disjuntos antes de unir.
Divisões/transferências sem prova permanecem incomparáveis.

Pendências: validação estrutural não executa regras de linhas estrangeiras,
contexto, não negatividade, contabilidade de categorias, composição ou seleção
canônica; publicação futura deve verificá-las conforme convenções. Códigos e
categorias específicos exigem adaptadores validados. Não houve aquisição ao vivo
nem operação Git; montagem herdada não tem histórico Git utilizável. O ignore
amplo `data/` inicialmente omitiu JSON do wheel; recursos agora estão sob
`election_audit/resources/contracts/`, e a verificação do wheel reconstruído passou.

Próxima tarefa exata: **2.2**, contratos de atributos/prontidão; consultar só
dicionário, alvos da pesquisa e registro de atributos. Concluída pelo mesmo agente
da Fase 2; handoff [2.2](task-2.2.md).
