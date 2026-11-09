# Processamento estrutural limitado e ajuste ao hardware

Document-ID: EA-NATIONAL-PROCESSING · Revision: 7 · Language: pt-BR

[English](../en/national-processing.md) · [Evidências da Fase 11](handoffs/task-11.md)

Este guia cobre o caminho estrutural **em nível de evento**. A passagem nacional do
segundo turno usou o caminho de resumos, mais rápido, descrito em
[processamento orientado a features](feature-oriented-processing.md); use os comandos
abaixo para benchmarks em nível de evento, estudos de hardware ou um armazenamento de
eventos completo.

Este fluxo perfila um manifesto concluído do coletor, registra uma amostra de
desenvolvimento selecionada por metadados e processa eventos estruturais sem perdas.
O autotuner finito mede tamanhos de lotes no seu hardware. Ele não ajusta verificação
eleitoral, reconstrução de sessões, modelos ou avaliação científica final. Um lote
mais rápido não altera elegibilidade científica nem o protocolo de pesquisa.

## Preparação e entrada

Use Linux com `/proc`, Python 3.14 e dependências travadas; DuckDB e PyArrow já estão
incluídos. Instale uv e just (o rtk é opcional) e execute na raiz do repositório. Instalação sem
rede exige dependências previamente em cache. Nenhum comando abaixo inicia coleta,
dashboard ou ajuste de modelos.

```sh
just setup
.venv/bin/python -B -m election_audit.national_benchmark --help
.venv/bin/python -B -m election_audit.national_tuning --help
```

Crie `data/my-national-sources.json` com seu manifesto concluído, raiz original do
coletor e UFs explícitas. Caminhos relativos partem do diretório de trabalho. O
exemplo pequeno seleciona AC/SP/ZZ, não o país inteiro. Turno declarado e URLs
oficiais devem concordar; nomes de arquivos não provam identidade do turno.

```json
{
  "version": "national-structural-v1",
  "sources": [{
    "round": 2,
    "root": "data/tse/2026/turno-2",
    "manifest": ".local-state/tse-2026.sqlite",
    "ufs": ["ac", "sp", "zz"]
  }]
}
```

O perfil lê metadados URL/hash/tamanho/geografia para SQLite, não resultados de
logs. A seleção usa posições por hash de conteúdo nos quatro quartis de tamanho
de cada UF e seu maior objeto. Antes da análise, `inspection.json` marca as seções
como inspecionadas para desenvolvimento. Propague esse histórico a locais estáveis
nos dois turnos antes de congelar qualquer partição de teste intocada; identidade
desconhecida não é elegível para teste. Pilotos e partições protegidas existentes
continuam obrigatórios. Se já existe protocolo congelado, passe `select --exclusions PATH` com registro revisado e verificado `structural-sample-exclusions-v1`: `round` correspondente, `section_keys` protegidas/estresse expandidas e hashes de evidências. Exclua todas as seções ligadas a cada local protegido, não somente um principal. Identidade entre turnos ausente continua indisponível. A revisão atual está em `data/national/phase11-protection-2026-10-31/`; propague seu registro de sobreposição antes de nova avaliação científica.

```sh
.venv/bin/python -B -m election_audit.national_benchmark profile --config data/my-national-sources.json --output data/my-profile --scratch .local-state/my-scratch
.venv/bin/python -B -m election_audit.national_benchmark select --profile data/my-profile --output data/my-sample --per-band 1
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B -m election_audit.national_benchmark compact --sample data/my-sample --output data/my-baseline --store data/my-national-store --scratch .local-state/my-scratch --output-budget-gib 0.25 --batch-rows 2048 --memory-gib 4
```

O último comando cria uma referência limitada e permite processamento manual sem
autotuning. A referência concluída fixa resumos e contagens de eventos usados para
validar cada tentativa. Diretórios de perfil, seleção, relatório e ajuste devem ser
novos; processamento comum pode reutilizar artefatos por conteúdo já verificados.

## Ajustar e aplicar

O autotuner escolhe até seis fontes já inspecionadas, uma por região disponível,
incluindo exterior. Cada candidato processa os mesmos originais em saídas duráveis
novas e distintas. Duas repetições em ordem direta/inversa reduzem efeitos de ordem.
A busca padrão usa 2048/8192/32768 linhas de eventos, sempre também limitada a 8 MiB
por lote. A execução usa um trabalhador; esta versão não afirma otimizar sua
quantidade. Originais e metadados podem estar em cache; caches não são expurgados.

```sh
.venv/bin/python -B -m election_audit.national_tuning prepare --sample data/my-sample --comparison data/my-baseline/benchmark.json --output data/my-tuning --store data/my-national-store --scratch .local-state/my-scratch --memory-gib 4 --output-mib 128 --seconds 900 --batches 2048 8192 32768
.venv/bin/python -B -m election_audit.national_tuning run data/my-tuning
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B -m election_audit.national_benchmark compact --sample data/my-sample --output data/my-tuned-report --store data/my-national-store --scratch .local-state/my-scratch --output-budget-gib 0.25 --tuning-config data/my-tuning/recommended.json
```

O comando final aplica a recomendação ao processamento de produção. Objetos
verificados existentes mantêm seus lotes físicos originais; use uma amostra recém
registrada para medir trabalho novo. Saídas de ajuste são artefatos separados de
benchmark e não substituem silenciosamente os checkpoints principais.

O objetivo é a mediana de **eventos por segundo** novos, desde leitura verificada
da fonte até análise, codificação e publicação durável. A validação integral da
reprodução lógica fica separada dentro do tempo total da tentativa e não entra
nesse objetivo. RSS do trabalhador e soma conservadora da árvore de processos
incluem margem de monitoramento. Tempos históricos reutilizados nunca viram medidas
de tentativa. Ganhos devem superar 3% e o ruído observado entre repetições; caso
contrário vence o lote menor. A busca finita retorna a melhor configuração segura
observada, não ótimo global nem garantia para outra carga ou máquina. Mistura de
fontes, cache, coleta concorrente e caudas de latência HDD podem dominar o tempo.

## Orçamentos, recuperação e portabilidade

O padrão de 4 GiB é orçamento agregado de memória de trabalho da Fase 11, não
alocação por trabalhador nem meta de uso. Nesse padrão o trabalhador tem limite
rígido de 3 GiB de endereçamento virtual, o supervisor pode usar 512 MiB RSS e
outros 512 MiB são margem. O supervisor amostra RSS da árvore e memória/pressão
do sistema a cada 100 ms, rejeitando violações de recursos, tempo ou disco. Isso
combina limite conservador de endereçamento e monitoramento, não garantia de RSS
por cgroup do sistema. O coletor está fora da árvore, mas afeta a pressão observada.

`prepare` aceita `--memory-gib`, `--output-mib`, `--seconds`, `--hdd-reserve-gib`,
`--ssd-reserve-gib`, `--scratch-gib` e `--batches`. `compact` manual aceita as mesmas
opções de memória/reserva/temporários, `--output-budget-gib` e `--batch-rows`.
Recursos da recomendação prevalecem com `--tuning-config`. Em hardware menor,
comece com 1–2 GiB RAM, lote 2048, ao menos 1 GiB temporário e orçamento de saída
menor; reduza reservas de disco somente após considerar outras cargas. Abaixo de
1 GiB o autotuner recusa execução. Preserve o ambiente de threads mostrado,
especialmente com limites pequenos de endereçamento.

Na máquina de referência, mantenha piso HDD de 20 GiB, reserva SSD de 10 GiB e
temporários de 8 GiB. São reservas
separadas do orçamento de saída. Reserve temporários e saída quando compartilharem
volume. Coleta incompleta não pode ser congelada como população completa. Amostras
limitadas e cenários de armazenamento não autorizam execução nacional sem capacidade.

`spec.json` fixa hashes/fontes/saídas lógicas esperadas, amostra, configurações,
hashes de módulos e versões de execução. `state.json` atômico contém checksum
interno; relatórios/logs por tentativa preservam medidas aceitas e rejeitadas.
`recommended.json` só é publicado ao concluir a busca finita. Repita o comando
`run` para retomar. Trabalhador anterior ativo impede duplicação. Trabalho
interrompido consome sua saída/tempo retidos reais e não é aceito como medida.
Rejeição por recursos aguarda e salva o motivo; duas rejeições ou o orçamento total
de tempo/saída encerram o estudo. Resolva a pressão antes de retomar. Identidade
alterada de código/fontes exige novo estudo explicitamente fixado. Não apague
originais nem sobrescreva tentativas congeladas para forçar sucesso.

Eventos compactos preservam hashes completos de linhas, IDs, localizadores de
membros/linhas e todos os campos lógicos; leitores verificam checksums físicos e
resumo da sequência integral reconstruída. Erros estruturais são gravados em fluxo,
sem o antigo teto de problemas. Informações de mensagens não suportadas são
contadas exatamente e continuam localizáveis nas linhas de eventos. O significado
científico desses fatos permanece não resolvido.

O processamento compacto registra dependência externa verificada dos arquivos CAS
do coletor em vez de copiar todo o armazenamento bruto. Revalida originais na
análise e reutilização. Preserve a raiz: os artefatos **não são autocontidos**.
Para movê-los, mantenha bytes/caminhos CAS ou crie nova configuração local
verificada. Para originais selecionados autocontidos, o caminho separado de censo
`national resume` copia/congela originais no armazenamento próprio e exige orçamento
maior; atualmente grava a representação payload maior. Não se afirma exportação
compacta autocontida.

Um estudo anterior no volume de saída original escolheu 2048 linhas: mediana
3067.749 eventos/segundo contra 3019.755 com 8192 e 2854.901 com 32768. Não se
estabeleceu ganho material com lotes maiores. O lote aplicado de 476 objetos produziu
4843988 eventos em 1044.902 segundos, pico RSS 93052 KiB; reutilizou 247 objetos e
produziu 229 novos. São evidências de execução limitada, não nacional completa.
Aceitação medida e limitações de capacidade nacional estão no handoff pareado da
Fase 11. Os comandos não dependem do caminho HDD específico desta máquina e
nenhuma escolha de ajuste concede acesso a resultados protegidos.

## Trabalhos em disco para a população elegível

`national_workload` agenda um perfil concluído e congelado por registro SQLite,
sem carregar lista nacional em memória. Forneça exclusões revisadas e verificadas;
`data/my-exclusions.json` no exemplo deve existir e registrar seções/turno/evidências
protegidos. Expanda grupos estáveis de teste/estresse para todas as seções-fonte.
Conteúdo idêntico compartilhado com qualquer observação excluída também é excluído
antes de abrir corpos ou originais em cache. Ausência dessa lista não concede
elegibilidade científica nem de teste intocado.

```sh
.venv/bin/python -B -m election_audit.national_workload --help
.venv/bin/python -B -m election_audit.national_workload prepare --profile data/my-profile --exclusions data/my-exclusions.json --tuning-config data/my-tuning/recommended.json --output data/my-workload --store data/my-national-store/workload --scratch .local-state/my-scratch --reuse-store data/my-national-store --output-budget-gib 4 --future-budget-gib 4 --source-growth-gib 0
.venv/bin/python -B data/my-workload/run_frozen.py preflight
.venv/bin/python -B data/my-workload/run_frozen.py status
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B data/my-workload/run_frozen.py run --max-objects 32
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B data/my-workload/run_frozen.py run
```

Os orçamentos do exemplo, saída de 4 GiB e reserva futura de 4 GiB, limitam o trabalho;
não estimam capacidade nacional. Escolha valores revisados para sua população.
`--source-growth-gib` reserva crescimento da coleta separadamente; só use zero quando
nenhum crescimento adicional precisar de reserva. Orçamentos no mesmo volume são
somados. O ponto de montagem é fixado para impedir escrita em volume substituto se
o disco externo desaparecer; `--volume-anchor PATH` permite indicá-lo explicitamente.
A política RAM de 4 GiB e o lote efetivo vêm da recomendação fixada; usa-se um trabalhador.

O trabalho preserva todas as observações, inclusive exclusões explícitas, em escopo
imutável com checksum. Registro durável separado guarda conteúdo único, tentativas,
falhas, saída alocada e referências externas verificadas. Reutilização revalida bytes
e custódia original; não copia nem adota resultados antigos silenciosamente. Saídas
novas recebem verificação integral da reprodução lógica. Preserve as raízes originais
e os armazenamentos de checkpoints reutilizados.

`run_frozen.py` verifica uma cópia congelada de pacote/recursos antes da importação;
alterações posteriores no workspace não mudam o trabalho longo ou sua retomada.
Ainda exige ambiente travado e originais externos; não é pacote de wheels nem
exportação autocontida. Use esse lançador para retomar/consultar. O progresso contém
contagens agregadas, não inspeção nova de resultados individuais. Históricos prévios
de desenvolvimento continuam obrigatórios. Identidade/histórico ausentes permanecem
indisponíveis. Observações protegidas são lacunas deliberadas de cobertura.

Use `--max-objects` no lote inicial revisado e retome sem esse limite. Falhas param
o trabalho e ficam registradas; após resolver a causa use `run --retry-failed`.
Esgotar saída interrompe antes de publicar mais. Orçamento maior exige nova
especificação/armazenamento fixado e reutilização explícita do anterior; não edite
manifestos congelados. A recuperação só limpa temporários privados não publicados
deste trabalho. Checkpoints congelados, originais e outros dados do disco permanecem.

## Histórico na máquina de referência

Na máquina de referência este caminho produziu os estudos de ajuste da Fase 11, as
parcelas de 476 e 256 objetos e um job congelado da população elegível do segundo
turno. Esse job foi parado em 2 de novembro de 2026 em 15425 de 498581 objetos, quando
o caminho de resumos o substituiu. Seus artefatos estão preservados em
`data/national/` e descritos no [handoff da Fase 11](handoffs/task-11.md). Não retome
seus lançadores: eles fixam as raízes de origem antigas.
