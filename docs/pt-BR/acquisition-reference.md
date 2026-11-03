# Logs da eleição presidencial de 2026 do TSE

Document-ID: EA-ACQUISITION-REFERENCE · Revision: 3 · Language: pt-BR

[English](../en/acquisition-reference.md)

Referência do coletor de logs por seção `scripts/download_tse_logs.py`. Ele coleta
os logs originais de seção/urna de qualquer turno da eleição presidencial de 2026,
nos 27 estados e em **ZZ (votação no exterior)**: `--round 1` para o primeiro turno
de 4 de outubro e `--round 2` (o padrão) para o **segundo turno de 25 de outubro de
2026**. Os scripts independentes de coleta e diagnóstico usam só a biblioteca padrão
do Python; o ambiente do projeto está descrito no [README](../../README.pt-BR.md).

## Estado da coleta

Os dois turnos foram coletados por completo. Estas são as execuções finais;
execuções anteriores foram interrompidas por quedas de DNS e retomadas com
`--missing-only`. Registros e logs das execuções estão em `data/phase10/`.

| Turno | Pleito / eleição | Concluída (UTC) | Versões de log | Agregadas | Sem log listado | Auxiliar não publicado | Bytes de objetos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3220 / 6257 | 2026-10-31 23:27 | 499176 | 17931 | 31 | 41 | 53722200971 |
| 2 | 3221 / 6258 | 2026-10-29 22:56 | 499177 | 17931 | 30 | 41 | 90643145031 |

Cada `coverage.json` informa `national_coverage: false` por causa das seções sem log
e sem auxiliar publicado, que permanecem lacunas explícitas. Os dois acervos foram
depois copiados para um volume maior e verificados objeto a objeto; veja o
[índice de implementação](implementation-index.md) para os locais atuais.

Os caminhos do manifesto são relativos ao diretório de saída, então as cópias não
exigiram reescrever manifestos: o `manifest-location.json` de cada raiz copiada
continua apontando para seu manifesto no SSD. Para análise, use as cópias dos
manifestos certificadas por hash feitas na migração, e não os arquivos vivos no SSD; a
raiz copiada do segundo turno também contém um `manifest.sqlite` obsoleto de antes da
separação, que não deve ser lido.

## Inspecionar logs salvos

Inspecione uma pequena amostra dos logs já salvos:

```sh
python3 scripts/inspect_tse_logs.py --per-uf 2
```

Lê o manifesto sem alterá-lo e escreve `data/analysis/log-inspection.json`. As
contagens são diagnósticos brutos por data, com horários ingênuos originais; a
amostra reflete a disponibilidade de downloads e não representa o país. O utilitário
não reconstrói sessões, não normaliza fusos nem atribui votos a candidatos.

`scripts/audit_statistics.py` fornece calibração por postos, correção BY e limites
de impacto de votos anônimos testados. Essas funções matemáticas não estabelecem
hipóteses nulas nem estimam votos fraudulentos.

## Download

```sh
python3 scripts/download_tse_logs.py
```

Comece com uma verificação pequena ao vivo, se desejar:

```sh
python3 scripts/download_tse_logs.py --ufs ac --limit 5
```

Acrescente `--round 1` a qualquer comando para coletar o primeiro turno. Sem
`--output`, o coletor grava em `data/tse/2026/turno-<round>/`.

Repita o comando completo para atualizar todas as seções; logs em cache são
verificados contra SHA-256 antes do reúso. Metadados são buscados novamente para
descobrir arquivos recém-publicados.
Para tentar apenas o trabalho ausente, preservando seções completas:

```sh
python3 scripts/download_tse_logs.py --missing-only
```

Use o mesmo `--output` da execução anterior. O modo atualiza os índices de UF e
verifica as seções salvas em lote. Se os metadados não mudaram e todo log anunciado
existe com o tamanho registrado, as requisições de seção são puladas. Seções com
falha, incompletas, alteradas, com arquivo ausente ou tamanho errado são processadas
de novo. Logs válidos em seção parcialmente completa também são reutilizados.
Agregadas não exigem requisição por seção. Registros de seção/log são copiados para
a nova execução em uma transação por UF, não por seção; a cobertura os inclui em
`reused_sections`.

Retomadas comuns confiam nos checksums registrados sem reler cada log. Para detectar
também corrupção de mesmo tamanho, acrescente `--verify-existing`:

```sh
python3 scripts/download_tse_logs.py --missing-only --verify-existing
```

A verificação completa lê e calcula hashes de todos os candidatos e pode ser lenta
em HDD. Downloads novos sempre mantêm SHA-256 e CRC de ZIP. Um estado completo ainda
exige inventário rápido de metadados/existência/tamanho; então imprime `SKIPPED` e
não cria tarefas por seção. Não há salto cego de UF. Omita `--missing-only` para
atualizar todos os auxiliares, inclusive mudanças ainda não refletidas no índice.

### Downloads paralelos

O coletor usa por padrão 16 trabalhadores de seção simultâneos, com fila contínua
que não espera o lote inteiro terminar. A espera por taxa usa trava separada da do
armazenamento. Todos os trabalhadores compartilham um único orçamento de
requisições; mais trabalhadores ocultam latência sem multiplicar a cota.

Para maior vazão, pare o processo atual com Ctrl+C, espere ele sair e retome na
mesma saída:

```sh
python3 scripts/download_tse_logs.py --missing-only --workers 32 --rps 40
```

`--workers` aceita 1–64; `--rps` aceita até 50 (padrão 20). Mais trabalhadores
ajudam até rede, disco ou limite de requisições virarem gargalo. A taxa conta
requisições de JSON auxiliar e de logs; 40 requisições/segundo não significa 40
seções novas/segundo. O progresso separa `already saved` / `skipped`, seções
restantes `processed`, `new logs` e bytes recebidos, `cached logs` e `aggregated`.
A taxa de processamento exclui seções puladas em lote; contagens de logs novos, não
de seções processadas, indicam downloads reais. O relatório de cobertura inclui
contadores globais e atividade por UF, além do tempo de varredura da retomada.

Execute um único coletor por diretório de saída. Processos separados teriam cotas
separadas e poderiam exceder o limite agregado ou disputar arquivos. Cada execução
obtém trava do SO em `.download.lock` na saída e rejeita outro coletor naquele
diretório. A trava POSIX é liberada ao sair; o arquivo vazio permanece e não
significa processo ativo.

Leituras e escritas do manifesto usam uma conexão SQLite protegida por travas
curtas, com uma transação imediata de escrita por vez. Isso evita competição entre
conexões de trabalhadores e inicialização repetida do WAL, mantendo em paralelo as
requisições de rede, os checksums e a validação dos arquivos.

A disponibilidade de espelhos e os requisitos de verificação estão em
[download-sources.md](../../research/download-sources.pt-BR.md). Nenhum espelho
bruto de 2026 foi verificado ou habilitado.

### Manifesto no SSD e logs no HDD

Pequenas atualizações SQLite podem saturar um HDD mesmo com poucos bytes. Para
manter o acervo no HDD e colocar só o banco no SSD, pare o coletor, espere ele sair
e execute:

```sh
python3 scripts/download_tse_logs.py \
  --output /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 \
  --manifest /home/tacio/code/personal/research/election-audit/.local-state/tse-2026.sqlite \
  --missing-only --workers 32 --rps 40
```

A primeira execução faz backup SQLite consistente no novo caminho, incluindo o WAL
confirmado. Deixa o banco original como snapshot, mantém os objetos no lugar e
registra atomicamente o caminho de referência em `manifest-location.json` na saída.
Execuções seguintes seguem o marcador mesmo sem `--manifest`. O inspetor também o
segue. O banco novo e seus arquivos WAL/SHM ficam juntos no SSD.

Em SQL bruto ou outra ferramenta, resolva o marcador e abra o banco externo; o
antigo `manifest.sqlite` no HDD não está mais atualizado. Mantenha o banco externo
disponível ao mover ou copiar o diretório de dados. Se o caminho registrado estiver
indisponível, o coletor se recusa a criar silenciosamente um manifesto vazio. Um
destino existente nunca é sobrescrito. `.local-state/` é ignorado pelo Git.

Para um disco maior, use `--output /path/on/that/disk/2026-turno-2`. O coletor
mantém uma reserva de espaço livre (`--reserve-gib`, padrão 2) e guarda os logs
comprimidos. Um turno completo ocupa de cerca de 54 GB (primeiro turno) a 91 GB
(segundo turno) em bytes de objetos, além do manifesto. Não há serviço de download
em segundo plano.

## Saídas

No diretório de saída:

- `objects/`: bytes exatos baixados, endereçados por SHA-256; metadados JSON originais
  e logs `.jez` comprimidos. CRCs ZIP dos JEZ são verificados antes de salvar.
- `manifest.sqlite`: URL, caminho local, SHA-256, tamanho, horário de recuperação,
  ETag e Last-Modified; identificadores de seção, agregações, nomes anunciados,
  hashes/estados de pacote e histórico de execuções. Com armazenamento dividido,
  `manifest-location.json` aponta para o banco atual.
- `coverage.json`: cobertura da última execução, incluindo auxiliares ausentes,
  listagens sem logs, versões baixadas e erros. Um subconjunto ou teste pequeno
  bem-sucedido não conta como cobertura nacional.

Consulta de exemplo para localizar originais com identificadores de seção:

```sql
SELECT l.uf, l.municipality, l.zone, l.section, l.package_status,
       l.filename, f.path, f.sha256, l.url
FROM logs l JOIN files f USING (url)
WHERE l.run = (SELECT id FROM runs ORDER BY started_at DESC LIMIT 1);
```

Seções agregadas são registradas com sua principal, não como urnas independentes
ausentes. Toda versão de log anunciada em auxiliar é mantida, inclusive pacotes
recebidos/rejeitados/excluídos; preserve `package_status` ao escolher a população
analítica. O identificador do pacote na URL é registrado separado do SHA-256
calculado localmente. Checksums estabelecem bytes reproduzíveis; não verificam
assinaturas digitais do TSE.

O coletor descobre os identificadores na configuração oficial e exige o turno
presidencial federal escolhido por `--round`: pleito **3220**/eleição **6257** de
04/10/2026, ou pleito **3221**/eleição **6258** de 25/10/2026. Rejeita URLs de
pacote do turno errado antes de retomar. Usa por padrão 20 requisições/segundo no
total, abaixo do máximo documentado pelo TSE de 100. Erros de rede, timeouts e
respostas HTTP 408 e 5xx são repetidos em até quatro tentativas, com espera de 1, 2
e 4 segundos; uma requisição que continua falhando para a execução para
investigação. HTTP 403 e 429 param imediatamente para não prolongar um bloqueio, e
outras respostas 4xx não são repetidas.

## Fontes e limites de cobertura

- [Documentação técnica e identificadores oficiais](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)
- [Configuração eleitoral](https://resultados.tse.jus.br/oficial/comum/config/ele-c.json)
- [EA16: especificação do índice de seções](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea16-arquivo-de-configuracao-de-secoes-eleitorais)
- [EA18: especificação do auxiliar de seção](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
- [Arquivos oficiais em lote](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao)

Os arquivos em lote contêm BU, log, RDV e outros, mas o portal os limita
explicitamente a pacotes **Totalizado**. O coletor por seção registra todos os
pacotes de log atualmente anunciados pelo TSE. Auxiliares podem mudar, e a
documentação diz que inicialmente podem conter só o último pacote recebido: é um
retrato da disponibilidade publicada, não garantia de toda transmissão histórica ou
de toda urna substituta utilizada.
