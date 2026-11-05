# Tarefa 20 — Verificações de integridade de nível 1

Document-ID: EA-HANDOFF-20 · Revision: 1 · Language: pt-BR

Objetivo: executar nacionalmente, para 2026 e nos dois turnos, as verificações
determinísticas de integridade I1–I9 do protocolo do estudo, com tabelas completas
de discrepâncias e sem modelo estatístico.

Pré-requisitos: [protocolo do estudo](../../../research/analysis-plan.pt-BR.md)
(Revisão 4), seção 5; [plano de conclusão](../../../research/completion-plan.pt-BR.md),
Fase 20; as entradas da Fase 19 ([handoff 19](task-19.md)) e as versões da Fase 21
([handoff 21](task-21.md)).

Arquivos e interfaces: `election_audit/integrity_checks.py` (`integrity-check
sections|bweb|hierarchy|correspondence|logs`; versões `integrity-sections-v1`,
`integrity-logs-v1`), `election_audit/resources/assinatura-2026-observed.asn1`,
`semantic_pass.verified_bulk_archives`, `tests/test_integrity_checks.py` e a seção
real do AC em `tests/fixtures/integrity-2026/`. Cada etapa grava uma raiz nova com
`binding.json` e um `release/` com somas de verificação; `sections` só retoma com
vínculo idêntico. Guia: [verificações de integridade](../integrity-checks.md).

Entregas:

- Versões nacionais dos dois turnos em `~/data/election-audit-stage/phase20/`:
  `national-r{1,2}-sections-v1-20261105`, `-bweb-v1c-`, `-hierarchy-v1-`,
  `-correspondence-v1-` e `-logs-v1-20261105`.
- As tabelas das versões guardam só situações e resumos; valores de votos aparecem
  só em linhas de discrepância; o comparecimento para o I5 fica em
  `release/restricted/`. Os 596 logs protegidos/de estresse foram resumidos por hash,
  nunca interpretados.
- O formato observado dos arquivos de assinatura de 2026, fixado por resumo.

Aceitação (5 de novembro de 2026):

- I1: as 499207 seções de cada turno coincidem com as duas listas de hashes; ECDSA
  (UE2013/UE2015) verificada em 99985 e 99957 seções sem falha; 399222 e 399250
  seções Ed521 não verificadas; toda cadeia de hash do BU íntegra.
- I2: toda disputa presente no BU e no BWEB é igual; I3: igual, exceto 10 disputas
  do primeiro turno em duas seções SA de MG (20 eleitores cada); I4: toda medida de
  voto igual nos 5786 nós; I9: a urna efetivada é igual ao BU em toda seção.
- I5: 85 e 36 seções diferem; I6: 99 logs do segundo turno com um bloco fechado do
  primeiro turno que difere; I7: 2138 e 1815 seções com alguma regra violada. Todos
  os números estão no [guia](../integrity-checks.md#resultados-nacionais).
- O novo código reproduziu byte a byte a versão de desenvolvimento do I2 no AC.
- `UV_OFFLINE=1 just check` passa com 371 testes.
- Não tentado: I8 (sem fonte), Ed521, cadeias de certificados, 2022.

Decisões:

- Logs protegidos: incluídos na passada e resumidos por hash (I1, I9), nunca
  interpretados; I5–I7 os pulam até o congelamento da Fase 23.
- Assinaturas: hashes e ECDSA agora, Ed521 depois.
- Cegamento: nenhum valor é guardado para linhas que concordam.
- Votos de legenda do RDV guardam os dígitos digitados; o partido são os dois
  primeiros.
- O I4 conta como nulos técnicos (`vnt`) os votos do BWEB numa candidatura que o
  arquivo nacional do EA20 não lista e compara as seções principais com `si`.
- Os códigos de carga das correspondências perdem um zero à esquerda e são
  completados até 24 dígitos.
- O teto de RAM agregada subiu de 4 GiB para 6 GiB em 5 de novembro de 2026, depois
  destas execuções. O maior processo isolado da passada de seções chegou a 4,6 GB
  (primeiro turno) e 4,0 GB (segundo); o total dos seis workers não foi medido, então
  a passada de seções pode ter passado do teto antigo e não está demonstrado que cabe
  no novo. É preciso medir o total (cgroup ou amostragem por processo) antes de
  reexecutá-la.
- A primeira execução nacional do BWEB esgotou a memória do DuckDB: um único banco
  para todas as UFs e um resumo `string_agg` em memória. Agora cada UF tem seu
  próprio banco, o DuckDB só agrupa e ordena, e o Python monta o resumo com a função
  do BU. As execuções seguintes passaram do orçamento de 4 GiB (5,0 GB, depois
  4,1 GiB), então as linhas de disputas agora são gravadas por UF, o banco da UF é
  fechado antes de montar as consultas em Python e o limite do DuckDB é 1 GB por UF
  (SP sozinho: 2,4 GB, mesmo tempo). `bweb-v1c` é a versão de referência; as
  execuções anteriores tiveram resumos, discrepâncias e tabelas de seções idênticos
  e as mesmas linhas de disputas na mesma ordem, e foram apagadas.

Questões em aberto:

- Ed521 (UE2020/UE2022): a curva do DOC-ICP-01.01 v6.0 (p = 2^521−1,
  d = −376014, SHAKE256 com prefixo de domínio `SigEd521`) não verificou nenhuma
  assinatura, no modo puro ou com pré-hash (SHA3-512, SHAKE256-64), com o hash do
  arquivo, a lista ou o seu DER como mensagem, em qualquer ordem de bytes. É preciso
  a construção exata do TSE.
- O I6 compara impressões digitais de segmentos inteiros, então o último bloco
  aberto do primeiro turno fica `open_prefix_unverified`; os 99 logs que diferem e
  os 3645 com blocos a mais exigem uma releitura bruta por bloco.
- Diferenças em aberto do I5, em logs com várias sessões (provavelmente
  reexecuções somadas duas vezes) e em sessões únicas com menos ciclos que o
  comparecimento: agrupamento de sessões da Fase 22.
- As duas seções SA de MG (41238/0039/0168, 50075/0047/0041): a diferença de 20
  eleitores é compatível com cédulas de papel, mas não está confirmada; conferir os
  logs SA e a ata da seção, se puder ser obtida.
- Dez eleições municipais realizadas com o segundo turno (6282–6293) não têm fonte
  no BWEB.
- Os arquivos em massa do segundo turno têm 77 membros `*.id` de 47 bytes sem
  explicação (19 arquivos, 25 de outubro) e um log para SP 64777/0395/0298, que o
  endpoint por seção publicou sem log. Os membros `.id` estão em
  `archive_members.json`; o log de SP é resumido por hash na linha da sua seção.

Próxima tarefa exata: Fase 22 (agrupamento de sessões e regras de relógio), usando
as tabelas de discrepâncias do I5 e do I6. A Fase 20b do
[plano de conclusão](../../../research/completion-plan.pt-BR.md) reúne as lacunas do
Ed521, das cadeias de certificados, do I6, do I2 e do I8 e precisa ser fechada, ou
escrita no protocolo, antes do congelamento da Fase 23. Arquivar o relatório consolidado do TCU
sobre os testes de integridade quando for publicado (por volta de 24 de novembro de
2026).
