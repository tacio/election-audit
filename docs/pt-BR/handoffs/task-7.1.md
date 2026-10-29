# Task 7.1 — Importações eleitorais explícitas

Document-ID: EA-HANDOFF-7.1 · Revision: 1 · Language: pt-BR

Objetivo: importações normalizadas estritas e versionadas com bytes originais, hashes, observações e localizadores de registros. Arquivos: `electoral_imports.py`, `tests/test_electoral_imports.py`. CSV exige cabeçalhos exatos do contrato, separador ponto e vírgula, UTF-8 estrito, inteiros canônicos e motivos explícitos para nulos; JSONL rejeita chaves repetidas. Retransmissões preservam testemunhas; conflitos de chaves imutáveis falham. Local, composição, eleitorado, hierarquia final, primeiro e segundo turnos usam contratos explícitos.

Evidência oficial inspecionada em 2026-10-29: página técnica TSE, EA16 revisão 2026-05-22, EA18 revisão 2026-05-22, EA20 revisão 2026-10-13 e recurso BU AC segundo turno 4753eb99-062b-484a-b569-04c51d039885. Identificam formatos/recursos oficiais, mas não verificam cabeçalho CSV BU, codificação ou mapeamento de categorias. Nenhum BU real foi fornecido/importado. Bloqueio exato: faltam bytes fixados de BU real e seu dicionário/cabeçalho junto do mapeamento normalizado revisado. O adaptador implementado é normalized_only; sem certificação de compatibilidade BU oficial ou assinatura.

Aceitação: quatro fixtures normalizadas do importador passaram, saída 0. Nenhuma leitura do corpus bruto ou alteração da aquisição. Git indisponível; sem alegação de commit. Próxima: tarefa 7.2 seleção canônica, evidência somente de acréscimo e reconciliação aritmética/hierárquica. Ler este repasse e apenas os contratos eleitorais.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_electoral_imports.py -v
```

Adaptador oficial TSE verificado continua pendente: entrega parcial da tarefa 7.1. Acesso limitado por intervalo ao ZIP AC também falhou no DNS (curl saída 6, zero bytes); web rejeitou conteúdo binário ZIP/arquivo de hash. Consulte [guia](../electoral-results.md) para links exatos e evidência de descoberta fixada.
