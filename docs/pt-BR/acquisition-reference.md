# Logs da eleição presidencial de 2026 do TSE

Document-ID: EA-ACQUISITION-REFERENCE · Revision: 8 · Language: pt-BR

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
  --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/raw/2026/turno-2 \
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

### Cópia certificada dos objetos para o SSD

Passadas sobre os logs brutos leem uma cópia verificada por hash no SSD, não o disco
rotacional. `stage-sources copy` copia cada objeto de uma cópia certificada do
manifesto para uma nova raiz, com os mesmos caminhos relativos. Confere cada corpo de
origem com o SHA-256 do manifesto durante a leitura, descarrega no disco, recalcula o
hash de cada corpo copiado e recusa arquivos faltantes ou extras. Retoma com
`--resume`, mantém um piso de espaço livre e grava na raiz a cópia do manifesto,
`staging-ledger.sqlite` e `staging-certificate.json`. `stage-sources benchmark`
compara antes as ordens de leitura em janelas novas e disjuntas; no disco de dados
rotacional, leia em ordem física, nunca em ordem de seção (URL do manifesto).

```sh
just stage-sources benchmark \
  --certificate /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/certificate-r2.json \
  --manifest /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/manifest-r2.sqlite \
  --output ~/data/election-audit-stage/benchmarks/20261103-r2-url/results.json \
  --window 2000 --orders url path physical --seed 7
just stage-sources copy \
  --certificate /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/certificate-r2.json \
  --manifest /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/manifest-r2.sqlite \
  --destination ~/data/election-audit-stage/2026/turno-2 \
  --order physical --floor-gib 100
```

### Arquivos de dados abertos em massa

Os conjuntos de dados abertos do TSE (arquivos em massa de BU/RDV/log, BWEB, perfil
do eleitorado, locais de votação, resultados, correspondências de mídias, logs de
preparação GEDAI) vêm do catálogo CKAN em `dadosabertos.tse.jus.br`.
`bulk-download fetch` guarda o JSON exato do catálogo, baixa cada recurso
selecionado uma vez numa nova raiz (só de `https://cdn.tse.jus.br/estatistica/sead/`),
retoma com intervalos HTTP só enquanto ETag e tamanho não mudam, registra SHA-256 e
SHA-512, confere o diretório central do ZIP e deixa os arquivos somente leitura.
Quando o TSE publica um `.sha512` irmão, ele é baixado e o arquivo precisa
coincidir; os arquivos em massa de logs não têm. O CDN pode guardar em cache HEAD e
GET separadamente, com cópias de uma republicação anterior ou sem tamanho; por isso
a consulta de metadados leva um parâmetro descartável `revalidate` que alcança a
versão atual, e um GET com ETag diferente é repetido uma vez do mesmo modo e precisa
então coincidir em ETag e tamanho. `bulk-download verify` recalcula
os hashes de uma raiz concluída. Arquivos grandes vão para o disco de dados ext4 e
entradas pequenas para o SSD.

```sh
just bulk-download fetch \
  --dataset resultados-2026-arquivos-transmitidos-para-totalizacao \
  --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
just bulk-download fetch --dataset resultados-2026-boletim-de-urna \
  --output ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna --reserve-gib 100
just bulk-download verify --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
```

#### Relatórios de totalização mudam com o tempo

O conjunto `resultados-2026` (frequência de atualização "Diária" no catálogo) inclui
29 pacotes PDF `Relatorio_Resultado_Totalizacao_2026_<UF>.zip` (27 UFs, BR, ZZ). O TSE recompacta
todos a cada poucas horas (visto em 2026-11-03 às 11:30, 19:30 e 22:30 GMT) com os
mesmos tamanhos em bytes; nessa data nenhum PDF interno era mais novo que
2026-10-25, e a recompactação dos 29 em 2026-11-04 às 08:30 GMT manteve CRC e
tamanho de todos os membros. Os PDFs em si mudam após decisões judiciais: 18 PDFs do primeiro turno
foram regerados entre 2026-10-07 e 2026-10-24, entre eles RJ ("Resultado em
10/10/2026") após a retotalização para governador e MS ("Resultado em 21/10/2026")
após a retotalização para deputados. Todo relatório diz "sujeito a modificações", e
retotalizações podem ocorrer por meses. Trate um relatório baixado como retrato de
um momento (o manifesto guarda ETag e Last-Modified), leia o horário de resultado
impresso em cada PDF e compare retratos pelo CRC dos membros do ZIP, não pelo hash
do arquivo.

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
