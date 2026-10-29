# Task 9.3 — Reprodução e pacote de revisão sem rede

Document-ID: EA-HANDOFF-9.3 · Revision: 1 · Language: pt-BR

Pré-requisitos: [8.3](task-8.3.md), [índice](../implementation-index.md), [análise](../analysis.md), [reprodução](../reproduction.md), [processamento](../backfill.md). Tarefa 7.1 permanece parcial; nenhuma validação BU real ou nacional é alegada.

Objetivo/arquivos/interfaces: reproduction.py oferece review_bundle/verify_bundle/reproduce e CLI/receitas correspondentes. Exportação inclui originais/inventário congelados, cadeia relativa completa, configurações, SQL/relatórios/nulos/limites, código explicitamente permitido e dependências/versões. Manifesto ativo, raiz original, .local-state, .git, .aws, .codex, .agents e ambiente não são copiados. Links simbólicos são rejeitados antes da leitura de destino. Hashes completos detectam alterações/remoções/adições; checksum do invólucro não é assinatura autenticada. Implementação instalada deve coincidir com o código incluído antes da reprodução; dependências sem rede precisam estar instaladas/em cache.

Entregas/aceitação/limites: Reprodução sintética relocada de quatro etapas, adulteração, rejeição de links simbólicos, metadados/blocos de cálculos pareados e verificações inofensivas de comandos/opções/SQL têm testes de aceitação focados. Manifestos exatos retêm fixações físicas/lógicas. Contêineres e IDs derivados novos podem diferir; reprodução mapeia somente proveniência parent_release_id para aliases e verifica exatamente os demais campos e identidade estrutural. Artefatos estáveis: data/phase9/demo-review, demo-reproduced, pilot-review e pilot-reproduced; reproduction-result.json registra correspondências reais/diferenças de runtime. scripts/check_doc_commands.py nunca executa aquisição/processamento/SQL documentados; scripts/check_docs.py mantém verificações de metadados/revisões/links/blocos/Mermaid. Significado da tradução permanece revisão humana.

```sh
rtk proxy env UV_OFFLINE=1 just review-bundle data/phase9/demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
rtk proxy env UV_OFFLINE=1 just docs-command-check
```
