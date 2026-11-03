# Trabalhos relacionados

Document-ID: EA-RELATED-WORK · Revision: 3 · Language: pt-BR

[English](related-work.md) · [Protocolo de pesquisa](analysis-plan.pt-BR.md) · [README](../README.pt-BR.md)

## Escopo e evidências

Este projeto situa-se na interseção entre engenharia de dados eleitorais,
reconciliação de artefatos eleitorais publicados e análise estatística forense de
eleições. Esta revisão direcionada compara projetos brasileiros de dados abertos
e trabalhos metodológicos relevantes; não é uma revisão sistemática da literatura
nem uma reivindicação de prioridade. Páginas públicas e arquivos de código
selecionados foram consultados em 30 de outubro de 2026. Os resultados relatados
são atribuídos aos autores e não foram reproduzidos independentemente aqui.
Links de branches são mutáveis; adotar código externo exige revisão fixada,
verificação da licença e validação com originais preservados do TSE.

## Infraestrutura brasileira de dados eleitorais

[eleicoes-brasil, de Turicas](https://github.com/turicas/eleicoes-brasil/tree/develop)
fornece extração e normalização de conjuntos eleitorais do TSE. Seus
[extratores](https://github.com/turicas/eleicoes-brasil/blob/develop/extractors.py)
ilustram cabeçalhos declarados e transformações específicas por fonte. Nosso
fluxo compartilha essa ênfase em esquemas explícitos, acrescentando snapshots
congelados dos bytes originais, testemunhos por registro e publicações imutáveis
vinculadas aos pais. Suporte a ETL histórico não estabelece compatibilidade com o
leiaute BWEB atual. Nosso adaptador verificado também se restringe ao leiaute
revisado do segundo turno presidencial de 2026 e à validação real do AC;
compatibilidade mais ampla ainda precisa ser estabelecida.
O `VotacaoZonaExtractor.get_headers()` inspecionado de Turicas rejeita anos depois de
2018 e lê entrada Latin-1; adotamos sua disciplina de esquema, não seu caminho de
código, e mantemos os códigos originais de valor ausente ao lado dos nulos
normalizados.

[eleicoes2026, do INEMA](https://github.com/inematds/eleicoes2026) trata da
divulgação de resultados ao vivo. Seu [contrato de dados](https://github.com/inematds/eleicoes2026/blob/main/contrato/README.md)
separa coleta e apresentação e distingue denominadores dos resultados. Essas
questões também importam em uma auditoria: respostas intermediárias podem
representar estados diferentes da publicação. Nossas análises operam sobre
populações explicitamente congeladas e preservam versões, correções e estados
desconhecidos. Isso sustenta a reprodução após mudanças nas fontes ao vivo, mas
não estabelece que nossa população derivada parcial represente o país.
O [código de normalização](https://github.com/inematds/eleicoes2026/blob/main/coleta/nucleo.py)
do INEMA aplica um ajuste de horário por UF; isso não basta como regra de relógio por
seção, porque exceções municipais e locais no exterior exigem evidência explícita.

## Reconciliação dos resultados publicados

A [conferência BWEB do Multiverso Digital](https://www.multiversodigital.com.br/eleicoes2026/metodo.php)
descreve a importação dos 28 arquivos de UFs/exterior, a conferência dos SHA-512
publicados e a comparação dos votos BWEB agregados com o JSON oficial. Destaca
escopo geográfico igual, seções agregadas e reclassificação pela situação da
candidatura. Nosso adaptador AC já verifica checksums e contabilidade por seção,
mas ainda não realiza reconciliação hierárquica final. A cobertura nacional e a
reconciliação daquele projeto são precedentes úteis de implementação, não
capacidades que possamos reivindicar a partir das verificações do AC.

[AnaliseEleicoes](https://github.com/radzki/AnaliseEleicoes) combina comparações
estatísticas com eleições históricas e reconciliação com publicações distintas do
TSE. Os autores relatam concordância no segundo turno nas 6.292 unidades
município–zona e com o relatório de totalização nos níveis nacional, UF e exterior.
Nossa próxima reconciliação deve igualmente comparar votos por candidato e
métricas contábeis sobre uma população comum explícita. Concordância agregada,
isoladamente, não identifica qual versão concorrente de BU foi incluída nem
exclui discrepâncias entre seções que se compensem. O vínculo seção/versão
continua sendo uma verificação separada.

Ambos os exemplos motivam uma distinção terminológica: um resultado publicado
separadamente pelo TSE é uma referência externa à nossa importação de BUs,
mas não uma medição independente da intenção dos eleitores. Somar novamente as
mesmas linhas BWEB importadas não fornece uma referência externa. Mesmo a
concordância entre produtos distintos do TSE verifica consistência dentro de uma
cadeia de produção parcialmente compartilhada.

## Artefatos binários e seções com votação zero

[DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) descreve a
decodificação de BUs binários, logs e assinaturas, totalização paralela,
reconciliação por UF e publicação em Parquet. É a comparação de engenharia mais
próxima entre os projetos revisados. Compartilhamos a necessidade de reconstruir
histórico operacional e preservar casos excepcionais, mas nossas evidências
implementadas atualmente cobrem processamento estrutural/de logs e importação
CSV verificada do AC. Decodificação de BU binário, certificação criptográfica e
vínculo com o resultado final continuam sendo lacunas. Parsers externos são
candidatos à reutilização validada; não dispensam a conferência de esquemas,
pressupostos de confiança e comportamento em arquivos excepcionais.

A [análise de votação zero de Wesley Cota](https://g.wcota.me/eleicoes2026/)
vincula resultados por seção ao contexto histórico e aos artefatos individuais
do TSE. Seu método informa que o CSV de votação por seção omite a linha de um
candidato quando ele não recebe votos. Isso é diretamente relevante para nossos
registros incompletos de escolhas, mas diz respeito a um conjunto específico:
não prova, por si só, a mesma semântica em toda edição BWEB nem estabelece que
uma seção ausente tenha zero votos. Nosso registro derivado pode informar zero
após verificar a regra aplicável de formato esparso e a cobertura completa do
pleito/seção, preservando a ausência original e as evidências utilizadas.
Até então, escolhas ausentes permanecem desconhecidas.

A [especificação EA18 do TSE](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
distingue situação da seção e situação dos hashes recebidos, incluindo versões
totalizadas, rejeitadas e excluídas. A [especificação EA20](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado)
fornece resultados hierárquicos e distingue apuração concluída de totalização
final. Esses contratos oficiais oferecem um caminho concreto para resolver as
lacunas de situação e referências. Ainda exigem bytes adquiridos e mapeamento
verificado entre o BU binário selecionado e o registro CSV.

## Análise estatística forense de eleições

[Klimek et al. (2012)](https://doi.org/10.1073/pnas.1210722109) estudam padrões de
comparecimento e votação com um modelo paramétrico de irregularidades
sistemáticas. O trabalho conecta um padrão estatístico a um mecanismo proposto.
Aplicá-lo a outra eleição exige validar a referência e os pressupostos; uma
combinação extrema de comparecimento e votação não é, por si só, uma contagem
de votos fraudulentos. AnaliseEleicoes e DataUrnas-BR ilustram o interesse prático
em triagem estatística junto às verificações de integridade. Nosso desenho separa
integridade, atipicidade condicional e possível impacto no resultado, para que uma
triagem não se transforme silenciosamente em alegação causal ou nacional.

Outros testes forenses usados no [protocolo do estudo](analysis-plan.pt-BR.md) miram
assinaturas específicas de manipulação. [Kobak, Shpilkin e Pshenichnikov
(2016)](https://doi.org/10.1214/16-AOAS904) buscam excesso de porcentagens inteiras,
rastro de resultados fabricados; [Rozenas (2017)](https://doi.org/10.1017/pan.2016.9)
testa esses picos contra um nulo reamostrado e mostra com que frequência proporções
redondas surgem sem fraude. O modelo de mistura finita eforensics de Mebane
([artigos de trabalho](https://public.websites.umich.edu/~wmebane/)) estima
componentes semelhantes a fraude a partir de comparecimento e votos, e seu autor
observa que voto estratégico e administração podem produzir os mesmos sinais. A
estatística de varredura de [Kulldorff (1997)](https://doi.org/10.1080/03610929708831995)
localiza agrupamentos geográficos com nulo de Monte Carlo. Usamos esses métodos como
testes globais ou de agrupamento com nulos dependentes do tamanho, nunca como
veredito por seção.

O segundo turno brasileiro de 2022 é um caso de alerta. Um relatório do Instituto Voto
Legal defendeu descartar os votos de modelos antigos de urna; o TSE rejeitou o pedido
e multou a coligação que o apresentou
([decisão](https://www.tse.jus.br/comunicacao/arquivos/voto-alexandre-de-moraes)).
Um contraste por modelo de urna que ignora onde as urnas antigas foram instaladas
confunde dispositivo com lugar. O protocolo reproduz esse contraste como controle
negativo e exige que a comparação dentro do local o remova.

O modelo condicional proposto se apoia nas [florestas de regressão quantílica de
Meinshausen (2006)](https://www.jmlr.org/papers/v7/meinshausen06a.html), que estimam
quantis condicionais dos resultados. O [protocolo de pesquisa](analysis-plan.pt-BR.md)
propõe referências empíricas pareadas e avaliação geográfica antes de interpretar
essas estimativas. [Bates et al. (2023)](https://doi.org/10.1214/22-AOS2244)
fornecem métodos conformais de teste de valores atípicos sob pressupostos
explícitos. Nossos dados não satisfazem automaticamente tais pressupostos:
dependência geográfica, locais repetidos e inspeção adaptativa exigem tratamento
explícito. A base implementada registra partições, acessos e resultados
exploratórios/nulos; não ajustou o modelo proposto nem estabeleceu valores-p
válidos de fraude.

## Posição deste projeto e trabalho restante

A contribuição pretendida é uma conexão auditável dos bytes congelados da fonte,
passando por evidências operacionais e eleitorais, até análises explicitamente
qualificadas. A ênfase implementada é rastreabilidade, populações versionadas e
estados indisponíveis quando falta evidência para uma interpretação. Isso é uma
ênfase de desenho em relação aos trabalhos revisados, não uma característica
comprovadamente exclusiva nem um detector superior.

| Dimensão | Precedente relevante | Situação atual aqui |
| --- | --- | --- |
| ETL eleitoral com esquema explícito | Turicas | Adaptador oficial AC BWEB fixado; contratos de importação normalizada. |
| Versões de publicação e denominadores | INEMA | Entradas congeladas e derivadas imutáveis; populações derivadas parciais. |
| Reconciliação hierárquica | Multiverso Digital; AnaliseEleicoes | Aritmética das linhas publicadas e totais da UF do AC conferem; reconciliação nacional BR/UF/municipal/ZZ pendente. |
| Integração de BU binário/log/assinatura | DataUrnas-BR | Fluxo de logs e resumos estruturais nacionais do segundo turno concluídos; conteúdo do BU binário do AC verificado contra o BWEB; assinaturas e RDV pendentes. |
| Escolhas omitidas com zero votos | Cota | Desconhecidos explícitos; normalização esparsa para completa com evidências pendente. |
| Triagem estatística condicional | Klimek et al.; Kobak et al.; Rozenas; Mebane; Meinshausen; Bates et al. | Rascunho do protocolo do estudo com mapa de ameaças, família confirmatória e estudo de poder; um ajuste de desenvolvimento de comparecimento no AC; sem modelo nacional ou inferência validada de fraude. |

O piloto de reconciliação do AC está feito para o segundo turno: as 2270 seções
do AC têm conteúdo verificado entre BU binário e BWEB, com totais da UF iguais ao
EA20. Os próximos passos, Fases 19 e 20 do [plano de conclusão](completion-plan.pt-BR.md), são nacionais: a mesma verificação em todas as UFs e nos
dois turnos, checagens de assinatura e RDV e reconciliação da hierarquia incluindo
ZZ. A elegibilidade deve acompanhar a evidência de cada resultado e medida. Relógios
não resolvidos podem bloquear alegações temporais sem bloquear aritmética de
contagens verificada independentemente. Inferência nacional e corroboração
independente da intenção dos eleitores continuam sendo requisitos de pesquisa
separados.
