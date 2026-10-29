# Download throughput and alternative sources

Document-ID: EA-DOWNLOAD-SOURCES · Revision: 1 · Language: en

[Português](download-sources.pt-BR.md)

Checked 29 October 2026. No independently hosted mirror of the complete **raw
2026 presidential runoff logs** has been verified. This is a bounded search result,
not a claim that no such mirror exists. The downloader currently uses TSE only.

## Sources checked

| Source | What was verified | Decision |
| --- | --- | --- |
| [TSE Resultados](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados) | Official section metadata/file hierarchy and a published limit of 100 requests/second/IP. | Keep one global budget for the existing collector; default 20 and configurable ceiling 50 requests/second. |
| [TSE bulk archives](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao) | Archives by UF/round contain several artifact types and only totalized packages. | Potential separate acquisition path, not a complete replacement for all advertised per-section versions. |
| [Turicas/Brasil.IO mirror script](https://github.com/turicas/eleicoes-brasil/blob/develop/mirror.sh) | Script documents historical electoral archives, including candidacy and other tables; it does not establish a current raw-runoff-log mirror. The public mirror directory could not be inspected with the web tool. | Useful historical-data lead; do not synthesize raw-log URLs from it. |
| [DataUrnas-BR](https://github.com/alissonlinneker/DataUrnas-BR) and its [releases](https://github.com/alissonlinneker/DataUrnas-BR/releases) | Project distributes derived Parquet tables and integrity material and provides code to fetch raw files from TSE. Inspected releases describe 2022 and 2026 first-round work. | Useful independent parser/data comparison; no verified raw second-round mirror suitable for this downloader. |

Names or metadata found in search results do not establish downloadable raw-file
coverage, provenance, service limits or current availability. No public services
were contacted to request hosting or access.

## Conditions for adding a mirror

An independently hosted mirror could serve additional concurrent requests within
its own published limits. Before enabling one:

1. Confirm the exact election, round, package versions and coverage. Prefer an
   explicit inventory keyed by official section/package/filename.
2. Preserve the official URL, actual mirror URL, retrieval time and original bytes
   as separate provenance fields. Do not mix derived CSV/Parquet with raw JEZ files.
3. Authenticate files against an independently trusted official digest or a
   verified TSE signature envelope. A mirror's own checksum detects corruption but
   does not independently establish authenticity; neither does a SHA-256 computed
   only after receiving the file. The package identifier in the URL is not assumed
   to be the content hash. Signature verification is not yet implemented here.
4. Use a shared budget for endpoints backed by the same service/rate policy;
   different hostnames do not automatically imply independent allowances. For
   genuinely independent mirrors, use explicit per-provider budgets and bounded
   concurrency. Avoid duplicate downloads of the same asset.
5. Respect 403/429 responses and each provider's retry policy. Preserve a manifest
   entry for missing/conflicting versions; do not fill a coverage gap with an
   earlier round or silently accept different bytes.

TSE's own bulk CDN is an alternative official distribution path, not evidence of
an independent mirror allowance. Full archives also download artifacts we do not
need. Selective ZIP retrieval could be investigated if HTTP range access and
archive layouts are verified, with byte-integrity checks and explicit coverage
accounting. It has not been implemented or benchmarked.

## Implemented improvements

The section downloader replaces fixed 256-section barriers with a bounded rolling
queue, separates rate waits from storage/state locking, and supports up to 64
workers. Manifest operations use one connection with coordinated short
transactions; an OS output-directory lock rejects duplicate new downloader
processes. Resume checks, original-byte storage, hashes, archive CRC checks and the
global request budget remain in place. Ordinary missing-only resumes check
manifest metadata plus file existence/size and copy reused records in one
transaction per UF. Full rehashing is available with `--verify-existing`; new
downloads always receive checksum and archive checks. Progress distinguishes
skipped sections, remaining processed sections, new log bytes/files, cached log
files and aggregated sections rather than combining them as a download rate.

The test suite checks that a slow task does not starve later work, rate waits do
not block storage, workers share one request budget, and errors/interruption stop
new scheduling while preserving resumability. No live speedup claim is made.

## Storage bottleneck observation and split storage

A five-second system-wide sample during acquisition on 29 October showed the
rotating `sda` drive at approximately 100% busy, 0.5 MiB/s writes, 88 completed I/O
operations/second and 35 ms average block-I/O latency. The mounted corpus resides
on a FUSE filesystem over an encrypted block device on that HDD. These counters
include other activity, but the pattern strongly supports an I/O-latency
bottleneck rather than exhaustion of sequential disk bandwidth.

`--manifest` can now place the SQLite database on a separate SSD while leaving
objects on the HDD. Migration uses SQLite backup and a persistent
`manifest-location.json` reference; the prior database is retained as a snapshot.
The downloader and inspection utility resolve that reference. Tests cover
committed WAL contents, later automatic resumes, missing external state and
refusal to overwrite another database. This storage change has not yet been
benchmarked on the user's live acquisition.
