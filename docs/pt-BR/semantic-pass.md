# Passada semântica em fluxo (Fase 21)

Document-ID: EA-SEMANTIC-PASS · Revision: 1 · Language: pt-BR

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

## Limites

- Os logs de 2022 usam outra versão de software e precisam de regras de 2022
  revisadas antes de produzir sessões oficiais.
- As impressões digitais comparam segmentos de contexto inteiros; um segmento do
  primeiro turno que termina antes num log do que no outro não coincide e precisa
  de comparação por prefixo.
- Sessões com várias execuções oficiais por objeto (troca de urna ou reinícios)
  ficam como observadas; agrupá-las é trabalho da Fase 22.
