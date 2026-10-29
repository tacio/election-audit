# Reproduction and peer review

Document-ID: EA-REPRODUCTION · Revision: 1 · Language: en

The offline demo is SYNTHETIC throughout: deterministic tiny ZIP originals exercise mixed device dates, exact copied history, replacement devices, manual request/cancellation, unresolved clocks and malformed nested content. Reviewed session/copy/semantic assertions are generated from exact preserved synthetic line hashes. Expected members 3, unique principals 2, normalized attending voters 10, eligible electors 20 and turnout 0.5 are known fixture numbers. They do not validate real electoral data. Unknown identity links remain unavailable; a registered exploration preserves its null result and complete history without fitting.

Run from the repository with locked dependencies already installed/cached. Each demo, bundle and reproduction output must be a new directory. Full verification reads frozen hashes and releases; no downloader or live manifest is used by reproduction.

```sh
rtk proxy env UV_OFFLINE=1 just demo --output data/my-demo
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-demo --output data/my-review
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-review --verify
rtk proxy env UV_OFFLINE=1 just reproduce data/my-review --output data/my-reproduction
rtk proxy env UV_OFFLINE=1 just docs-check
rtk proxy env UV_OFFLINE=1 just docs-command-check
```

`reproduction.json` preserves the source observation/snapshot identity, parse ID, bounded object groups, exact configuration paths, resources, stage validations and logical payload digests. Snapshot capture records actual local observation times; repeated fresh capture can have a different identity. Reproduction reuses those frozen bytes and times. It never fabricates observation timestamps. Synthetic source timestamps are fixture values explicitly marked as such.

Exact original physical and logical pins remain in each immutable release manifest. Fresh DuckDB container bytes, creation times and resulting child parent-manifest pins may differ. Reproduction compares each stage’s complete payload multiset after mapping only explicit parent_release_id provenance values to stage aliases; source hashes, record locators, configuration, counts, nulls and all other semantic fields remain exact. Parsed artifact identity must match. Each rebuilt release is independently validated. Review the original/reproduced IDs in reproduction-result.json.

`review-bundle` exports complete relative release chains, copied frozen source objects and inventories, inputs, reports/SQL and exact whitelisted source trees: election_audit, scripts, tests, docs and research, plus pyproject.toml, uv.lock, .python-version, .gitignore, justfile and both READMEs. Live SQLite/WAL, .local-state, .git, .aws, .codex, .agents, .venv, raw source roots, caches and unrelated files are excluded. Symlinks in selected trees are rejected before copying. A complete file inventory with SHA-256 detects edits, removals and additions; a sidecar protects its wrapper against accidental corruption. This is integrity verification, not an authenticated signature: an adversary replacing manifest and sidecar together needs an external trusted digest to detect.

Runtime/package versions and exact dependency lock are bundled; distributions/cache are not. Offline verification and reproduction use the installed pinned runtime. To run the exact bundled source, set the working directory to BUNDLE/source and use the already-installed Python interpreter with `-B` (or `PYTHONDONTWRITEBYTECODE=1`) so runtime bytecode does not alter the verified bundle, or install the bundled project from its lock with a populated offline cache. No network install or Git commit identity is claimed.

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
rtk proxy env UV_OFFLINE=1 just pilot --source /media/tacio/HDD/Data/tse/data/tse/2026/turno-2 --output data/my-pilot
rtk proxy env UV_OFFLINE=1 just review-bundle data/my-pilot --output data/my-pilot-review
rtk proxy env UV_OFFLINE=1 just reproduce data/my-pilot-review --output data/my-pilot-reproduction
```

This is a diagnostic geographic design, not a probability-weighted or national estimate. Unsampled/unavailable UFs, outside-selection members and unknown denominators remain explicit. Real device dates do not independently attribute a round. Only three exact baseline message classes are decoded automatically; unknown text remains unknown, with safe original line/hash locators retained. No official session, clock, candidate attribution or new message adapter is inferred. Missing real BU/official adapter remains task 7.1 and does not become operational validation.

Both-language reports share calculations, SQL, coverage, availability, exclusions and challenging evidence. Review original bytes and anchors, contradictory official message meanings, missing/aggregated principals, clock rules, copied/replacement histories, official BU/corrections and ZZ coverage. Reconstructed cycles are not reconciled votes. Source availability remains unknown, numeric feature eligibility unavailable, and no model/exchangeability/final national margin is supplied.

`docs-check` retains paired metadata/revision, links, code-fence parity and Mermaid structure checks. `docs-command-check` inspects shell quoting, known recipes/commands/long flags and DuckDB SQL syntax using fixture/harmless --help paths only. It never executes documented acquisition/backfill commands, SQL, shell substitutions or file arguments. Syntax checks do not establish query meaning, scientific validity or translation quality; those require review.

See [backfill planning](backfill.md), [the implementation index](implementation-index.md) and paired task 9 handoffs for actual acceptance artifacts and remaining work.
