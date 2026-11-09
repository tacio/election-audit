# Inputs downloaded by hand

Document-ID: EA-MANUAL-INPUTS · Revision: 1 · Language: en

TSE's `www.tse.jus.br` and its revocation-list host answer HTTP 403 to scripted
clients ([T5](observations.md#transparency)), so a few public inputs of the integrity
checks must be downloaded in a browser. The project does not redistribute them. This
guide lists each file, where to get it and the SHA-256 it must have; every run that
reads one records the digest it read. The open-data archives (BWEB, BU, RDV, logs,
GEDAI, voter profile) are fetched by `bulk-download` and are not listed here.

Put each group in its own new folder under `$EA_STAGE/inputs/` (see the
[implementation index](implementation-index.md#where-results-are) for `$EA_STAGE`),
write the digests below to its `SHA256SUMS`, and check them:

```sh
cd $EA_STAGE/inputs/tse-www-20261108
sha256sum -c SHA256SUMS
```

## Files

| Folder | File | Source page | SHA-256 | Used by |
| --- | --- | --- | --- | --- |
| `tse-format-docs-20261105/original/` | `formato-arquivos-de-bu-rdv-e-assinatura-digital.zip` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/formato-arquivos-de-bu-rdv-e-assinatura-digital | `b5ac413e81121d53de2bb1657af611f84a45fdc84388e9d9821872994bbfbafd` | The ASN.1 specifications and CA certificates already pinned in `election_audit/resources/` (provenance in `tse-format-2026-official.json`); only needed to re-derive them |
| `tse-www-20261108/` | `path1u13.zip`, `path1u15.zip`, `path1u20.zip`, `path1u22.zip` | https://www.tse.jus.br/eleicoes/urna-eletronica/seguranca-da-urna/hash/arquivos/2026/sistemas-em-ambiente-urna-eletronica/ followed by the file's stem | `1f34f451ac31f2b8f75db8bd84fda87426bb7a4c2537526d137027409f985afc`, `8f8de1376ca081be55146ea67bc6e4f2122a2da1f11f1409947851da660c422d`, `6f8ac6c7c5c213ddbacceb1c721e3473e8e9a23bd3a1d6c7eebac7512bf5efb7`, `8bd98e4cd27d637c4324106d71ad51de0024e8006134f77da30296835f8cf698` | `integrity-check hash-lists` |
| `tse-www-20261108/` | `manual-verificacao-jws.pdf` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/manual-verificacao-jws | `db1145145e98283689e53d3261c2f9188369d42c9e1e9db351b9e62c38684244` | The JWS key file, below |
| `tse-jws-crls-20261109/` | `acdivulgacao.crl`, `actot.crl` | http://actot.tse.jus.br/totalizacao/oficial/crls/ followed by the file name | `ad2ffae323c2b202a90a331b43cefbb6b121983e40440a1f570368fe891a90c2`, `bdb88926bf76f8878a2c641d3ee00c6c67f9650c44eacb75170e5d22e738c9f1` | `integrity-check jws --crls` |
| `i8-tse-qrbu-20261107/` | `manual-do-qr-code-no-boletim-de-urna.pdf`, `exemplos-de-boletins-de-urna-com-qr-code.zip` | https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/manual-do-qr-code-no-boletim-de-urna and …/exemplos-de-boletins-de-urna-com-qr-code | `ffded7303cdb883b11a4640b547afecaf486afc5dcdb6ca532f168c981461790`, `8b1e28fdaff1d589b26836c27727715df8de71efaf0b0bf0cda49c0380a47bc9` | Reference for `integrity-check printed` (the format is implemented in code) |

The revocation lists of the urn certification authorities are pinned in
`election_audit/resources/pki/` and need no download. A later revocation list
replaces the one above with a different digest; the JWS check reports when the list
it read was issued and its next update.

## The JWS key file

The key that verifies TSE's signed results is printed in appendix B of the JWS
manual. Extract it, then compare its digest with the pinned one in
`election_audit/signed_results.py` (`PINNED_KEY_FILES`); `integrity-check jws` refuses
any other key file:

```sh
python -I scripts/build_jws_key.py $EA_STAGE/inputs/tse-www-20261108/manual-verificacao-jws.pdf $EA_STAGE/inputs/tse-jws-key-20261108/key.json
sha256sum $EA_STAGE/inputs/tse-jws-key-20261108/key.json
```

The pinned file (`d702115854fdfa70fe663f3a190dcca09c04835c37b40f69c5c1d2dc52fb1229`)
was built with poppler's `pdftotext` 24.02.0. Another version may lay out the text
differently and give another digest for the same key; then compare the JWK and the
three certificates with those in the pinned file before trusting it.

## When a file changes

TSE may republish a page with different bytes. A digest that differs is not an
error to work around: keep the old file, save the new one in a new dated folder,
record both, and rerun the checks that read it into new outputs.
