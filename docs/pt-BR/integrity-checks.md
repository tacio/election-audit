# Verificações de integridade de nível 1 (Fase 20)

Document-ID: EA-INTEGRITY-CHECKS · Revision: 6 · Language: pt-BR

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
biométricos às habilitações biométricas do BU. Desde o `integrity-logs-v2`, uma sessão
copiada em várias memórias de uma urna conta uma vez, pela linhagem do bloco, como na
tabela por seção.

**I6, blocos do primeiro turno.** Todo bloco do primeiro turno de um log do segundo
turno precisa ser igual ao bloco que começa com a mesma linha, na mesma urna, no log
do primeiro turno. O último bloco do primeiro turno continua no log do segundo turno
depois de o log do primeiro turno ter sido gravado, então só pode coincidir como
prefixo; a Fase 21 guardou impressões digitais de segmentos inteiros, então esse
bloco aparece como `open_prefix_unverified`.

**I7, regras de relógio e sessão** (`integrity-logs-v1`, `integrity-logs-v2`): R1 ao menos uma sessão
oficial do turno; R2 a última tem leitura de encerramento; R3 nenhum recuo do relógio
dentro das sessões oficiais; R4 nenhuma conclusão fora de um ciclo; R5 toda sessão
oficial começa na data da eleição; R6 as sessões oficiais não se sobrepõem.

**I8, BUs impressos** (`printed-bu-v1`): cópias do BU lidas dos QR codes do papel
impresso na seção, reunidas por terceiros, contra o BU publicado da mesma seção. Ver
[Fase 20b: BUs impressos do I8](#fase-20b-bus-impressos-do-i8).

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
  São os únicos dois pacotes SA fora do ZZ; os outros 29 recontam exatamente. A Fase
  20b achou a causa: os RDVs deles têm dois blocos por disputa (20 cédulas, depois 261
  e 258), e o `integrity-sections-v3` ficou só com o último. O
  `integrity-sections-v4` soma os blocos ([O5](observations.md#operação)).
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
  Fase 22. A Fase 20b as reconciliou: veja
  [regras de sessão v2 e a reconciliação do I3/I5](#fase-20b-regras-de-sessão-v2-e-a-reconciliação-do-i3i5).
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

## Fase 20b: releitura por prefixo do I6

`integrity-check prefix` (`integrity-round1-prefix-v1`, módulo `round1_prefix`)
substitui a comparação do I6 só por impressão digital em todo par de blocos do 1º
turno de comprimentos diferentes. Ele relê, da cópia certificada, só objetos que as
versões da Fase 21 já leram, de modo que os logs protegidos/de estresse continuam sem
leitura, e confere o SHA-256 certificado de cada objeto. Fluxos e segmentos são
reconstruídos a partir das contagens de linhas registradas na Fase 21; um segmento
reconstruído só é usado se reproduzir a impressão digital e o hash da primeira linha
registrados; caso contrário o par fica `realignment_failed`. Em seguida, as primeiras
N linhas do bloco mais longo são resumidas e comparadas com a impressão digital do
bloco mais curto. Os pares que ainda diferem são lidos dos dois lados e descritos
pelo prefixo comum, pelas linhas do 1º turno reencontradas depois e por até dez
modelos de mensagem das linhas diferentes, com dígitos mascarados, em
`differences.jsonl`. A versão também traz `pairs.parquet` (uma linha por par de
blocos do 1º turno de conteúdo diferente) e `sections.parquet`, que mantém a situação
do `integrity-logs-v1` como `i6_v1` ao lado do `i6` revisto e conta os blocos por
estado.

Execução de 7 de novembro de 2026:

```sh
just integrity-check prefix \
  --logs ~/data/election-audit-stage/phase20/national-r2-logs-v1-20261105 \
  --semantic ~/data/election-audit-stage/phase21/national-r2-20261103 \
  --semantic-round1 ~/data/election-audit-stage/phase21/national-r1-20261103 \
  --output ~/data/election-audit-stage/phase20b-i6/national-v1-20261107 --workers 6
```

| Pares de blocos do 1º turno | Pares | Situação |
| --- | --- | --- |
| Último bloco do 1º turno, segundo turno mais longo, primeiras N linhas iguais | 496793 | `prefix_open` |
| Último bloco do 1º turno, ainda difere | 3 | `differs` |
| Bloco do 1º turno fechado, segundo turno mais curto e prefixo dele | 6 | `runoff_prefix_of_round1` |
| Bloco do 1º turno fechado, ainda difere | 110 | `differs` |

Nenhum objeto falhou e nenhum segmento deixou de ser reconstruído. Todo último bloco
aberto do log do 1º turno é prefixo exato da sua cópia no segundo turno: 493125
seções agora são `equal_open_prefix_equal`, onde o `integrity-logs-v1` deixou 493122
como `equal_closed_open_prefix_unverified` e 3 como `open_prefix_unverified`.

Os 113 pares que ainda diferem foram lidos linha a linha:

- 97 são as mesmas linhas com limites de bloco diferentes. O bloco do segundo turno é
  uma subsequência em ordem do fluxo do log do 1º turno que pula só linhas escritas
  quando a urna reinicia, antes de `Iniciando registro do log na MI e na ME` (95
  pulam exatamente seis: `Início das operações do logd`, `Urna ligada em …`,
  `Estrutura de diretórios da ME: OK`, `Iniciando aplicação - #º turno`, a versão do
  software e o modelo da urna). Sem a linha de mudança de contexto o bloco não fecha e
  segue pelas linhas de inicialização ([O14](observations.md#operação)).
- 15 estão em seções cujos logs trazem várias memórias de uma urna (membros MI e ME,
  membros `-01` de contingência). Em 12, toda linha do segundo turno está no log do 1º
  turno em outro fluxo; em 3, o log do 1º turno traz a cópia da memória externa e não
  tem as mesmas três linhas de reinício.
- 1, rj/60011/0008/0061, é uma divergência real entre cópias do dia de eleição de uma
  urna ([O15](observations.md#operação)). O log publicado do 1º turno tem 311 votos
  computados, igual ao comparecimento do BU; a cópia da memória externa levada no log
  do segundo turno tem 305, termina mais tarde e tem bytes corrompidos; a cópia da
  memória interna tem 303. O fluxo do log do 1º turno é quebrado por uma linha cujo
  identificador de urna difere em dois dígitos, por isso a Fase 21 contou só uma
  sessão de 36 votos e o I5 apontou esta seção.

Dos 7079 blocos do 1º turno presentes só no log do segundo turno, 5809 começam depois
da última linha do log do 1º turno na mesma urna e 1269 estão em urnas sem bloco do 1º
turno no log do 1º turno (em geral memórias de outras urnas levadas em objetos com
vários membros); um não tem explicação. 1464 seções não têm bloco do 1º turno no log do
segundo turno, 162 têm outra urna e 2 não têm log do 1º turno, como antes.

| Execução | Objetos lidos | Tempo de relógio | Tempo de CPU | Memória máxima |
| --- | --- | --- | --- | --- |
| 2º turno, prefixo v1 | 496793 | 1:19:42 | 26699 s | 3.6 GB |

Seis processos; o pico é o processo de planejamento, que mantém os pares de blocos no
DuckDB e no Python. A versão tem 36 MB e os fragmentos por lote 198 MB.

## Fase 20b: regras de sessão v2 e a reconciliação do I3/I5

Execuções de 7–8 de novembro de 2026. O `integrity-sections-v4` soma os blocos do
RDV de uma disputa ([O5](observations.md#operação)): o I3 agora é igual em todas as
2490805 e 539817 disputas. O release difere do v3 só nas linhas das duas seções SA de MG (suas
10 disputas); o 2º turno é idêntico. A passagem
semântica foi refeita com as regras de sessão `sessions-v2`
(`session-aggregates-v4`, [passada semântica](semantic-pass.md#versão-4-fase-20b)).
O I5–I7 rodou então duas vezes: sobre as novas passadas (`logs-v2`, código
`integrity-logs-v1`) e com as cópias de memória de uma sessão contadas uma vez
(`logs-v3`, código `integrity-logs-v2`, [O16](observations.md#operação)). As raízes
finais são `~/data/election-audit-stage/phase20/national-r{1,2}-logs-v3-20261108/`.

```sh
just integrity-check logs \
  --sections ~/data/election-audit-stage/phase20/national-r2-sections-v4-20261107 \
  --semantic ~/data/election-audit-stage/phase20b-sessions/v4-national-r2-20261107 \
  --semantic-round1 ~/data/election-audit-stage/phase20b-sessions/v4-national-r1-20261107 \
  --output ~/data/election-audit-stage/phase20/national-r2-logs-v3-20261108
```

| Verificação | Fase 20, 1º turno | Fase 20b, 1º turno | Fase 20, 2º turno | Fase 20b, 2º turno |
| --- | --- | --- | --- | --- |
| I3 recontagem do RDV igual | 2490795 de 2490805 | 2490805 de 2490805 | 539817 de 539817 | 539817 de 539817 |
| I5 iguais / diferem / indisponíveis | 496859 / 85 / 2263 | 498558 / 10 / 639 | 497096 / 36 / 2075 | 498570 / 7 / 630 |
| I5 biométrico iguais / diferem | — | 497277 / 10 | — | 497290 / 6 |
| I7 R1 (nenhuma sessão oficial) | 1636 | 12 | 1449 | 4 |
| I7 R2 (sem leitura de encerramento) | 438 | 434 | 349 | 347 |
| I7 R3 (passo de relógio para trás) | 34 | 34 | 9 | 9 |
| I7 R5 (sessão iniciada antes do dia da eleição) | 0 | 1569 | 0 | 1361 |
| I7 R6 (sessões sobrepostas) | 31 | 24 | 9 | 7 |

O R4 falha numa seção do 1º turno nas duas execuções. As seções indisponíveis são as
627 e 626 sem log na passada semântica mais as que não têm sessão oficial. O R1 cai
e o R5 sobe pelo mesmo motivo: uma urna ligada antes do dia da eleição e deixada
ligada agora tem sessão oficial, marcada `started_before_election_day`. O R5 falha
exatamente nas seções que têm uma sessão assim, uma por objeto.

Das 85 e 36 diferenças da Fase 20, as regras `sessions-v2` resolvem 69 e 27
(reinícios no meio do dia que perdiam os votos seguintes, urnas deixadas ligadas
durante a noite), e contar uma vez as cópias de memória resolve mais 6 e 2. Nenhuma
seção difere sem ter diferido na Fase 20. Cada uma das 17 restantes foi lida sessão
a sessão:

| Causa | 1º turno | 2º turno |
| --- | --- | --- |
| Log abaixo por no máximo seus ciclos não resolvidos (1 ou 2) | 7 | 3 |
| Log um ciclo abaixo além do seu ciclo não resolvido | 0 | 1 (rs/89060/0017/0191) |
| Pacote traz a urna de outra seção ([O13](observations.md#operação)) | 0 | 1 (es/57932/0009/0085) |
| Fluxo quebrado ([O15](observations.md#operação)) | 1 (rj/60011/0008/0061) | 0 |
| Log cobre só parte do dia de eleição ([O17](observations.md#operação)) | 2 | 2 |

As sete seções do 1º turno abaixo por seus ciclos não resolvidos são
es/56995/0053/0211, rj/58971/0087/0184, rn/16039/0029/0028, rs/89036/0083/0044,
sp/64254/0291/0346, sp/71072/0260/0037 e sp/63614/0227/0305; as três do 2º turno são
ba/34711/0021/0178, pb/21750/0002/0254 e pi/11533/0003/0216. Em nenhuma seção
restante o log tem mais ciclos concluídos que o comparecimento do BU, salvo
es/57932/0009/0085, cujo pacote traz duas urnas. Nenhuma das 17 tem cópia impressa
do BU (I8).

**DataUrnas-BR.** Sua tabela de log por seção do 1º turno (commit `f5e8005`,
congelada em `inputs/dataurnas-br-f5e8005-20261108/`) cobre as 499207 seções e marca
40 cujos votos no log diferem do comparecimento: 31 seções SA, que não têm log de
urna, e 9 outras. Essas 9 são as nossas seções do 1º turno exceto rj/60011/0008/0061,
com a mesma contagem de log em cada uma. Em rj/60011/0008/0061 ele conta 311, igual
ao comparecimento, porque não divide o fluxo pelo identificador da urna
([O15](observations.md#operação)). Nas seções em que contávamos as cópias de memória
duas vezes, sua contagem é igual ao comparecimento (rs/89036/0083/0044: um abaixo,
como a nossa agora): ele conta uma vez as linhas idênticas repetidas entre os
arquivos de um pacote. Sua tabela de seções do 2º turno não tem contagens de log,
então o 2º turno não foi comparado. Sua recontagem do RDV não relata divergência em
nenhum turno, o que concorda com o I3 v4. Só essas seções e as contagens nacionais do
DataUrnas-BR foram lidas.

**Nova execução do I6.** O `integrity-check prefix` rodou de novo sobre o `logs-v2` e
as passadas v4 em `~/data/election-audit-stage/phase20b-i6/national-v2-20261107/`
(mesmo código, `integrity-round1-prefix-v1`). Os novos limites de bloco mudam os
pares: 497032 pares de blocos, 496999 objetos lidos, nenhum erro de objeto ou de
reconstrução.

| Pares de blocos do 1º turno | v1 | v2 |
| --- | --- | --- |
| Último bloco do 1º turno, segundo turno mais longo, primeiras N linhas iguais (`prefix_open`) | 496793 | 496911 |
| Bloco do segundo turno é prefixo do bloco do 1º turno (`runoff_prefix_of_round1`) | 6 | 6 |
| Ainda difere, bloco fechado | 110 | 110 |
| Ainda difere, último bloco | 3 | 5 |

Os 115 pares que ainda diferem estão em 101 seções. 110 diferem só por linhas de
reinício ([O14](observations.md#operação)): em 99 a cópia do segundo turno não as
tem, em 11 é a cópia do 1º turno. 4 são as duas cópias de memória de
mg/44458/0103/0221 ([O16](observations.md#operação)) pareadas entre si, que terminam
em linhas diferentes. O último é rj/60011/0008/0061 ([O15](observations.md#operação)).
493160 seções agora são `equal_open_prefix_equal` (493125 no v1). Os blocos presentes
só no log do segundo turno (7079, dos quais 5809 começam depois do fim do log do 1º
turno), as 1464 seções sem bloco do 1º turno, as 162 com outra urna e as 2 sem log do
1º turno não mudam.

| Execução | Tempo de relógio | Tempo de CPU | Memória de pico | Release |
| --- | --- | --- | --- | --- |
| Seções v4, 1º turno (6 workers) | 1:10:48 | 10838 s | 4,7 GB | 266 MB |
| Seções v4, 2º turno (6 workers) | 1:02:15 | 5650 s | 4,1 GB | 118 MB |
| Logs v2, 1º turno / 2º turno | 0:27 / 0:51 | — | 2,7 / 3,2 GB | 1 / 2 MB |
| Logs v3, 1º turno / 2º turno | 0:22 / 0:41 | — | 2,6 / 3,3 GB | 1 / 2 MB |
| Prefixo v2 (6 workers) | 1:08:02 | 22707 s | 3,6 GB | 36 MB (+199 MB de shards) |

As execuções de logs são um processo; o pico é a tabela de sessões mantida no DuckDB e
no Python.

## Fase 20b: BUs impressos do I8

`integrity-check printed` (`printed-bu-v1`, módulo `printed_bu`) segue o manual de
2026 do TSE sobre os QR codes do BU (formato VRQR 6.0). Cada código `QRBU` traz uma
fatia do conteúdo do BU e `HASH`, o SHA-512 de tudo o que vem antes; o último código
acrescenta `ASSI`, a assinatura da urna sobre o SHA-512 do hash final (Ed521 nas
UE2020/UE2022, ECDSA P-521 nas UE2013/UE2015), e dois códigos `QRCE` trazem o
certificado da urna. Para cada cópia reunida, a passada recalcula a cadeia de hashes,
verifica a assinatura e a autoridade emissora do TSE do certificado (como na Fase 20b
acima) e compara cada campo impresso com o BU binário publicado para a seção:
cabeçalho (número da urna, código e histórico de carga, versão do software, local de
votação, eleitores, comparecimento, contagens de habilitação, horários de abertura e
encerramento) e, por eleição e cargo, cada contagem de candidato, partido, brancos e
nulos e os eleitores aptos. Também compara o certificado do QR com o certificado de
hardware do arquivo de assinatura da seção e confere os totais impressos contra as
contagens que somam. Campos impressos sem campo no BU (`AGRE`, `ORLC`, `PROC`, `DTPL`,
`VERC`) não são comparados; qualquer item não reconhecido é registrado.

Entradas, congeladas em 7 de novembro de 2026 em `~/data/election-audit-stage/inputs/`:

- `i8-cmind-20261107`: os 120 BUs da Totalização Paralela do CMInd, da sua API
  pública (`/api/public-bu`, o endpoint que o site chama sem login), com o texto bruto
  dos QR codes, baixados um a um com pausa de 3 segundos, com `SHA256SUMS`.
- `i8-arvor-20261107`: a Totalização paralela da Arvor como publicada em
  `ArvorCo/PNAD` no commit `570e7a2`, conferida contra o próprio manifesto: 408 BUs do
  segundo turno com o conteúdo remontado, hash final, assinatura e certificado. As
  fatias por código não são publicadas; a passada as recupera achando os pontos de
  corte cuja cadeia dá o hash final (toda cópia coube em um código).
- `i8-tse-qrbu-20261107`: o manual de QR do TSE (SHA-256 `ffded730…`) e os BUs de
  exemplo (`8b1e28fd…`). O TSE recusa requisições automatizadas, então os hashes foram
  calculados num navegador no site do TSE e os bytes tirados das cópias da Arvor, que
  coincidem.

A Arvor declara um lado político; o CMInd se apresenta como fiscalização cidadã.
Nenhuma das seleções é aleatória, e ambas dependem de quem decidiu escanear.

```sh
just integrity-check printed \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot \
  --cmind ~/data/election-audit-stage/inputs/i8-cmind-20261107 \
  --arvor ~/data/election-audit-stage/inputs/i8-arvor-20261107 \
  --output ~/data/election-audit-stage/phase20b-i8/v1-20261107
```

| Coleção | Turno | Cópias | Iguais |
| --- | --- | --- | --- |
| CMInd | 1 | 49 | 49 |
| CMInd | 2 | 71 | 71 |
| Arvor | 2 | 408 | 408 |

As 528 cópias têm cadeia íntegra, assinatura da urna verificada (Ed521 em 382, ECDSA
P-521 em 146) e certificado assinado pela autoridade do TSE, não revogado; cada
certificado é igual ao do arquivo de assinatura publicado da seção. Todo campo
impresso é igual ao BU publicado (739 disputas), e nenhum total impresso discorda das
suas contagens. As cópias cobrem 518 seções: 49 no 1º turno (4 UFs, 7 municípios) e
469 no segundo turno (21 UFs e exterior, 78 municípios); 10 seções têm cópia nas duas
coleções, com o mesmo hash final. Nenhuma das seções restantes do I5 tem cópia.

| Execução | Cópias | Tempo de relógio | Memória de pico |
| --- | --- | --- | --- |
| I8 v1 | 528 | 0:22 | 0,56 GB |

Um processo; a leitura dos diretórios centrais dos arquivos em lote domina (um
arquivo aberto por vez). O release (`printed.parquet` e seu manifesto) tem 140 kB.

## Limites

- As cadeias de certificados são verificadas só até as ACs intermediárias; os
  certificados raiz e da `AC URNA v2` não são públicos.
- O I6 cobre só os logs não protegidos; os 596 logs protegidos/de estresse são lidos
  depois do congelamento da Fase 23. Um bloco do 1º turno presente só no log do
  segundo turno não tem explicação.
- O I8 cobre 518 seções escolhidas por quem as escaneou, não uma amostra; não diz
  nada sobre outras seções.
- As dez eleições municipais realizadas com o segundo turno não estão no BWEB nacional,
  então o I2 não as cobre.
- O I5 difere em 10 e 7 seções. Todas menos uma têm causa conhecida (ciclos não
  resolvidos, a urna de outra seção, um fluxo quebrado, um log que cobre parte do
  dia); rs/89060/0017/0191 fica um ciclo abaixo além do seu ciclo não resolvido.
  Quatro logs cobrem só parte do dia de eleição (O17), então suas medidas são
  parciais.
- A concordância entre artefatos da mesma cadeia de software mostra consistência, não
  a intenção do eleitor.
