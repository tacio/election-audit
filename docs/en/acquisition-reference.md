# TSE 2026 presidential election logs

Document-ID: EA-ACQUISITION-REFERENCE · Revision: 8 · Language: en

[Português](../pt-BR/acquisition-reference.md)

Reference for the per-section log collector `scripts/download_tse_logs.py`. It
collects the original section/urn logs of either round of the 2026 presidential
election, for all 27 states and **ZZ (voting abroad)**: `--round 1` for the
4 October first round and `--round 2` (the default) for the **25 October 2026**
runoff. The standalone collector and diagnostic scripts use only the Python
standard library; the project environment is described in the
[README](../../README.md).

## Retrieval status

Both rounds are fully collected. These are the final runs; earlier runs were
interrupted by DNS outages and resumed with `--missing-only`. Run records and logs
are in `data/phase10/`.

| Round | Pleito / election | Finished (UTC) | Log versions | Aggregated | No log listed | Auxiliary not published | Object bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3220 / 6257 | 2026-10-31 23:27 | 499176 | 17931 | 31 | 41 | 53722200971 |
| 2 | 3221 / 6258 | 2026-10-29 22:56 | 499177 | 17931 | 30 | 41 | 90643145031 |

Each `coverage.json` reports `national_coverage: false` because of the no-log and
unpublished-auxiliary sections, which stay explicit gaps. Both stores were later
copied to a larger volume and verified object by object; see the
[implementation index](implementation-index.md) for current locations.

Manifest paths are relative to the output directory, so the copies needed no
manifest rewrite: each copied root's `manifest-location.json` still points at its
SSD manifest. For analysis, use the hash-certified manifest copies made during the
migration rather than the live SSD files; the copied round-2 root also contains a
stale pre-split `manifest.sqlite` that must not be read.

## Inspecting saved logs

Inspect a small sample of the logs already saved:

```sh
python3 scripts/inspect_tse_logs.py --per-uf 2
```

This reads the acquisition manifest without changing it and writes
`data/analysis/log-inspection.json`. Counts are raw message diagnostics by date,
with original naive device times; the sample reflects download availability and
is not nationally representative. The utility does not reconstruct voting
sessions, normalize timezones or attribute votes to candidates.

`scripts/audit_statistics.py` provides tested rank calibration, BY multiplicity
correction and anonymous-ballot impact bounds. These mathematical helpers do not
establish the null assumptions or estimate fraudulent votes.

## Download

```sh
python3 scripts/download_tse_logs.py
```

Start with a small live check if desired:

```sh
python3 scripts/download_tse_logs.py --ufs ac --limit 5
```

Add `--round 1` to any command to collect the first round. Without `--output`, the
collector writes to `data/tse/2026/turno-<round>/`.

Rerun the full command to refresh all sections; individual cached logs are checked
against SHA-256 before reuse. Metadata is fetched again to discover newly
published files.
To retry only missing work while keeping completed sections:

```sh
python3 scripts/download_tse_logs.py --missing-only
```

Use the same `--output` directory as the previous run. This mode refreshes the UF
indexes, then checks saved sections in bulk. When section metadata is unchanged
and every advertised log is present with the recorded size, section requests are
skipped. Failed, unfinished, changed, missing-file and wrong-size sections are
processed again. Valid logs within a partially completed section are reused too.
Aggregated sections require no per-section request. Existing section and log
records are copied into the new run in one database transaction per UF rather
than one transaction per section; coverage includes them in `reused_sections`.

Ordinary resumes trust the recorded checksums without rereading every saved log.
To detect same-size corruption as well, add `--verify-existing`:

```sh
python3 scripts/download_tse_logs.py --missing-only --verify-existing
```

Full verification reads and hashes all candidate logs and can be slow on an HDD.
Newly downloaded logs always retain SHA-256 and ZIP CRC checks. A completed state
still needs a quick metadata/existence/size inventory check, then prints `SKIPPED`
and creates no per-section download tasks. There is no blind state-level skip.
Omit `--missing-only` to refresh all section auxiliary files, including updates
which might not have changed the UF index yet.

### Parallel downloads

The collector defaults to 16 concurrent section workers, with a rolling work
queue that does not wait for a full batch to finish. Request-rate waits use a
separate lock from file storage. All workers share a single request budget;
adding workers hides network latency without multiplying that budget.

For more throughput, stop the current process with Ctrl+C, wait for it to exit,
and resume using the same output directory:

```sh
python3 scripts/download_tse_logs.py --missing-only --workers 32 --rps 40
```

`--workers` accepts 1–64; `--rps` accepts up to 50 (default 20). More workers help
until network, disk or the request limit becomes the bottleneck. The rate counts
both auxiliary JSON requests and log requests, so 40 requests/second does not
mean 40 new sections/second. Progress separates `already saved` / `skipped`,
`processed` remaining sections, `new logs` and bytes received, `cached logs`, and
`aggregated` sections. The processing rate excludes sections skipped in bulk;
new-log counts, not processed-section counts, indicate actual log downloads.
The coverage report includes global request/download counters and per-state
activity plus resume-scan time.

Run one downloader process per output directory. Separate processes would have
separate budgets and could exceed the server's aggregate limit or race on the
output files. Each run takes an OS lock on `.download.lock` in the output directory
and rejects another downloader for that directory. This POSIX lock is released
automatically on exit; the empty file remains and does not mean a process is still
running.

Manifest reads and writes use one SQLite connection guarded by short locks, with
one immediate write transaction at a time. This avoids competing worker
connections and repeated WAL initialization while retaining parallel network
requests, checksum checks and archive validation.

Mirror availability and verification requirements are recorded in
[download-sources.md](../../research/download-sources.md). No raw 2026 mirror
has been verified or enabled.

### Keep the manifest on SSD and logs on HDD

SQLite's small updates can saturate an HDD even at low byte throughput. To keep
the large log corpus on the HDD and place just the database on an SSD, stop the
current downloader, wait for it to exit, and run:

```sh
python3 scripts/download_tse_logs.py \
  --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/raw/2026/turno-2 \
  --manifest /home/tacio/code/personal/research/election-audit/.local-state/tse-2026.sqlite \
  --missing-only --workers 32 --rps 40
```

The first invocation makes a consistent SQLite backup to the new path, including
any committed WAL contents. It leaves the original database as a snapshot, keeps
the object files in place, and atomically records the authoritative database path
in `manifest-location.json` in the output directory. Later runs automatically
follow that marker even if `--manifest` is omitted. The inspection utility also
follows it. The new database and its WAL/SHM files live together on the SSD.

If using raw SQL or another tool, resolve the marker and open the external
database; the old HDD `manifest.sqlite` is no longer current. Keep the external
database available when moving or backing up the data directory. If the recorded
path is unavailable, the downloader refuses to silently create an empty manifest.
An existing destination is never overwritten. `.local-state/` is git-ignored.

To use a larger disk, pass `--output /path/on/that/disk/2026-turno-2`. The
collector keeps a free-space reserve (`--reserve-gib`, default 2) and keeps logs
compressed. A complete round occupies roughly 54 GB (round 1) to 91 GB (round 2)
of object bytes, plus the manifest. There is no background download service.

### Stage certified objects on the SSD

Passes over the raw logs read a hash-verified copy on the SSD, not the rotational
drive. `stage-sources copy` copies every object of a certified manifest copy into a
new root under the same relative paths. It checks each source body against the
manifest SHA-256 while reading, flushes, re-hashes every staged body and refuses
missing or extra files. It resumes with `--resume`, keeps a free-space floor and
writes the manifest copy, `staging-ledger.sqlite` and `staging-certificate.json`
into the root. `stage-sources benchmark` first compares read orders on fresh,
disjoint windows; on the rotational data drive, read in physical order, never in
section (manifest URL) order.

```sh
just stage-sources benchmark \
  --certificate /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/certificate-r2.json \
  --manifest /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/manifest-r2.sqlite \
  --output ~/data/election-audit-stage/benchmarks/20261103-r2-url/results.json \
  --window 2000 --orders url path physical --seed 7
just stage-sources copy \
  --certificate /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/certificate-r2.json \
  --manifest /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/2026/migration-2026-11-01/manifest-r2.sqlite \
  --destination ~/data/election-audit-stage/2026/turno-2 \
  --order physical --floor-gib 100
```

### Bulk open-data archives

TSE open-data datasets (bulk BU/RDV/log archives, BWEB, voter profile, polling
places, results, media correspondences, GEDAI preparation logs) come from the
CKAN catalog at `dadosabertos.tse.jus.br`. `bulk-download fetch` keeps the exact
catalog JSON, downloads each selected resource once into a new root (only from
`https://cdn.tse.jus.br/estatistica/sead/`), resumes with HTTP ranges only while
the ETag and length are unchanged, records SHA-256 and SHA-512, checks the ZIP
central directory and makes files read-only. When the TSE publishes a sibling
`.sha512`, it is fetched and the archive must match it; the bulk log archives have
none. The CDN can cache HEAD and GET separately, with copies from an earlier
republication or without a length, so the metadata request carries a throwaway
`revalidate` query that reaches the current version; a GET whose ETag differs is
retried once the same way and must then match ETag and length.
`bulk-download verify` re-hashes a finished root. Large archives go to the
ext4 data drive and small inputs to the SSD.

```sh
just bulk-download fetch \
  --dataset resultados-2026-arquivos-transmitidos-para-totalizacao \
  --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
just bulk-download fetch --dataset resultados-2026-boletim-de-urna \
  --output ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna --reserve-gib 100
just bulk-download verify --output /media/tacio/f6fe5b1e-92b6-4376-9d25-bbca73160229/election-audit/bulk/2026-arqurnatot
```

#### Totalization reports are a moving target

The `resultados-2026` dataset (catalog update frequency "Diária") includes 29
`Relatorio_Resultado_Totalizacao_2026_<UF>.zip` PDF packages (27 UFs, BR, ZZ). TSE re-zips all of
them every few hours (seen on 2026-11-03 at 11:30, 19:30 and 22:30 GMT) with the
same byte sizes; on that date no PDF inside was newer than 2026-10-25, and the
2026-11-04 08:30 GMT re-zip of all 29 kept every member CRC and size unchanged. The PDFs
themselves do change after court decisions: 18 first-round PDFs were regenerated
between 2026-10-07 and 2026-10-24, including RJ ("Resultado em 10/10/2026") after
the governor retotalization and MS ("Resultado em 21/10/2026") after the deputy
retotalization. Every report says "sujeito a modificações", and retotalizations
can follow for months. Treat a fetched report as a point-in-time snapshot (the
manifest keeps its ETag and Last-Modified), read the result time printed in each
PDF, and compare snapshots by ZIP member CRC rather than by archive hash.

## Outputs

Under the output directory:

- `objects/`: exact downloaded bytes, addressed by SHA-256; original JSON metadata
  and compressed `.jez` logs. JEZ ZIP CRCs are checked before saving.
- `manifest.sqlite`: source URL, local object path, SHA-256, byte length, retrieval
  time, ETag and Last-Modified; section identifiers, aggregation relationships,
  advertised filenames, package hashes and package status, plus run history. With
  split storage, `manifest-location.json` points to the current database instead.
- `coverage.json`: coverage for the latest invocation, including missing auxiliary
  files, missing log listings, downloaded versions and any error. A successful
  subset or smoke test does not count as national coverage.

Example query to locate the original files with section identifiers:

```sql
SELECT l.uf, l.municipality, l.zone, l.section, l.package_status,
       l.filename, f.path, f.sha256, l.url
FROM logs l JOIN files f USING (url)
WHERE l.run = (SELECT id FROM runs ORDER BY started_at DESC LIMIT 1);
```

Aggregated sections are recorded with their principal section rather than treated
as missing independent urns. Every log version advertised in an auxiliary file is
kept, including received/rejected/excluded packages; retain `package_status` when
choosing the analysis population. The package identifier in the URL is recorded
separately from our locally calculated SHA-256. Checksums establish reproducible
bytes; they do not verify TSE digital signatures.

The collector discovers identifiers from the official configuration and requires
the federal presidential round selected by `--round`: pleito **3220**/election
**6257** dated 04/10/2026, or pleito **3221**/election **6258** dated 25/10/2026.
It rejects wrong-round package URLs before resuming. It uses 20 requests/second
globally by default, below TSE's documented maximum of 100. Network errors,
timeouts, HTTP 408 and 5xx responses are retried up to four attempts with 1, 2 and
4 second backoff; a request that still fails stops the run for investigation.
HTTP 403 and 429 stop immediately to avoid extending a block, and other 4xx
responses are not retried.

## Sources and coverage limits

- [Official technical documentation and election identifiers](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)
- [Election configuration](https://resultados.tse.jus.br/oficial/comum/config/ele-c.json)
- [EA16: section index specification](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea16-arquivo-de-configuracao-de-secoes-eleitorais)
- [EA18: auxiliary section file specification](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea18-arquivo-auxiliar-de-secao)
- [Official bulk archives](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao)

The bulk archives contain BU, log, RDV and other files, but the portal explicitly
limits them to packages marked **Totalizado**. The per-section collector instead
records all log packages currently advertised by TSE. TSE can update auxiliary
files, and its documentation says they can initially contain only the last
received package: this is a snapshot of published availability, not a guarantee of
every historical transmission or every replacement urn ever used.
