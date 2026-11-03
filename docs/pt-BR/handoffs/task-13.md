# Tarefa 13 — Observações operacionais reais

Document-ID: EA-HANDOFF-13 · Revision: 1 · Language: pt-BR

`real-operational-v1` acrescenta adaptador limitado de mensagens reais sem alterar
publicações estruturais ou operacionais existentes. O guia oficial de setembro de
2026 foi revisado em https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema.
`resources/real-log-rules.json` fixa padrões semânticos exatos e páginas do guia
para software 10.23.0.0. É interpretação revisada, não certificação de assinatura.

Interfaces: `operational_review.review_object(structural, original, output,
round_number=2, clock=None, witnesses=())` e `review_national(store, output,
round_number=2, max_objects=None, clock_evidence=None)`; a função CLI
`operational_review_main(argv)` aceita `--store`, `--output`, `--round`,
`--max-objects`, `--clock-evidence`. O agente principal integra os comandos.

Cada diretório imutável contém `artifact.json`, `events.parquet`,
`cycles.parquet`, `sessions.parquet` e `review.sqlite`, com checksums. Linhas
Parquet têm JSON textual `payload`. Eventos preservam IDs estruturais e hashes
exatos das linhas, acrescentando semântica, hash das regras, sessão e prontidão.
Sessões preservam turno/objeto, âncoras oficiais e testemunhos de publicação.
Ciclos preservam estado/método anônimo, interrupção e duração anulável, nunca
escolha de candidato. Texto bruto, identificadores de eleitor/mesário e
autenticadores não são exportados. IDs observados do dispositivo permanecem
separados de números de série autoritativos.

Originais são verificados por hash/tamanho e unidos aos localizadores/hashes
estruturais por SQLite temporário; expansão e linhas são limitadas. Contexto
oficial exige âncora GAP exata do turno oficial, início VOTA correspondente,
data-alvo e versão revisada. Outras datas, simulação e versões não suportadas não
viram oficiais silenciosamente. Solicitação manual isolada não é conclusão manual;
exige autorização do operador e conclusão bem-sucedida. Suspensões parcial e total
são distintas. Eventos desconhecidos intermediários bloqueiam durações sem
suporte. Regras de relógio exigem IDs de eventos contíguos revisados e âncoras de
hash correspondentes; ambiguidades ficam indisponíveis. Não se inventa fuso padrão.

A revisão nacional usa índice em disco de fingerprints por fluxo. Fluxos completos
iguais com pelo menos dois registros viram candidatos a cópia, preservando todos
os testemunhos; não são removidos automaticamente nem somados como históricos
independentes. Revisão de substituições/cópias entre objetos e reconciliação com
comparecimento do BU continuam necessárias para elegibilidade de contagens
agregadas oficiais. Exposição/intervalos e após17 ficam indisponíveis sem
limites e continuidade de relógio sustentados separadamente.

Aceitação: cinco testes passam para classificação exata, contexto oficial dos dois
turnos, rejeição de simulação/turno incorreto, ciclos biométricos/manuais/parciais/
totais, falha após solicitação, relógios, retomada imutável e corrupção da fonte.
Ruff passa. Execução real limitada do AC: `data/phase13/real-run.json` registra um
log adquirido por turno. Turno 1 produziu 241 ciclos concluídos, um não resolvido
e uma sessão oficial; turno 2 produziu 232 ciclos concluídos e duas sessões
oficiais. Ambos preservam sessões de preparação/outras e classes de mensagens
desconhecidas. São observações, não reconciliação de comparecimento nem conclusão
nacional. Relógios absolutos continuam indisponíveis. Hashes das fontes e
artefatos exatos constam no registro. Publicações imutáveis e coleta não mudaram.

A fase 14 pode ler os payloads Parquet de sessões/ciclos em fluxo e vincular URLs
à população de seções/índices revisada; nunca inferir identidade estável da seção
principal pela urna física nem tomar uma associação como cobertura completa.

```sh
rtk proxy .venv/bin/python -B -m unittest discover -s tests -p test_operational_review.py -v
rtk proxy .venv/bin/python -B -m election_audit.operational_review --help
```
