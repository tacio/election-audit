# Passada semântica em fluxo (Fase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 2 · Language: pt-BR

[English](../en/semantic-pass.md) · [Índice de implementação](implementation-index.md)

`semantic-pass` transforma logs brutos de urna em agregados por sessão numa única
leitura em fluxo. Substitui o uso nacional do adaptador por evento
(`operational_review`, `real-operational-v1`), cujas regras e cuja máquina de
estados de sessão e ciclo ele reproduz exatamente, e guarda só o que as fases
seguintes precisam.

## Entradas

- Uma raiz copiada e certificada (`stage-sources copy`): objetos, `manifest.sqlite` e
  `staging-certificate.json`. A passada recusa a raiz do outro turno.
- As exclusões protegidas/de estresse
  (`data/national/phase11-protection-2026-10-31/exclusions.json`). Objetos com
  qualquer testemunha numa seção excluída nunca são abertos, em nenhum turno.
- `resources/real-log-rules.json` (software 10.23.0.0). Outras versões de software
  nunca viram sessões oficiais.

## Saídas

`<output>/release/` contém quatro tabelas Parquet e um `manifest.json` com o
vínculo (hashes das regras, do certificado da cópia, do manifesto e das exclusões)
e os hashes dos arquivos:

| Tabela | Uma linha por | Colunas principais |
| --- | --- | --- |
| `objects` | objeto de log | estado, erro, testemunhas de seção, estado do pacote, contagens de linhas/eventos, sessões, contagens por tipo |
| `sessions` | sessão | tipo (`official_vota` ou `unresolved`), motivo de fim, leituras, ciclos por estado × método, conclusões interrompidas, pedidos manuais, falhas, órfãos, conclusões por hora de leitura, intervalos entre conclusões, recuos do relógio |
| `segments` | segmento de contexto de um fluxo | contexto (`initial`, `official_round_N`, `other_context`), linhas, impressão digital dos bytes, hash da primeira/última linha, primeira/última leitura |
| `vocabulary` | aplicação × modelo de mensagem | contagem de eventos; toda sequência de dígitos mascarada como `#`, sequências hexadecimais longas como `<hex>` |

Leituras são leituras locais do relógio da urna, não horários normalizados. Os
ciclos são anônimos; não há atribuição a candidatos nem reconciliação com o
comparecimento (Fases 20/22). Valores de eleitor, mesário e autenticador não são
exportados.

## Equivalência

`semantic-pass equivalence` roda de novo o adaptador por evento numa amostra com
semente e compara as assinaturas ordenadas por sessão (tipo, motivo de fim,
encerramento, software, ciclos por estado × método, conclusões interrompidas) e as
contagens de órfãos e pedidos manuais do objeto. Em 3 de novembro de 2026 houve
coincidência em 200 de 200 objetos do AC amostrados por turno (45003 e 39466 ciclos
concluídos); a passada levou 12.8 s e 19.5 s contra 268.2 s e 412.3 s do adaptador.

```sh
just semantic-pass equivalence \
  --staged-root ~/data/election-audit-stage/2026/turno-2 --round 2 \
  --output ~/data/election-audit-stage/phase21/equivalence-r2-ac-200 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --uf ac --sample 200 --seed 2103
just semantic-pass run \
  --staged-root ~/data/election-audit-stage/2026/turno-2 --round 2 \
  --output ~/data/election-audit-stage/phase21/national-r2-20261103 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --workers 6
```

A execução é dividida em lotes (500 objetos por lote), retomável com `--resume` sob
o mesmo vínculo, registra erros por objeto sem parar e fica dentro de metade das
CPUs. Testes unitários: `tests/test_semantic_pass.py`.

## Execuções nacionais

Os dois turnos de 2026 rodaram em 3–4 de novembro de 2026 com 6 workers a partir da
cópia no SSD, sem erros por objeto. Cada raiz de saída guarda `binding.json`,
`status.json`, os 998 shards e `release/` (arquivos Parquet `objects`, `sessions`,
`segments` e `vocabulary` com `manifest.json`).

| Turno | Objetos | Sessões | Segmentos | Tempo de parede |
| --- | --- | --- | --- | --- |
| 1 | 498580 | 1704924 | 5048597 | 6642 s |
| 2 | 498581 | 3393756 | 9474325 | 2158 s + 11457 s (retomado uma vez) |

Os logs do segundo turno também trazem eventos de preparação e do primeiro turno,
por isso o segundo turno produz mais sessões. Registro da população: as duas cópias
certificadas guardam 499207 arquivos auxiliares de seção.

| Turno | Seções | Log da urna | Apuração SA, sem log da urna | Publicada sem log | Excluídas | Processadas |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 499207 | 499176 | 31 | 0 | 596 | 498580 |
| 2 | 499207 | 499177 | 29 | 1 | 596 | 498581 |

As seções SA foram apuradas pelo Sistema de Apuração de contingência: o pacote lista
arquivos `busa`, `logsa`, `rdv` e `sa` e nenhum `log` da urna. Duas seções de MG
(41238/0039/0168, 50075/0047/0041) usaram SA só no primeiro turno. A seção SP
64777/0395/0298 foi publicada no segundo turno com arquivos `bu`, `rdv` e `vota` e
sem log.

## Logs de apuração de contingência (SA)

Seções apuradas pelo Sistema de Apuração (SA), o sistema de apuração de
contingência do TSE, publicam `logsa.jez`, `busa.dat`, `imgbusa.dat` e `sa.vsc` em
vez dos arquivos da urna. Um log SA registra apuração, não votação: a preparação da
urna de contingência, cada tentativa de apuração (identidade da seção, tipo de
apuração, motivo, digitação do BU, apuração e geração do `busa.dat`),
cancelamentos e relatórios impressos. As regras do ciclo de votação da urna não se
aplicam, então esses logs têm um resumo próprio.

`sa-logs fetch` lista todo log SA citado nos arquivos auxiliares congelados da
cópia certificada, baixa-o do mesmo servidor oficial para uma nova raiz endereçada
por conteúdo, confere os CRCs do ZIP e compara cada arquivo com o membro
correspondente do arquivo em massa verificado. `sa-logs summarize` exige as
exclusões de proteção, pula seções protegidas antes de lê-las e grava uma linha por
seção em `sa_sections.parquet`.

```sh
just sa-logs fetch \
  --staged-root ~/data/election-audit-stage/2026/turno-1 --round 1 \
  --output ~/data/election-audit-stage/sa-logs/fetch-r1-20261104 \
  --bulk-root /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
just sa-logs summarize \
  --input ~/data/election-audit-stage/sa-logs/fetch-r1-20261104 \
  --input ~/data/election-audit-stage/sa-logs/fetch-r2-20261104 \
  --output ~/data/election-audit-stage/sa-logs/summary-20261104 \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json
```

Uma urna SA pode apurar muitas seções, e o arquivo de cada seção é um retrato do
log crescente dessa urna; os arquivos do segundo turno também trazem as tentativas
do primeiro. Tentativas só são atribuídas a uma seção quando o log imprime seu
município, zona e número de seção na data da eleição do turno; o tipo de apuração é
o último selecionado antes da confirmação da identidade. Identificadores de
operadores no log nunca chegam ao resumo.

Em 4 de novembro de 2026 todos os 31 logs SA do primeiro turno e 29 do segundo
foram baixados, os 60 coincidiram byte a byte com os arquivos em massa, nenhum era
protegido e os 60 foram atribuídos pela identidade impressa:

| Turno | Seções | Tipo de apuração | Motivo | Tentativas canceladas antes do sucesso |
| --- | --- | --- | --- | --- |
| 1 | 2 (MG 41238/0039/0168, 50075/0047/0041) | `DIGITAÇÃO DO BU MAIS CÉDULAS` | `Urna encerrada com eleitores na fila` | 1 em cada |
| 1 | 29 (ZZ) | `DIGITAÇÃO DE BUEx` | `Outros` | 1 seção |
| 2 | 29 (ZZ) | `DIGITAÇÃO DE BUEx` | `Outros` | 1 seção |

Os totais de votos das seções SA vêm do `busa.dat`, presente nos arquivos em massa;
a Fase 20 precisa lê-lo junto com o `bu.dat`.

## Limites

- Os logs de 2022 usam outra versão de software e precisam de regras de 2022
  revisadas antes de produzir sessões oficiais.
- Seções SA têm medidas de apuração SA, não medidas de sessão da urna: a votação
  ocorreu em cédulas ou numa urna cujo log não é publicado no pacote SA.
- As impressões digitais comparam segmentos de contexto inteiros; um segmento do
  primeiro turno que termina antes num log do que no outro não coincide e precisa
  de comparação por prefixo.
- Sessões com várias execuções oficiais por objeto (troca de urna ou reinícios)
  ficam como observadas; agrupá-las é trabalho da Fase 22.
