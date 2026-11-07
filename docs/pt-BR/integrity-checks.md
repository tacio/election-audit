# Verificações de integridade de nível 1 (Fase 20)

Document-ID: EA-INTEGRITY-CHECKS · Revision: 2 · Language: pt-BR

[English](../en/integrity-checks.md) · [Índice de implementação](implementation-index.md)

`integrity-check` executa as verificações determinísticas I1–I9 do
[protocolo do estudo](../../research/analysis-plan.pt-BR.md#5-nível-1-verificações-determinísticas-de-integridade)
para 2026, nos dois turnos. Cada etapa lê entradas congeladas e conferidas por hash,
grava uma raiz de saída nova e relata contagens com tabelas completas de
discrepâncias. Nenhum modelo estatístico é usado.

## Acesso aos dados

- As tabelas de saída guardam situações e resumos (digests), nunca contagens de
  votos. Valores aparecem só em `discrepancies.jsonl`, para linhas que discordam.
- Comparecimento e totais de votos de que verificações posteriores precisam (I5) são
  gravados em `release/restricted/attendance.parquet`. O código das verificações os
  lê; nada os relata ou consulta antes do congelamento da Fase 23.
- A passada de seções lê todo membro dos arquivos em massa, inclusive os 596 logs
  protegidos/de estresse, mas o processo pai só calcula o SHA-512 dos logs e das
  imagens de BU. Os workers recebem o BU, o RDV e o arquivo de assinatura de cada
  seção; nenhum log é interpretado.
- I5–I7 leem as versões da passada semântica da Fase 21, que nunca abriu os logs
  protegidos. Essas seções aparecem como `protected_or_unavailable`.

## Etapas

| Etapa | Verificações | Lê | Grava |
| --- | --- | --- | --- |
| `sections` | I1 (hashes, assinaturas ECDSA e Ed521, certificados das urnas, cadeia de hash do BU), I3, I9 (arquivos, identidade) | arquivos em massa de BU/RDV/log | `sections`, `contests`, `restricted/attendance`, `archive_members.json` |
| `bweb` | I2 | uma versão de `sections`, BWEB | `contests`, `sections` |
| `hierarchy` | I4 | BWEB, EA20 | `nodes` |
| `correspondence` | I9 (urna efetivada) | uma versão de `sections`, correspondências (CEFT) | `sections` |
| `logs` | I5, I6, I7 | uma versão de `sections`, versões da Fase 21 | `sections` |

Cada `release/` também guarda `discrepancies.jsonl` e um `manifest.json` com o
vínculo, um resumo e os hashes dos arquivos.

```sh
just integrity-check sections \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --round 2 --output ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --workers 6
just integrity-check bweb \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --bweb-root ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna \
  --output ~/data/election-audit-stage/phase20/national-r2-bweb-v1-20261105
just integrity-check hierarchy \
  --bweb-root ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna \
  --ea20-root ~/data/election-audit-stage/results-hierarchy/ea20-r2-20261104 \
  --round 2 --output ~/data/election-audit-stage/phase20/national-r2-hierarchy-v1-20261105
just integrity-check correspondence \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --ceft-root ~/data/election-audit-stage/inputs/resultados-2026-correspondencias-esperadas-e-efetivadas-2-turno \
  --output ~/data/election-audit-stage/phase20/national-r2-correspondence-v1-20261105
just integrity-check logs \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v1-20261105 \
  --semantic ~/data/election-audit-stage/phase21/national-r2-20261103 \
  --semantic-round1 ~/data/election-audit-stage/phase21/national-r1-20261103 \
  --output ~/data/election-audit-stage/phase20/national-r2-logs-v1-20261105
```

## O que cada verificação compara

**I1, assinaturas.** O arquivo de assinatura de cada seção (`-vota.vsc`, `-sa.vsc`)
guarda duas listas de hashes SHA-512 por arquivo: uma de software, assinada com
CEPESC, e uma de hardware, assinada com a chave da urna. A passada confere cada
arquivo publicado contra as duas listas, o auto-hash de cada lista e se as duas
listas concordam. As listas também citam sete arquivos que o TSE não publica
(`jufa`, `imgze`, `hash`, três imagens biométricas `wsq*` e `mr.ver`); eles são
registrados como não publicados, não como falhas.

- Urnas UE2013 e UE2015 assinam com ECDSA P-521. O certificado DER (emitido pela
  `AC URNA`) verifica a autoassinatura de hardware, a assinatura de cada arquivo
  publicado e a assinatura da cadeia de hash dos totais de cada BU. As assinaturas
  são DER e cobrem o hash SHA-512 de 64 bytes, de novo resumido com SHA-512.
- Urnas UE2020 e UE2022 assinam com EdDSA sobre a E-521 (Ed521, DOC-ICP-01.01 da
  ICP-Brasil; certificados PEM da `AC UE2020` e da `AC UE2022`), sobre o mesmo hash
  duplo. Desde a Fase 20b (`integrity-sections-v3`) elas são verificadas com o
  [`ed521rs`](https://pypi.org/project/ed521rs/) sob as regras de decodificação da RFC
  8032, que dão os veredictos de `election_audit/ed521.py`. Cada assinatura também é
  conferida como o ECPy, o verificador do pacote de formatos de 2026 do TSE, a
  conferiria; `ed521_ecpy_disagreements` conta as assinaturas em que os dois
  veredictos diferem.
- O certificado de cada urna é conferido contra o certificado publicado da AC que o
  emitiu (`urn-pki-v2`): a assinatura da AC (ECDSA P-521 com SHA-512, ou Ed521 sobre
  o TBSCertificate cru, como no `mr_util.valida_certificado` do TSE), o número de série
  contra a lista de revogados dessa AC e a validade do certificado da AC no dia da
  eleição. Os certificados das ACs e as listas de revogados estão fixados em
  `resources/pki/` com sua procedência. O elo seguinte (até a `AC RAIZ UE` e a
  `AC URNA v2`) não é conferido: esses certificados não são públicos
  ([T1](observations.md#transparência)).
- O CEPESC não é público; assinaturas de software nunca são verificadas.

Desde a Fase 20b, BU, RDV e arquivos de assinatura são decodificados com as
especificações oficiais do pacote de formatos de 2026 do TSE
(`resources/*-2026-official.asn1`, procedência em
`resources/tse-format-2026-official.json`), no lugar das espelhadas e observadas
([T7](observations.md#transparência)). Os valores não mudam; os rótulos de enumeração
mudam (o tipo de urna `reservaSecao` passa a `contingenciaSecao`).

**I1, cadeia de hash do BU.** Cada eleição do BU traz uma cadeia SHA-512 sobre seus
totais de votos. O cabeçalho é `pleito|eleição|município|zona|seção|código de carga`
(com zeros à esquerda até 5, 5, 5, 4, 4 e 24 dígitos); cada bloco é
`HASH_ANTERIOR_HEX_MAIÚSCULO|ordem|cargo|tipo de voto|quantidade[|candidato|partido]`,
na ordem de impressão e de hash. Todo hash de bloco e o `ultimoHashVotosVotavel` final
precisam coincidir.

**I2, BU contra BWEB.** Para cada seção e disputa, o resumo canônico das entradas
`(classe, número, quantidade)` não nulas do BU binário precisa ser igual ao das linhas
do BWEB. As classes são N (nominal), L (legenda), B (branco), X (nulo) e S (sem
candidato). Eleitores aptos, comparecimento, local de votação, número da urna, código
de carga, cartão de memória e horários de carga, abertura, encerramento e emissão
também são comparados. O BWEB omite quantidades zero.

**I3, recontagem do RDV.** Toda disputa do RDV é recontada e comparada com os totais
do BU. Um voto de legenda guarda o que foi digitado (um número de candidato
incompleto ou inexistente); o partido são os dois primeiros dígitos.

**I4, hierarquia.** As somas das seções do BWEB para a disputa presidencial (ligadas
ao BU pelo I2) são comparadas com cada arquivo de município do EA20, os municípios
com o arquivo da UF e as UFs (com o ZZ) com o arquivo nacional. O EA20 relata votos
numa candidatura anulada depois da eleição como nulos técnicos (`vnt`), que o BWEB
mantém como nominais; esses votos são remapeados antes da comparação. O EA20 conta
seções instaladas (`si`) e não instaladas (`sni`, sem BU); as seções principais são
comparadas com `si`.

**I5, comparecimento.** Os ciclos de voto concluídos nas sessões oficiais do turno
(somados entre reinícios) precisam ser iguais ao comparecimento do BU, e os ciclos
biométricos às habilitações biométricas do BU.

**I6, blocos do primeiro turno.** Todo bloco do primeiro turno de um log do segundo
turno precisa ser igual ao bloco que começa com a mesma linha, na mesma urna, no log
do primeiro turno. O último bloco do primeiro turno continua no log do segundo turno
depois de o log do primeiro turno ter sido gravado, então só pode coincidir como
prefixo; a Fase 21 guardou impressões digitais de segmentos inteiros, então esse
bloco aparece como `open_prefix_unverified`.

**I7, regras de relógio e sessão** (`integrity-logs-v1`): R1 ao menos uma sessão
oficial do turno; R2 a última tem leitura de encerramento; R3 nenhum recuo do relógio
dentro das sessões oficiais; R4 nenhuma conclusão fora de um ciclo; R5 toda sessão
oficial começa na data da eleição; R6 as sessões oficiais não se sobrepõem.

**I8, BUs impressos.** Não executado: nenhuma coleção independente de cópias
impressas de BU foi obtida.

**I9, população e identidade.** Presença de arquivos por seção, nomes de arquivo
contra o conteúdo do BU e do RDV, pleito e fase, identidade do BWEB, membros
inesperados nos arquivos e a urna efetivada de cada seção nos arquivos de
correspondência (número da urna, código de carga, cartão de memória, horário de
carga) contra o seu BU.

## Resultados de desenvolvimento

No AC (dois turnos, dado de desenvolvimento) e no ZZ (primeiro turno), antes das
execuções nacionais:

- I1: todo arquivo publicado coincidiu com as duas listas; as assinaturas ECDSA do ZZ
  (1310 seções, inclusive 29 pacotes SA) e as assinaturas das cadeias do BU foram
  todas verificadas; os certificados do AC são da `AC UE2020` (989) e da `AC UE2022`
  (1281), válidos no dia da eleição.
- I2, I3, I4: nenhuma discrepância (AC: 11350 e 4540 disputas, 22 municípios e o nó
  da UF).
- I5: os ciclos concluídos do AC são iguais ao comparecimento do BU, e os ciclos
  biométricos às habilitações biométricas, em toda seção com log (1667 e 1663).
- I6 (AC, segundo turno): 1651 seções iguais em todo bloco fechado do primeiro turno,
  com o último bloco aberto; 17 logs do segundo turno não têm bloco do primeiro turno
  (a urna foi recarregada), um é de outra urna, e cinco logs do segundo turno têm
  blocos do primeiro turno ausentes do log do primeiro turno.
- I9: a urna efetivada coincidiu com o BU em toda seção do AC e do ZZ depois de
  completar com zeros os códigos de carga das correspondências (que perdem um zero à
  esquerda).

## Resultados nacionais

Execuções de 5 de novembro de 2026, nos dois turnos, 499207 seções cada, em
`~/data/election-audit-stage/phase20/national-r{1,2}-*-20261105/` (`sections-v1`,
`bweb-v1c`, `hierarchy-v1`, `correspondence-v1`, `logs-v1`). A passada de seções
levou 64 e 59 minutos com seis workers.

| Verificação | 1º turno | 2º turno |
| --- | --- | --- |
| I1 arquivos publicados coincidem com as duas listas, listas concordam, auto-hashes | 499207 | 499207 |
| I1 ECDSA verificadas (UE2013/UE2015), arquivos e assinaturas das cadeias do BU | 99985, 0 falhas | 99957, 0 falhas |
| I1 Ed521, não verificadas (UE2020/UE2022) | 399222 | 399250 |
| I1 cadeias de hash do BU íntegras | 2490805 de 2490805 | 539817 de 539817 |
| I3 recontagem do RDV igual | 2490795 de 2490805 | 539817 de 539817 |
| I2 disputa do BU igual ao BWEB | 2490804 de 2490805 | 538944 de 539819 |
| I4 nós iguais em toda medida de voto | 5786 de 5786 | 5786 de 5786 |
| I5 ciclos concluídos iguais ao comparecimento do BU | 496859 (85 diferem, 2263 indisponíveis) | 497096 (36 diferem, 2075 indisponíveis) |
| I7 seções com alguma regra violada | 2138 | 1815 |
| I9 urna efetivada coincide com o BU | 499207 | 499207 |

- I1: todo certificado é válido no dia da eleição. Nenhuma assinatura que pôde ser
  conferida falhou.
- I3: as 10 diferenças do primeiro turno são todas as disputas de duas seções de MG
  apuradas com o sistema SA (41238/0039/0168 e 50075/0047/0041). Nas duas, o BU de
  cada disputa tem exatamente 20 eleitores a mais que o RDV (40 votos para o Senado).
  São os únicos dois pacotes SA fora do ZZ; os outros 29 recontam exatamente. Cédulas
  de papel digitadas no SA, que nunca passam pelo RDV, explicariam a diferença; isso
  não está confirmado, porque essas seções não têm log de urna e o I5 fica
  indisponível para elas.
- I2: nenhuma disputa presente nos dois lados difere. O restante são diferenças de
  presença ou de campos com causa conhecida:
  - Segundo turno, 871 disputas `bu_only`: dez eleições municipais realizadas junto
    com o segundo turno (eleições 6282–6293: eleições suplementares para prefeito,
    cargo 11, e três consultas, cargos 25–27) em 13 municípios de MT, PR, RJ, RS, SP e
    TO. Os arquivos nacionais do BWEB trazem só o segundo turno presidencial, então
    essas disputas não têm contraparte no BWEB e ficam sem verificação contra ele.
  - ZZ 29564/0091 (dois turnos) e 30686/0443 (segundo turno): seções SA com
    comparecimento zero. O BWEB omite a seção (primeiro turno) ou grava uma linha de
    marcação com cargo `-1` (segundo turno), então a disputa presidencial vazia do BU
    fica `bu_only` e a linha de marcação, `bweb_only`.
  - 30 e 29 linhas `section_fields`: o local de votação de todo pacote SA. O BU do SA
    registra o local `0001`; o BWEB registra o local da própria seção.
- I4: toda medida de voto (candidatos, brancos, nulos, nulos técnicos) e toda contagem
  de seções, salvo as duas abaixo, são iguais ao EA20 nos 5757 municípios, nos 28 nós
  de UF e no nó nacional. O eleitorado difere em 41 e 42 municípios do ZZ, todos sem
  linha presidencial no BWEB: 40 cidades no exterior com eleitores mas sem seção
  instalada, mais as seções SA com comparecimento zero acima (uma no primeiro turno,
  duas no segundo), que o EA20 conta como instaladas.
- I5: as 85 e 36 diferenças estão em aberto. Em 7 e 3, os logs têm mais ciclos
  concluídos que o comparecimento do BU, todas com várias sessões (uma seção do ES no
  segundo turno tem 612 = 2 × 306), o que aponta para sessões reexecutadas somadas
  duas vezes. Em 78 e 33 têm menos, 51 e 17 delas numa única sessão; ciclos não
  resolvidos explicam só 4 e 2. Agrupar sessões de várias execuções é trabalho da
  Fase 22.
- I6 (segundo turno): 493122 seções são iguais em todo bloco fechado do primeiro
  turno, com o último bloco aberto. Outras 3645 são iguais, exceto por terem também
  blocos do primeiro turno ausentes do log do primeiro turno (3553 com o bloco aberto,
  92 sem);
  1464 não têm bloco do primeiro turno; 162 são de outra urna; 99 têm ao menos um bloco
  fechado do primeiro turno que difere; 2 não têm log do primeiro turno (as seções SA
  de MG). O restante são combinações pequenas listadas no manifesto.
- I7: R1 (nenhuma sessão oficial do turno) falha em 1636 e 1449 seções, R2 (última
  sessão sem leitura de encerramento) em 438 e 349, R3 (recuo do relógio) em 34 e 9,
  R6 (sessões sobrepostas) em 31 e 9, R4 em 1 e 0; R5 nunca falha.
- I9: os arquivos de correspondência listam 3060 e 2721 seções cuja urna efetivada não
  é a esperada; em toda seção a urna efetivada é igual à urna, ao código de carga, ao
  cartão de memória e ao horário de carga do BU.
- Logs SA, ausentes e protegidos: 627 e 626 seções ficam `protected_or_unavailable` para
  I5–I7.

## Fase 20b: assinaturas e certificados

Execuções de 6 de novembro de 2026 em
`~/data/election-audit-stage/phase20/national-r{1,2}-sections-v3-20261106/`:

```sh
just integrity-check sections \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --round 1 --output ~/data/election-audit-stage/phase20/national-r1-sections-v3-20261106 \
  --workers 6
```

| Verificação | 1º turno | 2º turno |
| --- | --- | --- |
| Autoassinatura de hardware verificada | 499207 de 499207 | 499207 de 499207 |
| Seções ECDSA (UE2013/UE2015) | 99985 | 99957 |
| Seções Ed521 (UE2020/UE2022) | 399222 | 399250 |
| Assinaturas de arquivos verificadas | 1996828, 0 com falha | 1996828, 0 com falha |
| Assinaturas da cadeia do BU verificadas | 997114, 0 com falha | 539817, 0 com falha |
| Certificado da urna assinado pela sua AC | 499207 | 499207 |
| Número de série do certificado revogado | 0 | 0 |
| Veredictos Ed521 diferentes dos do ECPy | 0 | 0 |

- Todo certificado de urna era válido no dia da eleição. O da `AC URNA` (99985 e
  99957 seções) não era: o certificado publicado venceu em 2026-07-18
  ([T2](observations.md#transparência)).
- Em 14 e 3 seções o arquivo de assinatura foi assinado por outra urna que não a do
  BU; toda assinatura nelas confere com o certificado válido e não revogado dessa urna
  ([O13](observations.md#operação)). Elas respondem por seis das oito divergências de
  modelo relatadas pelo I9 na Fase 20.
- A mesma passada rodou antes com o verificador em Python puro
  (`integrity-sections-v2`, em `national-r{1,2}-sections-v2-20261106`). As execuções
  com o `ed521rs` são iguais a ela linha a linha nas tabelas de seções, disputas e
  restrita dos dois turnos.

| Execução | Verificador Ed521 | Tempo decorrido | Tempo de CPU | Memória máxima |
| --- | --- | --- | --- | --- |
| 1º turno, v2 | `election_audit/ed521.py` | 2:57:15 | 65017 s | 4.8 GB |
| 2º turno, v2 | `election_audit/ed521.py` | 2:21:17 | 50280 s | 4.1 GB |
| 1º turno, v3 | `ed521rs` 0.1.0 | 1:07:49 | 10210 s | 4.9 GB |
| 2º turno, v3 | `ed521rs` 0.1.0 | 1:00:38 | 5411 s | 4.2 GB |

Todas as execuções usaram seis processos. As execuções v3 usaram uma wheel local do
`ed521rs` gerada do commit anterior à tag `v0.1.0`, com o mesmo código de verificação;
as execuções do AC com a wheel do PyPI são iguais a elas linha a linha. O manifesto
registra a versão, o backend SIMD e o SHA-256 do módulo nativo.

## Limites

- As cadeias de certificados são verificadas só até as ACs intermediárias; os
  certificados raiz e da `AC URNA v2` não são públicos.
- O I6 não verifica o último bloco aberto; uma comparação por prefixo exige reler os
  logs não protegidos.
- O I8 não tem fonte.
- As dez eleições municipais realizadas com o segundo turno não estão no BWEB nacional,
  então o I2 não as cobre.
- I5 e I6 têm diferenças em aberto (85/36 e 99 seções) que exigem o agrupamento de
  sessões da Fase 22 ou uma releitura bruta.
- A concordância entre artefatos da mesma cadeia de software mostra consistência, não
  a intenção do eleitor.
