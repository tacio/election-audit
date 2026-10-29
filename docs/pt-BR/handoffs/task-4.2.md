# Tarefa 4.2 — Eventos estruturais e diagnósticos seguros

Document-ID: EA-HANDOFF-4.2 · Revision: 1 · Language: pt-BR

Objetivo: conservar evidências ordenadas de mensagens operacionais sem inventar
sessões nem persistir campos sensíveis de mensagens/tokens. Pré-requisitos:
[4.1](task-4.1.md), convenções de localizadores/identidade e contrato `parsing_issue`.

Arquivos/interfaces: `_Parser.lines` em `election_audit/archive_parsing.py`,
`events.jsonl`, `issues.jsonl`; [guia](../archive-parsing.md).

Entregas: decodificador Latin-1 de seis colunas, horários locais brutos validados
do dispositivo, identidade do dispositivo/aplicação, sequência e localizadores
de linhas, SHA-256 da linha física exata incluindo terminadores originais, três
classes exatas de mensagens VOTA e classes desconhecidas explícitas. Registros
malformados/excessivos produzem diagnósticos limitados sem amostras brutas. Os
bytes originais ficam congelados separadamente; não são selecionados IDs de
eleitores/mesários, mensagens brutas ou tokens sensíveis. Mensagens idênticas
repetidas permanecem eventos distintos, com todos os contextos não resolvidos.

Aceitação: os comandos abaixo terminaram com código 0; passaram todas as 15
fixtures do analisador e 83 testes offline no total. As fixtures verificam linhas
malformadas/excessivas, números originais de linhas, truncamento de diagnósticos,
mensagens repetidas no mesmo segundo, datas/aplicações de preparação misturadas,
minimização de dados e hashes distintos de textos/terminadores desconhecidos.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
```

Decisões: `completion_message` é evidência, não votos; sem turno inferido do nome
nem conversão de fuso. Deslocamentos de bytes desconhecidos ficam nulos. Pendente:
somente três classes VOTA são decodificadas; semânticas adicionais exigem extensões
versionadas, nunca deduplicação apenas por tipo/horário. Sem acervo real nem
alterações na aquisição.

Próxima: [4.3](task-4.3.md), artefatos reutilizáveis e associações congeladas.
