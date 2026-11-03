# Auditoria estatística da eleição presidencial de 2026: protocolo do estudo

Document-ID: EA-ANALYSIS-PLAN · Revision: 2 · Language: pt-BR

[English](analysis-plan.md) · [Plano de conclusão](completion-plan.pt-BR.md) · [Trabalhos relacionados](related-work.pt-BR.md)

**Estado: rascunho do protocolo, 3 de novembro de 2026.** Este documento diz o que
a auditoria vai afirmar, como cada afirmação é testada e qual a sensibilidade de
cada teste. Ainda não está congelado. Será congelado e pré-registrado publicamente
(registro no OSF e tag git assinada) na Fase 23, antes de qualquer análise
confirmatória. Depois do congelamento, toda mudança é um desvio registrado e seus
resultados são rotulados como exploratórios. Não existe hoje constatação de
fraude, margem nacional nem modelo nacional ajustado.

## 1. Perguntas e as afirmações que elas permitem

A auditoria responde a três perguntas separadas:

1. **Integridade.** Os artefatos publicados concordam entre si, com suas
   assinaturas e com cópias independentes? Respondida por verificações
   determinísticas (seção 5). Uma discrepância é um fato sobre artefatos, não
   sobre intenção.
2. **Excepcionalidade.** Alguns lugares, grupos de dispositivos ou a distribuição
   inteira dos resultados se afastam do que seções comparáveis e o primeiro turno
   das mesmas seções preveem? Respondida por uma família pequena e pré-especificada
   de testes estatísticos (seção 7). Uma rejeição diz "este padrão é improvável sob
   o modelo declarado", não "estes votos são fraudulentos".
3. **Sensibilidade do resultado.** Sob um mecanismo, uma população e um limite
   explícitos, quanto a margem nacional poderia mudar? Respondida por limites
   aritméticos (seção 8). São afirmações condicionais, não estimativas do que
   aconteceu.

**Resultados sempre vêm com seu poder.** A manchete da parte estatística é a
*manipulação mínima detectável*: para cada mecanismo, a menor mudança na margem
nacional que os testes detectariam com 80% de probabilidade. Um resultado nulo sem
esse número seria ininterpretável, por isso nunca é divulgado sozinho.

A auditoria **não** afirma:

- que alguma seção, pessoa ou partido cometeu fraude;
- que a ausência de sinais prova a ausência de fraude;
- que algum voto, ciclo tardio ou habilitação manual pertence a um candidato (o RDV
  é embaralhado; veja a seção 6);
- um vencedor corrigido, nem o resultado de remover seções sinalizadas.

## 2. O que já foi visto

Um pré-registro só tem sentido se revelar o que os autores viram antes de
escrevê-lo. Nesta revisão:

- **Acre (AC):** BWEB e BUs binários do segundo turno (2270 seções, conteúdo
  verificado); features de seção; um modelo de comparecimento ajustado e avaliado em
  dados de calibração; 126 pacotes de caso de desenvolvimento. AC é dado de
  desenvolvimento.
- **Piloto estrutural de cinco UFs (AC, AL, DF, ES, PR):** logs congelados, com
  sessões, ciclos e relógios todos não resolvidos. Dado de desenvolvimento.
- **Resumos estruturais nacionais do segundo turno (Fase 11):** contagens por log de
  linhas, eventos estruturais, habilitações, conclusões e pedidos manuais para
  498581 logs. Nenhum resultado eleitoral foi ligado a eles e nenhum ranking foi
  calculado. Cada log do segundo turno vai da preparação (setembro) ao primeiro e ao
  segundo turno, então essas contagens misturam turnos e não são medidas do segundo
  turno.
- **Registros de inspeção:** todo local listado em
  `data/phase15/inspection.sqlite`, `data/national/phase11-protection-2026-10-31/`
  e nos registros de lotes da Fase 11 é dado de desenvolvimento.
- **Não visto:** qualquer resultado eleitoral nacional por seção, qualquer medida
  operacional nacional, os 596 logs protegidos/de estresse do segundo turno e
  qualquer dado de 2022.

## 3. Modelo de ameaças: do mecanismo ao observável

Cada mecanismo deixa rastros em artefatos específicos, ou nenhum. A auditoria é
desenhada em torno desta tabela; um teste que não aparece aqui não pertence à
família confirmatória.

| Mecanismo | Onde deixaria rastros | Verificações e testes | O que a auditoria não vê |
| --- | --- | --- | --- |
| Resultados alterados ou substituídos depois da urna (transmissão, totalização, publicação) | Assinatura do BU; BU binário vs BWEB vs totais hierárquicos; cópias impressas do BU | I1, I2, I4, I8 | Nada dentro da cadeia eletrônica se as próprias chaves de assinatura forem comprometidas; cópias impressas são a verificação fora da cadeia |
| Software que altera votos dentro da urna, com BU, RDV e log todos consistentes | Nenhum rastro no log; só padrões agregados de resultado | Testes de integridade do TSE no dia da eleição (evidência externa, seção 4); C1, C2, C4, C6 | Uma troca pequena e espacialmente uniforme que imita a variação comum; seu tamanho é limitado pela manipulação mínima detectável |
| Enchimento de urna ou personificação por mesários | Habilitações manuais (não biométricas), ciclos fora do horário normal, rajadas de ciclos rápidos; picos de comparecimento e de proporção | I5; C2, C3, C5 | Enchimento diluído em muitas seções, em horários normais e com habilitação biométrica |
| Supressão ou obstrução de eleitores | Queda de comparecimento do primeiro para o segundo turno em relação aos pares; longas pausas, suspensões, abertura tardia, troca de urna | C1 (comparecimento), C4, C5 | Causas fora do local de votação; causas legítimas (transporte, clima) produzem o mesmo sinal |
| Logs adulterados, copiados ou fabricados | Hashes de blocos; o trecho do primeiro turno dentro de cada log do segundo turno vs o log do primeiro turno; descontinuidades de relógio | I6, I7 | Uma cadeia de artefatos completa e reassinada de forma consistente |
| Erros na publicação ou neste pipeline | Qualquer falha de reconciliação | I1–I9 | — |

Processos benignos produzem vários desses sinais: mudanças políticas regionais,
idade e acessibilidade do eleitorado, taxas de cadastro biométrico, transporte,
trocas de urna e prática administrativa. Por isso cada teste tem uma alternativa
benigna declarada e um controle (seção 7.6).

## 4. Dados e proveniência congelada

| Entrada | Uso | Estado |
| --- | --- | --- |
| Logs de seção, os dois turnos | Sessões, ciclos, tipo de habilitação, tempos | Coletados; manifestos fixados pelos certificados SHA-256 da migração |
| Release estrutural do segundo turno da Fase 11 `55e55e91549dac53eb546a596f62033bc837e0a34e3ff9b178c4687ae9257f88` | Hashes de blocos, estrutura de membros, índice de objetos | Completa para 498581 logs elegíveis; só estrutural |
| BWEB, 27 UFs e ZZ, os dois turnos | Resultados por seção | A coletar (AC feito); o TSE publica checksums SHA-512 |
| BUs binários, RDVs e assinaturas (pacotes totalizados) | I1–I3 | A coletar (AC feito para BUs) |
| Resultados hierárquicos (EA20) | I4 | A coletar |
| Perfil do eleitorado por seção (idade, sexo, escolaridade) e locais de votação | Covariáveis, chaves de local | A coletar |
| BWEB, BUs e logs presidenciais de 2022, os dois turnos, com perfil do eleitorado | Controle negativo (seção 7.6) | A coletar |
| Relatórios do teste de integridade do TSE no dia da eleição, os dois turnos | Evidência externa sobre o software da urna | A reunir |
| Cópias impressas independentes do BU (QR codes) | I8 | A reunir; a seleção não é aleatória |

Regras que valem para toda tabela:

- As análises leem as **cópias congeladas e certificadas dos manifestos** em
  `migration-2026-11-01/manifest-r{1,2}.sqlite`, identificadas por hash, e não os
  manifestos vivos em `.local-state/`. Os caminhos nos manifestos são relativos à
  raiz de objetos.
- Um resultado canônico por seção principal depois de resolver retransmissões,
  mantendo as versões concorrentes. Seções agregadas se juntam à principal
  exatamente uma vez. Chaves ficam como texto com zeros à esquerda; contagens ficam
  inteiras.
- Um livro de população registra seções esperadas, agregadas, instaladas, não
  instaladas, com BU, com log, reconciliadas, com falha e excluídas, por UF e modelo
  de urna. Desconhecido nunca é zero; nada é descartado em silêncio.
- Pacotes `Recebido` (recebidos, não totalizados) nunca são somados aos votos
  totalizados.

## 5. Nível 1: verificações determinísticas de integridade

Estas verificações não precisam de modelo estatístico. São divulgadas primeiro, como
contagens com tabelas completas de discrepâncias e os hashes de origem necessários
para verificar cada linha.

| ID | Verificação | Unidade | Uma falha significa |
| --- | --- | --- | --- |
| I1 | Verificação da assinatura do BU com o material de confiança do TSE | BU | O artefato não é o assinado pela urna |
| I2 | Conteúdo do BU binário igual à linha do BWEB | Seção × opção | A publicação difere do artefato assinado |
| I3 | Recontagem do RDV igual ao BU | Seção | Registro de votos e contagem discordam |
| I4 | Somas das seções iguais aos totais publicados de município, UF, ZZ e país | Nó da hierarquia | A totalização difere das seções |
| I5 | Ciclos concluídos na sessão identificada do segundo turno iguais ao comparecimento do BU | Seção | Log e contagem discordam (muitas vezes um problema de parse ou de sessão; investigado) |
| I6 | Blocos do primeiro turno dentro de cada log do segundo turno iguais ao log do primeiro turno da mesma urna | Urna | Um dos dois históricos publicados mudou |
| I7 | Continuidade do relógio do log e estrutura de sessões passam nas regras de reconstrução | Sessão | O histórico está incompleto ou fora de ordem |
| I8 | Cópias impressas independentes iguais ao BU publicado | Seção (amostra) | A publicação difere do registro impresso |
| I9 | Estado do pacote, agregação e identidade do turno consistentes | Pacote | A população está mal especificada |

Se o acervo de RDVs não cobrir todas as seções, I3 usa uma amostra aleatória
uniforme pré-especificada. Para afirmar, com 95% de confiança, que a taxa de
discrepância está abaixo de `p` quando a amostra não mostra nenhuma, o tamanho da
amostra é:

```
n = ceil(ln(0.05) / ln(1 - p))        # p = 0.001 gives n = 2995
```

Cópias impressas independentes (I8) vêm de coleções de terceiros cuja seleção não é
aleatória. A concordância delas corrobora as seções que cobrem; não se estende a
outras seções.

Concordância entre artefatos produzidos pela mesma cadeia de software (I1–I4) mostra
consistência, não a intenção do eleitor. Os testes de integridade do TSE e as cópias
impressas são a única evidência fora da cadeia, e são divulgados com essa ressalva.

## 6. Semântica dos logs (regras antes de qualquer medida operacional)

- Um arquivo de log do segundo turno não é um filtro de eventos do segundo turno. Um
  `logd.dat` contém eventos da preparação, do primeiro e do segundo turno.
  Identifique sessões oficiais de votação, transições de turno, identidade da urna,
  reinícios, suspensões e mudanças de relógio na ordem das linhas antes de escolher
  uma sessão.
- Conte ciclos de eleitor concluídos, não mensagens. Um pedido de dado manual pode
  ser cancelado; não é um voto manual concluído. Ciclos não resolvidos ficam
  desconhecidos.
- Horários são leituras ingênuas do relógio do dispositivo. Guarde a leitura
  original, o deslocamento atribuído, os ajustes, a regra de conversão e sua
  confiança. Não infira fuso a partir de um primeiro voto cedo ou tarde. Relógios não
  resolvidos bloqueiam afirmações de horário absoluto, mas não verificações de
  contagem.
- Elimine históricos copiados por linhagem verificada de blocos, nunca por texto de
  mensagem idêntico e horário com resolução de segundos, que se repetem
  legitimamente.
- O RDV é embaralhado por projeto
  ([TSE](https://www.tse.jus.br/comunicacao/noticias/2021/Julho/registro-digital-do-voto-permite-recontagem-e-amplia-transparencia-do-processo-eleitoral)),
  então ciclos do log não podem ser ligados a escolhas de voto. Nenhum evento
  operacional é atribuído a um candidato.
- A semântica das mensagens vem do
  [guia oficial de logs](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema)
  como modelos exatos revisados (`real-log-rules.json`); mensagens fora deles ficam
  desconhecidas e são contadas num vocabulário de modelos publicado.

## 7. Nível 2: análise estatística

### 7.1 Unidades e desfechos

A unidade é a seção principal, harmonizada entre turnos; seções cuja composição
mudou entre turnos só são pareadas por uma tabela de correspondência explícita, ou
marcadas como incomparáveis. Desfechos:

- comparecimento no segundo turno (comparecimento / eleitorado apto);
- proporção do candidato A entre votos válidos, `A / (A + B)`, indefinida quando não
  há votos válidos; todo teste roda nas duas direções (A e B), com A e B fixados por
  identificadores oficiais de candidatura;
- proporções de brancos e nulos, com denominadores próprios;
- medidas operacionais: proporção de habilitações manuais entre ciclos concluídos,
  proporção de ciclos depois do horário oficial de encerramento e cadência de ciclos
  (ciclos concluídos por minuto ativo).

### 7.2 Modelo principal: variação do primeiro para o segundo turno

O desfecho de cada seção no segundo turno é previsto a partir do seu próprio vetor
do primeiro turno (proporções dos candidatos, brancos, nulos, comparecimento), do
perfil do eleitorado (faixas de idade, sexo, escolaridade), do tamanho e do local
(UF, município, local de votação). Prever a mudança em vez do nível remove a maior
parte da estrutura local estável, principal fonte de falsos alarmes em modelos
transversais.

- **Ruído dependente do tamanho.** Contagens são modeladas com verossimilhança
  binomial superdispersa (beta-binomial), para que seções pequenas não sejam
  sinalizadas por serem ruidosas. Cada seção recebe uma probabilidade preditiva de
  cauda para a contagem observada, com mid-p para a discretude. Um gráfico de funil
  do resíduo contra o tamanho é publicado para cada desfecho.
- **Validação cruzada com ajuste cruzado.** Toda seção é pontuada por um modelo que
  nunca viu seu local de votação: 10 dobras agrupadas por local de votação e
  estratificadas por UF
  ([Chernozhukov et al. 2018](https://doi.org/10.1111/ectj.12097)). Isso dá uma
  pontuação honesta para toda seção, em vez de um pequeno conjunto de teste.
- **Contraste dentro do local.** Seções do mesmo local de votação compartilham
  vizinhança, equipe e logística. A diferença entre uma seção e as demais seções do
  seu local é divulgada como estatística principal, com pouco modelo.
- **Comparador flexível.** Uma floresta de regressão quantílica
  ([Meinshausen 2006](https://www.jmlr.org/papers/v7/meinshausen06a.html)) é
  comparada ao modelo beta-binomial de variação em dados de desenvolvimento, por
  perda quantílica fora da amostra e cobertura de intervalo. O modelo é escolhido
  antes do congelamento; a escolha e os resultados do modelo preterido são
  publicados.
- **Sem o primeiro turno.** Os modelos também são ajustados sem o vetor do primeiro
  turno, porque o próprio primeiro turno pode ter sido afetado.

### 7.3 Família confirmatória

Testes confirmatórios atuam só em nível global ou de agrupamento, onde 500.000 seções
dão poder em vez de uma carga impossível de testes múltiplos. Cada teste é bilateral
ou roda nas duas direções de candidato, e cada um tem nulo por simulação a partir do
modelo ajustado, com reamostragem de locais inteiros.

| ID | Teste | Detecta | Alternativa benigna |
| --- | --- | --- | --- |
| C1 | Calibração dos resíduos de variação: excesso de probabilidades preditivas de cauda extremas, com sinal, para proporção e comparecimento | Manipulação ampla além da variação comum | Especificação errada do modelo (verificada em 2022 e nos dados de desenvolvimento) |
| C2 | Distribuição conjunta comparecimento × proporção comparada ao nulo implicado pelo modelo, no espírito de [Klimek et al. 2012](https://doi.org/10.1073/pnas.1210722109) | Enchimento que eleva comparecimento e um candidato juntos | Comunidades homogêneas fortemente mobilizadas |
| C3 | Excesso de porcentagens inteiras em relação a um nulo dependente do tamanho ([Kobak et al. 2016](https://doi.org/10.1214/16-AOAS904); [Rozenas 2017](https://doi.org/10.1017/pan.2016.9)) | Resultados fabricados ou arredondados | Seções pequenas; testado contra o nulo discreto exato |
| C4 | Estatística de varredura sobre locais de votação e municípios nos resíduos ([Kulldorff 1997](https://doi.org/10.1080/03610929708831995)) | Manipulação geograficamente concentrada | Eventos políticos locais; revistos com evidência de origem |
| C5 | Associação entre excesso operacional (proporção manual, ciclos tardios, cadência) e resíduo de proporção, nas duas direções | Enchimento ou personificação ligados a um candidato | Baixo cadastro biométrico, acessibilidade, filas |
| C6 | Resíduo de variação por modelo de urna e versão de software, dentro do local | Manipulação de software específica de dispositivo | Composição dos locais que usam urnas mais antigas (o erro do Instituto Voto Legal em 2022; seção 7.6) |

A multiplicidade é controlada nessa família por Benjamini–Yekutieli a 5% de FDR
([Benjamini e Yekutieli 2001](https://doi.org/10.1214/aos/1013699998)). A família, as
estatísticas, os nulos, as sementes e os limiares ficam congelados no pré-registro.
Modelos forenses de mistura, como o eforensics de Mebane, rodam como análise
secundária e exploratória; sua conhecida sensibilidade a voto estratégico e à
administração é divulgada com eles.

### 7.4 Rankings de seções servem só para triagem

Pontuações de seções e locais são publicadas como probabilidades preditivas de cauda
ordenadas, para investigação (seção 9). Com 500.000 seções, o menor p-valor de posto
possível e o limiar de testes múltiplos tornam inalcançáveis afirmações
confirmatórias individuais, então rankings não levam rótulo de significância.

### 7.5 Poder e manipulação mínima detectável

Antes do congelamento, manipulações sintéticas são injetadas em cópias dos dados de
desenvolvimento e dos dados de 2022, e o pipeline completo (ajuste, pontuação,
testes) roda de novo:

- mecanismos: troca de votos, enchimento de urna (aumento de comparecimento com
  proporção unilateral), supressão (queda de comparecimento), resultados redondos
  fabricados, trechos de log copiados ou ausentes, erros de relógio;
- magnitudes: de 0,1% a 10% dos votos das seções afetadas;
- concentração: espalhada uniformemente, concentrada em municípios, concentrada numa
  UF, concentrada num modelo de urna.

Para cada mecanismo e concentração o protocolo divulga curvas de poder e a
**manipulação mínima detectável**: a menor mudança na margem nacional detectada com
80% de poder pela família. Perturbações benignas injetadas (erros de relógio, logs
copiados) medem falsos alarmes. Esses números fazem parte do pré-registro e dos
resultados principais.

### 7.6 Controles negativos

- **Eleição presidencial de 2022, os dois turnos,** pelo mesmo pipeline. 2022 não é
  certificada como limpa, mas um método que sinaliza 2022 com a mesma força com que
  sinalizaria uma eleição manipulada não é informativo, e a comparação é publicada de
  qualquer forma.
- **A alegação sobre modelos de urna de 2022.** Em novembro de 2022 um relatório do
  Instituto Voto Legal defendeu descartar os votos de modelos antigos de urna; o TSE
  rejeitou o pedido e multou a coligação que o apresentou
  ([decisão do TSE](https://www.tse.jus.br/comunicacao/arquivos/voto-alexandre-de-moraes)).
  C6 precisa mostrar como um contraste ingênuo por modelo de urna surge de onde as
  urnas antigas foram instaladas, e que o contraste dentro do local o remove.
- **Placebos:** rótulos de candidato permutados dentro do local, rótulos de local
  aleatorizados e o primeiro turno previsto a partir de si mesmo, que devem produzir
  resultados nulos.

### 7.7 Dados de desenvolvimento, confirmatórios e reservados

- **Desenvolvimento:** os dados listados na seção 2. Usados para construir e ajustar
  tudo.
- **Reserva lacrada:** no congelamento, 10% dos locais de votação, sorteados e
  estratificados por UF, com semente publicada no pré-registro e lista com hash. A
  reserva não é aberta até que a rodada confirmatória sobre o restante seja
  publicada. Então replica C1–C6 uma vez, e a concordância é divulgada.
- **Confirmatório:** todos os demais locais. Seus testes rodam uma vez, depois do
  congelamento. Os 596 logs protegidos/de estresse do segundo turno continuam sem
  leitura até o congelamento e então são alocados pelo mesmo sorteio que todos os
  outros locais.
- **UFs de desenvolvimento** são divulgadas de forma descritiva, nunca como evidência
  confirmatória.

## 8. Sensibilidade do resultado

Seja `M = total_A - total_B > 0` a margem nacional oficial, tomada de dados finais
reconciliados. Os limiares aritméticos são:

| Mecanismo assumido e corroborado | Maior mudança de margem por cédula afetada |
| --- | --- |
| Remover um voto inválido contado para A | 1 voto |
| Corrigir um voto contado para A que deveria ser de B | 2 votos |
| Restaurar um voto adicional suprimido para B | 1 voto |

Uma vitória estrita de B exige pelo menos `floor(M/2) + 1` trocas de A para B, ou
`M + 1` remoções ou votos adicionais para B. Para um subconjunto anônimo de `r`
cédulas concluídas removidas de uma seção com `a` votos em A, `b` votos em B e `c`
outras cédulas:

```
d_max = min(r, a) - max(0, r - a - c)
d_min = max(0, r - b - c) - min(r, b)
corrected national margin in [M - d_max, M - d_min]
```

Os limites somam sobre seções disjuntas; detectores sobrepostos são deduplicados
antes. `r` conta cédulas presidenciais, não habilitações nem mensagens. Com um limite
validado `q_i` de cédulas trocadas, a maior correção adversa é `2 * min(q_i, a_i)` por
seção. Se o total ficar abaixo de `M`, esse mecanismo, nessa população e com esse
limite, não pode inverter o resultado; nada se conclui sobre mecanismos fora dele.

Um contrafactual baseado em modelo `2 * sum(a_i - n_valid_i * p_hat_i)` é rotulado
como **excesso em relação à linha de base**, nunca como votos roubados. Sua incerteza
vem de reamostragem geográfica em blocos de todo o pipeline de ajuste, seleção e
estimação. A manipulação mínima detectável (seção 7.5) é divulgada ao lado, para que
o leitor compare o que poderia ficar oculto com o que foi visto.

## 9. Protocolo de investigação

Locais ordenados e uma amostra aleatória de locais não sinalizados recebem o mesmo
pacote de caso: hashes de origem, chaves, valores observados e esperados, definição
de pares, pontuação, resultados de integridade, explicações alternativas,
corroboração buscada e limites de votos afetados. Quem revisa evidência operacional
fica cego à direção do candidato quando possível. A corroboração é buscada em atas de
seção, registros de ocorrência e cópias impressas do BU. Os resultados da
investigação são divulgados para casos sinalizados e não sinalizados, para que a
taxa de falsos alarmes da triagem fique visível.

## 10. Salvaguardas contra inferência seletiva

- Um livro de análise só de acréscimo registra todo desfecho, subgrupo, geografia,
  janela de tempo, comparação de dispositivos e variante de modelo examinados,
  inclusive especificações nulas e malsucedidas.
- Escolher subgrupos depois de ver resultados já é seleção; corrigir só a lista
  exibida não considera a busca ([xkcd 882](https://xkcd.com/882/)).
- Uma vez inspecionado, um dado vira dado de desenvolvimento. Novas afirmações
  confirmatórias precisam de nova evidência reservada.
- Acompanhar resultados à medida que chegam é descritivo; não há regra sequencial de
  parada.
- Um p-valor pequeno não é a probabilidade de fraude; um teste não significativo não
  prova sua ausência; uma FDR de 5% não limita a proporção de votos fraudulentos
  ([declaração da ASA](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf)).
- Testes de dígitos no estilo Benford não são usados como evidência
  ([Deckert, Myagkov e Ordeshook 2011](https://authors.library.caltech.edu/records/5jbtk-8wn05)).
- Permutabilidade só é assumida onde declarada e verificada dentro de estratos;
  onde falha, as pontuações são postos descritivos
  ([Bates et al. 2023](https://doi.org/10.1214/22-AOS2244);
  [Barber et al. 2023](https://arxiv.org/abs/2202.13415)).

## 11. Reprodutibilidade e como contestar os resultados

Os resultados devem poder ser verificados por quem não confia nos autores.

- **Pré-registro.** O protocolo congelado, a família confirmatória, as sementes, o
  hash da reserva e os resultados de poder são registrados no OSF e numa tag git
  assinada antes da rodada confirmatória.
- **Registro de afirmações.** Todo número do relatório de resultados aponta para a
  consulta que o produz, os hashes das releases de entrada e o comando que o
  reconstrói.
- **Kit de replicação.** As tabelas Parquet publicadas e os scripts recalculam todo
  número principal num notebook em menos de uma hora, sem os logs brutos.
- **Reexecução forense.** O pacote de revisão reconstrói qualquer release a partir
  dos bytes originais do TSE, verificados por hash, numa máquina limpa.
- **Explorador.** Notebooks marimo bilíngues sobre as tabelas publicadas permitem
  inspecionar cobertura, resultados de integridade, mapas de resíduos, gráficos de
  funil e pacotes de caso, com toda visão exportável com sua proveniência.
- **Especificações alternativas.** Chaves documentadas (definição de pares,
  conjunto de covariáveis, com ou sem primeiro turno, família de modelo) permitem que
  um revisor rode a família com suas próprias escolhas e compare.
- **Desvios e erratas** são publicados no mesmo repositório, datados e nunca
  reescritos.

## 12. Dados históricos

A história melhora a definição de pares e põe o método à prova; não é um grupo de
controle limpo. Harmonize divisões e fusões de seções, mudanças de eleitorado, regras
de fuso, gerações de urna, fluxos biométricos e número de cargos. Não concatene anos
como se fossem observações independentes. 2022 está no escopo como controle negativo
(seção 7.6); 2018 continua como teste de estresse posterior.

## Referências

- Barber, R. F. et al. (2023). [Conformal prediction beyond exchangeability](https://arxiv.org/abs/2202.13415).
- Bates, S. et al. (2023). [Testing for outliers with conformal p-values](https://doi.org/10.1214/22-AOS2244). *Annals of Statistics*.
- Benjamini, Y. e Yekutieli, D. (2001). [The control of the false discovery rate in multiple testing under dependency](https://doi.org/10.1214/aos/1013699998). *Annals of Statistics*.
- Chernozhukov, V. et al. (2018). [Double/debiased machine learning for treatment and structural parameters](https://doi.org/10.1111/ectj.12097). *Econometrics Journal*.
- Deckert, J., Myagkov, M. e Ordeshook, P. (2011). [Benford's Law and the detection of election fraud](https://authors.library.caltech.edu/records/5jbtk-8wn05). *Political Analysis*.
- Klimek, P., Yegorov, Y., Hanel, R. e Thurner, S. (2012). [Statistical detection of systematic election irregularities](https://doi.org/10.1073/pnas.1210722109). *PNAS*.
- Kobak, D., Shpilkin, S. e Pshenichnikov, M. (2016). [Integer percentages as electoral falsification fingerprints](https://doi.org/10.1214/16-AOAS904). *Annals of Applied Statistics*.
- Kulldorff, M. (1997). [A spatial scan statistic](https://doi.org/10.1080/03610929708831995). *Communications in Statistics: Theory and Methods*.
- Mebane, W. R. Jr. [Artigos de trabalho sobre forense eleitoral](https://public.websites.umich.edu/~wmebane/), incluindo o modelo de mistura finita eforensics (Ferrari, Mebane, McAlister e Wu 2019, e artigos posteriores).
- Meinshausen, N. (2006). [Quantile regression forests](https://www.jmlr.org/papers/v7/meinshausen06a.html). *JMLR*.
- Rozenas, A. (2017). [Detecting election fraud from irregularities in vote-share distributions](https://doi.org/10.1017/pan.2016.9). *Political Analysis*.
- Wasserstein, R. e Lazar, N. (2016). [The ASA statement on p-values](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf).
