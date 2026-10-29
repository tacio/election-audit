# Tarefa 2.2 — Contratos de atributos/prontidão

Document-ID: EA-HANDOFF-2.2 · Revision: 1 · Language: pt-BR

Objetivo: identificar entradas, denominadores, papéis e indisponibilidades
explícitas de todos os marts e alvos do protocolo, sem ajustar modelos.

Pré-requisitos: tarefa 2.1 e `research/analysis-plan.md`; sem exigir nova importação.

Arquivos/interfaces: `election_audit/resources/contracts/features.json`, par
`docs/en/feature-readiness.md` / `docs/pt-BR/feature-readiness.md`, validador e testes
orientados a falhas. `load_contract("features")` expõe 21 contratos de atributos,
18 definições de entrada, estados/motivos de prontidão e campos do registro.

Entregas: cobertura operacional, resumos de sessão, disponibilidade de eventos de
processamento, votação tardia, resultados canônicos, unanimidade estrita, horários,
comparação harmonizada de turnos e papéis do registro longo; alvos de comparecimento/
proporção/brancos-nulos, covariáveis, alternativas dispositivo/logística,
integridade, inusualidade/calibração, multiplicidade, validação/investigação e
pré-requisitos de impacto/contrafactual condicionais. Todo atributo inicia
`not_evaluated`. Exclusões: sem cálculo de atributos, modelo nacional, ajuste,
rótulos de fraude ou atribuição de ciclos anônimos a candidato.

Aceitação: `rtk proxy env UV_OFFLINE=1 just check` terminou com 0 e 43 testes,
validação de registros e paridade documental aprovados. Testes cobrem pré-requisitos
de denominadores ausentes e processamento de pacotes independente de BUs importados.

Decisões: after17 doméstico é conclusão estritamente após 17:00:00 Brasília;
igualdade não conta, exterior separado e relógio não resolvido bloqueia o atributo
absoluto. Unanimidade estrita exige total positivo, um candidato com todos os
votos, categorias completas e zero brancos/nulos/especiais/não resolvidos. AC–RJ
parcial nunca sustenta inferência nacional. Outros turnos/histórico são importações
explícitas. Denominador zero torna razão indefinida, não zero. Papéis/especificações
evitem controlar automaticamente os efeitos hipotéticos.

Pendências: registros não fornecem entradas congeladas, reconstrução validada nem
importações eleitorais. Prontidão exige avaliação posterior por unidade.
Permutabilidade, evidência independente, mecanismos e contrafactuais podem seguir
sem suporte mesmo com tabelas preenchidas. Nenhuma margem nacional final é afirmada.

Próxima tarefa exata: **2.3**, referências bilíngues de protocolo/aquisição e
verificações documentais; consultar pesquisa em inglês, referência README,
convenção de pares e modelo. Concluída aqui; handoff [2.3](task-2.3.md).
