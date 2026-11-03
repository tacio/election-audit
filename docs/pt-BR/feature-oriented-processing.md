# Processamento nacional orientado a features

Document-ID: EA-FEATURE-PIPELINE · Revision: 3 · Language: pt-BR

## Decisão e escopo científico

Em 2 de novembro de 2026 o usuário aprovou substituir a materialização nacional
obrigatória de eventos por resumos derivados das fontes, evidência relevante e
releitura indexada, com paralelismo real e preservação do uso interativo do PC.
Muda a representação computacional, não a semântica eleitoral nem os critérios de
elegibilidade. Originais preservados, artefatos antigos congelados, testemunhos das
fontes e histórico de inspeção continuam imutáveis e autoritativos. A população
atual do segundo turno mantém 499177 observações, excluindo 596 protegidas/de
estresse e todos os aliases de conteúdo antes de acesso semântico ou ao cache.
Verificar a cópia do primeiro turno não autoriza sua análise.

`source-operational-summary-v1` registra contagens estruturais exatas de eventos e
classes, todos os erros com hashes das linhas/localizadores dos membros, ordem das
fontes e limites/reversões do relógio bruto por membro, mudanças de fluxo, eventos
reconhecidos e âncoras de contexto/erro. As contagens de mensagens não suportadas
permanecem exatas. Linhas comuns não suportadas usam índices de membro/bloco de
linhas físicas e fingerprints SHA-256; seus hashes individuais são derivados dos
originais preservados sob demanda. Mensagens, tokens pessoais e identidade do
eleitor não são armazenados. Esses resumos não validam sessões oficiais, ciclos
anônimos, fusos, correções de relógio, remoção de históricos copiados ou resultados
eleitorais. Parsing incompleto continua parcial; indisponível não vira zero.
A ausência de tabela de eventos não concede prontidão científica.

O parser fundido preserva limites de tamanho/diretório/profundidade/membros/CRC/linhas.
Membros pequenos usam spools de RAM limitados a 2 MiB, com disco apenas quando
necessário. A validação de calendário evita parsing repetido de locale. Callbacks
tipados evitam JSON temporário por evento, reinterpretação e geração repetida de
IDs. A amplificação de evidência/erros tem teto explícito e falha em vez de truncar
diagnósticos necessários. Cada fonte é conferida no ledger de realocação fixado,
recebe um hash no descritor aberto, é interpretada no mesmo descritor e passa por
checagem final de inode/tamanho/mtime/ctime. Não há fallback para originais antigos.

`grouped-source-summary-shards-v3` usa processos trabalhadores, prefetch/resultados
limitados e um único escritor SQLite por grupos. Cada shard indexa objetos, membros,
blocos, âncoras e erros. Transações SQLite FULL, fsync, publicação atômica de diretório
e ledger durável por grupo substituem o custo por evento/objeto. Grupos publicados
sem registro no ledger são verificados por checksum e reconciliados após interrupção;
somente temporários privados não publicados são reconstruídos. Artefatos antigos
completos mantêm referências explícitas para uso forense opcional. O resultado lógico
independe da ordem de conclusão dos trabalhadores; bytes físicos do SQLite podem variar.

## Recursos e uso prático

Os padrões são 4 GiB de RAM agregada, no máximo metade da capacidade de CPU disponível,
nice +10, uma thread de biblioteca por processo e I/O best-effort de baixa prioridade.
A afinidade prefere grupos de núcleos físicos/irmãos e deixa margem para o desktop.
Nesta máquina com 12 CPUs lógicas/6 núcleos o teto é 600%, com CPUs 0,1,2,6,7,8 e
três trabalhadores iniciais. SMT, caches e I/O continuam compartilhados; não há
isolamento físico nem garantia de latência. Um slice systemd do próprio usuário
impõe uma única cota de CPU e MemoryMax=4 GiB, sem swap, para auxiliares, ajuste e
produção em conjunto. Nenhuma configuração global ou cgroup de root é alterado.
O fallback portátil usa afinidade herdada, parcelas limitadas de espaço de
endereçamento, threads e observação do RSS da árvore. Exige duas CPUs disponíveis;
um sistema com uma CPU precisa de cota fracionária imposta separadamente. O orçamento
inclui pai, escritor, fila e bibliotecas; não são 4 GiB por trabalhador.

Mantêm-se piso de 20 GiB no HDD, teto de 256 GiB de saída e 256 GiB para derivados
futuros, reserva de 10 GiB no SSD e 8 GiB de temporários limitados. Não é necessária
nova cópia de 144 GB dos originais. Máquinas menores podem usar menos trabalhadores,
grupos menores, menos prefetch e orçamentos explícitos; protocolo e parsing científico
continuam iguais. Falhas de recursos interrompem a execução e preservam grupos duráveis.

O [guia de processamento nacional](national-processing.md) explica aquisição,
verificação de manifestos, amostras de desenvolvimento e escopos elegíveis congelados.
O scope workload é pré-requisito de metadados e não exige tabela nacional de eventos.
Mantenha disponíveis seu SQLite, exclusões e registro verificado dos originais.
Aliases absolutos são vínculos locais de custódia; crie e verifique os vínculos de
sua máquina em vez de editar arquivos congelados.

Prepare um trabalho manual com a CLI real e orçamentos explícitos:

```bash
rtk proxy .venv/bin/python -B -m election_audit.national_parallel prepare --scope-workload work/scope --output work/summary-config --store /path/to/derived/summary --memory-gib 4 --cpu-fraction 0.5 --workers 2 --batch-objects 32 --prefetch 1 --hdd-reserve-gib 20 --ssd-reserve-gib 10 --scratch-gib 8 --output-gib 256 --future-gib 256
rtk proxy .venv/bin/python -B work/summary-config/run_frozen.py run --max-objects 112
rtk proxy .venv/bin/python -B work/summary-config/run_frozen.py status
```

Quando disponível, use um cgroup de usuário em torno do launcher congelado; afinidade
e prioridade também são aplicadas no modo manual. `national_summary_tuning` executa
sequência finita, balanceada em ordem direta/inversa, de configurações reais de
trabalhadores/grupos sobre a mesma seleção elegível explícita de desenvolvimento,
com saídas novas, no máximo 900 segundos e 1 GiB total de saída. Preserva pins de
código/fontes/configuração, cada tentativa, CPU/RSS/cgroup/I/O, motivos, medianas/MAD
e recomendação. Tentativas inseguras ou com falha interrompem/recuam; artefatos
interrompidos ficam para revisão. Mudança de identidade exige novo estudo. Ganhos
dentro do ruído preferem menos recursos. Trata-se da melhor configuração local
segura observada, não de ótimo global. Caches do SO podem estar aquecidos; não são
esvaziados. O ajuste muda trabalhadores/grupos, não especificações científicas,
modelos, partições protegidas ou avaliação final.

## Dependências revalidadas das Fases 10–18

| Fase | Entrada/saída revisada e condição restante |
|---|---|
| 10 | Aquisição concluída e custódia bruta/metadados verificada independentemente; ausentes/desconhecidos continuam desconhecidos. |
| 11 | Resumos fundidos, evidência relevante e índices de releitura; execução elegível do segundo turno medida e limitada. Sem tabela nacional completa obrigatória de eventos. |
| 12 | BU/resultados canônicos independentes, escolhas completas, vínculo de totalização e totais finais BR/UF/município; logs estruturais não os substituem. |
| 13 | Validar sessões, relógios e cópias com fluxos ancorados/releitura bruta direcionada. O caminho antigo de dicionário global/max-events ainda exige adaptador limitado por partições/releitura antes de uso nacional. |
| 14 | Marts de features qualificados a partir de operações validadas/releitura e referências eleitorais, com denominadores, desconhecidos e linhagem. Resumo da Fase 11 não é feature-release-v1. |
| 15 | Congelar alvos, papéis, famílias e partições agrupadas com definições qualificadas de features. Locais previamente inspecionados continuam de desenvolvimento. |
| 16 | Ajustar/calibrar modelos só com marts qualificados; validação independente, poder, multiplicidade e acesso protegido à avaliação final permanecem iguais. |
| 17 | Evidência de casos usa janelas indexadas, histórico explícito de acesso/inspeção e replay completo opcional por objeto. Sem atribuir ciclos anônimos a candidatos. |
| 18 | Marimo/dashboard por último; explorar marts agregados, cobertura, prontidão, desempenho e ponteiros de evidência sem carregar um lago nacional de eventos. |

## Preservação das 21 famílias de features

Contratos e pré-requisitos de evidência/prontidão permanecem obrigatórios. O quadro
mapeia dependências, sem afirmar implementação ou elegibilidade atual das features.

| Família | Entrada de resumos/releitura e requisitos independentes |
|---|---|
| population_coverage | Testemunhos e estados do parser; denominadores de população esperada/composição/local ainda necessários. |
| session_summary | Âncoras suportadas, limites e originais; seleção revisada de sessões e deduplicação de históricos ainda necessárias. |
| cycle_duration_gap | Âncoras/janelas ordenadas; ciclos anônimos, intervalos, exposição e relógios validados. |
| processing_event_availability | Metadados explícitos de recebimento/processamento/geração/publicação; download não é transmissão. |
| late_voting | Âncoras de conclusão/releitura; sessões selecionadas deduplicadas, relógios absolutos e regras do exterior. |
| section_results | BU canônico elegível, escolhas completas e composição, independentes das contagens dos logs. |
| unanimous_results | Categorias completas reconciliadas, incluindo especiais/desconhecidas e total positivo. |
| result_timing | Extremos temporais explícitos de resultados/pacotes, semântica e relógios comparáveis. |
| round_comparison | Contagens dos dois turnos e harmonização de composição/locais; sem inferir transferências individuais. |
| audit_features | Marts qualificados e papéis/especificações congelados; entradas indisponíveis explícitas. |
| turnout_target | Comparecimento/eleitorado oficiais; conclusões dos logs são apenas corroboração. |
| candidate_share_target | Identidades oficiais A/B fixadas e denominador reconciliado de candidatos. |
| blank_null_targets | Semântica oficial completa das categorias e total de cédulas. |
| peer_covariates | Importações de local/histórico/pré-eleição e desenho congelado sem vazamento. |
| device_logistics | Limites de fluxo/membro e releitura técnica; exposição de equipamento/versão e papéis validados. |
| integrity | Hashes das fontes, releitura exata de cópias e BU/final/RDV/assinaturas independentes; hash não é assinatura. |
| conditional_unusualness | Features qualificadas, desenho congelado, modelos treinados/calibrados, sobreposição e poder. |
| multiplicity | Família completa pré-especificada, p-valores válidos e histórico protegido de acesso. |
| validation_investigation | Validação sintética/benigna, releitura autorizada e corroboração independente. |
| conditional_margin_bounds | Limites validados de ciclos anônimos/mecanismo e margem final independente; sem atribuir ciclos a candidatos. |
| counterfactual_excess | Resultados oficiais reconciliados, modelos qualificados/calibrados, hipóteses de mecanismo e reamostragem completa. |

## Verificação e execução medida

A linha de base de 112 objetos foi selecionada antes de examinar resultados pelo
menor hash em cada estrato UF/faixa de tamanho já aprovado. O caminho antigo com
saída nova levou 161,91 segundos. A comparação completa dos 476 objetos seguros
validou 4.843.988 eventos estruturais e 531.048 âncoras retidas, com igualdade de
contagens, diagnósticos, detalhes de erros, hashes/localizadores e contagens por
bloco. Fixtures verificam IDs exatos e todos os campos de replay, arquivos aninhados,
fontes ausentes/corrompidas, fingerprints desconhecidos, limites e exclusão protegida.
Testes com subprocessos reais comparam um/dois trabalhadores, determinismo lógico,
retomada e recuperação de shards publicados sem ledger. A evidência de ajuste,
benchmark e produção está em `data/national/phase11-feature-oriented-2026-11-02/`.

## Execução concluída do segundo turno

O job de produção processou todo o escopo elegível do segundo turno entre 2 e 3 de
novembro de 2026 (terminou às 12:28 UTC de 3 de novembro) com três trabalhadores e
lotes de 32 objetos. Os 498581 objetos elegíveis foram concluídos com 0 falhas:
498575 parses completos e 6 parciais, que retêm todos os 190 erros. Foram percorridos
5032537448 eventos estruturais em 35992 segundos (13,85 objetos/segundo, 111% de CPU
média, pico de RSS da árvore de processos de 195719168 bytes), com 68797890560 bytes
de checkpoints de recuperação. Ao final, a pressão de I/O do host
era de 94% (some, média de 300 segundos), enquanto o job usava 111% de seus 600% de
CPU permitidos: o I/O de armazenamento, não a CPU, limitou a vazão.

A release analítica
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` tem 546620085
bytes de Parquet: `source_summaries` (498581 linhas), `source_witnesses` e
`source_index` (499177 linhas cada), `members` (511541) e `blocks` (10085027).
O manifesto registra `complete_requested_scope=true`, `full_national_complete=false`
(as 596 observações protegidas/de estresse estão ausentes por desenho) e
`scientific_eligibility=unavailable_structural_only`. Cerca de 90% dos eventos
percorridos pertencem a classes de mensagem que o parser estrutural deixa como
`unknown`; a Fase 13 precisa classificá-las antes que sessões, ciclos ou relógios se
tornem elegíveis. O primeiro turno não foi processado. O ponteiro do job é
`data/national/current-phase11.json`.

## Finalização analítica compacta e releitura

A recuperação usa até 32 objetos por checkpoint (cerca de 15.600 shards neste escopo).
A finalização lê os shards confirmados sequencialmente uma vez e escreve cinco
tabelas analíticas tipadas: `source_summaries`, `members`, `blocks`, `source_index`
e `source_witnesses`. Partes Parquet têm alvo de 128 MiB, com excesso limitado por
grupo de linhas; não há partição por seção ou UF. Âncoras/erros continuam na evidência
de recuperação e na releitura bruta direcionada. Hashes completos mantêm 256 bits;
dicionários inteiros por shard e hashes binários reduzem armazenamento sem mudar
identidades lógicas. Consultas analíticas comuns precisam apenas do Parquet, com
estados pendentes/protegidos/fora da seleção explícitos. O CAS bruto é necessário
para replay forense; o SQLite de checkpoints serve à recuperação, não a cada consulta.
Um único SQLite consistente de auditoria acompanha o manifesto determinístico com
checksums para proveniência.

Se necessário, prepare somente os metadados do escopo antes do primeiro trabalho;
isso não abre corpos de logs nem materializa eventos:

```bash
rtk proxy .venv/bin/python -B -c "from election_audit.national_workload import initialise; initialise('work/scope')"
```

Inicie o trabalho elegível completo com cgroup compartilhado de usuário e finalização
analítica automática após a conclusão do produtor:

```bash
rtk proxy .venv/bin/python -B -m election_audit.national_parallel launch work/summary-config --unit election-audit-summary --analysis-output /path/to/derived/analysis-release
```

O launcher cria um slice restrito de usuário com tetos de CPU/RAM da configuração,
afinidade herdada, nice +10 e I/O best-effort prioridade7. `--no-cgroup` seleciona
explicitamente o fallback de afinidade/AS/RSS. Um produtor pausado ou concluído também
pode publicar um dataset imutável do prefixo confirmado; o lock impede corrida entre
publicação e ingestão no orçamento combinado:

```bash
rtk proxy .venv/bin/python -B work/summary-config/run_frozen.py export --output /path/to/derived/partial-analysis --target-mib 128
```

A publicação reserva cota durável, valida checksums, escreve/fsync partes tipadas e
publica atomicamente. Uma reserva interrompida permanece conservadora até revisão/
retomada; uma versão concluída é idempotente com verificação. Resumos ausentes ficam
indisponíveis nos índices/testemunhos. Contagens observadas em parses parciais são
limites inferiores de observação, não totais completos. Publicar não autoriza acesso
humano a testes nem concede prontidão qualificada de features.

Para ajuste real limitado, crie configuração JSON com caminhos absolutos:

```json
{
  "old_workload": "/absolute/project/work/scope",
  "development_sample": "/absolute/project/work/development-sample",
  "selection": "/absolute/project/work/safe-selection.json",
  "resources": "/absolute/project/work/resources.json",
  "output": "/absolute/project/work/tuning",
  "store": "/absolute/derived/tuning"
}
```

`resources.json` contém o objeto `resources` da configuração de resumo preparada;
`safe-selection.json` contém `{"sha256s": ["..."]}` selecionados por metadados na
amostra de desenvolvimento previamente registrada. O ajuste confere registro,
membros, aliases protegidos, pins e desempenho repetido com ruído. Execute no mesmo
slice de usuário com recursos limitados quando disponível:

```bash
rtk proxy .venv/bin/python -B -m election_audit.national_summary_tuning work/tuning-config.json
```

Leia `recommended.json` e aplique trabalhadores/grupos pelas flags `prepare --workers`
e `--batch-objects`. Configuração manual dispensa o ajuste; controles de CPU/RAM/disco
continuam válidos. Tentativas concluídas retomam só com identidades iguais; falhas/
interrupções ficam para diagnóstico. Código alterado exige novo estudo ou registro
explícito de compatibilidade revisada. O registro atual identifica uma correção
posterior de guarda: hash indisponível de linha longa não é mais descrito como hash
completo. Nenhuma das 476 fontes de desenvolvimento atinge essa guarda; caminhos
comuns de parser/escritor/recursos são iguais, e tempos continuam atribuídos ao
runtime congelado original.

A comparação controlada de 112 objetos mediu mediana final de 10,117 objetos/s com
três trabalhadores/grupo32 contra 0,692 no caminho antigo com saída nova: 14,6× nesse
trabalho. A execução ampliada de 476 objetos percorreu 4.843.988 eventos em 33,805
segundos e produziu 66.191.360 bytes de checkpoints, contra 164.696.064 antes da
normalização física. O pico de RSS somado foi 187.535.360 bytes; CPU média de 110%
(uma CPU lógica equivale a 100%; o teto imposto é 600%). A publicação de desenvolvimento
contém cinco arquivos Parquet de 78.251.772 bytes, todos os 499177 testemunhos e
estados desconhecidos/protegidos explícitos. Consultas agregadas DuckDB novas com uma
thread levaram 0,0336 segundo com arquivos possivelmente aquecidos, sem ler SQLite/
originais. Isso não garante desempenho em disco frio, outras caudas, máquinas ou modelos.

O tempo total inclui verificação do runtime, inicialização, trabalhadores, filas,
escrita/durabilidade e encerramento. Tempo por objeto exclui escritor/fila. RSS soma
todos os descendentes; a contabilização do cgroup difere de RSS. I/O físico pode ser
zero em leituras aquecidas; pressão e throttling são preservados. Etapas posteriores
ganham eficiência de leitura compacta, mas validar BU/assinaturas, novas semânticas,
reconstruir, ajustar e reamostrar ainda exige checks próprios. O replay redigido atual
reconstrói campos/IDs estruturais exatos; novos classificadores devem ler originais
preservados sob o protocolo de evidência/acesso da Fase13.
