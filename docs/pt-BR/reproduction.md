# Reprodução e revisão por pares

Document-ID: EA-REPRODUCTION · Revision: 6 · Language: pt-BR

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

## O que esperar nos dados nacionais

Tempos medidos na máquina de referência: Intel Core i7-9750H (6 núcleos, 12
threads), 31 GB de RAM, cópia de trabalho em SSD NVMe e um HDD de 2,5 polegadas e
5400 rpm como volume de saída. As execuções usaram no máximo metade das threads da
CPU e 6 GiB de RAM no total. "Ativo" exclui suspensões da máquina. "Não registrado"
quer dizer que nenhuma medição foi guardada; nada abaixo é estimado.

| Etapa | Comando | Escala | Workers | Tempo | Pico de RAM | Saída |
| --- | --- | --- | --- | --- | --- | --- |
| Logs das urnas, dois turnos (Fase 10) | `download` | 499176 e 499177 versões de log, 53.7 GB e 90.6 GB | — | Vários dias, limitado pela rede; não registrado por turno | Não registrado | Raízes brutas |
| Entradas de dados abertos (Fase 19) | `bulk-download` | BWEB 4.9 GB (2026) e 1.5 GB (2022); perfil do eleitorado 3.3 GB e 0.96 GB; arquivos de BU/RDV/log 219.2 GB (2026) e 168.5 GB (2022) | — | Limitado pela rede; não registrado | Não registrado | `inputs/`, `bulk/` |
| Cópia no SSD, dois turnos | `stage-sources copy` | 53.7 GB e 90.6 GB | — | 86 min: cópias 931 s e 1587 s, novos hashes 954 s e 1431 s | Não registrado | 144.3 GB no SSD |
| Verificações de integridade, 2026, por turno (Fase 20) | `integrity-check sections` | 499207 seções | 6 | 64 e 59 min | Não registrado | 618 MB e 325 MB |
| | `integrity-check bweb` | BWEB 5.1 GB (1º turno, todos os cargos) e 0.14 GB (2º turno) | 1 | 30 min e 66 s | Não registrado | 2.1 MB e 1.2 MB |
| | `integrity-check hierarchy` | Nós do EA20 | 1 | 17 min e 21 s | Não registrado | 96 KB |
| | `integrity-check correspondence`, `logs` | Por turno | 1 | Menos de um minuto cada | Não registrado | Menos de 2 MB |
| Seções de integridade v3, 2026, por turno (Fase 20b) | `integrity-check sections` | 499207 seções, Ed521 com `ed521rs` | 6 | 1:07:49 e 1:00:38; CPU 10210 s e 5411 s (v2 em Python puro: 2:57:15 e 2:21:17) | 4.9 GB e 4.2 GB (maior processo) | 629 MB e 337 MB |
| Passada semântica v3, por ano e turno (Fase 22) | `semantic-pass run` | 2026: 498580 e 498581 objetos; 2022: 471859 e 471983 | 5 | Ativo 8002 s e 12808 s (2026), 7277 s e 11809 s (2022) | Cerca de 1.7 GB no total; maior processo 1.2 GB | 1.8, 2.9, 1.7 e 2.7 GB |
| Tabela por seção v3, por ano (Fases 22 e 20b) | `section-table build` | 499248 e 472693 seções por turno | 1 | 47 min (2026) e 78 min (2022); v2: 45 e 41 min | 3.7 GB e 3.0 GB | 192 MB e 183 MB |
| Verificação offline | `just check` | 394 testes | 1 | 117 s | — | — |

Depois dos downloads, reproduzir as versões atuais leva cerca de 17 horas de
processamento: cópia no SSD, verificações de integridade, as quatro passadas
semânticas e as duas tabelas. As passadas da Fase 21 (v1 para 2026, v2 para 2022)
não são necessárias, porque a v3 contém todas as colunas delas.

O que determina os tempos:

- O 2º turno demora mais porque cada log do 2º turno guarda toda a história da urna,
  da preparação ao 1º turno, e por isso tem o dobro de sessões.
- Os logs de 2026 são lidos da cópia no SSD. No HDD, a ordem das seções leu a 1.9–3.5 MB/s e a
  ordem física a 73–92 MB/s
  ([índice de implementação](implementation-index.md#estado-atual)).
- Os logs de 2022 são lidos direto dos arquivos 7z no HDD, na ordem física.
- O BWEB do 1º turno traz todos os cargos, então suas verificações leem 35 vezes
  mais dados que no 2º turno.

Execuções longas retomam com `--resume` e o mesmo vínculo. Desligue a suspensão
automática do desktop para execuções noturnas: um bloqueio de suspensão não impediu
uma suspensão, embora as execuções tenham retomado sem erros. Envolva cada execução
nacional em `/usr/bin/time -v` para registrar tempo e pico de memória.
