# Índice de implementação

Document-ID: EA-IMPLEMENTATION-INDEX · Revision: 36 · Language: pt-BR

[English](../en/implementation-index.md)

Este é o único ponto de entrada sobre o estado atual. Ele diz o que existe, o que
de fato foi executado, onde estão os resultados e qual é o próximo passo. Os guias
em `docs/pt-BR/` descrevem o comportamento de cada ferramenta. Os handoffs em
`docs/pt-BR/handoffs/` são registros datados do que cada tarefa fez na época;
leia-os para detalhes, não para saber o estado. Os planos ficam em `research/`.
O estado abaixo é de **9 de novembro de 2026**.

## Estado atual

**Coleta (Fase 10): concluída nos dois turnos.** O coletor baixou todas as versões
de log anunciadas pelos endpoints por seção do TSE.

| Turno | Pleito / eleição / data | Execução concluída (UTC) | Versões de log | Agregadas | Sem log listado | Arquivo auxiliar não publicado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3220 / 6257 / 2026-10-04 | 2026-10-31 23:27 | 499176 | 17931 | 31 | 41 |
| 2 | 3221 / 6258 / 2026-10-25 | 2026-10-29 22:56 | 499177 | 17931 | 30 | 41 |

Os pacotes do primeiro turno estão todos `Totalizado`; o segundo turno tem 488333
`Totalizado` e 10844 `Recebido`. Por causa das seções sem log e sem arquivo auxiliar,
nenhuma das execuções atende ao critério `national_coverage` do coletor; essas seções
permanecem lacunas explícitas. Em 1º de novembro os dois acervos brutos (53722200971
e 90643145031 bytes) foram copiados para o volume de saída, e cada objeto foi
verificado por SHA-256. As cópias são os originais de referência para o
processamento derivado; os manifestos em `.local-state/` foram preservados sem
alteração. Em 3 de novembro os metadados das raízes do HDD antigo foram arquivados
com hashes e seus objetos brutos, duplicatas das cópias certificadas, foram
liberados para exclusão.

A mudança de disco não exigiu reescrever manifestos: os caminhos nos manifestos são
relativos à raiz de objetos (`objects/xx/<sha>.<ext>`), e o `manifest-location.json`
de cada nova raiz aponta para seu manifesto no SSD (`.local-state/tse-2026.sqlite`
no segundo turno, `.local-state/tse-2026-t1-verified.sqlite` no primeiro). As cópias
certificadas `migration-2026-11-01/manifest-r{1,2}.sqlite` batem com os hashes dos
certificados e, em 3 de novembro, suas linhas de files, logs, sections e runs se
mostraram idênticas às dos manifestos vivos no SSD. As análises fixam as cópias
certificadas. Sobras a ignorar: `raw/2026/turno-2/manifest.sqlite` é o banco obsoleto de
antes da separação; `.local-state/tse-2026-t1.sqlite` é um manifesto do primeiro
turno superado; e `migration-2026-11-01/status.json` mostra `FAILED_STOPPED` porque
o job encadeado depois da cópia verificada foi parado, não porque a cópia falhou.

**Processamento estrutural (Fase 11): concluído no escopo elegível do segundo
turno.** O job de resumos orientados a features processou todos os 498581 objetos
elegíveis (499177 observações menos 596 observações protegidas/de estresse e seus
aliases de conteúdo), com 0 falhas, em 35992 segundos, com três trabalhadores
dentro do orçamento de 4 GiB / metade da CPU. 498575 objetos foram analisados por
completo e 6 parcialmente (190 erros retidos). Foram percorridos 5032537448 eventos
estruturais; cerca de 90% estão em classes de mensagem que o parser estrutural deixa
como `unknown`. A release publicada
`55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88`
(`source-summary-analysis-release-v1`, 546,6 MB de Parquet) guarda contagens por
log, estrutura de membros e hashes de blocos; os 68,8 GB de checkpoints agrupados
ficam só para recuperação e evidência.

Para que ela não serve: cada `logd.dat` do segundo turno vai da preparação em
setembro, passando pelo primeiro turno, até o segundo turno, então as contagens de
habilitações e conclusões por log (252940011 e 252882361 no total) misturam turnos e
não são medidas do segundo turno. Não há sessões, relógios nem tempos. Os 596 logs
protegidos/de estresse e todo o primeiro turno não foram processados. Toda medida
operacional precisa da passada semântica da Fase 21.

A Fase 11 leu 91.5 GB de objetos pequenos a cerca de 2.5 MB/s com 94% de pressão
de E/S, enquanto gravava checkpoints no mesmo disco. O benchmark de 3 de novembro
(`stage-sources benchmark`, janelas de 2000 objetos, os dois turnos) achou a causa:
a ordem de leitura. As cópias certificadas foram gravadas em ordem de caminho, então
a ordem de seção (URL do manifesto) lê a 1.9–3.5 MB/s, a ordem de caminho a
41–61 MB/s e a ordem física (FIEMAP) a 73–92 MB/s.

**Cópia para o SSD (3 de novembro): concluída nos dois turnos.** Todo objeto bruto
foi copiado em ordem física para `~/data/election-audit-stage/2026/turno-1/` e
`turno-2/` (998412 e 998413 objetos, 53722200971 e 90643145031 bytes); cada corpo de
origem foi conferido com o SHA-256 do manifesto certificado e depois cada corpo
copiado foi recalculado no SSD. As cópias levaram 931 s e 1587 s (cerca de
57 MB/s), as reverificações 954 s e 1431 s; 86 minutos no total. Cada raiz guarda
sua cópia do manifesto, um ledger e um `staging-certificate.json` vinculado ao hash
do manifesto certificado. O diretório home é eCryptfs, então um único leitor
reverifica a apenas 56–63 MB/s. O
[plano de conclusão](../../research/completion-plan.pt-BR.md#regras-de-recursos-e-es)
define as regras de E/S para a próxima passada.

**Fase 19 (entradas nacionais): concluída; documentos do teste de integridade amostrados.** `bulk-download` baixou, com
SHA-256/SHA-512 e o JSON do catálogo do TSE, o BWEB de 2026 e de 2022 (112
arquivos por ano, todos os 56 por ano coincidindo com o `.sha512` publicado).
Os 12 conjuntos
de entradas pequenas (BWEB e resultados de 2026 e 2022, perfil do eleitorado e
locais de votação, correspondências de mídias dos dois turnos de 2026 e 2022, logs
GEDAI de 2026 dos dois turnos) estão completos em `~/data/election-audit-stage/inputs/`,
com todo `.sha512` publicado coincidindo. O CDN pode servir cópias antigas em cache
para HEAD ou GET, então `bulk-download` revalida com um parâmetro descartável e
continua exigindo ETag e tamanho coincidentes. Os relatórios de totalização são
recompactados a cada poucas horas e mudam após retotalizações; veja a
[referência de aquisição](acquisition-reference.md#relatórios-de-totalização-mudam-com-o-tempo).
Os arquivos em massa de BU/RDV/log (56 por ano; 2026: 219.2 GB, 2022: 168.5 GB)
estão completos em `bulk/` no volume de saída, e `bulk-download verify` recalculou
os hashes dos 112 contra seus manifestos em 2026-11-04 (o TSE não publica `.sha512`
para eles).
`results-hierarchy` baixou a hierarquia EA20 da eleição presidencial nos dois turnos
(BR, 27 UFs e ZZ, 5757 municípios e os arquivos de andamento: 5815 arquivos por
turno, todos finais); o ZZ do primeiro turno foi regerado em 2026-10-24. Os hashes
dos manifestos certificados estão fixados em
`election_audit/resources/pins/certified-manifests-2026.json` e as duas cópias foram
conferidas contra eles. Os documentos do teste de integridade não são dados abertos
e os sites dos TREs recusam requisições automatizadas, então um navegador coletou
uma amostra de dez tribunais (SP, AC, AL, DF, ES, PR, MG, RJ, BA, RS):
`integrity-docs` arquivou 125 documentos, todos iguais ao hash do navegador
([referência de aquisição](acquisition-reference.md#documentos-do-teste-de-integridade-sites-dos-tres)).
Veja o [handoff da Fase 19](handoffs/task-19.md).

**Fase 20b (conclusão da integridade): em andamento.** O Ed521 está implementado
(`election_audit/ed521.py`, confirmado com o verificador do pacote de formatos de
2026 do TSE) e roda no país todo pelo [`ed521rs`](https://pypi.org/project/ed521rs/),
cujos veredictos são iguais aos do Python puro em toda linha e aos do ECPy em toda
assinatura. BU, RDV e arquivos de assinatura são decodificados com as especificações
oficiais de 2026 do TSE. Os certificados das urnas são conferidos contra as ACs
publicadas `AC URNA`, `AC UE2020` e `AC UE2022` e suas listas de revogados. A nova
execução nacional
(`~/data/election-audit-stage/phase20/national-r{1,2}-sections-v3-20261106/`)
verificou toda autoassinatura de hardware, 1996828 assinaturas de arquivos por turno
e 997114 e 539817 assinaturas da cadeia do BU, sem falha; todo certificado de urna é
assinado pela sua AC e nenhum está revogado. Em 14 e 3 seções outra urna assinou os
arquivos ([O13](observations.md#operação)). As tabelas por seção foram reconstruídas
como versão 3 (`table-2026-v3-20261107/`, `table-2022-v3-20261106/`): onze
municípios do Amazonas no horário do Acre estão fixados com suas fontes
([O12](observations.md#operação)) e nenhuma seção fica sem regra de encerramento.
A releitura por prefixo do I6 (`integrity-check prefix`, 7 de novembro,
`~/data/election-audit-stage/phase20b-i6/national-v1-20261107/`) releu 496793 logs
do segundo turno sem erro: todo último bloco aberto do 1º turno é prefixo exato da
sua cópia no segundo turno (493125 seções agora totalmente iguais). Dos 113 pares de
blocos que ainda diferem, 112 têm as mesmas linhas com limites de bloco diferentes,
porque linhas de reinício escritas antes do registro na MI e na ME faltam em algumas
cópias ([O14](observations.md#operação)); um, rj/60011/0008/0061, é uma divergência
real entre três cópias do dia de eleição de uma urna, e o log publicado do 1º turno é
o que concorda com o BU ([O15](observations.md#operação)).
O I8 (`integrity-check printed`, 7 de novembro,
`~/data/election-audit-stage/phase20b-i8/v1-20261107/`) conferiu as 528 cópias
impressas de BU lidas de QR codes pela Totalização Paralela do CMInd e pela
Totalização paralela da Arvor (518 seções, 49 no 1º turno, 469 no segundo turno):
toda cadeia de hashes está íntegra, toda assinatura e todo certificado de urna
verificam, cada certificado é igual ao do arquivo de assinatura da seção, e todo campo
impresso é igual ao BU publicado. As coleções não são amostras. A lacuna municipal do
I2 está registrada na revisão 5 do protocolo.
A conciliação de I3/I5 está feita (7–8 de novembro). Os blocos do RDV de uma disputa
são somados (`integrity-sections-v4`), então o I3 é igual em toda disputa dos dois
turnos. As regras de sessão `sessions-v2` (`session-aggregates-v4`) mantêm o
contexto do turno em reinícios no meio do dia e tornam oficiais as sessões de urnas
deixadas ligadas durante a noite. O I5–I7 conta uma vez as cópias de memória de uma
sessão (`integrity-logs-v2`, [O16](observations.md#operação)). Das 85 e 36
diferenças do I5, restam 10 e 7. Todas têm causa registrada, salvo
rs/89060/0017/0191, um ciclo abaixo; quatro logs cobrem só parte do dia de eleição
([O17](observations.md#operação)). A tabela de logs do 1º turno do DataUrnas-BR marca
as mesmas seções com as mesmas contagens, salvo o fluxo quebrado da O15, que ele lê
inteiro. As passadas semânticas, a releitura por
prefixo do I6 e as tabelas por seção (versão 4) foram refeitas com as novas regras;
os arquivos de resultados e de unidades não mudam.
As verificações trazidas do DataUrnas-BR rodaram no país todo em 8–9 de novembro. O
próprio verificador Ed521 do DataUrnas-BR concordou com todo veredito (3193786 e
2827813 assinaturas, 0 divergências). Nenhuma zerésima vem depois de um voto; a única
seção reprovada em Z1 por turno é uma seção da O17 cuja primeira urna não está no
pacote, e várias zerésimas por seção vêm de reinícios e substituições antes da votação
([O18](observations.md#operação)). O GEDAI casou as cargas de urna de 498444 e 498388
seções; 482 seções em três zonas e 284 em outras três não podem ser verificadas porque
os logs de preparação dessas zonas não foram publicados
([T11](observations.md#transparência)), e 281 e 337 seções são reprovadas em G1, a
maioria em sp/0176. Todo nome de pacote verificado nos logs está nas listas de hash do
TSE, exceto sete arquivos da mídia de carga e da carga
([T12](observations.md#transparência)); 86 linhas de verificação na inicialização
terminaram em `ERRO` ([O19](observations.md#operação)). Os 5786 arquivos de resultado
assinados com JWS por turno verificam com a chave oficial do TSE e são iguais ao
snapshot EA20. O passe semântico `session-aggregates-v5` acrescenta as tabelas de
marcadores e de pacotes que essas verificações leem e é igual à versão 4 no resto.
Veja o [handoff da Fase 20b](handoffs/task-20b.md), o
[guia das verificações de integridade](integrity-checks.md#fase-20b-verificações-trazidas-do-dataurnas-br),
sua [seção de assinaturas](integrity-checks.md#fase-20b-assinaturas-e-certificados),
sua [seção da conciliação](integrity-checks.md#fase-20b-regras-de-sessão-v2-e-a-reconciliação-do-i3i5),
sua [seção do prefixo do I6](integrity-checks.md#fase-20b-releitura-por-prefixo-do-i6) e
sua [seção do I8](integrity-checks.md#fase-20b-bus-impressos-do-i8).

**Fase 22 (tabela por seção v2): concluída para 2026 e 2022.** A passada semântica
`session-aggregates-v3` acrescenta modelo da urna, software e evidência de relógio
por sessão. Ela rodou no país todo nos dois anos e turnos sem erros, e toda coluna
em comum com as versões anteriores é igual em todas as linhas
([passada semântica](semantic-pass.md#versão-3-fase-22)). `section-table build`
gravou 998496 linhas de seção em 499248 unidades harmonizadas para 2026 e 945386
linhas em 472693 unidades para 2022, em `~/data/election-audit-stage/phase22/table-{2026,2022}-20261106/`.
Cópias de uma sessão na memória interna e na externa contam uma vez. Os relógios são
julgados pelos horários legais de encerramento, com o Amazonas resolvido pelos
encerramentos que as urnas imprimem. Toda unidade mantém a mesma seção principal nos
dois turnos. Resultados e medidas operacionais ficam só em `restricted/` e não foram
lidos. Os dois itens em aberto foram resolvidos na Fase 20b: seis das oito
diferenças de modelo do 1º turno são arquivos de assinatura assinados por outra
urna, e as seções do Amazonas sem regra de encerramento agora a tiram da lista de
municípios no horário do Acre (tabelas versão 3, abaixo). Veja o
[guia da tabela por seção](section-table.md#resultados-nacionais), o
[registro de observações](observations.md) e o [handoff da Fase 22](handoffs/task-22.md).

**Fase 21 (passada semântica): concluída nos dois turnos de 2026 e em 2022.** `semantic-pass` coincidiu com o adaptador por evento em 400 de 400
objetos do AC amostrados (84469 ciclos concluídos). As execuções nacionais
processaram 498580 objetos do primeiro turno e 498581 do segundo, sem erros
(1704924 e 3393756 sessões), em
`~/data/election-audit-stage/phase21/national-r{1,2}-20261103/`. O registro da
população reconcilia cada uma das 499207 seções por turno: 31 e 29 seções foram
apuradas pelo Sistema de Apuração (SA) de contingência e não têm log da urna, uma
seção de SP do segundo turno foi publicada sem log e 596 são excluídas. `sa-logs`
baixou os 60 logs SA (idênticos byte a byte aos arquivos em massa) e atribuiu cada
um à sua seção ([logs SA](semantic-pass.md#logs-de-apuração-de-contingência-sa)). As versões de
2026 são `session-aggregates-v1`; o código atual grava v2 (colunas de segundos de 64
bits) e reproduziu exatamente as linhas do AC dos dois turnos. Para 2022 (o controle
negativo), um leitor 7z só com a biblioteca padrão e regras de 2022 revisadas
(`tse-real-log-rules-2022-v1`) alimentam um modo em massa sobre os arquivos de 2022
que recusa 2026. Ele coincidiu com o adaptador em 200 de 200 objetos do AC por
turno e então processou 471859 e 471983 objetos sem erros (1805887 e 3570943
sessões) em
`~/data/election-audit-stage/phase21/national-2022-r{1,2}-v2-20261104/`. O registro
de 2022 contabiliza cada seção dos arquivos (472024 e 472027). As análises comparam
a habilitação biométrica com todas as outras (plano de análise rev. 3). Veja o
[guia da passada semântica](semantic-pass.md#logs-de-2022) e o
[handoff da Fase 21](handoffs/task-21.md).

**Fase 20 (verificações de integridade de nível 1): concluída para 2026, nos dois
turnos.** `integrity-check` executou I1–I9 sobre as 499207 seções de cada turno em
`~/data/election-audit-stage/phase20/national-r{1,2}-*-20261105/`. Todo arquivo
publicado de BU, RDV e imagem coincide com as duas listas de hashes assinadas; as
assinaturas ECDSA das urnas UE2013/UE2015 foram verificadas em 99985 e 99957 seções
sem falha, enquanto as 399222 e 399250 seções Ed521 (UE2020/UE2022) não são
verificadas. Toda cadeia de hash do BU está íntegra; toda disputa presente no BU e
no BWEB é igual; toda medida de voto do EA20 é igual às somas do BWEB nos 5786 nós;
e toda urna efetivada nas correspondências é igual ao seu BU. A recontagem do RDV só
difere em duas seções SA de MG (20 eleitores cada, primeiro turno). Em aberto: 85 e
36 diferenças de comparecimento no I5, 99 logs do segundo turno com um bloco do
primeiro turno que difere (I6), regras do I7 violadas em 2138 e 1815 seções, Ed521 e
I8. Ver o [guia das verificações de integridade](integrity-checks.md#resultados-nacionais)
e o [handoff da Fase 20](handoffs/task-20.md).

**Fases 12–18: encerradas como pilotos de desenvolvimento do Acre (AC).** A revisão
metodológica de 3 de novembro substituiu suas definições; o trabalho revisado são as
Fases 19–26. Suas ferramentas existem, foram exercitadas com dados reais do AC e são
reutilizadas, mas nada foi executado em escala nacional:

- Fase 12: 2270 seções do segundo turno no AC com conteúdo verificado entre BU binário
  e BWEB; os totais da UF batem. Assinaturas, recontagem de RDV e hierarquia nacional
  não foram feitas.
- Fase 13: adaptador de mensagens reais (`real-operational-v1`) executado em um log
  do AC por turno. Relógios absolutos e conciliação de comparecimento não foram feitos.
- Fase 14: 2270 unidades do AC, 54480 linhas de features, 668 grupos de locais no
  mesmo turno. Sem identidade entre turnos e sem features eleitorais do primeiro turno.
- Fase 15: protocolo do AC congelado (treino 1259, calibração 399, teste protegido
  340, estresse municipal 256, inspecionadas em desenvolvimento 16).
- Fase 16: um ajuste de comparecimento no AC (variante `no_first_round`) avaliado só
  com dados de calibração. O conjunto de teste protegido não foi aberto.
- Fase 17: 126 pacotes de casos de desenvolvimento do AC (20 + 20 ranqueados, 86
  controles não sinalizados).
- Fase 18: quatro notebooks marimo sobre a exportação do AC; QA no navegador não feito.

Não existe resultado eleitoral nacional, margem nacional, modelo nacional ajustado
nem rótulo de fraude.

**Verificações.** A verificação offline completa `just check` passa (lock, formato,
lint, verificação de tipos, contratos, documentos, comandos documentados e todos os
427 testes). Toda função em `election_audit/`, `scripts/` e `tests/` tem anotações
de tipo (ruff `ANN`) e `ty check` (fixado em 0.0.94) não relata diagnósticos; as
convenções estão em `CLAUDE.md`.

## Próximo passo

Fechar as pendências da Fase 20b, condição para o congelamento da Fase 23: uma regra
por sessão para as urnas que registraram erro de assinatura de programa (alguma
registrou votos depois?), as 13 e 70 seções isoladas reprovadas em G1 no GEDAI e
sp/0176, e a lista de revogação do JWS. Depois, registrar no protocolo as verificações
de zerésima, GEDAI, listas de hash e JWS com as lacunas que não puderem ser fechadas
([handoff](handoffs/task-20b.md)). A resposta do TSE ao pedido dos
certificados raiz (protocolo 83529705172533) é devida até 25 de novembro de 2026.
Arquivar o relatório
consolidado do TCU sobre o teste de integridade quando for publicado (previsto até
30 dias após o segundo turno). O
[protocolo do estudo](../../research/analysis-plan.pt-BR.md) (Revisão 7) define as
afirmações, o mapa de ameaças e observáveis, as verificações de integridade I1–I9, os
testes confirmatórios C1–C6, o estudo de poder e a política de dados; o
[plano de conclusão](../../research/completion-plan.pt-BR.md) (Revisão 14) define as
Fases 19–26. O protocolo é um rascunho até ser congelado e pré-registrado
publicamente na Fase 23.

## Regras de trabalho

Leia o `CLAUDE.md` do repositório, este índice, o handoff atribuído e só os
contratos relevantes. Execute uma fase por vez. Após cada tarefa numerada, escreva
um handoff em pares a partir do [modelo](task-handoff-template.md) e atualize este
índice nos dois idiomas. Mantenha o processamento dentro de metade da CPU, 6 GiB de
RAM agregada (4 GiB até 5 de novembro de 2026) e uma thread de biblioteca por processo.

As 596 observações protegidas/de estresse do segundo turno ficam excluídas antes de
qualquer acesso semântico ou a cache. Os históricos de inspeção em
`data/phase15/inspection.sqlite`, `data/national/phase11-protection-2026-10-31/` e
nos registros das parcelas da Fase 11 continuam vinculantes: qualquer local listado
neles é dado de desenvolvimento, nunca teste intocado. Identidade ausente entre
turnos permanece indisponível.

## Estado das fases

As tarefas de fundação 1.1–9.4 estão concluídas. Aceite (29 de outubro de 2026):
166 testes offline, lock, Ruff, contratos e verificação de documentos em pares; um
piloto real congelado em cinco regiões (AC/AL/DF/ES/PR) com todas as sessões, ciclos
e relógios não resolvidos. A tarefa 7.1 depois acrescentou o adaptador oficial BWEB
com verificações aritméticas reais do AC (177 testes).

| Tarefa | Entregas | Handoff |
| --- | --- | --- |
| 1.1 | Python 3.14, uv lock, pacote/CLI, DuckDB/PyArrow | [1.1](handoffs/task-1.1.md) |
| 1.2 | Ruff, formatação mecânica dos legados | [1.2](handoffs/task-1.2.md) |
| 1.3 | Receitas just, onboarding em pares, índice/modelo | [1.3](handoffs/task-1.3.md) |
| 2.1 | 30 contratos dimensionais, dicionário, linhagem, uniões seguras | [2.1](handoffs/task-2.1.md) |
| 2.2 | 21 contratos de features/prontidão, denominadores e bloqueios | [2.2](handoffs/task-2.2.md) |
| 2.3 | Traduções em pares de pesquisa/coleta, glossário/diagramas, verificação de docs | [2.3](handoffs/task-2.3.md) |
| 3.1 | Inventário de origem somente leitura, isolamento do WAL, desconhecidos históricos explícitos | [3.1](handoffs/task-3.1.md) |
| 3.2 | Índices esperados congelados, cobertura de membros/principais e seleção limitada | [3.2](handoffs/task-3.2.md) |
| 3.3 | Cópias imutáveis atômicas, CLI de snapshot/inspeção, proveniência congelada e guia | [3.3](handoffs/task-3.3.md) |
| 4.1 | Decodificação limitada de JEZ/ZIP aninhados, CRC e localizadores de membros duplicados | [4.1](handoffs/task-4.1.md) |
| 4.2 | Eventos estruturais ordenados, relógios ingênuos, diagnósticos limitados e seguros | [4.2](handoffs/task-4.2.md) |
| 4.3 | Cache de parse imutável verificado, associações congeladas, CLI/API e guia | [4.3](handoffs/task-4.3.md) |
| 5.1 | Contextos candidatos/oficiais, identidades separadas, linhagem exata de blocos copiados | [5.1](handoffs/task-5.1.md) |
| 5.2 | Máquina de estados anônima de habilitação/conclusão/suspensão/cancelamento | [5.2](handoffs/task-5.2.md) |
| 5.3 | Regras de relógio por seção/exterior com evidência, UTC/correções e continuidade | [5.3](handoffs/task-5.3.md) |
| 5.4 | Denominadores operacionais, shards imutáveis limitados/contexto compartilhado, CLI/API | [5.4](handoffs/task-5.4.md) |
| 6.1 | Releases DuckDB/Parquet imutáveis e limitadas, limites de recursos, current atômico | [6.1](handoffs/task-6.1.md) |
| 6.2 | Marts de cobertura/sessão/disponibilidade/voto tardio, incerteza de relógio | [6.2](handoffs/task-6.2.md) |
| 6.3 | Build/validação/consulta somente leitura/relatórios bilíngues | [6.3](handoffs/task-6.3.md) |
| 7.1 | Importações normalizadas e adaptador oficial BWEB fixado; aritmética real do AC verificada | [7.1](handoffs/task-7.1.md) |
| 7.2 | Derivados imutáveis presos ao pai, seleção canônica com evidência, conciliação | [7.2](handoffs/task-7.2.md) |
| 7.3 | Quatro marts eleitorais, SELECT limitado, validação e relatórios em pares | [7.3](handoffs/task-7.3.md) |
| 8.1 | Registro versionado de 21 contratos de features e saídas descritivas em fluxo | [8.1](handoffs/task-8.1.md) |
| 8.2 | Partições de locais estáveis revisados com semente, estratos e reservas municipais | [8.2](handoffs/task-8.2.md) |
| 8.3 | Ledgers imutáveis de protocolo/exploração/investigação/cenário e histórico de acesso ao teste | [8.3](handoffs/task-8.3.md) |
| 9.1 | Passo a passo sintético offline, quatro estágios imutáveis e relatórios em pares | [9.1](handoffs/task-9.1.md) |
| 9.2 | Piloto diagnóstico real congelado em cinco regiões | [9.2](handoffs/task-9.2.md) |
| 9.3 | Pacotes de revisão relocáveis, releitura congelada/digests lógicos | [9.3](handoffs/task-9.3.md) |
| 9.4 | Reinício limitado verificado e guia de backfill/armazenamento | [9.4](handoffs/task-9.4.md) |

| Fase | Estado | Pendências | Handoff |
| --- | --- | --- | --- |
| 10 | Concluída: dois turnos coletados, copiados e verificados por SHA-256 | Seções com lacuna continuam explícitas; BWEB, cadastros e fontes de RDV/assinatura de outras UFs são importações separadas | [10](handoffs/task-10.md) |
| 11 | Concluída no escopo elegível do segundo turno (498581 objetos, 0 falhas) | Logs protegidos lidos só depois do congelamento da Fase 23 | [11](handoffs/task-11.md) |
| 12 | Só AC: 2270 seções com conteúdo verificado, totais da UF batem | Outras UFs, dois turnos, assinaturas, RDV, hierarquia BR/UF/municipal/ZZ | [12](handoffs/task-12.md) |
| 13 | Amostra do AC: um log por turno | Sessões, relógios, históricos copiados e conciliação de comparecimento nacionais | [13](handoffs/task-13.md) |
| 14 | Só AC: 54480 linhas de features | Features nacionais, identidade entre turnos, resultados do primeiro turno | [14](handoffs/task-14.md) |
| 15 | Protocolo do AC congelado | Substituída pelo congelamento e pré-registro da Fase 23 | [15](handoffs/task-15.md) |
| 16 | Ajuste de desenvolvimento de comparecimento no AC | Família completa de alvos/variantes, simulações com reajuste, avaliação final | [16](handoffs/task-16.md) |
| 17 | Pacotes de casos de desenvolvimento do AC | Casos nacionais, corroboração, limites de impacto, sensibilidade do pipeline completo | [17](handoffs/task-17.md) |
| 18 | Notebooks sobre a exportação do AC | QA no navegador, conjuntos de dados nacionais | [18](handoffs/task-18.md) |
| 19 | Concluída: BWEB, arquivos de BU/RDV/log, perfil do eleitorado, correspondências, GEDAI, hierarquia EA20, manifestos fixados, dois turnos e 2022 | Documentos do teste de integridade dos 17 tribunais fora da amostra; relatório consolidado do TCU | [19](handoffs/task-19.md) |
| 20 | Concluída: I1–I9 para 2026, nos dois turnos, todas as seções; ECDSA verificada, BWEB, EA20 e correspondências concordam | Assinaturas Ed521, cadeias de certificados, releitura por prefixo do I6, diferenças em aberto do I5/I6, I8, 2022 | [20](handoffs/task-20.md) |
| 21 | Concluída: 2026 nos dois turnos (v1, reproduzida pela v2 no AC) e 2022 nos dois turnos (v2); os registros conciliam todas as seções; logs SA atribuídos | Agrupar sessões com várias execuções e regras de relógio passam para a Fase 22 | [21](handoffs/task-21.md) |
| 22 | Concluída: passada semântica v3 no país todo (2026 e 2022, igual às versões anteriores nas colunas em comum); tabelas por seção dos dois anos com mapeamento entre turnos, regras de relógio e registro | Resultados e valores operacionais sem leitura até o congelamento; diferenças de modelo e regras de encerramento do Amazonas passam para a Fase 20b | [22](handoffs/task-22.md) |
| 20b | Em andamento: Ed521 verificado no país todo (`ed521rs`, igual ao verificador em Python puro), especificações oficiais do TSE, certificados das urnas conferidos contra as ACs publicadas e listas de revogados, tabelas por seção v3 com a lista do Amazonas, releitura por prefixo do I6 (todo bloco aberto é prefixo verificado; 112 de 113 pares divergentes explicados, O14/O15), I8 (528 cópias impressas, todas iguais), lacuna municipal do I2 registrada, I3/I5 conciliados (regras de sessão v2, cópias de memória contadas uma vez, I5 85/36 → 10/7, O16/O17; passadas semânticas, I6 e tabelas por seção v4 refeitos); verificações trazidas do DataUrnas-BR executadas (comparação do Ed521 com 0 divergências, zerésima v2, GEDAI v2 com T11, listas de hash com T12/O19, JWS todo verificado; passe semântico v5); pendências abertas; condição para o congelamento da Fase 23 | Raízes pedidas ao TSE | [20b](handoffs/task-20b.md) |
| 23–26 | Não iniciadas; definidas no [plano de conclusão](../../research/completion-plan.pt-BR.md#fases-revisadas) | Todas | — |

## Onde estão os resultados

Caminhos em `data/` são relativos ao repositório e ignorados pelo Git. Caminhos
absolutos ficam no volume de saída da máquina de referência
`/media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/`.

| Artefato | Local |
| --- | --- |
| Originais brutos dos dois turnos (cópias de referência) | `raw/2026/turno-1/`, `raw/2026/turno-2/` no volume de saída |
| Certificados de cópia, cópias certificadas dos manifestos (entradas da análise), ledgers de verificação | `2026/migration-2026-11-01/` no volume de saída |
| Cópia verificada por hash dos dois turnos no SSD (leia estas nas passadas de logs), com certificados | `~/data/election-audit-stage/2026/turno-1/`, `~/data/election-audit-stage/2026/turno-2/` |
| Benchmarks de ordem de leitura | `~/data/election-audit-stage/benchmarks/` |
| Entradas pequenas da Fase 19 (BWEB, resultados, perfil do eleitorado, correspondências, GEDAI), cada uma com catálogo, manifesto e estado | `~/data/election-audit-stage/inputs/<dataset>/` |
| Arquivos em massa de BU/RDV/log da Fase 19, 2026 e 2022 | `bulk/2026-arqurnatot/`, `bulk/2022-arqurnatot/` no volume de saída |
| Versões do `integrity-check` da Fase 20 (seções, BWEB, hierarquia, correspondências, logs), execuções de desenvolvimento do AC/ZZ | `~/data/election-audit-stage/phase20/` |
| Releitura por prefixo do I6 da Fase 20b (versões nacionais v1 e v2, execução de desenvolvimento do AC) | `~/data/election-audit-stage/phase20b-i6/` |
| Passadas semânticas v4 da Fase 20b (2026, 2022), amostras de equivalência do AC, tabelas por seção v4, logs e scripts das execuções | `~/data/election-audit-stage/phase20b-sessions/` |
| Tabelas do DataUrnas-BR usadas na conciliação de I3/I5, congeladas no commit `f5e8005` | `~/data/election-audit-stage/inputs/dataurnas-br-f5e8005-20261108/` |
| Comparação do Ed521 da Fase 20b; suas referências congeladas | `~/data/election-audit-stage/phase20b-ed521/`; `~/data/election-audit-stage/inputs/ed521-crosscheck-refs-20261108/` |
| Passadas semânticas v5 e verificações de zerésima da Fase 20b; verificações do GEDAI; verificação das listas de hash; arquivos e verificações JWS | `~/data/election-audit-stage/phase20b-zeresima/`, `phase20b-gedai/`, `phase20b-hash-lists/`, `phase20b-jws/` |
| Listas de hash e manual JWS do TSE (baixados num navegador); o arquivo da chave JWS | `~/data/election-audit-stage/inputs/tse-www-20261108/`, `tse-jws-key-20261108/` |
| BUs impressos do I8 da Fase 20b; suas entradas congeladas (CMInd, Arvor, manual de QR do TSE) | `~/data/election-audit-stage/phase20b-i8/`; `~/data/election-audit-stage/inputs/i8-cmind-20261107/`, `i8-arvor-20261107/`, `i8-tse-qrbu-20261107/` |
| Relatórios de equivalência, passada de desenvolvimento do AC, reprodução v2 do AC e passadas nacionais (2026 e 2022) da Fase 21 | `~/data/election-audit-stage/phase21/` |
| Passadas semânticas v3, tabelas por seção (2026, 2022), execuções de desenvolvimento do AC e seleção das raízes da Fase 20, da Fase 22 | `~/data/election-audit-stage/phase22/` |
| Pacote de formatos de 2026 do TSE (especificações, verificador de referência, certificados das ACs) e as cinco listas de revogados, congelados | `~/data/election-audit-stage/inputs/tse-format-docs-20261105/`, `~/data/election-audit-stage/inputs/tse-crls-20261105-complete/` |
| Logs SA (apuração de contingência) por turno e seu resumo por seção | `~/data/election-audit-stage/sa-logs/` |
| Resultados hierárquicos EA20 da eleição presidencial, dois turnos | `~/data/election-audit-stage/results-hierarchy/` |
| Documentos do teste de integridade, amostra de dez tribunais, com arquivos de registros do navegador; os downloads originais do navegador | `~/data/election-audit-stage/inputs/integrity-tests-2026-sample-20261104/`; `~/data/election-audit-stage/integrity-downloads-20261104/` |
| Manifestos originais da coleta (vivos) | `.local-state/` |
| Metadados da coleta no HDD antigo (cobertura, marcadores, manifesto obsoleto anterior à divisão) e o store por evento inicial da Fase 11 do AC, verificados por hash; os objetos brutos do HDD antigo duplicavam as cópias certificadas e foram liberados para exclusão em 3 de novembro de 2026 | `archive/old-hdd-2026-11-03/` no volume de saída |
| Logs de execução e registros de lançamento da coleta | `data/phase10/` |
| Release de resumos do segundo turno da Fase 11 | `2026/runoff-summary-analysis-full-20261102/` no volume de saída |
| Configuração, progresso e benchmarks do job da Fase 11 | `data/national/phase11-feature-oriented-2026-11-02/`, ponteiro `data/national/current-phase11.json` |
| Job em nível de evento substituído (parado em 2 de novembro com 15425 objetos) | `data/national/phase11-overnight-2026-11-01/`; não retome |
| Ajustes, parcelas, capacidade e revisões de proteção anteriores da Fase 11 | `data/national/phase11-*-2026-10-31/` |
| Demo, piloto e pacotes de revisão da fundação | `data/phase9/` |
| Importação oficial BWEB do AC | `data/official-bu/ac-runoff-2026-10-30/` |
| Artefatos de desenvolvimento do AC, Fases 12–17 | `data/phase12/` … `data/phase17/` |
| Conjuntos de dados dos painéis | `data/dashboard-ac-2026-10-30/`, `data/dashboard-development-2026-10-30/` |

## Mapa de interfaces

| Área | Módulos e guias |
| --- | --- |
| Ambiente | `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked` |
| CLI | `election_audit/cli.py`. Legados: `download resume inspect doctor`. Pipeline: `snapshot snapshot-inspect parse reconstruct build validate query report import-results analyze demo pilot reproduce review-bundle backfill`. Extensões: `national electoral-verify operational-review features research-protocol research-models investigations dashboard dashboard-export stage-sources bulk-download semantic-pass sa-logs results-hierarchy integrity-docs integrity-check section-table` |
| Receitas | `justfile`; uma receita por comando da CLI, mais `setup doctor fmt lint test contracts-check docs-check docs-command-check check` |
| Coleta | `scripts/download_tse_logs.py` (`--round 1` ou `--round 2`), `election_audit/elections.py`; cópia para SSD `source_staging` (`stage-sources`); arquivos de dados abertos `bulk_acquisition` (`bulk-download`); hierarquia EA20 `results_hierarchy` (`results-hierarchy`); documentos do teste de integridade dos TREs `integrity_documents` (`integrity-docs`); hashes fixados dos manifestos certificados `resources/pins/`; [referência de coleta](acquisition-reference.md) |
| Snapshot/origem/cobertura | `source_inventory`, `coverage`, `snapshots`; [snapshots](snapshots.md) |
| Parse estrutural | `archive_parsing` (`jez-structural-v1`), `sevenzip` (logs 7z de 2022); [parse de arquivos](archive-parsing.md) |
| Reconstrução operacional | `reconstruction` (`operational-v1`), `operational_review` (`real-operational-v1`, Fase 13), `semantic_pass` (`session-aggregates-v5`, regras de sessão `sessions-v2`, Fases 21–22 e 20b; regras `real-log-rules.json` e `real-log-rules-2022.json`), `sa_logs` (`sa-log-summary-v1`); [reconstrução](reconstruction.md), [passada semântica](semantic-pass.md) |
| Releases operacionais | `publication`, `operational_marts`, `release_tools`; [publicação](publication.md) |
| Processamento estrutural nacional | Caminho de resumos: `national_parallel`, `national_summary`, `national_summary_release`, `national_summary_tools`, `national_summary_tuning`, `national_resources`; [processamento orientado a features](feature-oriented-processing.md). Caminho em nível de evento: `national_benchmark`, `national_tuning`, `national_workload`, `national`, `national_storage`, `national_relocation`, `national_migration`, `national_overnight`; [processamento nacional](national-processing.md) |
| Verificações de integridade | `integrity_checks` (`integrity-sections-v4`, `integrity-logs-v2`; formato de assinatura `resources/assinatura-2026-observed.asn1`), `round1_prefix` (`integrity-round1-prefix-v1`, `integrity-check prefix`), `printed_bu` (`printed-bu-v1`, `integrity-check printed`), `ed521_crosscheck` (`ed521-crosscheck-v1`), `zeresima` (`integrity-zeresima-v2`), `gedai` (`integrity-gedai-v2`), `hash_lists` (`integrity-hash-lists-v1`), `signed_results` (`signed-results-fetch-v1`, `integrity-jws-v1`; `results-hierarchy fetch-signed`); [verificações de integridade](integrity-checks.md) |
| Importação e verificação eleitoral | `electoral_imports`, `electoral_results`, `derivatives`, `electoral_reports`, `official_bu`; `binary_bu` e `electoral_verification` (Fase 12); [resultados eleitorais](electoral-results.md). `electoral_references` é um protótipo sem integração na CLI e sem testes para conjuntos de referência oficiais |
| Fundação analítica | `analysis`, `analysis_partitions`, `analysis_ledgers`, `analysis_reports`; [análise](analysis.md) |
| Tabela por seção | `section_table` (`section-features-v4`, Fases 22 e 20b); [tabela por seção](section-table.md), [registro de observações](observations.md) |
| Caminho de pesquisa | `features` (Fase 14), `research_protocol` e `research_evaluation` (Fase 15), `research_models` (Fase 16), `investigations` (Fase 17); veja seus handoffs |
| Painel | `dashboard`, `dashboard_data`, `dashboard_ui`, `dashboard_development`, `election_audit/notebooks/` (Fase 18) |
| Reprodução | `reproduction`, `pilot`, `walkthrough`; [reprodução](reproduction.md) (tempos e recursos das execuções nacionais: [o que esperar](reproduction.md#o-que-esperar-nos-dados-nacionais)), [backfill](backfill.md) |
| Contratos | `election_audit/resources/contracts/schema.json` e `features.json`; `contracts.py`; [dicionário do esquema](schema-dictionary.md), [prontidão de features](feature-readiness.md), [convenções de transformação](transformation-conventions.md) |
| Documentos de pesquisa | [protocolo do estudo](../../research/analysis-plan.pt-BR.md), [plano de conclusão](../../research/completion-plan.pt-BR.md), [fontes de download](../../research/download-sources.pt-BR.md), [trabalhos relacionados](../../research/related-work.pt-BR.md) |
| Verificação de documentação | `scripts/check_docs.py` (pares, revisões, links, paridade de blocos), `scripts/check_doc_commands.py` (flags via `--help`, sintaxe SQL) |

Pares em `docs/en/` e `docs/pt-BR/` compartilham Document-ID e Revision; documentos
de pesquisa mantêm caminhos em inglês com equivalentes `.pt-BR.md`. Incremente as
duas revisões juntas. Código, comandos, SQL, fórmulas e números permanecem idênticos
byte a byte.
