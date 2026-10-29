# Vazão de downloads e fontes alternativas

Document-ID: EA-DOWNLOAD-SOURCES · Revision: 1 · Language: pt-BR

[English](download-sources.md)

Verificado em 29 de outubro de 2026. Nenhum espelho independente do conjunto
completo de **logs brutos do segundo turno presidencial de 2026** foi verificado.
É resultado de busca delimitada, não afirmação de inexistência de espelho. O
downloader atualmente usa apenas o TSE.

## Fontes verificadas

| Fonte | O que foi verificado | Decisão |
| --- | --- | --- |
| [TSE Resultados](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados) | Hierarquia oficial de metadados/arquivos de seção e limite publicado de 100 requisições/segundo/IP. | Manter orçamento global único; padrão 20 e teto configurável 50 requisições/segundo. |
| [Arquivos em lote do TSE](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao) | Arquivos por UF/turno têm vários tipos de artefato e só pacotes totalizados. | Caminho potencial separado de aquisição, não substituição completa de todas as versões anunciadas por seção. |
| [Script de espelho Turicas/Brasil.IO](https://github.com/turicas/eleicoes-brasil/blob/develop/mirror.sh) | Script documenta arquivos eleitorais históricos, inclusive candidaturas e outras tabelas; não estabelece espelho atual de logs brutos do segundo turno. O diretório público do espelho não pôde ser inspecionado pela ferramenta web. | Pista útil para histórico; não sintetizar URLs de logs brutos a partir dele. |
| [DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) e seus [releases](https://github.com/alissonlinneker/DataUrnas-BR/releases) | Distribui tabelas Parquet derivadas e material de integridade, com código que busca originais do TSE. Releases inspecionados descrevem 2022 e primeiro turno de 2026. | Comparação independente útil de parser/dados; nenhum espelho bruto de segundo turno verificado e adequado ao downloader. |

Nomes ou metadados de resultados de busca não comprovam cobertura de arquivos
brutos baixáveis, proveniência, limites do serviço ou disponibilidade atual.
Nenhum serviço público foi contatado para solicitar hospedagem ou acesso.

## Condições para acrescentar um espelho

Espelho independente poderia atender requisições concorrentes adicionais dentro
de seus próprios limites publicados. Antes de habilitar:

1. Confirme eleição, turno, versões e cobertura exatos. Prefira inventário explícito
   identificado por seção/pacote/nome de arquivo oficial.
2. Preserve URL oficial, URL real do espelho, horário de recuperação e bytes originais
   como campos separados de proveniência. Não misture CSV/Parquet derivados com JEZ bruto.
3. Autentique arquivos contra resumo oficial com confiança independente ou envelope
   de assinatura TSE verificado. Checksum do próprio espelho detecta corrupção, mas
   não estabelece autenticidade independentemente; tampouco SHA-256 calculado só
   após receber. Não se presume que identificador do pacote na URL seja hash do
   conteúdo. Verificação de assinatura ainda não está implementada aqui.
4. Use orçamento compartilhado em endpoints do mesmo serviço/política; hostnames
   diferentes não implicam cotas independentes. Para espelhos realmente independentes,
   use orçamentos explícitos por provedor e concorrência limitada. Evite baixar o
   mesmo ativo em duplicidade.
5. Respeite 403/429 e política de novas tentativas do provedor. Preserve entrada de
   manifesto para versões ausentes/conflitantes; não preencha lacuna com turno
   anterior nem aceite silenciosamente bytes diferentes.

A CDN em lote do TSE é distribuição oficial alternativa, não evidência de cota de
espelho independente. Arquivos completos também baixam artefatos desnecessários.
Recuperação seletiva de ZIP poderia ser investigada se acesso HTTP por intervalos
e estrutura fossem verificados, com integridade dos bytes e cobertura explícita.
Não foi implementada nem medida.

## Melhorias implementadas

O downloader substitui barreiras fixas de 256 seções por fila contínua limitada,
separa espera de taxa das travas de armazenamento/estado e suporta até 64 workers.
Operações do manifesto usam uma conexão com transações curtas coordenadas; trava
do sistema operacional na saída rejeita novos processos duplicados. Verificações
de retomada, bytes originais, hashes, CRC e orçamento global continuam. Retomadas
comuns de ausentes verificam metadados e existência/tamanho, copiando registros
reutilizados em transação única por UF. Rehash completo usa `--verify-existing`;
novos downloads sempre recebem checksum e verificação do arquivo. Progresso
separa seções puladas, restantes processadas, bytes/arquivos de logs novos,
arquivos em cache e seções agregadas, em vez de combiná-los em taxa de download.

Testes verificam que tarefa lenta não bloqueia as seguintes, esperas de taxa não
bloqueiam armazenamento, workers compartilham orçamento e erros/interrupção param
novo agendamento preservando retomada. Não há alegação de ganho de velocidade ao vivo.

## Observação de gargalo e armazenamento dividido

Amostra de cinco segundos do sistema durante aquisição em 29 de outubro mostrou
o disco rotacional `sda` aproximadamente 100% ocupado, escritas de 0.5 MiB/s,
88 operações de E/S concluídas/segundo e latência média de bloco de 35 ms. O corpus
montado está em sistema FUSE sobre dispositivo criptografado nesse HDD. Contadores
incluem outras atividades, mas o padrão sustenta fortemente gargalo de latência
de E/S, em vez de esgotamento de largura de banda sequencial.

`--manifest` pode colocar SQLite em SSD separado, mantendo objetos no HDD. Migração
usa backup SQLite e referência persistente `manifest-location.json`; o banco
anterior é retido como snapshot. Downloader e inspetor resolvem a referência.
Testes cobrem WAL confirmado, retomadas automáticas, estado externo ausente e
recusa de sobrescrever outro banco. A mudança ainda não foi medida na aquisição
ao vivo do usuário.
