# Fase 10 — Identidade dos turnos e aquisição correta do primeiro turno

Document-ID: EA-HANDOFF-10 · Revision: 4 · Language: pt-BR

[English](../../en/handoffs/task-10.md)

## Resultado — 3 de novembro de 2026

A Fase 10 está concluída. A retomada só de faltantes iniciada em 2026-10-31T16:56:17Z
(PID 574060) terminou em 2026-10-31T23:27:30Z com estado `finished` e sem erro.
Todas as 27 UFs e ZZ foram solicitadas: 499176 versões de log estão salvas, 17931
seções estão agregadas, 31 seções não têm log listado e 41 não têm arquivo auxiliar
publicado. Todos os pacotes do primeiro turno estão `Totalizado` no pleito 3220/eleição
6257. A flag `national_coverage` do coletor é falsa só por causa dessas 72 seções com
lacuna, que permanecem explícitas. Em 1º de novembro os dois turnos foram copiados
para o volume de saída e cada objeto do manifesto foi verificado por SHA-256 e por uma
segunda passagem de stat (`certificate-r1.json` e `certificate-r2.json` em
`2026/migration-2026-11-01/`). BWEB, referências finais, cadastros de candidaturas e
locais e fontes de assinatura/RDV dos dois turnos continuam como importações
separadas, de responsabilidade das fases seguintes.

As seções abaixo são o registro datado de progresso; suas afirmações de "em
andamento" e "em execução" foram superadas por este resultado.

## Recuperação mais recente — 2026-10-31T16:56:17.247041+00:00

A execução seguinte (PID 540761) também parou durante falha de DNS, em
RJ/58335/0126/0088. Seu registro imutável terminou interrompido em
2026-10-31T16:48:44.441478+00:00 com 322610 seções baixadas, 15074 agregadas,
2 registros sem log e 1 erro; cobertura nacional permaneceu falsa. Não havia
coletor ativo na verificação, e nova sondagem ao TSE retornou HTTP 200. Restavam
aproximadamente 250 GiB no HDD, acima da reserva de 20 GiB.

Uma única retomada apenas dos faltantes agora usa PID 574060; comando e local
de progresso estão em `data/phase10/current-acquisition.json` e `data/phase10/resume-launch-20261031T165617Z.json`.
Acompanhe com `tail -f data/phase10/first-round-acquisition-resume-20261031T165617Z.log`. Bytes originais e logs/erros anteriores
continuam preservados. Recuperação não significa conclusão: confira situação
final, cobertura esperada das UFs/ZZ e integridade antes de concluir a Fase 10.

## Condição atual de conclusão — 31 de outubro de 2026

A Fase 10 permanece EM ANDAMENTO. O trabalho agora é sequencial: uma fase/
subagente por vez, concluir e revisar esta fase antes da próxima; marimo (Fase 18)
fica por último. Preservar trabalho posterior já produzido sem executar ou ampliar.

A retomada nacional anterior (PID 483059) terminou após quatro tentativas com
falha de DNS em MG/48950/0194/0172. A execução terminou interrompida no manifesto
em 2026-10-31T10:24:47Z, com 165970 seções baixadas, 9854 agregadas, 2 registros
sem log e 1 erro. Falhas anteriores continuam como histórico; não são apagadas.
O manifesto tinha 331961 mapeamentos de arquivos (17944931974 bytes); o HDD tinha
aproximadamente 249 GiB livres. Uma sondagem posterior ao endpoint oficial retornou
HTTP 200, e a ausência do processo anterior foi confirmada antes de iniciar uma
única retomada apenas dos faltantes. Comando, PID e log novos estão preservados em
`data/phase10/resume-launch-2026-10-31.json`. Usa a mesma raiz/manifesto verificados,
16 trabalhadores, 20 requisições/segundo, reserva de 20 GiB e timeout de 30 segundos.

Iniciar uma retomada não estabelece completude nacional. Antes de concluir a
Fase 10, a execução corrigida deve terminar sem limite, todas as UFs e ZZ devem
ser contabilizadas pelos índices oficiais, erros atuais devem ser resolvidos ou
justificados explicitamente, identidades devem concordar com 3220/6257 e originais
disponíveis devem passar verificações de integridade. Os dois manifestos originais
com nomes incorretos e suas raízes continuam preservados. A Fase 11 não começa antes.


Implementado: ElectionDescriptor validado com election_for_round/coerce_election;
turno 1 é pleito 3220/eleição 6257 em 2026-10-04, turno 2 é pleito 3221/eleição
6258 em 2026-10-25. A aquisição aceita --round (padrão 2), deriva o diretório
padrão dele, confere identificadores/data no catálogo oficial e rejeita URLs de
pacotes do turno errado antes da retomada. Novas linhas run_identity fixam
descritor, raiz e manifesto com SHA-256; execuções históricas não são preenchidas.
Funções de URL do inventário, identidades da cobertura e snapshots aceitam
descritor explícito. read_manifest/inventory_sources/create_snapshot aceitam
source_manifest; a CLI snapshot expõe --round e --source-manifest. Padrões do
segundo turno e snapshots congelados continuam legíveis.

Auditoria real: os dois bancos fornecidos tinham zero mapeamentos 3220 e 998412
mapeamentos 3221. Preserve o corpus incorretamente nomeado primeiro turno; não
foi renomeado nem sobrescrito. data/phase10/source-audit.json preserva contagens
somente leitura. Aquisição corrigida selecionou 3220/6257 oficial e baixou um log
AC (102203 bytes), concluindo uma execução limitada. A nova raiz é
/media/tacio/HDD/Data/tse/data/tse/2026/turno-1-verified e seu manifesto é
.local-state/tse-2026-t1-verified.sqlite. Uma retomada nacional independente está
registrada em data/phase10/first-round-launch.json, com progresso em
first-round-acquisition.log. Usa 16 trabalhadores, 20 requisições/segundo e
reserva de 20 GiB. Iniciada não significa completa; confira processo/manifesto/
situação antes de consumir novos snapshots.

Validação: passaram 31 regressões da aquisição, 23 de snapshots e 4 novos testes
de turno/manifesto/snapshot do primeiro turno. Verificações dedicadas de lint e
formatação cobrem os arquivos atribuídos. Os testes incluem seleção exata de
turno/data/códigos, rejeição de retomada no turno errado e identidades distintas
de snapshots do primeiro turno.

Trabalho restante da Fase 10: a aquisição nacional do primeiro turno deve
terminar; BWEB, referências finais, candidaturas/locais e fontes de assinaturas/
RDV dos dois turnos exigem aquisição/importação separadas. Censo nacional de
fontes e planejamento de recursos são Fase 11. Este registro não afirma cobertura
nacional do primeiro turno nem reconciliação concluída.

Próximo: a Fase 11 usa election_audit.elections e os caminhos verificados acima;
a Fase 12 deve respeitar o descritor ao importar BUs oficiais.
