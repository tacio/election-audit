# Auditoria estatística do segundo turno presidencial de 2026

Document-ID: EA-ANALYSIS-PLAN · Revision: 1 · Language: pt-BR

[English](analysis-plan.md)

Protocolo de trabalho, 29 de outubro de 2026. Este é um desenho de análise proposto,
não uma constatação de fraude, um modelo nacional ajustado nem um pré-registro feito
antes de observar qualquer dado. A inspeção inicial cobriu o manifesto de aquisição
e alguns logs de AC/AL/AM. Congele protocolo e snapshot dos dados antes de examinar
rankings de anomalias por candidato; registre alterações posteriores como análises
exploratórias.

## Recomendação

Use uma referência condicional não paramétrica para comparecimento e proporção de
votos por candidato, com modelo operacional separado para os logs. Comece com
comparações empíricas pareadas; use florestas de regressão quantílica como principal
preditor flexível. Calibre escores em locais de votação reservados, investigue
agrupamentos espaciais e aplique controle de multiplicidade apenas quando suas
hipóteses forem defensáveis. Trate achados como anomalias relativas que exigem
investigação. Uma população de referência montada com resultados oficiais não tem
certificação independente de ausência de fraude.

Há três perguntas distintas:

1. **Integridade:** versões de fontes, contagens e registros independentes conferem?
2. **Inusualidade:** quais seções ou agrupamentos diferem de pares comparáveis?
3. **Resultado:** sob mecanismo e população afetada explícitos, quanto poderia mudar
   a margem nacional?

Um resíduo de modelo responde à segunda pergunta. Por si só, não identifica votos
fraudulentos nem efeito causal sobre o resultado. A fraude também pode parecer
comum ou atingir toda a população de referência; não encontrar valores atípicos
não certifica ausência de fraude.

## Revisão de repositórios

Foram revisados arquivos acessíveis pelo navegador nos branches indicados, não
todos os arquivos nem a segurança de cada projeto. Fixe hashes de commits antes de
adotar código.

| Fonte | Práticas úteis | Limites para este projeto |
| --- | --- | --- |
| [Turicas / eleicoes-brasil](https://github.com/turicas/eleicoes-brasil), `develop` | Esquemas históricos explícitos, mapeamentos de cabeçalhos originais para normalizados e separação bruto/derivado. | ETL histórico não é parser validado de logs de seção de 2026. |
| [INEMA / eleicoes2026](https://github.com/inematds/eleicoes2026), `main` | Proveniência, versões imutáveis de publicação, verificações contábeis e tratamento de atualizações assíncronas. | Painel ao vivo e estimativas agregadas não estabelecem fraude por seção nem transferências individuais de votos. |

A [implementação do extrator](https://raw.githubusercontent.com/turicas/eleicoes-brasil/develop/extractors.py)
do Turicas usa entrada Latin-1 e valida cabeçalhos CSV observados contra esquema
declarado. O `VotacaoZonaExtractor.get_headers()` inspecionado rejeita anos após
2018. Adote a disciplina de esquema; não presuma suporte à eleição atual nesse
caminho. Preserve códigos originais de ausência junto aos nulos normalizados, sem
perder seus significados distintos.

O [contrato de dados](https://github.com/inematds/eleicoes2026/blob/main/contrato/README.md)
do INEMA distingue eleitores aptos das seções apuradas de todo o eleitorado e votos
válidos de votos totais. Seu
[coletor](https://raw.githubusercontent.com/inematds/eleicoes2026/main/coleta/coletor.py)
preserva respostas brutas e trata diferenças nacionais/estaduais durante publicação
assíncrona de forma distinta das discrepâncias finais. Adote essas verificações.
Nossa auditoria também deve reter decréscimos e correções como observações
versionadas, em vez de descartá-los pela expectativa de totais crescentes.

Seu [histórico de falhas](https://github.com/inematds/eleicoes2026/blob/main/FALHAS.md)
registra problemas de fuso e CDN desatualizada. O
[código de normalização](https://raw.githubusercontent.com/inematds/eleicoes2026/main/coleta/nucleo.py)
usa ajuste de horário por UF. Isso não basta como regra geral do relógio da seção:
exceções municipais e locais no exterior precisam de tratamento explícito.

Outra implementação a examinar é
[DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR): o tratamento
documentado de urnas substitutas, logs copiados, exceções de fuso e saída Parquet é
relevante. Valide independentemente seus parsers e achados contra originais do TSE
antes de reutilizar; conclusões publicadas não são verdade de referência do modelo.

## Dados necessários antes do ajuste

O downloader atual coleta logs e metadados auxiliares. Só os logs não fornecem os
totais por candidato, denominadores de eleitorado e atributos de local necessários
ao modelo eleitoral proposto.

| Entrada | Finalidade | Validação / fonte |
| --- | --- | --- |
| BUs do segundo turno, preferencialmente CSV publicado e BUs binários selecionados | Totais por candidato, eleitores aptos, comparecimento, brancos/nulos, local, identificadores de urna/versão | [Conjunto de BUs do TSE](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna); conferir CSV com amostras binárias e totais finais. |
| BUs e detalhes de seção do primeiro turno | Vetor de preferência e comparecimento de referência do primeiro turno | Mesmo conjunto, turno e cargo corretos; agregar composições alteradas antes de unir. |
| Logs, auxiliares e índices de seção do segundo turno | Sessões, eventos de votação, histórico operacional, agregação e estado de publicação | [Documentação técnica do TSE](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados). |
| Resultado federal final nos níveis BR/UF/município | Margem final e reconciliação hierárquica | Eleição 6258, cargo 1; usar snapshot final coerente. |
| RDVs e envelopes de assinatura selecionados | Recalcular contagens e validar artefatos assinados | [Links de formatos do TSE](https://www.tse.jus.br/eleicoes/eleicoes-2026/eleicoes-2026); exigem downloads adicionais. |
| Cadastro de seções/localidades, resultados históricos, transferências temporárias, informações dos locais | Uniões estáveis e escolha de pares | Verificar esquema de cada ano, mapeamento TSE/IBGE e definições dos denominadores. |
| Ocorrências, atas, cópias independentes de BU e outras confirmações | Resolver casos específicos suspeitos e estudar acesso/supressão | Obter para os casos identificados; artefatos eletrônicos oficiais compartilham parte da cadeia de produção. |

O TSE publica BUs por UF e turno, com recursos separados de checksum, no
[catálogo de BUs](https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna).
Não confunda exemplo de catálogo ou simulação de painel com resultado final
observado. Este plano não afirma nenhuma margem final.

## Tabelas canônicas e verificações de integridade

Use chave de seção principal `(year, round, election, UF, municipality_TSE, zone,
section)` e chaves separadas `physical_urn`, `source_package` e `voting_session`.
Códigos ficam como texto com zeros à esquerda e votos como inteiros. Uma urna
física pode servir várias sessões históricas; uma seção pode usar hardware substituto.

Produza snapshots de fontes apenas com acréscimos, correspondência de composição,
resultados por seção, resumos de sessão, problemas de parsing e atributos de
anomalia independentes de candidato. Use Parquet para grandes tabelas derivadas
quando as dependências estiverem instaladas; mantenha SQLite para consultas ao
manifesto. Durante análise, mantenha o manifesto do downloader ativo somente para
leitura. Sua tabela `files` atual registra o mapeamento mais recente de URLs: antes
da análise, acrescente/congele proveniência URL-objeto por execução para que futuras
atualizações de metadados não alterem silenciosamente as entradas da análise.
Se existir `manifest-location.json`, resolva-o com `manifest_path()` do downloader;
`manifest.sqlite` no HDD pode ser snapshot anterior à migração, não o banco autorizado.

Verificações necessárias incluem:

- Data, turno, cargo, fase oficial e estado de pacote corretos; versões recebidas,
  rejeitadas/excluídas baixadas não devem ser adicionadas aos votos totalizados.
- Um resultado canônico por principal após resolver retransmissões; preservar
  versões concorrentes e conflitos. Não somar todos os hashes.
- Agregar integrantes no eleitorado principal exatamente uma vez. Para comparação
  histórica, harmonizar composições alteradas ou marcá-las incomparáveis.
- Votos de candidatos + brancos + categorias aplicáveis de nulos = votos
  presidenciais; conferir comparecimento/abstenção contra eleitorado apropriado,
  documentando transferências ou categorias excepcionais. Linhas repetidas de BU
  não podem multiplicar eleitorado ou comparecimento da seção.
- Somar resultados em município, UF e BR, incluindo ZZ, usando a mesma população
  final e versão. Separar lacunas de publicação de discrepâncias numéricas.
- Comparar conclusões e suspensões dos logs contra totais de BU após decodificar
  a semântica das sessões; divergência de contagem de mensagens brutas é item a investigar.
- Verificar assinaturas digitais com esquema e material de confiança do TSE,
  separadamente de hashes de transporte ou CRC de ZIP. Concordância entre
  artefatos gerados pelo mesmo software verifica consistência, não comprova
  independentemente a intenção do eleitor.

Mantenha registro populacional: seções esperadas, agregadas, instaladas/não
instaladas, BUs disponíveis, logs disponíveis, registros reconciliados, falhas de
parser e exclusões. Informe cobertura por UF, local, modelo/versão e apoio a
candidato; não descarte silenciosamente registros incomuns. A ordem alfabética
dos downloads torna a coleta parcial atual inadequada para inferência nacional.

## Semântica dos logs: verificações antes dos atributos

A inspeção direta de três arquivos salvos de AC/AL/AM encontrou datas de preparação,
eventos de 4 de outubro e 25 de outubro no mesmo `logd.dat`. Nome de segundo turno
não filtra seus eventos. Preserve ordem de linhas e identifique sessões oficiais
VOTA, transições de turno, identidade da urna, reinícios, suspensões e mudanças de
relógio antes de selecionar a sessão alvo. Filtrar datas é diagnóstico útil, não
substitui reconstrução de sessão.

O [guia oficial de logs](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema)
mostra votação concluída, suspensões parciais/totais e fluxos de registro. Conte
ciclos completos de eleitores, não toda mensagem que mencione voto ou autorização
manual. Uma solicitação de dados manuais pode ser cancelada e não é automaticamente
voto manual concluído. Mantenha ciclos não resolvidos explicitamente desconhecidos.

Horários de log são leituras ingênuas do relógio do dispositivo. Preserve leitura
original, fuso/deslocamento atribuído, ajustes, regra de conversão e confiança.
Valide mapeamentos municipais e convenções do exterior contra registros de BU/sessão;
não infira fuso de primeiro voto incomumente cedo/tarde. Abertura, fechamento,
transmissão e download são grandezas diferentes. Avalie sensibilidade a erros
plausíveis de relógio; relógios não resolvidos impedem afirmações de horário
absoluto, mas não necessariamente verificações de contagem de resultados.

Deduplique arquivos copiados e blocos de eventos sobrepostos verificados entre
pacotes de substituição, mantendo linhagem. Não deduplique só por mensagens
idênticas ou horários com resolução de segundos, que podem se repetir legitimamente.
Não some a mesma sessão física através de várias referências de seção/pacote.

O TSE explica que entradas do RDV são embaralhadas para impedir reconstrução da
ordem dos eleitores: [explicação oficial do RDV](https://www.tse.jus.br/comunicacao/noticias/2021/Julho/registro-digital-do-voto-permite-recontagem-e-amplia-transparencia-do-processo-eleitoral).
Logo, horários dos logs não podem ser unidos a escolhas do RDV por número de linha.
Não podemos atribuir ciclos tardios, rápidos ou autorizados manualmente a candidato.

## Especificação do modelo não paramétrico

### Alvos e controles

Ajuste distribuições condicionais separadas para:

- Comparecimento: eleitores que concluíram / eleitorado apto da seção harmonizada.
- Proporção do candidato A: A / (A + B), indefinida com zero votos válidos.
- Proporções de brancos/nulos com denominadores corretos.
- Medidas operacionais: distribuições de duração dos ciclos completos, intervalos
  na sessão, autorizações falhas, interrupções/reinícios e mudanças de intensidade
  ao longo do dia.

Use vetor de preferência do primeiro turno pré-especificado, eleitorado/tamanho,
geografia, padrões históricos comparáveis e características pertinentes do local
anteriores à eleição. Verifique se o estado também votou para governador: o número
de disputas altera a duração. Definições A/B são fixadas por identificadores
oficiais e os testes executados simetricamente nas duas direções.

Mantenha duas especificações: uma ajusta comparações operacionais por modelo/versão
e logística conhecida; outra examina esses fatores como mecanismos possíveis.
Não controle automaticamente comparecimento, autorização manual ou interrupções
quando forem efeitos hipotéticos da manipulação. Repita modelos eleitorais sem
referência do primeiro turno atual, que também pode estar afetado.

### Preditores e escores

Comece com medianas de pares interpretáveis, quantis empíricos condicionais e
desvios absolutos medianos. Compare dentro do local quando possível, depois dentro
da zona/município com pareamento de tamanho e preferência histórica. Eleitores não
são aleatoriamente alocados às seções: permutações dentro de escola não são
automaticamente testes exatos de aleatorização. Exija sobreposição e sinalize
casos fora do suporte em vez de forçar previsão.

O principal preditor não linear é uma **floresta de regressão quantílica**, que
estima quantis condicionais sem modelo fixo de erro normal:
[Meinshausen (2006)](https://www.jmlr.org/papers/v7/meinshausen06a.html).
Compare com referência empírica pareada por perda quantílica e cobertura de
intervalos em dados reservados. Flexibilidade sozinha não estabelece robustez a
dados ruins, confundimento ou populações de treinamento contaminadas.

Para intervalo `[L_j(x), U_j(x)]`, um escore componente possível é
`s_ij = max(L_j(x_i) - y_ij, y_ij - U_j(x_i), 0) / scale_j(x_i)`.
Especifique pisos de escala e tratamento de valores discretos/denominadores zero
com dados de treinamento. Pré-especifique escore conjunto máximo entre componentes
e então calibre esse escore; não some p-valores separados sem justificativa.
Guarde resíduos com sinal para interpretação e escores absolutos para detecção simétrica.

### Calibração, geografia e multiplicidade

Divida locais inteiros de votação entre treinamento, calibração e teste, com sementes
fixas e estratos geográficos. Use municípios reservados como teste mais forte.
Diagnósticos entre pares do mesmo local formam camada descritiva separada; usar
vizinhos para treinar e testar exageraria a generalização.

Para escore congelado e referência permutável, p-valor conservador por postos é
`p_i = (1 + number of calibration scores >= s_i) / (n_cal + 1)`.
[Bates et al. (2023)](https://doi.org/10.1214/22-AOS2244) desenvolvem testes conformais
de valores atípicos sob hipóteses amostrais declaradas. Seções compartilham ambientes
e não são sorteios aleatórios independentes; dividir por agrupamentos não prova
permutabilidade. Examine calibração nos estratos pré-especificados e use escores
de agrupamentos inteiros nos testes geográficos confirmatórios. Quando hipóteses
seguirem sem suporte, publique postos empíricos de cauda como escores descritivos,
não p-valores válidos de fraude. [Barber et al. (2023)](https://arxiv.org/abs/2202.13415)
discutem o impacto de desvios de permutabilidade.

As unidades inferenciais primárias devem inicialmente ser agrupamentos de
local/município; rankings por seção orientam investigação. Para p-valores válidos,
use família de testes pré-especificada e procedimento que admita dependência,
como [Benjamini–Yekutieli](https://doi.org/10.1214/aos/1013699998), com FDR proposto
de 5%. Isso controla critério de erro sob suas hipóteses, não a porcentagem de
acusações que constituem fraude. Não corrige p-valores inválidos. Defina famílias
entre desfechos, escalas geográficas e variantes de modelo antes do teste; buscas
adicionais são exploratórias.

Verifique resolução e poder antes de decidir: com 20,000 unidades de calibração,
o menor p-valor por postos é cerca de 0.00005. Para 500,000 testes, o primeiro
limiar BH a 5% é 0.0000001, e BY é mais rigoroso. Esse desenho não detecta valor
atípico isolado nesse limiar. Não invente p-valores minúsculos extrapolando cauda
sem suporte. Testes de agrupamentos mais amplos, testes globais pré-especificados
ou referência válida maior podem ser necessários. Declare a faixa de efeitos indetectáveis.

### Proteções contra teste seletivo e inspeções repetidas

A [tirinha Significant do xkcd](https://xkcd.com/882/) ilustra testar muitos subgrupos
e relatar seletivamente um p-valor baixo. Com 20 testes independentes sob nulas
verdadeiras a 5%, a probabilidade de pelo menos uma rejeição falsa é
`1 - 0.95**20`, cerca de 64%; o número esperado é um. Dependência altera a primeira
conta, mas não torna buscas exploratórias não ajustadas confirmatórias.

Mantenha registro de análise com todo desfecho, subgrupo, escala geográfica, janela
temporal, comparação de hardware, variante e eleição histórica examinados,
inclusive resultados nulos e especificações malsucedidas. Congele família
confirmatória e escore conjunto antes de examinar rankings do teste. Escolher
subgrupos interessantes após ver resultados já é seleção; corrigir só a lista
exibida não contabiliza a busca anterior.

Reserve partição de teste de fato intocada. Escolha atributos, pares, hiperparâmetros
e limiares usando desenvolvimento e testes retrospectivos históricos. Após inspeção,
o teste vira desenvolvimento para mudanças posteriores; use nova evidência reservada
ou análise justificadamente ajustada à seleção para novas alegações confirmatórias.
Correção estatística de multiplicidade não corrige vazamento treino/teste nem
seleção adaptativa de modelo.

Trate monitoramento durante downloads como descritivo. Testes confirmatórios usam
população e snapshot congelados. Inspecionar p-valores repetidamente e parar ao
cruzar limiar não é coberto pelas funções de família fixa atuais; alegações
sequenciais exigiriam método sequencial válido especificado separadamente.

Informe tamanhos de efeito e limites condicionais da margem junto à incerteza.
Teste não significativo não prova ausência de fraude; p-valor pequeno não dá
probabilidade de fraude. Meta FDR de 5% trata da fração esperada de rejeições falsas
entre rejeições, com zero quando não há rejeições; não é probabilidade por caso
nem limite da parcela de votos fraudulentos. Essas proteções interpretativas seguem
a [declaração da ASA sobre p-valores](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf).
Modelagem não paramétrica não remove essas exigências de desenho.

## Eleições históricas: prioridade de aquisição e validação

Histórico pode melhorar pares, revelar comportamento local persistente e testar
generalização. Não é grupo de controle certificado limpo. Um padrão recorrente
entre eleições pode ser estrutura comum, artefato recorrente ou irregularidade
persistente; recorrência sozinha não distingue essas possibilidades.

Priorize:

1. **Resultados e composição de 2026 primeiro turno:** referência de eleitorado
   mais próxima ao segundo turno. Distinguir mudança real de agregação e
   transferências, permitindo contaminação no próprio primeiro turno.
2. **Resultados presidenciais de 2022, ambos os turnos, e logs comparáveis:** ciclo
   anterior para comparecimento/preferências e validação operacional. O TSE lista
   resultados presidenciais por seção e detalhes no
   [catálogo de 2022](https://dadosabertos.tse.jus.br/dataset/resultados-2022) e
   [documenta logs públicos online de 2022](https://www.justicaeleitoral.jus.br/fato-ou-boato/checagens/2022/logs-das-urnas-eletronicas-sao-dados-publicos-e-nao-revelam-votos-de-eleitores).
   Verificar disponibilidade atual e formatos anuais antes de baixar em massa.
3. **Resultados presidenciais de 2018, ambos os turnos:** outro ciclo para avaliar
   estabilidade e sensibilidade temporal. O
   [catálogo de 2018](https://dadosabertos.tse.jus.br/dataset/resultados-2018) inclui
   votos presidenciais por seção e detalhes. Não presumir a mesma cobertura online
   de logs de 2022 nem significados idênticos dos esquemas.

Use desenvolvimento/testes retrospectivos cronológicos quando viável: por exemplo,
desenvolva com 2018 e faça verificação retrospectiva congelada em 2022 antes da
avaliação final de 2026. Se 2022 informar outra revisão, classifique a verificação
anterior como desenvolvimento e preserve teste final novo. Compare modelos com
histórico e só do ciclo atual sob a mesma avaliação reservada; mantenha histórico
só quando melhorar calibração, previsão ou qualidade da investigação.

Harmonize divisões/fusões de seções, mudanças de eleitorado, locais, regras de fuso,
gerações de dispositivo/software, fluxos biométricos e número de disputas. Não
iguale proporções brutas de candidatos diferentes nem presuma preferências fixas.
Dados municipais podem validar parsing e alguns mecanismos operacionais, mas não
pertencem automaticamente à referência de comparecimento/proporção presidencial.
Use histórico como contexto e teste de estresse, sem simplesmente concatenar tudo
e alegar amostra independente maior. Observações repetidas dos mesmos locais e
mudanças de distribuição entre anos invalidam esse atalho.

## Protocolo de validação e investigação

Antes de aplicar rótulos de anomalia:

1. Valide parser e reconciliação entre hardware, software, geografia, sessões
   normais/de substituição e tipos excepcionais de BU.
2. Use geografia reservada e eleições históricas independentes como testes de
   estresse, não como rótulos de treinamento presumidamente sem fraude. Diferenças
   entre turnos podem refletir transferências legítimas e números distintos de disputas.
3. Injete mecanismos sintéticos documentados em cópias separadas de validação:
   adição/troca de votos, redução de comparecimento, históricos duplicados,
   segmentos ausentes e erros de relógio, em várias concentrações e magnitudes.
   Reajuste/calibre quando apropriado para também testar contaminação.
4. Informe poder de detecção, localização, alarmes falsos sob mecanismos benignos
   simulados e cobertura por estrato. Simulações avaliam detector implementado
   contra mecanismos especificados, não toda fraude possível.
5. Investigue casos ranqueados com evidência de origem e amostra aleatória de não
   sinalizados. Busque cópias independentes de BU, atas, explicações de incidentes
   e confirmação. Analistas de logs devem inicialmente desconhecer identidade dos
   candidatos quando viável.

Inspecione deslocamentos regionais e de modelo/versão coerentes, além de extremos
isolados: alteração ampla pode ser absorvida por referência flexível. Por outro
lado, preferências regionais, idade, acessibilidade, transporte e administração
podem gerar diferenças coerentes sem fraude. Mudanças agregadas entre turnos não
identificam transferências individuais (problema de identificação ecológica).

Use evidência operacional e resultados juntos, com explicações alternativas
explícitas. Apoio alto, pouca biometria, votação rápida, fechamento tardio,
transmissão tardia ou modelo específico não bastam sozinhos. Não use conformidade
com Benford como teste principal: [Deckert, Myagkov e Ordeshook
(2011)](https://authors.library.caltech.edu/records/5jbtk-8wn05) mostram que pode
classificar dados eleitorais incorretamente. Não exclua sinalizadas para declarar
a soma restante como resultado verdadeiro.

## Estimando o impacto no resultado

Seja `M = total_A - total_B > 0` a margem nacional oficial congelada. Obtenha-a de
dados finais reconciliados, não dos logs locais incompletos. Distinga:

| Mecanismo suposto e corroborado | Maior mudança de margem por voto afetado |
| --- | --- |
| Remover voto inválido contado para A | 1 voto |
| Corrigir voto contado para A que deveria ser B | 2 votos |
| Restaurar voto adicional suprimido para B | 1 voto |

Para vitória estrita de B, são necessárias ao menos `floor(M/2) + 1` trocas A-para-B,
se houver tantos votos A elegíveis para correção. São necessárias ao menos `M + 1`
remoções de A ou votos adicionais B nos mecanismos de um voto correspondentes.
São limiares aritméticos, não estimativas do que aconteceu.

Para subconjunto anônimo sinalizado de `r` cédulas completas em seção com
`a` votos A, `b` votos B e `c` outros, suponha removidos todos os `r`. A contribuição
A-menos-B removida tem limites factíveis exatos:

```
d_max = min(r, a) - max(0, r - a - c)
d_min = max(0, r - b - c) - min(r, b)
corrected national margin in [M - d_max, M - d_min]
```

Some esses limites de contribuição entre seções/subconjuntos afetados disjuntos.
Usam só tamanho anônimo e contagens do BU; não alocam votos tardios/manuais a
candidato. Detectores sobrepostos devem ser deduplicados antes de somar limites.
A hipótese de remoção exige justificativa, e `r` deve contar votos presidenciais,
não tentativas de autorização ou mensagens genéricas. Se forem afetados “no máximo
r”, inclua também o caso sem remoção.

Para cenário de troca entre dois candidatos com limite validado `q_i` de votos
afetados, a maior correção adversa de margem é `2 * min(q_i, a_i)` por seção.
Isso supõe que no máximo esse número de votos atualmente A pode mudar para B;
outros mecanismos, eleitorados alterados e conversões de brancos/nulos exigem
outras restrições. Se o limite total for menor que M, *esse mecanismo, nessa
população e sob esse limite* não pode inverter o resultado. Nada diz sobre
manipulação não detectada fora da população.

Contrafactual baseado em modelo pode estimar votos A esperados como `n_valid_i * p_hat_i`
com comparecimento válido fixo. A diferença de margem entre dois candidatos é
`2 * sum(a_i - n_valid_i * p_hat_i)`. Chame de **excesso relativo à referência**,
não votos roubados. Para manipulação de comparecimento, modele participação
separadamente e varie escolhas hipotéticas de ausentes; não são observadas nos
logs. Use reamostragem em blocos geográficos de todo o pipeline de ajuste/seleção/
estimação, informe efeitos com sinal e sensibilidade a pareamento, contaminação e
fatores omitidos. Bootstrap simples de resíduos selecionados ignora viés de seleção.
Intervalos de previsão por seção não podem ser simplesmente somados como intervalo
de confiança nacional, e incerteza preditiva não identifica incerteza causal.

Todo caso relatado deve incluir hashes, chaves de seção/sessão/pacote, atributos
observados/esperados, definição dos pares, escore/hipóteses, situação de
multiplicidade, explicações alternativas, confirmação, limites de votos afetados
e implicações condicionais na margem nacional. “Impacto real” permanece não
identificado sem evidência defensável do mecanismo e contrafactual.

## Ordem de execução

1. Deixe a aquisição continuar; inspecione amostra pequena, reproduzível e somente
   para leitura dos logs.
2. Obtenha BUs dos dois turnos, totais finais, correspondência de seções e esquemas
   necessários; acrescente verificações direcionadas de RDV/assinaturas.
3. Congele snapshot de cobertura/proveniência; construa e reconcilie sessões/resultados.
4. Congele alvos, hipóteses nulas, divisões, famílias e simulações; implemente e
   compare modelos condicionais empíricos e de florestas.
5. Produza tabela de investigação simétrica entre candidatos, depois limites
   condicionais de impacto e análises de sensibilidade. Não publique contagens de
   fraude nem vencedor corrigido a partir só de resíduos estatísticos.

`scripts/audit_statistics.py` contém funções testadas de calibração por postos,
multiplicidade e limites de impacto. Não ajusta o modelo proposto. O utilitário de
inspeção de logs é diagnóstico de parser, sem conversão de fuso nem classificador
de fraude.
