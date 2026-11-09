# Reproduction and peer review

Document-ID: EA-REPRODUCTION · Revision: 7 · Language: en

The offline demo is SYNTHETIC throughout: deterministic tiny ZIP originals exercise mixed device dates, exact copied history, replacement devices, manual request/cancellation, unresolved clocks and malformed nested content. Reviewed session/copy/semantic assertions are generated from exact preserved synthetic line hashes. Expected members 3, unique principals 2, normalized attending voters 10, eligible electors 20 and turnout 0.5 are known fixture numbers. They do not validate real electoral data. Unknown identity links remain unavailable; a registered exploration preserves its null result and complete history without fitting.

Run from the repository with locked dependencies already installed/cached. Each demo, bundle and reproduction output must be a new directory. Full verification reads frozen hashes and releases; no downloader or live manifest is used by reproduction.

```sh
env UV_OFFLINE=1 just demo --output data/my-demo
env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
env UV_OFFLINE=1 just review-bundle data/my-review --verify
env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
env UV_OFFLINE=1 just docs-check
env UV_OFFLINE=1 just docs-command-check
```

`reproduction.json` preserves the source observation/snapshot identity, parse ID, bounded object groups, exact configuration paths, resources, stage validations and logical payload digests. Snapshot capture records actual local observation times; repeated fresh capture can have a different identity. Reproduction reuses those frozen bytes and times. It never fabricates observation timestamps. Synthetic source timestamps are fixture values explicitly marked as such.

Exact original physical and logical pins remain in each immutable release manifest. Fresh DuckDB container bytes, creation times and resulting child parent-manifest pins may differ. Reproduction compares each stage’s complete payload multiset after mapping only explicit parent_release_id provenance values to stage aliases; source hashes, record locators, configuration, counts, nulls and all other semantic fields remain exact. Parsed artifact identity must match. Each rebuilt release is independently validated. Review the original/reproduced IDs in reproduction-result.json.

`review-bundle` exports complete relative release chains, copied frozen source objects and inventories, inputs, reports/SQL and exact whitelisted source trees: election_audit, scripts, tests, docs and research, plus pyproject.toml, uv.lock, .python-version, .gitignore, justfile and both READMEs. Live SQLite/WAL, .local-state, .git, .aws, .codex, .agents, .venv, raw source roots, caches and unrelated files are excluded. Symlinks in selected trees are rejected before copying. A complete file inventory with SHA-256 detects edits, removals and additions; a sidecar protects its wrapper against accidental corruption. This is integrity verification, not an authenticated signature: an adversary replacing manifest and sidecar together needs an external trusted digest to detect.

Runtime/package versions and exact dependency lock are bundled; distributions/cache are not. Offline verification and reproduction use the installed pinned runtime. To run the exact bundled source, set the working directory to BUNDLE/source and use the already-installed Python interpreter with `-B` (or `PYTHONDONTWRITEBYTECODE=1`) so runtime bytecode does not alter the verified bundle, or install the bundled project from its lock with a populated offline cache. The environment must live outside the bundle: uv's default `.venv` inside BUNDLE/source would add files that verification rejects. No network install or Git commit identity is claimed.

```sh
cd BUNDLE/source
UV_PROJECT_ENVIRONMENT=/path/outside/the/bundle/venv PYTHONDONTWRITEBYTECODE=1 uv sync --locked --offline
UV_PROJECT_ENVIRONMENT=/path/outside/the/bundle/venv PYTHONDONTWRITEBYTECODE=1 uv run --locked --offline election-audit reproduce BUNDLE --output /new/reproduction
```

```python
from election_audit.reproduction import frozen_pipeline, review_bundle, reproduce
from election_audit.pilot import select_pilot, run_pilot
from election_audit.publication import ResourceConfig

config = ResourceConfig()
# frozen_pipeline(snapshot, output, config=config) resumes existing immutable stages.
# review_bundle(run, output) exports the exact declared chain and frozen inputs.
# reproduce(bundle, fresh_output) verifies and rebuilds without raw acquisition.
```

The real pilot selects one available principal in each of AC, AL, DF, ES and PR, spanning five macroregions within configured AC–RJ. It opens a query-only SQLite transaction including committed WAL and uses indexed URL ranges, at most 100000 current log mappings per UF. It records each pool count/hash/truncation, selected-UF pool rows, seed diagnostic-geographic-pilot-v1, exact index hashes, eligible principal pools, municipality/zone strata, ranks and exclusions. Index principals must self-map or have no aggregation target; selected files must exist with matching size and at most 64 MiB. Snapshot creation then hashes/copies only selected assets and UF indexes, retaining full-UF expected denominators. Selection and snapshot are separate live views: frozen selected checks, inventory and later reproduction are authoritative; later downloads cannot enter the frozen calculation.

```sh
env UV_OFFLINE=1 just pilot --source $EA_DATA/raw/2026/turno-2 --output data/my-pilot
env UV_OFFLINE=1 just review-bundle data/my-pilot --output data/my-pilot-review
env UV_OFFLINE=1 just reproduce data/my-pilot-review --output data/my-pilot-reproduction
```

This is a diagnostic geographic design, not a probability-weighted or national estimate. Unsampled/unavailable UFs, outside-selection members and unknown denominators remain explicit. Real device dates do not independently attribute a round. Only three exact baseline message classes are decoded automatically; unknown text remains unknown, with safe original line/hash locators retained. No official session, clock, candidate attribution or new message adapter is inferred. Official BU validation is a separate electoral path (see the [electoral guide](electoral-results.md)) and never becomes operational validation.

Both-language reports share calculations, SQL, coverage, availability, exclusions and challenging evidence. Review original bytes and anchors, contradictory official message meanings, missing/aggregated principals, clock rules, copied/replacement histories, official BU/corrections and ZZ coverage. Reconstructed cycles are not reconciled votes. Source availability remains unknown, numeric feature eligibility unavailable, and no model/exchangeability/final national margin is supplied.

`docs-check` retains paired metadata/revision, links, code-fence parity and Mermaid structure checks. `docs-command-check` inspects shell quoting, known recipes/commands/long flags and DuckDB SQL syntax using fixture/harmless --help paths only. It never executes documented acquisition/backfill commands, SQL, shell substitutions or file arguments. Syntax checks do not establish query meaning, scientific validity or translation quality; those require review.

See [backfill planning](backfill.md), [the implementation index](implementation-index.md) and paired task 9 handoffs for actual acceptance artifacts and remaining work.

## What to expect on the national data

Times measured on the reference machine: Intel Core i7-9750H (6 cores, 12
threads), 31 GB of RAM, SSD staging on NVMe, and a 2.5-inch 5400 rpm HDD as the
output volume. Runs used at most half the CPU threads and 6 GiB of RAM in all.
"Active" excludes machine suspends. "Not recorded" means no measurement was kept;
nothing below is estimated.

| Step | Command | Scale | Workers | Time | Peak RAM | Output |
| --- | --- | --- | --- | --- | --- | --- |
| Urn logs, both rounds (Phase 10) | `download` | 499176 and 499177 log versions, 53.7 GB and 90.6 GB | — | Several days, network-bound; not recorded per round | Not recorded | Raw roots |
| Open-data inputs (Phase 19) | `bulk-download` | BWEB 4.9 GB (2026) and 1.5 GB (2022); voter profile 3.3 GB and 0.96 GB; BU/RDV/log archives 219.2 GB (2026) and 168.5 GB (2022) | — | Network-bound; not recorded | Not recorded | `inputs/`, `bulk/` |
| SSD staging, both rounds | `stage-sources copy` | 53.7 GB and 90.6 GB | — | 86 min: copies 931 s and 1587 s, re-hashes 954 s and 1431 s | Not recorded | 144.3 GB on SSD |
| Integrity checks, 2026, per round (Phase 20) | `integrity-check sections` | 499207 sections | 6 | 64 and 59 min | Not recorded | 618 MB and 325 MB |
| | `integrity-check bweb` | BWEB 5.1 GB (round 1, every office) and 0.14 GB (round 2) | 1 | 30 min and 66 s | Not recorded | 2.1 MB and 1.2 MB |
| | `integrity-check hierarchy` | EA20 nodes | 1 | 17 min and 21 s | Not recorded | 96 KB |
| | `integrity-check correspondence`, `logs` | Per round | 1 | Under a minute each | Not recorded | Under 2 MB |
| Integrity sections v3, 2026, per round (Phase 20b) | `integrity-check sections` | 499207 sections, Ed521 with `ed521rs` | 6 | 1:07:49 and 1:00:38; CPU 10210 s and 5411 s (pure-Python v2: 2:57:15 and 2:21:17) | 4.9 GB and 4.2 GB (largest process) | 629 MB and 337 MB |
| Semantic pass v3, per year and round (Phase 22) | `semantic-pass run` | 2026: 498580 and 498581 objects; 2022: 471859 and 471983 | 5 | Active 8002 s and 12808 s (2026), 7277 s and 11809 s (2022) | About 1.7 GB in all; largest process 1.2 GB | 1.8, 2.9, 1.7 and 2.7 GB |
| Section table v3, per year (Phases 22 and 20b) | `section-table build` | 499248 and 472693 sections per round | 1 | 47 min (2026) and 78 min (2022); v2: 45 and 41 min | 3.7 GB and 3.0 GB | 192 MB and 183 MB |
| Offline gate | `just check` | 394 tests | 1 | 117 s | — | — |

After the downloads, reproducing the current releases takes about 17 hours of
compute: staging, integrity checks, the four semantic passes and both tables. The
Phase 21 passes (v1 for 2026, v2 for 2022) are not needed, because v3 contains
every column they have.

What drives the times:

- Round 2 takes longer because each runoff log holds the urn's whole history, from
  setup through round 1, so it has twice the sessions.
- 2026 logs are read from the SSD staging. From the HDD, section order read at 1.9–3.5 MB/s
  and physical order at 73–92 MB/s
  ([implementation index](implementation-index.md#current-state)).
- 2022 logs are read straight from the bulk 7z archives on the HDD, in physical
  order.
- Round-1 BWEB holds every office, so its checks read 35 times more data than
  round 2.

Long runs resume with `--resume` and the identical binding. Turn off the desktop's
automatic suspend for overnight runs: a sleep inhibitor did not prevent one
suspend, although the runs then resumed without errors. Wrap each national run in
`/usr/bin/time -v` to record its time and peak memory.
