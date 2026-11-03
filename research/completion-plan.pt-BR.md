# Plano de conclusão da auditoria de 2026

Document-ID: EA-COMPLETION-PLAN · Revision: 10 · Language: pt-BR

[English](completion-plan.md) · [Protocolo do estudo](analysis-plan.pt-BR.md)

Escopo aprovado: fluxo completo de pesquisa dos dois turnos presidenciais de 2026,
com a eleição presidencial de 2022 como controle negativo. O desenho do estudo é o
[protocolo do estudo](analysis-plan.pt-BR.md); este plano o transforma em fases.
Cada fase numerada é atribuída a um novo subagente, roda sozinha e é revisada antes
do despacho da seguinte. Estado atual e locais dos artefatos estão no
[índice de implementação](../docs/pt-BR/implementation-index.md).

## Estado (3 de novembro de 2026)

| Fase | Entrega | Estado |
| --- | --- | --- |
| 10 | Verificar identidades dos dois turnos; coleta explícita por turno; preservar manifestos e bytes originais | Concluída |
| 11 | Processamento estrutural nacional com recursos limitados; medir antes de expandir | Concluída para os 498581 logs elegíveis do segundo turno (só estrutural; veja abaixo) |
| 12–18 | Fases da primeira versão: BU binário, semântica operacional, features, protocolo, modelos, investigações, notebooks | Encerradas como pilotos de desenvolvimento do Acre (AC); as ferramentas são reutilizadas abaixo |

A revisão metodológica de 3 de novembro de 2026 substituiu as definições da primeira
versão das Fases 12–18. Seu código e seus artefatos do AC ficam como pilotos de
desenvolvimento e seus handoffs ficam como registros datados. O trabalho revisado
continua nas Fases 19–26, para que novos handoffs nunca sobrescrevam os antigos.

O que a Fase 11 oferece e o que não oferece: contagens estruturais por log, estrutura
de membros e hashes de blocos para todo log elegível do segundo turno. Cada log do
segundo turno também contém eventos da preparação e do primeiro turno, então suas
contagens misturam turnos; não há sessão, relógio nem tempos; os 596 logs
protegidos/de estresse e todo o primeiro turno não foram processados. Toda medida
operacional precisa, portanto, da passada semântica da Fase 21.

## Fases revisadas

| Fase | Entrega | Reutiliza |
| --- | --- | --- |
| 19 | **Entradas nacionais.** Coletar e congelar, com checksums e manifestos imutáveis: BWEB das 27 UFs e ZZ, os dois turnos; BUs binários, RDVs e assinaturas dos pacotes totalizados; resultados hierárquicos (EA20); perfil do eleitorado por seção e locais de votação; BWEB, BUs, logs e perfil do eleitorado presidenciais de 2022, os dois turnos; relatórios do teste de integridade do TSE no dia da eleição. Fixar as cópias certificadas dos manifestos como entradas da análise e documentar os arquivos de manifesto obsoletos. | `official_bu`, `electoral_imports`, coletor |
| 20 | **Verificações de integridade de nível 1 (I1–I9)** em nível nacional, os dois turnos: relatórios determinísticos com tabelas completas de discrepâncias, hashes de origem e livro de população. Reunir cópias impressas independentes do BU para I8. | `binary_bu`, `electoral_verification` (piloto AC) |
| 21 | **Passada semântica nacional dos logs,** os dois turnos e 2022: uma passada em fluxo por turno aplica as regras de mensagem revisadas e grava agregados por sessão (ciclos por tipo de habilitação, suspensões, leituras de abertura/encerramento, contagens por hora, cadência, eventos de relógio), comparações de blocos do primeiro turno (I6) e um vocabulário de modelos de mensagem. Testada por equivalência contra o adaptador por evento do AC antes da execução nacional. | `national_summary`, `operational_review`, `real-log-rules.json` |
| 22 | **Tabela de features por seção v2:** unidades harmonizadas entre turnos com tabela de correspondência explícita, covariáveis do perfil do eleitorado, chaves de local de votação, modelo de urna e software, medidas operacionais, livro de disponibilidade. | `features` (piloto AC) |
| 23 | **Modelagem de desenvolvimento, estudo de poder e congelamento do protocolo.** Só em dados de desenvolvimento: modelo beta-binomial de variação, contrastes dentro do local, ajuste cruzado, o comparador de floresta quantílica, os testes C1–C6 e seus nulos simulados; corrigir os defeitos conhecidos do modelo da primeira versão (piso de escala fixo `1e-6`, pontuações zero empatadas, seleção de folhas inconsistente com a calibração por local reservado, comparação otimista floresta vs referência). Rodar o estudo de injeção e divulgar a manipulação mínima detectável. Sortear e registrar o hash da reserva lacrada. Congelar e pré-registrar publicamente (OSF e tag git assinada). | `research_models`, `research_protocol`, `research_evaluation` |
| 24 | **Rodada confirmatória,** uma vez: pontuações com ajuste cruzado para toda seção, C1–C6 com controle BY, controle negativo de 2022, testes placebo; depois a única abertura da reserva lacrada. Todos os desvios registrados. | Código congelado da Fase 23 |
| 25 | **Investigações e sensibilidade do resultado:** pacotes de triagem para locais ordenados e locais aleatórios não sinalizados, pedidos de corroboração, limites condicionais de margem e excesso relativo à linha de base. | `investigations` |
| 26 | **Publicação:** relatório bilíngue de resultados liderado pelos resultados de integridade e pela manipulação mínima detectável; registro de afirmações; kit de replicação para notebook; explorador marimo sobre as tabelas publicadas; pacote de revisão reconstruído numa máquina limpa. | `dashboard*`, `reproduction` |

## Regras de recursos e E/S

A máquina tem dois discos de dados rotacionais e uma raiz SSD com cerca de 25 GB
livres. A Fase 11 leu 91.5 GB a cerca de 2.5 MB/s com 94% de pressão de E/S,
enquanto gravava 68.8 GB de checkpoints no mesmo disco para produzir uma release de
547 MB. Leituras aleatórias pequenas, não a CPU, ditam o ritmo. Toda passada completa deve, portanto:

- medir antes a ordem de leitura (ordem do manifesto vs ordem no disco) numa
  amostra;
- manter o volume de checkpoints e saídas proporcional ao resultado, num disco
  diferente do que está sendo lido;
- considerar fundir à primeira passada um reempacotamento sequencial único dos
  objetos brutos no outro disco, para que passadas seguintes leiam em sequência;
- ficar dentro de metade da CPU, 4 GiB de RAM agregada e uma thread de biblioteca por
  processo, com pisos explícitos de espaço livre no SSD e no HDD.

## Política de dados

- Dados de desenvolvimento: AC, as cinco UFs do piloto (AC, AL, DF, ES, PR) e todo
  local nos registros de inspeção das Fases 11 e 15.
- Reserva lacrada: 10% dos locais de votação sorteados por UF no congelamento (Fase
  23) e abertos uma vez, depois da rodada confirmatória (Fase 24).
- Os 596 logs protegidos/de estresse do segundo turno continuam sem leitura até o
  congelamento e então seguem o mesmo sorteio que todos os outros locais.
- As análises leem as cópias certificadas dos manifestos por hash, nunca manifestos
  vivos.
- Desconhecido nunca é zero; sem rótulos de fraude; sem atribuição de ciclos anônimos
  a candidatos.

## Aceitação

Cada fase precisa de testes de regressão, exemplos reais redigidos, livros de
população que reconciliam, execuções interrompidas/retomadas quando longas, medições
de recursos, documentação pareada e um handoff compacto. O relatório da fase
distingue ferramentas implementadas, execuções reais e evidências pendentes. Fontes,
relógios, assinaturas ou permutabilidade ausentes nunca viram fatos inventados.

## Registro de execução

Benchmarks medidos, estudos de ajuste, parcelas, revisões de capacidade, mudança para
o volume de saída adicionado, migração das cópias de origem e a execução final
orientada a features do segundo turno na Fase 11 estão registrados no
[handoff da Fase 11](../docs/pt-BR/handoffs/task-11.md) e no
[guia de processamento orientado a features](../docs/pt-BR/feature-oriented-processing.md).
As evidências salvas estão em `data/national/`. Os pilotos da primeira versão das
Fases 12–18 estão registrados em seus handoffs.
