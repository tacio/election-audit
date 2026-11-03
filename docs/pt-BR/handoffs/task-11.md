# Tarefa 11 — Processamento estrutural nacional limitado e ajuste ao hardware

Document-ID: EA-HANDOFF-11 · Revision: 8 · Language: pt-BR

## Resultado — 3 de novembro de 2026

A Fase 11 está concluída no escopo elegível do segundo turno. Em 2 de novembro o
usuário aprovou substituir o job de produção em nível de evento por resumos orientados
a features ([guia](../feature-oriented-processing.md)). O job em nível de evento em
`data/national/phase11-overnight-2026-11-01/` foi parado por SIGTERM em 15425 de
498581 objetos; seus artefatos foram preservados e ele não deve ser retomado.

O job de resumos `c7b864888159193cb15257415757f0368d675b54a8376ed335ddc6ed79626333`
(`data/national/phase11-feature-oriented-2026-11-02/production/`) concluiu os 498581
objetos elegíveis em 2026-11-03 12:28 UTC: 0 falhas, 498575 parses completos e 6
parciais (190 erros retidos), 5032537448 eventos estruturais, 35992 segundos
decorridos, três trabalhadores, 111% de CPU média, pico de RSS da árvore de processos
de 195719168 bytes e 68797890560 bytes de checkpoints. Sua release analítica
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` está em
`runoff-summary-analysis-full-20261102/` no volume de saída, com 546620085 bytes de
Parquet: `source_summaries` (498581 linhas), `source_witnesses` e `source_index`
(499177 cada), `members` (511541) e `blocks` (10085027).

As 596 observações protegidas/de estresse continuam adiadas. O primeiro turno está
registrado só para custódia e não foi processado. A elegibilidade científica continua
`unavailable_structural_only`. As seções abaixo são o registro datado de execução;
afirmações de que um job está em execução, programado ou pendente foram superadas.

## Fluxo aprovado e escopo

O usuário autorizou um subagente da Fase 11 enquanto continua a coleta corrigida
do primeiro turno. Fases posteriores seguem pausadas e marimo fica por último.
Também pediu orçamento agregado de 4 GiB e autotuning medido com documentação
portátil. Os ~128 MiB anteriores eram RSS observado, não limite imposto. O
[guia do usuário](../national-processing.md) cobre preparação, opções reais,
alternativa manual, ajuste, reprodução, retomada e dependências dos originais.

Ferramentas e execuções limitadas reais são distintas de execução nacional completa.
O perfil concluído de tamanho/geografia cobre 499177 mapeamentos de logs do segundo
turno e 90350525589 bytes. A coleta correta do primeiro continua incompleta em
`turno-1-verified`, com `.local-state/tse-2026-t1-verified.sqlite`; a raiz antiga
fornecida como primeiro turno duplica o segundo. O coletor não foi interrompido,
reiniciado ou duplicado; bytes brutos e publicações anteriores foram preservados.

## Interfaces, proveniência e recursos

`national.py` oferece censo em disco, preflight, retomada/estado e checkpoints
verificados por conteúdo. Fontes explícitas têm turno/raiz/manifesto/UFs e podem
restringir `section_keys`. O censo mantém mapeamentos e históricos de metadados sem
inventar associações URL/bytes passadas. O caminho payload maior congela originais
no próprio armazenamento; processamento sem limite de objetos exige orçamento
positivo explícito. O estado separa artefatos legados e conclusão estrutural atual.

`national_benchmark.py` oferece perfil SQLite somente de metadados, seleção
determinística por UF/quartil, registro prévio de inspeção de desenvolvimento,
exclusões protegidas opcionais fixadas, execução limitada e relatórios medidos.
A seleção não lê resultados eleitorais. Após vincular identidades, locais
selecionados devem continuar fora de testes intocados nos dois turnos.

`national_storage.py` publica Parquet tipado sem perdas. Preserva hash exato da
linha com 32 bytes, campos textuais/sequência/linha e moldes compartilhados de
localizadores. `iter_compact` reconstrói cada campo lógico e ID determinístico,
verificando checksums físicos e resumo integral. Não usa hashes truncados nem omite
evidências. Erros estruturais fluem sem o antigo teto de problemas. Informações
não suportadas são contadas exatamente e localizáveis por eventos desconhecidos.
Artefatos limitados antigos permanecem intactos sob chaves legadas.

O produtor compacto registra dependências verificadas do CAS original em vez de
copiar toda a fonte. Revalida originais antes/depois da análise e na reutilização.
Os artefatos declaram dependência externa e não são autocontidos; preserve a raiz.
Publicação usa checksums, fsync, renomeação atômica, travas por conteúdo e registro
de falhas; problemas temporários nunca viram sucesso. Saídas ficam em
`compact/KEY_PREFIX/KEY/`, ligando hashes às observações congeladas. O diretório
compartilhado histórico chama-se `phase11-ac`, mas o catálogo define o escopo.

A produção atual usa um trabalhador. O orçamento é 4 GiB agregado; a CLI ajustada
usa limite rígido de 3 GiB de endereçamento virtual, supervisor com 512 MiB RSS e
512 MiB de margem, verificando pressão/RSS da árvore durante o ajuste. Não é
garantia RSS por cgroup. O piso HDD é 20 GiB, reserva SSD 10 GiB e temporários
limitados por objeto 8 GiB. Em volume compartilhado, somam-se temporários e saída;
volumes separados são verificados separadamente. Limites por linhas e bytes valem
simultaneamente. Quatro trabalhadores/threads são tetos planejados, não concorrência ativa.

## Evidências reais medidas

As evidências anteriores permanecem em `data/national/phase11-ac/benchmark.json`
e `phase11-review-2026-10-31/`: metadados AC/três logs e cinco principais do piloto.
Essas execuções pequenas não são nacionais.

`phase11-stratified-2026-10-31/` contém perfil e amostra de 252 alvos: duas posições
por hash em cada quartil por UF e maiores caudas, todas as 28 UFs/ZZ e regiões.
Processou 47760088 bytes em 2660764 eventos e 218718728 bytes payload em 1100.888
segundos, pico RSS 124012 KiB. Um maior objeto RJ é realmente parcial: 70 erros de
horário e 111 de colunas, todos preservados. Suas 18228 informações não suportadas
são contadas e localizáveis. Metadado oficial `f:O` maiúsculo revelou divergência
de normalização; o censo agora concorda com o coletor sem alterar originais.

`phase11-compact-2026-10-31/sample/benchmark.json` contém exatamente as mesmas
252 sequências: saída 102914374 bytes, 1270.869 segundos incluindo comparação
integral e pico RSS 312268 KiB. IDs, campos, hashes, localizadores, contagens e
estados coincidem. Razões saída/fonte: mínimo 2.0057, mediana 2.1586, p95 2.1855,
máximo 2.2642. Blocos alocados incluindo subdiretórios somaram 104990208 bytes.
Cópias e hashes do código distinguem implementações carregadas de reforços posteriores.

`phase11-tuning-v3-2026-10-31/` registra seis tentativas novas com seis fontes
regionais/ZZ já inspecionadas, duas repetições equilibradas, lotes 2048/8192/32768,
saída total de 128 MiB e teto de 900 segundos. Concluiu em 135.844 segundos, gerou
13444806 bytes e atingiu 173486080 bytes de RSS agregado. Medianas eventos/segundo:
3194.220, 2797.049 e 2798.317; MAD relativo 11.42%, 5.71% e 3.88%. Não houve ganho
sustentado seguro com lotes maiores; a melhor configuração observada é 2048,
não ótimo global. Todas as sequências/contagens coincidiram. O primeiro estudo
interrompido foi preservado; a corrida de RSS de processo zumbi foi corrigida e testada.

Um lote seguinte de 476 alvos foi admitido em `phase11-tranche-2026-10-31/`, quatro
posições elegíveis por quartil e caudas, reutilização verificada, nenhuma cópia
bruta e teto de saída 4 GiB. A recomendação v3 medida foi aplicada à produção real.
Concluiu em 1044.902 segundos: 4843988 eventos de 86934493 bytes de fontes,
187528258 bytes lógicos / 191419904 alocados, pico RSS 93052 KiB. Reutilizou 247
objetos verificados e produziu 229 novos (2232828 eventos em 553.635 segundos de
produção). Todos os fluxos lógicos foram verificados; somente o RJ conhecido segue
parcial. `tranche-review.json` separa tempos novos dos antigos checkpoints.
`planning-scenarios.json` usa quatro objetos primários elegíveis por estrato: ponto
nacional alocado 198525442560 bytes, cenário sequencial nas médias novas de
14.304 dias; sem garantia nacional nem orçamento para derivadas.
O estudo final com código correspondente em `phase11-tuning-final-2026-10-31/`
também concluiu seis tentativas em 131.656 segundos. Seu `recommended.json` atual
mantém 2048 linhas: medianas eventos/segundo 3067.749 contra 3019.755 (8192) e
2854.901 (32768), máximo RSS agregado 172756992 bytes e saída 13444799 bytes.
Não se afirma ganho material com lotes maiores. Fixa cópias de código, contadores
CPU/I/O e equivalência lógica. Retomar estado concluído reconstrói atomicamente
recomendação ausente sem repetir tentativas; execuções preservam os hashes originais.
Não é necessário processamento novo apenas para republicar metadados.

## Proteção e condição de capacidade nacional

`phase11-protection-2026-10-31/impact.json` registra revisão apenas de metadados:
quatro seções AC da amostra original sobrepõem teste protegido e uma estresse
municipal. Não foram abertos valores eleitorais, avaliação final ou métricas
operacionais individuais. O registro prévio de desenvolvimento é conservador:
não afirme que esses locais seguem intocados. Preserve o protocolo congelado e
propague o histórico na Fase 15 antes de nova avaliação final. O lote novo exclui
596 seções protegidas/estresse AC, em 171 locais; nenhuma das seis fontes de ajuste
é AC. Não foram reescritos registros ou protocolos de fases posteriores.

`phase11-capacity-2026-10-31/capacity.json` fixa contadores e blocos medidos. Havia
272355491840 bytes HDD e 29056479232 SSD livres. Reservar 90643145031 bytes adicionais
de coleta, piso de 20 GiB e lote de 4 GiB deixa 155942543033 bytes. O ponto nacional
compacto ponderado é 193092144007.5 bytes lógicos e 197122369024 alocados; o cenário
de maior razão observada por estrato é 195806592270.4 bytes. Duração sequencial nas
médias primárias seria 17.179 dias. São cenários, não intervalos de confiança,
garantias ou reservas para derivadas. Crescimento da coleta é hipótese, não limite
do primeiro turno. A execução nacional não cabe nesse cenário mesmo sem nova cópia bruta.

## Aceitação e dependências

Testes cobrem históricos grandes em fluxo, identidade, corrupção, isolamento de
turno/escopo, limites de saída/temporários/HDD, travas, retomada, diagnósticos em
fluxo, reprodução compacta integral, efeito real de lotes, rejeições por recursos,
seleção por ruído/platô, hashes, espera e contabilização de saída interrompida.
Guia pareado, links README/índice, planos e handoffs integram a aceitação. Quarenta testes direcionados passaram; Ruff, formatação, documentação pareada e
comandos passaram (238 comandos, 14 consultas SQL, 19 invocações de ajuda). A
verificação atual e a aceitação final ficam em `data/national/phase11-acceptance-2026-10-31/`.

Não congele populações incompletas do primeiro turno. Aguarde o tamanho concluído,
revise disco/derivadas, propague inspeções e conecte produtores operacionais,
eleitorais e de modelos entre objetos antes de afirmar pipeline nacional. São
condições explícitas restantes, não capacidades da análise estrutural. Ferramentas
e benchmarks ampliados são reais; a meta nacional de dois turnos não está concluída
e este handoff não despacha outra fase.

```sh
rtk proxy .venv/bin/python -B -m unittest discover -s tests -p 'test_national*.py' -q
rtk proxy .venv/bin/python -B -m election_audit.national_benchmark --help
rtk proxy .venv/bin/python -B -m election_audit.national_tuning prepare --help
rtk proxy .venv/bin/python -B -m scripts.check_docs
rtk proxy .venv/bin/python -B -m scripts.check_doc_commands
```

## Continuação no novo disco — em execução, não concluída

O diretório dedicado agora pertence ao usuário; prova de escrita com fsync e
verificações nativas de montagem/capacidade passaram. O volume resolve a limitação
anterior. Saída do segundo turno tem teto de 256 GiB, incluindo 2 GiB de metadados;
há reserva separada de 256 GiB para futuras derivadas do primeiro e piso de 20 GiB.
O HDD original mantém cenário de coleta de 85 GiB mais piso de 20 GiB; o SSD mantém
reserva de 10 GiB e temporários de 8 GiB. Somam-se obrigações no mesmo volume com a
maior reserva, uma vez. São orçamentos, não garantias para derivadas incompletas.
Não foram movidos/apagados originais ou dados alheios; o coletor segue intacto.

O ajuste no disco concluiu seis tentativas novas em 134.158 segundos, com seis
fontes não AC já inspecionadas. Lote 2048 permaneceu melhor observado: mediana
5702.844 eventos/s contra 5403.572 (8192) e 1500.777 (32768); máximo RSS agregado
observado 172212224 bytes. Resumos/contagens integrais coincidiram. Não se afirma
melhora de lote maior nem ótimo global. Estudo/revisão estão em
`data/national/phase11-new-drive-tuning-2026-10-31/`.

O lote real inicial concluiu 256 objetos e 2603602 eventos em 206.947 segundos após
preparar metadados: 183 reutilizações e 73 checkpoints novos (31174656 bytes alocados),
sem falhas/parcialidade/problemas. Os novos registraram 83.429 segundos para 754471
eventos; maior HWM registrado nos checkpoints foi 124272 KiB. Todos os fluxos novos
foram reproduzidos/verificados; nenhum registro de trabalho protegido existe.
Os 256 alvos foram registrados conservadoramente antes dos corpos em
`execution/initial-tranche-inspection.json`; propague com históricos anteriores a
locais estáveis/nos dois turnos. Mistura de cache não estima duração nacional.
Artefatos iniciais e configuração imutável são preservados; sua revisão registra o
hash auxiliar inicialmente omitido. A produção final congela scripts auxiliares e
locks, referenciando checkpoints iniciais validados sem copiar dados brutos.

A configuração ativa está em
`data/national/phase11-new-drive-2026-10-31/production/`, trabalho
`3016f117a075e64281fe8730e254e47bcf5e6cd0d76790a93506a12c78ad72dc`, subárvore
`election-audit/2026/runoff-production`. Seus 58 arquivos congelados incluem os
auxiliares dos adaptadores; regressão verifica origem das importações. Use
`production/run_frozen.py` para consultar/retomar; verifica a cópia antes de importar.
Ainda exige ambiente travado e raízes originais/reutilizadas. Cinquenta testes,
Ruff, formatação e documentação/comandos pareados passaram.

Escopo: 499177 observações, 596 exclusões protegidas/estresse e 498581 objetos únicos
elegíveis. Aliases de bytes protegidos também são excluídos antes de corpos/cache.
`iter_observations` preserva observações; contagens adiadas, pendentes e falhas são
nulas. Análise parcial e indisponibilidade científica ficam explícitas. Não se
processa população do primeiro turno nem fase posterior. Pré-processamento não
afirma teste intocado; históricos prévios e impacto original continuam obrigatórios.

Supervisor GNU time e trabalhador ficam em `current-launch.json`; cópias agregadas
`production/progress.json`, `processing.log` e `monitor-latest.json` mostram estado.
O relatório time finaliza ao encerrar a tentativa. SQLite WAL ativo exige consulta
no host; o volume somente leitura do agente pode falhar, então leia progresso no
workspace e nunca use `immutable=1` nesse registro. Sondagem limitada em fonte de
desenvolvimento encontrou verificação externa lenta no fuseblk antigo; não é nova
tentativa de processamento nem prova de duração nacional. As saídas iniciais estão
verificadas; meça separadamente o progresso de produção. O trabalho está em execução;
a população pendente não é análise nacional concluída. Fases posteriores/marimo
seguem pausados e o coletor do primeiro turno permanece independente.

## Migração de fontes copiadas sem supervisão (1 de novembro de 2026)

A execução noturna atual está em `data/national/phase11-overnight-2026-11-01/`.
Ela aguarda todas as identidades registradas de PID/início do rsync e só aceita
cada turno copiado após um snapshot SQLite consistente do manifesto, tamanho e
SHA-256 de cada objeto único e uma segunda passagem apenas de stat para estabilidade.
Os hashes incluem originais protegidos como verificação cega de integridade; nenhum
conteúdo eleitoral é decodificado nessa etapa. Arquivos ausentes, cópias alteradas,
escritores relevantes inesperados, mudanças de montagem ou reservas interrompem a
execução. Não há reparo, exclusão nem retorno às fontes antigas. O processo pai não
consegue recuperar o código de saída de um rsync não filho já encerrado: estados
desconhecidos continuam desconhecidos; os hashes completos aceitam os dados copiados.
Descritores de processos não relacionados ocultos por ptrace não comprovam custódia
exclusiva contra escritores hostis.

Após a aceitação, a continuação fixada copia somente os 476 checkpoints de piloto
seguros já aprovados ainda necessários no disco antigo, verifica os fluxos físicos
e lógicos completos dos checkpoints elegíveis existentes, registra as duas raízes
realocadas, executa ajuste limitado novo em seis unidades regionais já inspecionadas
para desenvolvimento, congela um novo trabalho do segundo turno, valida uma retomada
de 25 objetos e continua o processamento estrutural do segundo turno. Os bytes dos
checkpoints/configurações congelados são preservados; aliases do registro estrito
resolvem referências antigas somente nos novos originais verificados. O primeiro
turno é registrado apenas para custódia. As 596 observações protegidas/de estresse e
aliases de conteúdo continuam excluídos antes de acesso semântico/cache; o histórico
de inspeção permanece obrigatório. Parciais do parser mantêm todos os diagnósticos e
continuam parciais; exceções operacionais interrompem imediatamente a sequência.

A execução mantém 4 GiB de RAM agregada, teto de 256 GiB de saída do segundo turno,
256 GiB para derivados futuros, piso de 20 GiB no HDD, reserva de 10 GiB no SSD e
8 GiB para temporários. A previsão de crescimento das fontes agora é zero para as
duas cópias concluídas. A memória da árvore de processos é limitada pelo teto de
3 GiB de espaço de endereçamento de um trabalhador mais as parcelas de supervisor
e margem; isso não constitui garantia de RSS por cgroup. O disco antigo ainda pode
ser lido para copiar esses derivados, mas os corpos das fontes originais são
resolvidos e verificados exclusivamente no disco novo. Preserve ambas as cópias
das fontes e as versões antigas congeladas até a aceitação da migração.

Execute este visualizador na raiz do repositório; Ctrl-C encerra só o visualizador:

```bash
rtk proxy .venv/bin/python -B data/national/phase11-overnight-2026-11-01/watch.py --watch
```

`overnight.log`, `current-launch.json`, `continuation-status.json` e, após o início,
`current-production.json` e `production/progress.json` registram etapa real, PID,
contadores e falhas. `migration-2026-11-01/` no destino contém os manifestos
consistentes, ledgers duráveis por lotes, certificados e o registro estrito de
realocação. `continuation-ready.json` fixa todo o runtime congelado e a configuração
antes da execução automática. Nenhum interpretador em execução importa alterações
posteriores do checkout. Uma retomada exige o mesmo plano fixado e arquivos aceitos;
identidades inode/stat antigas, ledgers alterados ou cópias de checkpoints não
publicadas param para revisão. Não execute o launcher antigo de produção congelada:
ele preserva as raízes antigas. Iniciar ou retomar não conclui a análise nacional.
