# Tabela de atributos por seção v5.1 (Fases 22 e 20b)

Document-ID: EA-SECTION-TABLE · Revision: 6 · Language: pt-BR

[English](../en/section-table.md) · [Índice de implementação](implementation-index.md)

`section-table build` grava, para um ano eleitoral, uma linha por seção principal e
turno. Cada linha traz composição, local de votação, covariáveis do perfil do
eleitorado, modelo e software da urna, regra de relógio, situação de integridade e
medidas operacionais. A tabela também define um mapeamento entre turnos em unidades
harmonizadas e um registro da população. Ela é a entrada dos modelos de nível 2
([protocolo do estudo](../../research/analysis-plan.pt-BR.md#7-nível-2-análise-estatística)).
Nada é imputado: um valor ausente, conflitante ou não resolvido fica nulo, e cada
família de medidas tem um estado de disponibilidade com motivo.

## Acesso aos dados

Resultados e medidas operacionais são gravados só em `restricted/`. Antes do
congelamento da Fase 23, o código os lê e as pessoas não, exceto nas UFs de
desenvolvimento
([protocolo do estudo, seção 2](../../research/analysis-plan.pt-BR.md#2-o-que-já-foi-visto)).
A parte pública (`sections.parquet`, `units.parquet`, `ledger.json`) traz chaves,
covariáveis, campos de urna, relógio e disponibilidade, e contagens.

## Entradas

| Entrada | Origem | Uso |
| --- | --- | --- |
| BWEB, linhas de presidente, dois turnos | Fase 19 `resultados-<year>-boletim-de-urna` | Resultados, composição (seções agregadas), metadados do BU |
| Perfil do eleitorado por seção, locais de votação | Fase 19 `eleitorado-<year>` | Covariáveis, chaves de local, coordenadas |
| Passagem semântica `session-aggregates-v4`, dois turnos | `semantic-pass run` | Medidas operacionais, modelo, software, evidência de relógio |
| Releases da Fase 20 (só 2026) | `integrity-check` | Situação I1–I9, modelo e software do lado do BU |
| Exclusões de proteção (2026) | `data/national/phase11-protection-2026-10-31/exclusions.json` | As 596 seções protegidas ficam `outside_scope` |

A versão 4 da tabela (`section-features-v4`, `session-aggregates-v4`) lê a passada
semântica com as regras de sessão `sessions-v2`; suas regras não mudam.
`session-aggregates-v3` acrescentou nove colunas por sessão e não mudou mais nada.
No país todo, nos dois anos e turnos, toda coluna em comum com a versão anterior é
igual em cada linha de sessão, segmento e objeto
([passada semântica](semantic-pass.md#versão-3-fase-22)). As colunas novas:

- `model`: de `Identificação do Modelo de Urna: UE####` no mesmo fluxo.
- `software_version`: de `Versão da aplicação: …`, lida na sessão VOTA.
- Evidência de relógio registrada antes da sessão, acumulada por fluxo:
  - ajustes de relógio feitos pelo operador no aplicativo ADH (`clock_adh_before`,
    mais o deslocamento digitado, `clock_adh_shift_s_before`);
  - ajustes de fuso horário (`clock_tz_shifts_before`, `clock_tz_shift_s_before`);
  - ajustes de horário de verão (`clock_dst_before`).
- `configured_close`: o horário de encerramento que a urna imprime quando alguém
  tenta encerrar antes da hora.
- `segment_ordinal`: liga a sessão ao seu segmento de contexto.

## Regras

**População.** As seções de um turno são a união de quatro fontes:

- as seções principais do BWEB;
- as seções principais dos locais de votação;
- as seções citadas por um log;
- em 2026, as seções das releases da Fase 20.

Os membros de uma seção são a principal e as seções agregadas que o BWEB lista.
Composições que não podem ser lidas são contadas no manifesto.

**Cópias de uma mesma sessão.** O pacote de uma urna pode trazer o mesmo log duas
vezes, da memória interna (`…MI.jez`) e da memória externa (`…ME.jez`); isso
acontece quando a urna foi substituída. Cópias são reconhecidas pela linhagem de
blocos, nunca pelo texto da mensagem ou pelo horário. Duas sessões oficiais de uma
seção são cópias quando três coisas coincidem:

- o dispositivo;
- o início do bloco, isto é, o hash da primeira linha do segmento do turno oficial;
- a posição da sessão dentro desse bloco.

Fica a cópia com o bloco mais longo. Se uma cópia mais curta tiver mais votos
concluídos, há conflito, e as medidas operacionais da seção ficam `unavailable`
(`conflict`). Sessões sem ligação a um segmento nunca são unidas. A igualdade das
cópias como prefixos é verificada na Fase 20b.

**Urna.** Em 2026 o modelo vem do arquivo de assinatura da urna (`equipment` da Fase
20) e é comparado com o modelo da última sessão oficial da seção, a urna que emitiu
o BU. Em 2022 o modelo vem só dos logs. Seções cuja urna foi substituída guardam
todos os modelos em `log_models_json`.

**Horário de encerramento.** Os relógios das urnas marcam a hora local. A votação
termina às 17:00 de Brasília no Brasil e às 17:00 locais no exterior. O horário de
encerramento esperado no relógio da urna vem dos fusos legais (Decreto 2.784/1913,
art. 2º, com a redação da Lei 12.876/2013):

| Regra | Onde | Leitura de encerramento |
| --- | --- | --- |
| `law_uf` | UFs com um só fuso (AC −2 h; MT, MS, RO, RR −1 h; as demais 0 h) | 15:00, 16:00 ou 17:00 |
| `law_noronha` | Fernando de Noronha (PE) | 18:00 |
| `abroad` | ZZ | 17:00 |
| `am_configured` | Amazonas, dividido por uma linha, e não por município | O encerramento configurado impresso pelas urnas do município, quando todas as observações do ano concordam com a lista abaixo |
| `am_list` | Municípios do Amazonas cujas urnas não imprimiram encerramento configurado | 15:00 para os onze municípios no horário do Acre, 16:00 para os demais |
| `unresolved` | Municípios do Amazonas cujos encerramentos impressos divergem entre si ou da lista | Indisponível |

Os onze municípios do Amazonas no horário do Acre (UTC−5) estão fixados em
`resources/am-acre-time-municipalities.json` com suas fontes: avisos do TRE-AM de
2024 e 2026, os arquivos de locais de votação do TSE e as impressões das próprias
urnas ([observação O12](observations.md#operação)). O TSE não publica conjunto de
dados com os fusos dos municípios ([T10](observations.md#transparência)).

**Estado do relógio.** A primeira condição atendida decide o estado. Medidas de
horário exigem `ok` ou `adjusted`.

| Estado | Significado |
| --- | --- |
| `no_sessions` | Nenhuma sessão oficial |
| `no_close_rule` | Nenhuma regra de encerramento se aplica |
| `off_election_date` | Uma sessão começa em outra data |
| `backstep` | O relógio volta dentro de uma sessão |
| `overlap` | Duas sessões se sobrepõem |
| `close_conflict` | Um encerramento configurado difere da regra |
| `adjusted` | Ajuste do operador, de fuso ou de horário de verão antes da sessão |
| `ok` | Nenhum dos anteriores |

**Prontidão dos resultados.** Os resultados de uma seção só ficam `ready` quando o BWEB
informa seu eleitorado, seu comparecimento e suas abstenções, e duas equações valem:
eleitorado = comparecimento + abstenções, e votos nominais + brancos + nulos + outros =
comparecimento. Linhas que não são lidas, contagens negativas e linhas repetidas do BWEB
deixam os resultados `unavailable` (`conflict` ou `unreconciled`). O BWEB lista só as
categorias que têm votos, então uma categoria de brancos, nulos ou outros sem linha é
nula. Ela conta como zero apenas porque a equação então vale com ela zerada. Uma seção
cujas categorias não somam o comparecimento continua `unreconciled`, e o total nominal
nunca recebe valor padrão (`reconciled`, xr1-20261109-P5-01).

**Medidas** (`restricted/sections.parquet`):

- ciclos concluídos, suspensos, cancelados e não resolvidos, por forma de
  habilitação;
- votos concluídos sem biometria;
- votos concluídos por hora de leitura, e votos concluídos no horário de
  encerramento esperado ou depois (por hora cheia);
- segundos ativos (do primeiro ao último voto concluído, por sessão);
- o maior intervalo;
- pedidos manuais e votos concluídos sem ciclo.

As medidas operacionais ficam `partial` quando há ciclos não resolvidos ou votos
concluídos sem ciclo.

**Mapeamento entre turnos.** Uma unidade harmonizada é um componente conexo de
seções cadastradas ligadas à sua principal em qualquer dos turnos. Assim, seções
agregadas de forma diferente nos dois turnos são comparadas como um todo e nunca se
misturam com outros eleitores. Tipos de unidade:

| Tipo | Significado |
| --- | --- |
| `same_principal` | A mesma principal nos dois turnos |
| `recombined` | A composição mudou entre os turnos |
| `one_round_only` | Presente em só um turno |

Uma unidade é `comparable` quando toda principal, nos dois turnos, tem resultados
prontos. `restricted/unit_votes.parquet` soma os votos por número votável, por
unidade e turno.

## Comando

```sh
just section-table build --year 2026 \
  --bweb-root $EA_STAGE/inputs/resultados-2026-boletim-de-urna \
  --electorate-root $EA_STAGE/inputs/eleitorado-2026 \
  --semantic-r1 $EA_STAGE/phase20b-sessions/v4-national-r1-20261107 \
  --semantic-r2 $EA_STAGE/phase20b-sessions/v4-national-r2-20261107 \
  --integrity-r1 "$(cat $EA_STAGE/phase20b-sessions/integrity-v4c-r1.json)" \
  --integrity-r2 "$(cat $EA_STAGE/phase20b-sessions/integrity-v4c-r2.json)" \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --output $EA_STAGE/phase20b-sessions/table-2026-v4-20261108c
```

`--integrity-r1`/`--integrity-r2` recebem um objeto JSON com as raízes da Fase 20 do
turno (`sections`, `logs`, `bweb`, `correspondence`). Para 2022, omita as opções de
integridade e de exclusão. A construção roda em um só processo com duas threads do
DuckDB e `--memory-limit` (1 GB por padrão). Ela guarda linhas em Python para um
bloco por vez: municípios inteiros de uma UF, cerca de 10000 seções, porque regras
de encerramento e unidades nunca cruzam um município. No país todo, a versão 3 levou 47 e 78 minutos (2026, 2022), com pico de 3.7 e 3.0 GB;
a versão 4 levou 45 e 42 minutos, com pico de 3,7 e 3,1 GB, e cada release tem cerca
de 190 MB. Uma primeira construção de 2026 sobre os logs v2 da Fase 20b
(`table-2026-v4-20261108b/`, 49 minutos) difere da final só no I5 e no I7 das 8 e 9
seções cujas cópias de memória eram contadas duas vezes.
Testes de unidade:
`tests/test_section_table.py`.

## Resultados de desenvolvimento

AC em 5 de novembro de 2026 (só contagens):

| | 2026 1º t. | 2026 2º t. | 2022 1º t. | 2022 2º t. |
| --- | --- | --- | --- | --- |
| Seções | 2270 | 2270 | 2124 | 2124 |
| Resultados prontos | 2270 | 2270 | 2124 | 2124 |
| Perfil pronto | 2270 | 2270 | 2124 | 2124 |
| Protegidas (logs não lidos) | 596 | 596 | 0 | 0 |
| Operações prontas / parciais | 1202 / 465 | 1317 / 346 | 1200 / 915 | 1401 / 718 |
| Relógio `ok` / `adjusted` | 1666 / 1 | 1662 / 1 | 2115 / 0 | 2118 / 1 |

Todas as unidades do AC são `same_principal` e comparáveis nos dois anos. Toda urna
do AC que imprimiu um encerramento configurado imprimiu 15:00 (52 sessões no 2º
turno de 2026, 30 no 2º turno de 2022), o que confirma que os relógios das urnas
marcam a hora local.

## Resultados nacionais

Versão 5.1 (`section-features-v5.1`), construída em 11 de novembro de 2026 em
`$EA_STAGE/phase20b-sessions/table-2026-v51-20261111/` e `table-2022-v51-20261111/`,
sobre as mesmas entradas da versão intermediária 5 (as passagens semânticas
`v4-national-*` de 7 de novembro, as seções de integridade v6 e os logs v5). A versão 5
(`table-2026-v5-20261110/`, `table-2022-v5-20261110/`) aplicou a regra de resultados
acima, mas leu uma categoria de brancos ou nulos sem linha como não conciliada. Ela
marcou 93278 seções de 2026 e 71143 de 2022 como `unavailable` (`unreconciled`), 9,3%
e 7,5% das seções. Em todas as UFs de desenvolvimento (AC, AL, DF, ES, PR) as falhas
eram uma categoria sem linha no BWEB cujas outras contagens somam exatamente o
comparecimento, e a versão 5.1 restaura todas as 93278 seções de 2026 e 71138 de 2022.
Cinco seções de 2022 (quatro no turno 1, uma no turno 2) continuam `unreconciled`. A
versão 5 está substituída; use a versão 5.1.

Em relação à versão 4, só estes campos mudam (apenas contagens; resultados e valores
operacionais continuam sem leitura fora das UFs de desenvolvimento):

| | 2026 | 2022 |
| --- | --- | --- |
| Resultados `ready` → `unavailable` (`unreconciled`) | 0 | 5 |
| Operações e tempos `partial` → `unavailable` (`unsupported_software`) | 1 | 9 |
| `i7_failed_json` | 20 seções | — |
| Unidades comparáveis | 499205 de 499248 | 472024 de 472693 |
| Tempo de construção, pico de memória | 3074 s, 3,74 GB | 2811 s, 3,25 GB |

Todos os outros campos são iguais aos da versão 4. A tabela da versão 4 segue para
referência.

Versão 4, construída em 8 de novembro de 2026 em
`$EA_STAGE/phase20b-sessions/table-2026-v4-20261108c/` (sobre as
seções de integridade v4 e os logs v3 da Fase 20b) e `table-2022-v4-20261108b/` (só
contagens; resultados e valores operacionais ficam sem leitura):

| | 2026 r1 | 2026 r2 | 2022 r1 | 2022 r2 |
| --- | --- | --- | --- | --- |
| Seções | 499248 | 499248 | 472693 | 472693 |
| Resultados prontos | 499206 | 499205 | 472028 | 472028 |
| Perfil pronto | 498858 | 498858 | 472349 | 472349 |
| Com sessões / sem sessão oficial / sem log | 498568 / 12 / 72 | 498577 / 4 / 71 | 471844 / 15 / 834 | 471971 / 12 / 710 |
| Protegidas (logs não lidos) | 596 | 596 | 0 | 0 |
| Operações prontas / parciais / indisponíveis | 333365 / 165203 / 680 | 359069 / 139508 / 671 | 261283 / 210560 / 850 | 300549 / 171422 / 722 |
| Relógio `ok` / `adjusted` | 495490 / 1451 | 495549 / 1651 | 469688 / 1202 | 469678 / 1439 |
| Relógio `backstep` / `overlap` / `no_close_rule` | 34 / 24 / 0 | 9 / 7 / 0 | 23 / 60 / 0 | 4 / 15 / 0 |
| Modelo do log concorda / difere do BU | 498560 / 8 | 498577 / 0 | — | — |

Em relação à versão 3 (`$EA_STAGE/phase22/table-2026-v3-20261107/`
e `table-2022-v3-20261106/`), só mudam campos derivados dos logs. Em 3069 seções
(2026) e 1993 (2022) o turno agora tem sessão oficial: urnas deixadas ligadas durante
a noite ou reiniciadas no meio do dia ([passada semântica](semantic-pass.md#versão-4-fase-20b)).
Com isso mudam seus campos de situação do log, modelo, operações, relógio e cópias. Em
2026 o campo do I3 muda nas duas seções SA de MG, e o I5–I7 e o I6 vêm dos releases da
Fase 20b. Os arquivos de resultados e de unidades são idênticos, assim como as regras
de encerramento.

Toda unidade é `same_principal` nos dois anos: 499248 unidades em 2026 (499205
comparáveis) e 472693 em 2022 (472028 comparáveis). As unidades não comparáveis
não têm resultados em algum turno. Regras de encerramento, por seção e ano (os dois
turnos as compartilham):

| Regra | 2026 | 2022 |
| --- | --- | --- |
| `law_uf` | 489730 | 464164 |
| `am_configured` | 8063 | 6752 |
| `am_list` | 94 | 704 |
| `abroad` | 1351 | 1064 |
| `law_noronha` | 10 | 9 |

Observações:

- O exterior (ZZ) responde por 1211 dos 1451 relógios `adjusted` do 1º turno de
  2026, e por todo `backstep`.
- No 2º turno de 2026, 82 seções de Mato Grosso são `adjusted`, contra nenhuma no 1º
  turno. Todas são ajustes do operador no ADH com deslocamento perto de −3600 s, em
  três municípios, a maioria na zona 0053
  ([observação O11](observations.md#operação)).
- No 1º turno de 2026, oito seções têm modelo de log da última sessão diferente do
  modelo de quem assinou o BU. Em seis, o arquivo de assinatura foi assinado por
  outra urna ([observação O13](observations.md#operação)); duas (RJ 60011/0214/0023
  e 0024) usaram urna de reserva.
- As seções `am_list` (94 em 2026, 704 em 2022) ficam em municípios cujas urnas não
  imprimiram encerramento configurado no ano: ninguém tentou encerrar antes da hora,
  então o encerramento vem da lista (2026: 32 às 15:00 e 62 às 16:00; 2022: 88 e
  616). A versão 2 as deixava `unresolved`, e versões anteriores desta página davam a
  causa errada (mais de um encerramento impresso). Nenhum encerramento impresso
  contradiz a lista em nenhum dos anos.
- Versão 3, em relação à versão 2: só mudam as regras de encerramento do Amazonas e seus
  estados de relógio e de horário e, em 2026, os campos de integridade da Fase 20b:
  `i1_signature` passa a `verified` em toda seção Ed521 e o tipo de urna
  `reservaSecao` passa a `contingenciaSecao`. Os arquivos de resultados e de
  unidades são idênticos.

## Limites

- A linhagem pelo início do bloco identifica cópias, e a cópia mais longa é mantida;
  cópias que terminam em linhas diferentes (uma seção, [O16](observations.md#operação))
  não são comparadas linha a linha.
- Votos concluídos após o encerramento são contados por hora cheia. Isso só é exato
  porque todo horário legal de encerramento cai em hora cheia.
- O perfil do eleitorado é um retrato anterior à eleição (julho de 2026, agosto de
  2022). Seções criadas depois não têm perfil e ficam `unavailable`.
- A situação de integridade existe só para 2026, porque a Fase 20 não foi executada
  para 2022.
