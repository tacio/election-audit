# Task 12 — Binary BU content verification

Document-ID: EA-HANDOFF-12 · Revision: 1 · Language: en

Implementation: schema-driven `binary_bu` decoder and disk-backed
`electoral_verification` producer. CLI integration uses `electoral_verify_main`.
Streamed BWEB records, preserved EA18/EA20 objects, exact section/local/urn/emission
and choice matching, derived-zero origins, source hashes, resumable section
checkpoints and completed-artifact verification are implemented. Existing v1
releases are unchanged. A completed artifact is verified read-only on replay.

Real execution: `data/phase12/ac-round2/summary.json` records all 2270 AC runoff
principals as `content_verified`, with UF counts matching final EA20 and 4587
preserved source objects. `artifact.json` pins `evidence.sqlite`; inspection
rehashed the database and every preserved source successfully. All three original
binary samples have offline tests against separately acquired BWEB records.
Five verification tests pass; Ruff check and formatting pass.

Scientific limits: `content_verified` certifies the implemented content linkage,
not signature trust, independent voter intent or national completeness. Signature
and RDV verification remain `not_verified`. The official ASN.1 ZIP and attachment
endpoints returned HTTP 403. The exact reviewed public schema mirror is pinned at
SHA-256 `e53e28e9812bb7e19cc4bcc77b6ce48f25c413f62a60369a91c4f269e19b7ed6`,
with its provenance JSON alongside the packaged schema. No official ZIP authenticity
claim follows. Encrypted, nonofficial, wrong-round, trailing-byte and unsupported
presidential category inputs fail.

Compatibility: 374 early real records predate `member_sections`; they retain
`composition_raw` and `location_code`. Consumers must derive members as principal
plus slash-separated aggregated codes, treating `#NULO#`, `#NULO` and `-1` as no
aggregates. Do not rewrite the pinned database. New records include explicit
`member_sections`. Non-valid candidate destinations retain raw nominal counts and
set `legal_final_counts_ready=false`; unsupported legal reclassification must not
be treated as an eligible target.

Remaining: full hierarchical production reconciliation beyond UF, first-round and
other-UF BWEB sources/runs, independently acquired official schema ZIP, signature
trust-chain checks and targeted RDV recounts. The earlier 46-scope AC diagnostic is
separate evidence and is not a claim that this new producer reconciles all levels.
Next: Phase14 consumes the verified artifact with the compatibility rule above;
Phase12 source extensions must close the explicitly retained evidence gaps.
