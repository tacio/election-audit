# Task 7.1 — Importações eleitorais explícitas

Document-ID: EA-HANDOFF-7.1 · Revision: 2 · Language: pt-BR

A lacuna de acesso/adaptador oficial foi resolvida para o leiaute BWEB AC verificado.
O importador normalizado permanece disponível. `official_bu.py` adiciona adaptador
CSV oficial limitado e versionado por `read_import` e `import-results`. ZIP original,
hash publicado, metadados de catálogo/recurso, CSV descompactado e dicionário são
preservados por hash em derivadas imutáveis. Testemunhas cobrem dimensões, composição,
escolhas, totais e tokens originais de eventos. `bweb-2026-layout.json` fixa dicionário,
cabeçalho, codificação e semântica de categorias.

Fonte real AC: ZIP de 1254611 bytes, SHA-256
`35c1f1676e04d0824eb57df158f40d3c1e943926fd4754933a9d2863ccf06e1b`;
SHA-512 publicado e CRCs passam. 17622 linhas se dividem em 8697 presidenciais e
8925 de governador excluídas. Importadas 2270 seções principais presidenciais,
2411 seções membros e 668 locais. Escolhas publicadas somam 453654 votos. Todas as
2270 verificações soma de votos/comparecimento e contabilização do eleitorado conferem.

Limites: escolhas ausentes nunca viram zero; lista completa não é certificada.
Apurada não certifica Totalizado; situação oficial fica desconhecida. Nenhuma razão
eleitoral canônica, conversão de fuso, hierarquia final independente, certificação de
assinatura, cobertura nacional BU ou elegibilidade científica é alegada. Composição
BU usa snapshot próprio; vínculo operacional exige revisão explícita. Outros leiautes/
categorias falham até revisão. Primeiro turno/histórico e referências externas
finais/de eleitorado continuam usando contratos normalizados explícitos.

Regressões incluem subconjunto atribuído do CSV real e dicionário exato, escolhas/
relógios/situações desconhecidos, filtro de cargos, agregações, retransmissões,
registros imutáveis contraditórios, hashes corrompidos, categorias desconhecidas,
limites de recurso/codificação/cabeçalho/dicionário e relocação de derivada imutável.
Verificação oficial persiste no carregador/validador/relatório e indicadores por
snapshot; nenhum modelo é ajustado. Falhas anteriores de acesso permanecem como
evidência histórica. Consulte [guia](../electoral-results.md) para pacote e comandos reais.

Aceitação: `rtk just check` passou com 177 testes sem rede, formatação, lint,
lock, registros de contratos, documentação em par e verificações inofensivas de comandos/SQL.
Validação real da fonte está em `data/official-bu/ac-runoff-2026-10-30/validation-final.json`;
validação imutável, relatórios e ID atual estão ao lado em `release-validation.json`,
`reports/` e `run-evidence.json`. Novas observações dos mesmos bytes acrescentam
resultados/eventos/testemunhas congelados separados sem alterar snapshots anteriores.
Aquisição original de logs e publicações existentes do piloto foram preservadas.
