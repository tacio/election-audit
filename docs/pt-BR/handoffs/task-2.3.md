# Tarefa 2.3 — Pesquisa bilíngue e verificações documentais

Document-ID: EA-HANDOFF-2.3 · Revision: 2 · Language: pt-BR

Objetivo: preservar referências integrais de pesquisa/aquisição em inglês e
português brasileiro, verificando pares, revisão, links e exemplos mecanicamente.

Pré-requisitos: tarefas 2.1/2.2, pesquisa inglesa e README de aquisição original.
Conteúdos locais foram autoridade; fontes vinculadas não foram buscadas novamente.

Arquivos/interfaces: `research/analysis-plan.md`, `research/download-sources.md` e
pares vinculados `*.pt-BR.md`; `docs/en/acquisition-reference.md` e tradução
integral. Onboarding README em Revisão 2 aponta para eles. Pares de dicionário,
prontidão, glossário, convenções, três handoffs e índice. `scripts/check_docs.py`
expõe `check_docs(root)`; `just docs-check` e `just contracts-check` entram em
`just check`. Testes exercitam falhas deliberadas de revisão/exemplo/link.

Entregas: tradução integral de protocolo preservando desenho/hipóteses, ressalvas,
referências, fórmulas e exemplos numéricos; notas de fontes/espelhos e referência
histórica traduzidas. Referência ainda estava embutida no README após Fase 1,
portanto foi extraída intacta com links locais ajustados. Contagens históricas
continuam observações datadas, não cobertura atual. Identificadores, fórmulas e
exemplos de código ficam iguais nos idiomas. IDs/estrutura Mermaid permanecem
iguais; rótulos humanos são traduzidos. Exclusões: docs-check não executa
comandos; validação completa fica para Fase 9. Sem site, artefatos renderizados ou
aquisição ao vivo.

Aceitação: `rtk proxy env UV_OFFLINE=1 just check` terminou com 0; 43 testes passaram,
incluindo verificações documentais; 16 pares validam metadados/revisão/links locais/
blocos de exemplos. Revisão manual comparou toda seção do protocolo, ressalva,
conjunto de referências externas, fórmula e exemplo numérico. Blocos SQL sintéticos
são iguais nos idiomas e o exemplo retornou `(80, 80)` no DuckDB. Não se afirma
atualidade de links externos nem instalação limpa por rede. ResourceWarning legado
de SQLite pode aparecer no Python 3.14; todos os testes passam.

Decisões: caminhos ingleses da pesquisa permanecem; português usa `*.pt-BR.md`.
Guias paralelos compartilham Document-ID/Revision e revisões sobem juntas.
Verificador descobre pares docs/pesquisa/README por metadados, compara código sem
executá-lo, verifica estrutura Mermaid permitindo rótulos traduzidos e relata
caminhos/âncoras locais ausentes. Significado da tradução
exige revisão humana; paridade mecânica não o certifica.

Pendências: especificações/URLs externas podem mudar; esta fase traduziu fontes
fornecidas sem navegar novamente. Detalhes de parser, prontidão real, assinaturas
oficiais e exemplos executáveis completos ficam para etapas posteriores.

Próxima tarefa exata: **3.1**, implementar localizador autorizado somente para
leitura e inventário imutável de snapshot/cobertura preservando aquisição. Ler só
índice, handoff 2.1, dicionário/convenções e subconjuntos de fontes/snapshots/
cobertura/linhagem em `election_audit/resources/contracts/schema.json`; consultar
`manifest_path(root)` de `scripts/download_tse_logs.py`. Congelar observações atuais
URL-bytes honestamente; manter mapeamentos históricos indisponíveis explicitamente
desconhecidos.

Correção da revisão: rótulos portugueses dos diagramas de esquema/prontidão estão
traduzidos; revisões dos guias em pares são 2. Comparação Mermaid preserva tipo/
direção, IDs de entidades/nós, ligações, setas/cardinalidade e formas suportadas.
Só rótulos humanos reconhecidos podem diferir; sintaxe não suportada permanece
exata. Testes permitem tradução e rejeitam IDs, setas, direção, cardinalidade ou
relações removidas; blocos executáveis/de código continuam exatos. A aceitação
focada está registrada abaixo; índice e outras fases não foram alterados nesta correção.

Aceitação da correção: comandos abaixo terminaram com 0; 4 testes documentais
focados passaram, todos os pares atuais passaram e Python alterado passou lint
e formato. A correção isolada não exigiu repetir toda a suíte.

```sh
rtk proxy env UV_OFFLINE=1 just docs-check
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked python -m unittest discover -s tests -p test_docs.py -v
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked ruff check scripts/check_docs.py tests/test_docs.py
rtk proxy env UV_CACHE_DIR=/tmp/election-audit-uv-cache UV_OFFLINE=1 uv run --locked ruff format --check scripts/check_docs.py tests/test_docs.py
```
