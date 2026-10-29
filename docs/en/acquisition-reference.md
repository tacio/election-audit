# TSE 2026 presidential runoff logs

Document-ID: EA-ACQUISITION-REFERENCE · Revision: 1 · Language: en

[Português](../pt-BR/acquisition-reference.md)

Historical reference preserved from the original README. Dated counts below are
observations at that time; use `rtk proxy just check` for current checks.

Collect the original section/urn logs for the **25 October 2026** presidential
runoff, including all 27 states and **ZZ (voting abroad)**. The standalone collection and diagnostic scripts use only the Python 3.10+
standard library; the project environment is described above.

## Statistical analysis

The [analysis protocol](../../research/analysis-plan.md) reviews the Turicas and INEMA
repositories and specifies a non-parametric statistical audit, required inputs,
validation, multiplicity controls and conditional outcome-impact bounds. It is a
research design; the national model has not been fitted and no fraud finding has
been made. Candidate results from BUs and additional reconciliation are required
alongside the logs.

Inspect a small sample of the logs already saved, while acquisition continues:

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

Run all checks with `python3 -m unittest discover -s tests -v` (34 tests currently).

## Download

```sh
python3 scripts/download_tse_logs.py
```

Start with a small live check if desired:

```sh
python3 scripts/download_tse_logs.py --ufs ac --limit 5
```

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

### Faster parallel downloads

The collector now defaults to 16 concurrent section workers, with a rolling work
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

Run one downloader process. Separate processes would have separate budgets and
could exceed the server's aggregate limit or race on the output files. New runs
take an OS lock on `.download.lock` in the output directory and reject another
downloader for that directory. This POSIX lock is released automatically on exit;
the empty file remains and does not mean a process is still running. Older script
versions do not take the lock, so let any existing old process exit first. A process
already running continues using its original code/settings until restarted.
The throughput gain has not been benchmarked against the live TSE service.

Manifest reads and writes now use one SQLite connection guarded by short locks,
with one immediate write transaction at a time. This avoids competing worker
connections and repeated WAL initialization while retaining parallel network
requests, checksum checks and archive validation. The database schema and stored
paths are unchanged; resume with the existing output directory after a lock error.
The single-connection path passes a 32-worker test with a 1 ms busy timeout on the
test filesystem; it has not been live-tested on the external HDD.

Mirror availability and verification requirements are recorded in
[download-sources.md](../../research/download-sources.md). No raw 2026 runoff mirror
has been verified or enabled.

### Keep the manifest on SSD and logs on HDD

SQLite's small updates can saturate an HDD even at low byte throughput. To keep
the large log corpus on the HDD and place just the database on an SSD, stop the
current downloader, wait for it to exit, and run:

```sh
python3 scripts/download_tse_logs.py \
  --output /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 \
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

This change targets manifest I/O; creating the log files still uses the HDD, and
the actual end-to-end speedup must be measured after restarting.

To use a larger disk, pass `--output /path/on/that/disk/2026-turno-2`.
The collector reserves 2 GiB of free space and keeps logs compressed. The complete
collection's size is unknown until retrieval; it may exceed this workspace's
available space. There is no background download service.

## Outputs

Under `data/tse/2026/turno-2/`:

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

The collector discovers the runoff identifiers from the official configuration
and requires the federal presidential second round dated 25/10/2026. Official
documentation currently identifies pleito **3221** and election **6258**.
It uses 20 requests/second globally by default, below TSE's documented maximum
of 100. It stops on 403/429 and on an unexpected section error; investigate before
rerunning. It does not retry a block, missing URL or DNS failure continuously.

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

## Retrieval status on 29 October 2026

The initial smoke test could not resolve TSE's hostname. A subsequent collection
saved **10,107 log versions**, completing 10,107 principal sections and recording
359 aggregated sections before stopping in Amazonas. The manifest identified five
auxiliary files with uppercase `"f": "O"`; the previous phase check incorrectly
rejected them. Another 210 error rows were cancellation fallout. Both lowercase
and uppercase official phase flags are now accepted, and cancellation no longer
hides the original failure or creates error rows for unattempted sections.

Retry with `--missing-only` to continue. Inspect `coverage.json` before analysis;
this partial collection does not establish national coverage.

Eleven offline tests pass (`python3 -m unittest discover -s tests -v`), covering
missing-only resumption, corrupted/deleted-object repair, changed metadata,
multiple package versions, aggregation, official phase casing, cancellation,
invalid archives, rate-limit stops, disk reserves and election/index selection.
