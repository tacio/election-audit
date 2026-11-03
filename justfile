set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments
export UV_CACHE_DIR := env("UV_CACHE_DIR", "/tmp/election-audit-uv-cache")

# List the available, implemented commands.
default:
    rtk proxy just --list

# Install the project and development tools from uv.lock.
setup:
    rtk proxy uv sync --locked

# Check local tools and installed package versions without reading acquisition data.
doctor:
    rtk proxy uv run --locked election-audit doctor

# Format Python source files.
fmt:
    rtk proxy uv run --locked ruff format .

# Check lint rules without changing source.
lint:
    rtk proxy uv run --locked ruff check .

# Run offline unit tests with isolated temporary fixtures.
test:
    rtk proxy uv run --locked python -m unittest discover -s tests -v

# Check paired documentation without executing its examples.
docs-check:
    rtk proxy uv run --locked python -m scripts.check_docs

# Check declarative schema and feature registry metadata.
contracts-check:
    rtk proxy uv run --locked python -m election_audit.contracts

# Verify formatting, lint, contracts, documentation and all unit tests.
check:
    rtk proxy uv lock --check
    rtk proxy uv run --locked ruff format --check .
    rtk proxy just lint
    rtk proxy just contracts-check
    rtk proxy just docs-check
    rtk proxy just docs-command-check
    rtk proxy just test

# Run the original downloader; forwards all options.
download *args:
    rtk proxy uv run --locked election-audit download "$@"

# Resume acquisition with --missing-only; forwards all other options.
resume *args:
    rtk proxy uv run --locked election-audit resume "$@"

# Run the bounded raw-message diagnostic; forwards all options.
inspect *args:
    rtk proxy uv run --locked election-audit inspect "$@"

# Freeze a declared local population; requires --source and --store.
snapshot *args:
    rtk proxy uv run --locked election-audit snapshot "$@"

# Inspect immutable snapshot metadata; --verify-objects rehashes frozen copies.
snapshot-inspect *args:
    rtk proxy uv run --locked election-audit snapshot-inspect "$@"

# Parse frozen archive objects; requires --store outside raw/snapshot roots.
parse *args:
    rtk proxy uv run --locked election-audit parse "$@"

# Reconstruct a bounded frozen parse group; original acquisition is never input.
reconstruct *args:
    rtk proxy uv run --locked election-audit reconstruct "$@"

# Publish immutable DuckDB/Parquet from frozen reconstruction, parse or snapshot inputs.
build *args:
    rtk proxy uv run --locked election-audit build "$@"

# Verify release hashes, grains, foreign keys, accounting, lineage and resources.
validate *args:
    rtk proxy uv run --locked election-audit validate "$@"

# Run one bounded read-only SELECT against a verified release.
query *args:
    rtk proxy uv run --locked election-audit query "$@"

# Generate initial English and Portuguese reports by default.
report *args:
    rtk proxy uv run --locked election-audit report "$@"

# Import an explicit normalized electoral bundle as an immutable parent-pinned derivative.
import-results *args:
    rtk proxy uv run --locked election-audit import-results "$@"

# Publish descriptive features, frozen location partitions and immutable analysis ledgers.
analyze *args:
    rtk proxy uv run --locked election-audit analyze "$@"

# Create a small explicitly synthetic end-to-end offline walkthrough in a new directory.
demo *args:
    rtk proxy uv run --locked election-audit demo "$@"

# Verify and rebuild a relocated review bundle from frozen inputs, in a new directory.
reproduce *args:
    rtk proxy uv run --locked election-audit reproduce "$@"

# Export the complete release chain, frozen inputs, code whitelist and review evidence.
review-bundle *args:
    rtk proxy uv run --locked election-audit review-bundle "$@"

# Freeze and process only the bounded five-region diagnostic selection, without acquisition.
pilot *args:
    rtk proxy uv run --locked election-audit pilot "$@"

# Resume bounded per-object stages from one already frozen population; no acquisition.
backfill *args:
    rtk proxy uv run --locked election-audit backfill "$@"

# Inspect example commands/flags and SQL syntax, invoking only harmless CLI --help.
docs-command-check:
    rtk proxy uv run --locked python -m scripts.check_doc_commands

# Preflight, resume or inspect bounded national processing.
national *args:
    rtk proxy uv run --locked election-audit national "$@"

# Open the local marimo notebook gallery against an explicit dataset.
dashboard *args:
    rtk proxy uv run --locked --extra dashboard election-audit dashboard "$@"

# Export a checksummed portable exploration dataset.
dashboard-export *args:
    rtk proxy uv run --locked election-audit dashboard-export "$@"

# Verify binary BU linkage and electoral evidence.
electoral-verify *args:
    rtk proxy uv run --locked --extra verification election-audit electoral-verify "$@"

# Review real operational rules over structural shards.
operational-review *args:
    rtk proxy uv run --locked election-audit operational-review "$@"

# Produce harmonized feature ledgers.
features *args:
    rtk proxy uv run --locked election-audit features "$@"

# Freeze a grouped research protocol and protected evaluation population.
research-protocol *args:
    rtk proxy uv run --locked election-audit research-protocol "$@"

# Fit, evaluate or simulate a frozen research specification.
research-models *args:
    rtk proxy uv run --locked --extra research election-audit research-models "$@"

# Build evidence packets and explicitly conditional impact scenarios.
investigations *args:
    rtk proxy uv run --locked --extra research election-audit investigations "$@"
