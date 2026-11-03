# Tarefa 12 — Verificação do conteúdo de BU binário

Document-ID: EA-HANDOFF-12 · Revision: 1 · Language: pt-BR

Implementação: decodificador `binary_bu` orientado por esquema e produtor
`electoral_verification` em disco. A integração CLI usa `electoral_verify_main`.
Foram implementados leitura BWEB em fluxo, preservação de objetos EA18/EA20,
comparação exata de seção/local/urna/emissão e escolhas, origens de zeros derivados,
hashes, checkpoints por seção e verificação de artefato concluído. Publicações v1
existentes permanecem intactas. Repetições verificam artefatos concluídos sem escrita.

Execução real: `data/phase12/ac-round2/summary.json` registra as 2270 seções
principais AC do segundo turno como `content_verified`, com totais da UF iguais ao
EA20 final e 4587 objetos preservados. `artifact.json` fixa `evidence.sqlite`; a
inspeção recalculou com sucesso o hash do banco e de cada fonte. Os três exemplos
binários originais têm testes sem rede contra registros BWEB adquiridos
separadamente. Os cinco testes passam; Ruff e formatação passam.

Limites científicos: `content_verified` certifica o vínculo de conteúdo
implementado, não confiança criptográfica, intenção independente do eleitor nem
completude nacional. Assinaturas e RDV permanecem `not_verified`. O ZIP ASN.1
oficial e seus endpoints de anexos responderam HTTP 403. O esquema espelhado público
revisado está fixado no SHA-256
`e53e28e9812bb7e19cc4bcc77b6ce48f25c413f62a60369a91c4f269e19b7ed6`,
com JSON de proveniência junto ao esquema empacotado. Isso não autentica o ZIP
oficial. Entradas cifradas, não oficiais, de outro turno, com bytes excedentes ou
categorias presidenciais não suportadas falham.

Compatibilidade: 374 registros reais iniciais antecedem `member_sections`; preservam
`composition_raw` e `location_code`. Consumidores devem derivar membros como seção
principal mais códigos agregados separados por barra, tratando `#NULO#`, `#NULO` e
`-1` como ausência de agregadas. Não reescrever o banco fixado. Novos registros
incluem `member_sections`. Destinações não válidas preservam contagens nominais
brutas e indicam `legal_final_counts_ready=false`; reclassificação jurídica não
suportada não pode virar alvo elegível.

Restam reconciliação hierárquica de produção além da UF, fontes e execuções BWEB do
primeiro turno e outras UFs, ZIP oficial adquirido independentemente, cadeia de
confiança de assinaturas e recontagens RDV direcionadas. O diagnóstico AC anterior
de 46 abrangências é evidência separada e não significa que este produtor
reconcilia todos os níveis. Próximo passo: fase14 consome o artefato verificado com
a regra de compatibilidade acima; extensões de fontes da fase12 devem resolver as
lacunas de evidência explicitamente preservadas.
