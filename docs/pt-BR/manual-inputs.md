# Entradas baixadas à mão

Document-ID: EA-MANUAL-INPUTS · Revision: 1 · Language: pt-BR

O `www.tse.jus.br` e o servidor das listas de revogação do TSE respondem HTTP 403 a
clientes automatizados ([T5](observations.md#transparência)), então algumas entradas
públicas das verificações de integridade precisam ser baixadas num navegador. O
projeto não as redistribui. Este guia lista cada arquivo, onde obtê-lo e o SHA-256
que ele deve ter; toda execução que lê um deles registra o hash lido. Os arquivos de
dados abertos (BWEB, BU, RDV, logs, GEDAI, perfil do eleitorado) são baixados pelo
`bulk-download` e não estão aqui.

Ponha cada grupo numa pasta nova própria em `$EA_STAGE/inputs/` (ver o
[índice de implementação](implementation-index.md#onde-estão-os-resultados) para
`$EA_STAGE`), escreva os hashes abaixo no seu `SHA256SUMS` e confira:

```sh
cd $EA_STAGE/inputs/tse-www-20261108
sha256sum -c SHA256SUMS
```

## Arquivos

| Pasta | Arquivo | Página de origem | SHA-256 | Usado por |
| --- | --- | --- | --- | --- |
| `tse-format-docs-20261105/original/` | `formato-arquivos-de-bu-rdv-e-assinatura-digital.zip` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/formato-arquivos-de-bu-rdv-e-assinatura-digital | `b5ac413e81121d53de2bb1657af611f84a45fdc84388e9d9821872994bbfbafd` | As especificações ASN.1 e os certificados de AC já fixados em `election_audit/resources/` (procedência em `tse-format-2026-official.json`); só é preciso para derivá-los de novo |
| `tse-www-20261108/` | `path1u13.zip`, `path1u15.zip`, `path1u20.zip`, `path1u22.zip` | https://www.tse.jus.br/eleicoes/urna-eletronica/seguranca-da-urna/hash/arquivos/2026/sistemas-em-ambiente-urna-eletronica/ seguido do nome do arquivo sem extensão | `1f34f451ac31f2b8f75db8bd84fda87426bb7a4c2537526d137027409f985afc`, `8f8de1376ca081be55146ea67bc6e4f2122a2da1f11f1409947851da660c422d`, `6f8ac6c7c5c213ddbacceb1c721e3473e8e9a23bd3a1d6c7eebac7512bf5efb7`, `8bd98e4cd27d637c4324106d71ad51de0024e8006134f77da30296835f8cf698` | `integrity-check hash-lists` |
| `tse-www-20261108/` | `manual-verificacao-jws.pdf` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/manual-verificacao-jws | `db1145145e98283689e53d3261c2f9188369d42c9e1e9db351b9e62c38684244` | O arquivo de chave JWS, abaixo |
| `tse-jws-crls-20261109/` | `acdivulgacao.crl`, `actot.crl` | http://actot.tse.jus.br/totalizacao/oficial/crls/ seguido do nome do arquivo | `ad2ffae323c2b202a90a331b43cefbb6b121983e40440a1f570368fe891a90c2`, `bdb88926bf76f8878a2c641d3ee00c6c67f9650c44eacb75170e5d22e738c9f1` | `integrity-check jws --crls` |
| `i8-tse-qrbu-20261107/` | `manual-do-qr-code-no-boletim-de-urna.pdf`, `exemplos-de-boletins-de-urna-com-qr-code.zip` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/manual-do-qr-code-no-boletim-de-urna e …/exemplos-de-boletins-de-urna-com-qr-code | `ffded7303cdb883b11a4640b547afecaf486afc5dcdb6ca532f168c981461790`, `8b1e28fdaff1d589b26836c27727715df8de71efaf0b0bf0cda49c0380a47bc9` | Referência para `integrity-check printed` (o formato está implementado no código) |

As listas de revogação das autoridades certificadoras das urnas estão fixadas em
`election_audit/resources/pki/` e não precisam ser baixadas. Uma lista de revogação
posterior substitui a de cima com outro hash; a verificação JWS informa quando a lista
lida foi emitida e sua próxima atualização.

## O arquivo de chave JWS

A chave que verifica os resultados assinados do TSE está impressa no apêndice B do
manual JWS. Extraia-a e compare seu hash com o fixado em
`election_audit/signed_results.py` (`PINNED_KEY_FILES`); `integrity-check jws` recusa
qualquer outro arquivo de chave:

```sh
python -I scripts/build_jws_key.py $EA_STAGE/inputs/tse-www-20261108/manual-verificacao-jws.pdf $EA_STAGE/inputs/tse-jws-key-20261108/key.json
sha256sum $EA_STAGE/inputs/tse-jws-key-20261108/key.json
```

O arquivo fixado (`d702115854fdfa70fe663f3a190dcca09c04835c37b40f69c5c1d2dc52fb1229`)
foi gerado com o `pdftotext` 24.02.0 do poppler. Outra versão pode dispor o texto de
outro jeito e dar outro hash para a mesma chave; nesse caso compare o JWK e os três
certificados com os do arquivo fixado antes de confiar nele.

## Quando um arquivo muda

O TSE pode republicar uma página com outros bytes. Um hash diferente não é um erro a
contornar: guarde o arquivo antigo, salve o novo numa pasta datada nova, registre os
dois e rode de novo as verificações que o leem em saídas novas.
