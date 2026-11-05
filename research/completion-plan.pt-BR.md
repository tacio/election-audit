# Plano de conclusão da auditoria de 2026

Document-ID: EA-COMPLETION-PLAN · Revision: 13 · Language: pt-BR

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
| 20b | **Conclusão da integridade,** condição para o congelamento da Fase 23: verificar as assinaturas Ed521 das urnas UE2020/UE2022 (descobrir a construção exata do TSE, a partir de vetores de teste publicados, material de verificação do TSE ou uma implementação revisada; conferir a implementação contra vetores antes de qualquer execução nacional); obter as autoridades certificadoras das urnas do TSE (`AC URNA`, `AC UE2020`, `AC UE2022` e suas raízes) e verificar toda cadeia de certificados, ECDSA inclusive; reexecutar o I1 nacionalmente. Também: releitura por prefixo, bloco a bloco, para o I6 (o último bloco aberto, os 99 logs que diferem e os 3645 com blocos a mais); uma fonte para as dez eleições municipais realizadas com o segundo turno (I2); cópias impressas de BU para o I8, ou uma decisão registrada de que nenhuma pode ser obtida. Acrescentado em 5 de novembro de 2026: verificações que o DataUrnas-BR faz e este projeto não, a saber as assinaturas JWS do TSE nos totais divulgados (uma extensão do I4), a zerésima em todo log, as cargas das urnas contra os logs de preparação do GEDAI e os nomes dos programas nos logs contra as listas oficiais de hashes; as cópias de BU impresso lidas por QR Code pelo DataUrnas-BR e a totalização paralela do CMInd como fontes do I8; uma conferência da implementação de Ed521 contra a do DataUrnas-BR nas mesmas assinaturas; uma conciliação, caso a caso, das diferenças de I3 (dez disputas em duas seções de SA) e de I5 com os resultados do DataUrnas-BR; um teste da lista de fusos do oeste do Amazonas do DataUrnas-BR contra os horários de encerramento configurados nas urnas. Os certificados das ACs `AC URNA`, `AC UE2020` e `AC UE2022` vêm do pacote de formatos de 2026 do TSE (`formato-arquivos-de-bu-rdv-e-assinatura-digital.zip`, SHA-256 `b5ac413e81121d53de2bb1657af611f84a45fdc84388e9d9821872994bbfbafd`), que também substitui as especificações ASN.1 espelhadas; as raízes (`AC RAIZ UE`, `AC RAIZ UE v2`) e a `AC URNA v2` não são públicas e são pedidas ao TSE pela Lei de Acesso à Informação (formulário da Ouvidoria, protocolo 83529705172533, registrado em 5 de novembro de 2026; resposta devida até 25 de novembro de 2026, prorrogável até 5 de dezembro), junto com o certificado renovado da `AC URNA` e uma lista de revogados vigente da `AC RAIZ UE` (a publicada venceu em 3 de novembro de 2024). As constatações de transparência e de operação ficam no registro de observações (`docs/pt-BR/observations.md`), atualizado à medida que as fases as revelam. Se algum item não puder ser concluído, o protocolo congelado na Fase 23 declara quais afirmações perdem o apoio do I1 (ou do I6, do I8). | `integrity_checks` |
| 21 | **Passada semântica nacional dos logs,** os dois turnos e 2022: uma passada em fluxo por turno aplica as regras de mensagem revisadas e grava agregados por sessão (ciclos por tipo de habilitação, suspensões, leituras de abertura/encerramento, contagens por hora, cadência, eventos de relógio), comparações de blocos do primeiro turno (I6) e um vocabulário de modelos de mensagem. Testada por equivalência contra o adaptador por evento do AC antes da execução nacional. | `national_summary`, `operational_review`, `real-log-rules.json` |
| 22 | **Tabela de features por seção v2:** unidades harmonizadas entre turnos com tabela de correspondência explícita, covariáveis do perfil do eleitorado, chaves de local de votação, modelo de urna e software, medidas operacionais, livro de disponibilidade. | `features` (piloto AC) |
| 23 | **Modelagem de desenvolvimento, estudo de poder e congelamento do protocolo.** Só em dados de desenvolvimento: modelo beta-binomial de variação, contrastes dentro do local, ajuste cruzado, o comparador de floresta quantílica, os testes C1–C6 e seus nulos simulados; corrigir os defeitos conhecidos do modelo da primeira versão (piso de escala fixo `1e-6`, pontuações zero empatadas, seleção de folhas inconsistente com a calibração por local reservado, comparação otimista floresta vs referência). Rodar o estudo de injeção e divulgar a manipulação mínima detectável. Sortear e registrar o hash da reserva lacrada. Congelar e pré-registrar publicamente (OSF e tag git assinada). | `research_models`, `research_protocol`, `research_evaluation` |
| 24 | **Rodada confirmatória,** uma vez: pontuações com ajuste cruzado para toda seção, C1–C6 com controle BY, controle negativo de 2022, testes placebo; depois a única abertura da reserva lacrada. Todos os desvios registrados. | Código congelado da Fase 23 |
| 25 | **Investigações e sensibilidade do resultado:** pacotes de triagem para locais ordenados e locais aleatórios não sinalizados, pedidos de corroboração, limites condicionais de margem e excesso relativo à linha de base. | `investigations` |
| 26 | **Publicação:** relatório bilíngue de resultados liderado pelos resultados de integridade e pela manipulação mínima detectável; registro de afirmações; kit de replicação para notebook; explorador marimo sobre as tabelas publicadas; pacote de revisão reconstruído numa máquina limpa. | `dashboard*`, `reproduction` |

## Regras de recursos e E/S

A máquina tem dois discos de dados rotacionais e uma raiz NVMe (home em eCryptfs,
cerca de 241 GB livres em 3 de novembro depois da cópia). A Fase 11 leu 91.5 GB a
cerca de 2.5 MB/s com 94% de pressão de E/S, enquanto gravava 68.8 GB de checkpoints
no mesmo disco para produzir uma release de 547 MB. O benchmark de 3 de novembro
atribuiu isso à ordem de leitura: no disco de dados, a ordem de seção (URL do
manifesto) lê a 1.9–3.5 MB/s e a ordem física a 73–92 MB/s. Os dois turnos de 2026
estão agora copiados no SSD com certificados de hash (144.4 GB em 86 minutos). Toda
passada completa deve, portanto:

- ler objetos brutos da cópia certificada no SSD ou, num disco rotacional, em ordem
  física ou de caminho, nunca em ordem de seção, e agrupar os resultados depois;
- medir leituras paralelas no SSD antes de escolher o número de workers (um leitor
  reverificou a 56–63 MB/s pelo eCryptfs);
- manter o volume de checkpoints e saídas proporcional ao resultado, fora do disco
  que está sendo lido;
- gravar arquivos grandes de leitura sequencial (zips em massa do TSE) no disco de
  dados ext4, não no SSD nem no disco NTFS compartilhado;
- ficar dentro de metade da CPU, 6 GiB de RAM agregada (elevado de 4 GiB em
  5 de novembro de 2026, ainda pequeno o bastante para máquinas modestas) e uma
  thread de biblioteca por processo, com pisos explícitos de espaço livre no SSD e no HDD (a cópia usou
  100 GiB no SSD).

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
