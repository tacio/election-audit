# Reprodução e revisão por pares

Document-ID: EA-REPRODUCTION · Revision: 4 · Language: pt-BR

A demonstração sem rede é inteiramente SINTÉTICA: pequenos originais ZIP determinísticos exercitam datas mistas do dispositivo, histórico copiado exato, substituição de dispositivos, solicitação manual/cancelamento, relógios não resolvidos e conteúdo aninhado malformado. Asserções revisadas de sessão/cópia/semântica são geradas com hashes exatos de linhas sintéticas preservadas. Membros esperados 3, principais únicos 2, comparecimento normalizado 10, eleitores aptos 20 e comparecimento proporcional 0.5 são números conhecidos da fixture. Não validam dados eleitorais reais. Ligações de identidade desconhecidas ficam indisponíveis; exploração registrada preserva resultado nulo e histórico completo sem ajuste de modelo.

Execute no repositório com dependências fixadas já instaladas/em cache. Cada saída de demonstração, pacote e reprodução deve ser um diretório novo. Verificação completa lê hashes e publicações congeladas; reprodução não usa coletor nem manifesto ativo.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
rtk proxy env UV_OFFLINE=1 just docs-check
rtk proxy env UV_OFFLINE=1 just docs-command-check
```

`reproduction.json` preserva identidade da observação/snapshot, ID da análise estrutural, grupos limitados de objetos, caminhos exatos de configuração, recursos, validações e resumos criptográficos lógicos. A captura do snapshot registra tempos reais da observação local; nova captura pode produzir identidade diferente. Reprodução reutiliza bytes e tempos congelados. Nunca fabrica tempos de observação. Tempos da origem sintética são valores da fixture explicitamente identificados.

Fixações físicas e lógicas originais exatas permanecem no manifesto de cada publicação imutável. Bytes de novos contêineres DuckDB, tempos de criação e fixações do manifesto-pai podem diferir. Reprodução compara o multiconjunto completo de conteúdo de cada etapa após mapear somente valores explícitos de proveniência parent_release_id para aliases das etapas; hashes da origem, localizadores, configuração, contagens, nulos e demais campos semânticos permanecem exatos. A identidade do artefato estrutural deve coincidir. Cada publicação reconstruída é validada independentemente. Revise IDs originais/reproduzidos em reproduction-result.json.

`review-bundle` exporta cadeias relativas completas de publicações, objetos originais e inventários congelados, entradas, relatórios/SQL e árvores de código explicitamente permitidas: election_audit, scripts, tests, docs e research, além de pyproject.toml, uv.lock, .python-version, .gitignore, justfile e ambos os READMEs. SQLite/WAL ativo, .local-state, .git, .aws, .codex, .agents, .venv, raízes originais, caches e arquivos alheios ficam excluídos. Links simbólicos nas árvores selecionadas são rejeitados antes da cópia. Inventário completo com SHA-256 detecta alterações, remoções e adições; arquivo lateral protege o invólucro contra corrupção acidental. É verificação de integridade, não assinatura autenticada: um adversário que substitua manifesto e arquivo lateral juntos exige resumo criptográfico externo confiável para detecção.

Versões de runtime/pacotes e dependências fixadas exatas são incluídas; distribuições/cache não. Verificação e reprodução sem rede usam runtime fixado instalado. Para executar o código exato do pacote, use BUNDLE/source como diretório de trabalho e o interpretador Python já instalado com `-B` (ou `PYTHONDONTWRITEBYTECODE=1`) para que bytecode não altere o pacote verificado, ou instale o projeto incluído com seu arquivo de dependências e cache sem rede preenchido. Nenhuma instalação pela rede ou identidade de commit Git é alegada.

```python
from election_audit.reproduction import frozen_pipeline, review_bundle, reproduce
from election_audit.pilot import select_pilot, run_pilot
from election_audit.publication import ResourceConfig

config = ResourceConfig()
# frozen_pipeline(snapshot, output, config=config) resumes existing immutable stages.
# review_bundle(run, output) exports the exact declared chain and frozen inputs.
# reproduce(bundle, fresh_output) verifies and rebuilds without raw acquisition.
```

O piloto real seleciona um principal disponível em cada uma de AC, AL, DF, ES e PR, abrangendo cinco macrorregiões dentro de AC–RJ configurado. Abre transação SQLite somente de consulta incluindo WAL confirmado e usa intervalos indexados de URL, com no máximo 100000 mapeamentos atuais de logs por UF. Registra contagem/hash/truncamento dos conjuntos, linhas das UFs amostradas, semente diagnostic-geographic-pilot-v1, hashes exatos dos índices, conjuntos de principais elegíveis, estratos município/zona, posições e exclusões. Principais do índice devem apontar para si ou não ter destino de agregação; arquivos selecionados devem existir, ter tamanho correspondente e no máximo 64 MiB. A criação do snapshot verifica/copia somente ativos selecionados e índices das UFs, mantendo denominadores esperados completos das UFs. Seleção e snapshot são visões ativas separadas: verificações selecionadas congeladas, inventário e reprodução posterior são autoritativos; downloads posteriores não entram no cálculo congelado.

```sh
rtk proxy env UV_OFFLINE=1 just pilot --source /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/raw/2026/turno-2 --output data/my-pilot
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-pilot --output data/my-pilot-review
rtk proxy env UV_OFFLINE=1 just reproduce data/my-pilot-review --output data/my-pilot-reproduction
```

É desenho geográfico diagnóstico, não estimativa ponderada por probabilidades ou nacional. UFs não amostradas/indisponíveis, membros fora da seleção e denominadores desconhecidos permanecem explícitos. Datas reais do dispositivo não atribuem turno independentemente. Somente três classes básicas exatas de mensagens são decodificadas automaticamente; texto desconhecido permanece desconhecido, com localizadores seguros de linha/hash preservados. Não se infere sessão oficial, relógio, atribuição de candidato ou adaptador novo. A validação oficial de BU é um caminho eleitoral separado (veja o [guia eleitoral](electoral-results.md)) e nunca vira validação operacional.

Relatórios nos dois idiomas compartilham cálculos, SQL, cobertura, disponibilidade, exclusões e evidências contestadoras. Revise bytes originais e âncoras, significados oficiais contraditórios, principais ausentes/agregados, regras de relógio, históricos copiados/substituição, BU/correções oficiais e cobertura ZZ. Ciclos reconstruídos não são votos reconciliados. Disponibilidade temporal da origem permanece desconhecida, elegibilidade numérica indisponível, e não há modelo/permutabilidade/margem nacional final.

`docs-check` mantém verificações de metadados/revisões pareados, links, igualdade de blocos de código e estrutura Mermaid. `docs-command-check` inspeciona aspas shell, receitas/comandos/opções longas conhecidas e sintaxe SQL DuckDB usando somente fixtures/caminhos inofensivos --help. Nunca executa comandos documentados de aquisição/processamento retroativo, SQL, substituições shell ou argumentos de arquivo. Sintaxe não estabelece significado da consulta, validade científica ou qualidade da tradução; exigem revisão.

Veja [planejamento retroativo](backfill.md), [índice de implementação](implementation-index.md) e handoffs pareados da tarefa 9 para artefatos reais de aceitação e trabalho restante.
