# Logs do segundo turno presidencial de 2026 do TSE

Document-ID: EA-ACQUISITION-REFERENCE · Revision: 1 · Language: pt-BR

[English](../en/acquisition-reference.md)

Referência histórica preservada do README original. Contagens datadas abaixo são
observações daquele momento; use `rtk proxy just check` para verificações atuais.

Colete logs originais de seção/urna do **segundo turno presidencial de 25 de outubro
de 2026**, incluindo os 27 estados e **ZZ (votação no exterior)**. Os scripts
independentes de coleta e diagnóstico usam só biblioteca padrão Python 3.10+; o
ambiente do projeto está descrito no [onboarding](../../README.pt-BR.md).

## Análise estatística

O [protocolo de análise](../../research/analysis-plan.pt-BR.md) revisa os repositórios
Turicas e INEMA e especifica auditoria não paramétrica, entradas necessárias,
validação, multiplicidade e limites condicionais de impacto. É desenho de pesquisa;
modelo nacional não foi ajustado e não há constatação de fraude. Resultados de BUs
e reconciliação adicional são necessários junto aos logs.

Inspecione pequena amostra dos logs salvos enquanto a aquisição continua:

```sh
python3 scripts/inspect_tse_logs.py --per-uf 2
```

Lê manifesto sem alterá-lo e escreve `data/analysis/log-inspection.json`. Contagens
são diagnósticos brutos por data, com horários ingênuos originais; a amostra reflete
disponibilidade de downloads e não representa o país. O utilitário não reconstrói
sessões, normaliza fusos nem atribui votos a candidatos.

`scripts/audit_statistics.py` fornece calibração por postos, correção BY e limites
de impacto de votos anônimos testados. Essas funções matemáticas não estabelecem
hipóteses nulas nem estimam votos fraudulentos.

Execute todas as verificações com `python3 -m unittest discover -s tests -v`
(34 testes naquele momento).

## Download

```sh
python3 scripts/download_tse_logs.py
```

Comece com verificação pequena ao vivo, se desejar:

```sh
python3 scripts/download_tse_logs.py --ufs ac --limit 5
```

Repita comando completo para atualizar todas as seções; logs em cache são
verificados contra SHA-256 antes do reúso. Metadados são buscados novamente para
descobrir arquivos recém-publicados.
Para tentar apenas trabalho ausente preservando seções completas:

```sh
python3 scripts/download_tse_logs.py --missing-only
```

Use o mesmo `--output` da execução anterior. O modo atualiza índices de UF e verifica
seções salvas em lote. Se metadados não mudaram e todo log anunciado existe com
tamanho registrado, requisições de seção são puladas. Seções falhas, incompletas,
alteradas, com arquivo ausente ou tamanho errado são processadas outra vez. Logs
válidos em seção parcialmente completa também são reutilizados. Agregadas não
exigem requisição por seção. Registros de seção/log são copiados para nova execução
em transação única por UF, não por seção; cobertura inclui-os em `reused_sections`.

Retomadas comuns confiam nos checksums registrados sem reler cada log. Para
detectar corrupção de mesmo tamanho, acrescente `--verify-existing`:

```sh
python3 scripts/download_tse_logs.py --missing-only --verify-existing
```

Verificação completa lê e calcula hashes de todos os candidatos e pode ser lenta
em HDD. Downloads novos sempre mantêm SHA-256 e CRC de ZIP. Estado completo ainda
exige inventário rápido de metadados/existência/tamanho, então imprime `SKIPPED`
e não cria tarefas individuais. Não há salto cego de UF. Omita `--missing-only`
para atualizar todos os auxiliares, inclusive mudanças ainda não refletidas no índice.

### Downloads paralelos mais rápidos

Coletor usa por padrão 16 workers de seção simultâneos, com fila contínua que não
espera lote inteiro. Espera por taxa usa trava separada do armazenamento. Todos
compartilham orçamento único; mais workers ocultam latência sem multiplicar cota.

Para maior vazão, pare o processo atual com Ctrl+C, espere sair e retome na mesma saída:

```sh
python3 scripts/download_tse_logs.py --missing-only --workers 32 --rps 40
```

`--workers` aceita 1–64; `--rps` até 50 (padrão 20). Mais workers ajudam até rede,
disco ou limite de requisições virarem gargalo. Taxa conta JSON auxiliar e logs;
40 requisições/segundo não significa 40 seções novas/segundo. Progresso separa
`already saved` / `skipped`, restantes `processed`, `new logs` e bytes recebidos,
`cached logs` e `aggregated`. Taxa de processamento exclui puladas em lote;
contagens de logs novos, não de seções processadas, indicam downloads reais. O
relatório de cobertura inclui contadores globais e atividade por UF mais tempo
de varredura de retomada.

Execute um downloader. Processos separados teriam cotas separadas e poderiam
exceder limite agregado ou disputar arquivos. Novas execuções obtêm trava do SO
em `.download.lock` na saída e rejeitam outro downloader naquele diretório. A
trava POSIX é liberada ao sair; arquivo vazio permanece e não significa processo
ativo. Versões antigas não usam trava: deixe processo antigo sair primeiro.
Processo em execução continua com código/configuração originais até reiniciar.
O ganho de vazão não foi medido contra serviço TSE ao vivo.

Leituras/escritas do manifesto usam conexão SQLite única protegida por travas
curtas, com uma transação imediata de escrita por vez. Evita competição entre
workers e inicialização repetida de WAL, mantendo rede, checksums e validação de
arquivos paralelos. Esquema e caminhos não mudam; retome com mesma saída após erro
de trava. Conexão única passa teste de 32 workers com busy timeout de 1 ms no
sistema de teste; não foi testada ao vivo no HDD externo.

Disponibilidade de espelhos e requisitos de verificação estão em
[download-sources.md](../../research/download-sources.pt-BR.md). Nenhum espelho
bruto do segundo turno de 2026 foi verificado ou habilitado.

### Manifesto no SSD e logs no HDD

Pequenas atualizações SQLite podem saturar HDD mesmo com poucos bytes. Para
manter corpus no HDD e colocar só banco no SSD, pare downloader, espere sair e execute:

```sh
python3 scripts/download_tse_logs.py \
  --output /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 \
  --manifest /home/tacio/code/personal/research/election-audit/.local-state/tse-2026.sqlite \
  --missing-only --workers 32 --rps 40
```

Primeira execução faz backup SQLite consistente no novo caminho, incluindo WAL
confirmado. Deixa banco original como snapshot, mantém objetos no lugar e registra
atomicamente caminho autorizado em `manifest-location.json` na saída. Execuções
seguintes seguem o marcador mesmo sem `--manifest`. Inspetor também segue.
Banco novo e WAL/SHM ficam juntos no SSD.

Em SQL bruto ou outra ferramenta, resolva marcador e abra banco externo; o antigo
`manifest.sqlite` no HDD não está mais atualizado. Mantenha banco externo disponível
ao mover/copiar diretório de dados. Se caminho registrado estiver indisponível,
downloader recusa criar manifesto vazio silenciosamente. Destino existente nunca
é sobrescrito. `.local-state/` é ignorado pelo Git.

Mudança trata E/S do manifesto; criação de logs ainda usa HDD e ganho real de ponta
a ponta deve ser medido depois de reiniciar.

Para disco maior, use `--output /path/on/that/disk/2026-turno-2`. Coletor reserva
2 GiB livres e mantém logs comprimidos. Tamanho completo é desconhecido até coleta;
pode exceder espaço do workspace. Não há serviço de download em segundo plano.

## Saídas

Sob `data/tse/2026/turno-2/`:

- `objects/`: bytes exatos baixados, endereçados por SHA-256; metadados JSON originais
  e logs `.jez` comprimidos. CRCs ZIP dos JEZ são verificados antes de salvar.
- `manifest.sqlite`: URL, caminho local, SHA-256, tamanho, horário de recuperação,
  ETag e Last-Modified; identificadores de seção, agregações, nomes anunciados,
  hashes/estados de pacote e histórico de execuções. Com armazenamento dividido,
  `manifest-location.json` aponta para banco atual.
- `coverage.json`: cobertura da última execução, incluindo auxiliares ausentes,
  listagens sem logs, versões baixadas e erros. Subconjunto ou teste pequeno
  bem-sucedido não conta como cobertura nacional.

Consulta de exemplo para localizar originais com identificadores de seção:

```sql
SELECT l.uf, l.municipality, l.zone, l.section, l.package_status,
       l.filename, f.path, f.sha256, l.url
FROM logs l JOIN files f USING (url)
WHERE l.run = (SELECT id FROM runs ORDER BY started_at DESC LIMIT 1);
```

Agregadas são registradas com sua principal, não como urnas independentes ausentes.
Toda versão anunciada em auxiliar é mantida, inclusive pacotes recebidos/rejeitados/
excluídos; preserve `package_status` ao selecionar população analítica. Identificador
do pacote na URL é separado de SHA-256 calculado localmente. Checksums estabelecem
bytes reproduzíveis; não verificam assinaturas digitais TSE.

Coletor descobre IDs do segundo turno na configuração oficial e exige eleição
presidencial federal de segundo turno de 25/10/2026. Documentação oficial identifica
pleito **3221** e eleição **6258**. Usa padrão global de 20 requisições/segundo,
abaixo do máximo documentado TSE de 100. Para em 403/429 e erro inesperado de seção;
investigue antes de repetir. Não repete bloqueio, URL ausente ou DNS continuamente.

## Fontes e limites de cobertura

- [Documentação técnica e identificadores oficiais](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)
- [Configuração eleitoral](https://resultados.tse.jus.br/oficial/comum/config/ele-c.json)
- [EA16: especificação do índice de seções](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea16-arquivo-de-configuracao-de-secoes-eleitorais)
- [EA18: especificação do auxiliar de seção](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
- [Arquivos oficiais em lote](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao)

Arquivos em lote contêm BU, log, RDV e outros, mas portal limita explicitamente a
pacotes **Totalizado**. Coletor por seção registra todos os pacotes de log atualmente
anunciados pelo TSE. Auxiliares podem mudar, e documentação diz que inicialmente
podem conter só último pacote recebido: é snapshot da disponibilidade publicada,
não garantia de toda transmissão histórica ou urna substituta utilizada.

## Estado da recuperação em 29 de outubro de 2026

Teste inicial não resolveu hostname TSE. Coleta posterior salvou **10,107 versões
de log**, completando 10,107 principais e registrando 359 agregadas antes de parar
no Amazonas. Manifesto identificou cinco auxiliares com `"f": "O"` maiúsculo;
checagem anterior de fase rejeitava-os incorretamente. Outras 210 linhas de erro
vieram de cancelamento. Agora flags oficiais minúsculos/maiúsculos são aceitos,
e cancelamento não esconde erro original nem cria erro para seção não tentada.

Tente `--missing-only` para continuar. Inspecione `coverage.json` antes da análise;
coleta parcial não estabelece cobertura nacional.

Onze testes offline passam (`python3 -m unittest discover -s tests -v`), cobrindo
retomada de ausentes, reparo de objetos corrompidos/apagados, metadados alterados,
várias versões, agregação, caixa de fase oficial, cancelamento, arquivos inválidos,
parada por taxa, reserva de disco e seleção de eleição/índice.
