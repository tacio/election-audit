set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments
export UV_CACHE_DIR := env("UV_CACHE_DIR", "/tmp/election-audit-uv-cache")

# rtk (a token-saving output filter for AI coding agents) wraps commands when it is
# installed; it is optional and changes no result.
rtk := if `command -v rtk || true` == "" { "" } else { "rtk proxy " }

# List the available, implemented commands.
default:
    {{rtk}}just --list

# Install the project and development tools from uv.lock.
setup:
    {{rtk}}uv sync --locked

# Check local tools and installed package versions without reading acquisition data.
doctor:
    {{rtk}}uv run --locked election-audit doctor

# Format Python source files.
fmt:
    {{rtk}}uv run --locked ruff format .

# Check lint rules without changing source.
lint:
    {{rtk}}uv run --locked ruff check .

# Check type annotations with ty (all extras, so optional imports resolve).
typecheck:
    {{rtk}}uv run --locked --all-extras ty check

# Run offline unit tests with isolated temporary fixtures.
test:
    {{rtk}}uv run --locked python -m unittest discover -s tests -v

# Check paired documentation without executing its examples.
docs-check:
    {{rtk}}uv run --locked python -m scripts.check_docs

# Check declarative schema and feature registry metadata.
contracts-check:
    {{rtk}}uv run --locked python -m election_audit.contracts

# Verify formatting, lint, contracts, documentation and all unit tests.
check:
    {{rtk}}uv lock --check
    {{rtk}}uv run --locked ruff format --check .
    {{rtk}}just lint
    {{rtk}}just typecheck
    {{rtk}}just contracts-check
    {{rtk}}just docs-check
    {{rtk}}just docs-command-check
    {{rtk}}just test

# Run the original downloader; forwards all options.
download *args:
    {{rtk}}uv run --locked election-audit download "$@"

# Resume acquisition with --missing-only; forwards all other options.
resume *args:
    {{rtk}}uv run --locked election-audit resume "$@"

# Run the bounded raw-message diagnostic; forwards all options.
inspect *args:
    {{rtk}}uv run --locked election-audit inspect "$@"

# Freeze a declared local population; requires --source and --store.
snapshot *args:
    {{rtk}}uv run --locked election-audit snapshot "$@"

# Inspect immutable snapshot metadata; --verify-objects rehashes frozen copies.
snapshot-inspect *args:
    {{rtk}}uv run --locked election-audit snapshot-inspect "$@"

# Parse frozen archive objects; requires --store outside raw/snapshot roots.
parse *args:
    {{rtk}}uv run --locked election-audit parse "$@"

# Reconstruct a bounded frozen parse group; original acquisition is never input.
reconstruct *args:
    {{rtk}}uv run --locked election-audit reconstruct "$@"

# Publish immutable DuckDB/Parquet from frozen reconstruction, parse or snapshot inputs.
build *args:
    {{rtk}}uv run --locked election-audit build "$@"

# Verify release hashes, grains, foreign keys, accounting, lineage and resources.
validate *args:
    {{rtk}}uv run --locked election-audit validate "$@"

# Run one bounded read-only SELECT against a verified release.
query *args:
    {{rtk}}uv run --locked election-audit query "$@"

# Generate initial English and Portuguese reports by default.
report *args:
    {{rtk}}uv run --locked election-audit report "$@"

# Import an explicit normalized electoral bundle as an immutable parent-pinned derivative.
import-results *args:
    {{rtk}}uv run --locked election-audit import-results "$@"

# Publish descriptive features, frozen location partitions and immutable analysis ledgers.
analyze *args:
    {{rtk}}uv run --locked election-audit analyze "$@"

# Create a small explicitly synthetic end-to-end offline walkthrough in a new directory.
demo *args:
    {{rtk}}uv run --locked election-audit demo "$@"

# Verify and rebuild a relocated review bundle from frozen inputs, in a new directory.
reproduce *args:
    {{rtk}}uv run --locked election-audit reproduce "$@"

# Export the complete release chain, frozen inputs, code whitelist and review evidence.
review-bundle *args:
    {{rtk}}uv run --locked election-audit review-bundle "$@"

# Freeze and process only the bounded five-region diagnostic selection, without acquisition.
pilot *args:
    {{rtk}}uv run --locked election-audit pilot "$@"

# Resume bounded per-object stages from one already frozen population; no acquisition.
backfill *args:
    {{rtk}}uv run --locked election-audit backfill "$@"

# Inspect example commands/flags and SQL syntax, invoking only harmless CLI --help.
docs-command-check:
    {{rtk}}uv run --locked python -m scripts.check_doc_commands

# Preflight, resume or inspect bounded national processing.
national *args:
    {{rtk}}uv run --locked election-audit national "$@"

# Acquire or verify TSE open-data bulk archives into a new checksummed root.
bulk-download *args:
    {{rtk}}uv run --locked election-audit bulk-download "$@"

# Phase 21 streaming per-session aggregates and adapter equivalence over staged logs.
semantic-pass *args:
    {{rtk}}uv run --locked election-audit semantic-pass "$@"

# Fetch and summarize contingency-counting (SA) logs listed by certified stagings.
sa-logs *args:
    {{rtk}}uv run --locked election-audit sa-logs "$@"

# Fetch the official hierarchical presidential results (EA20) of a round.
results-hierarchy *args:
    {{rtk}}uv run --locked election-audit results-hierarchy "$@"

# File browser-collected TRE integrity test documents by SHA-256.
integrity-docs *args:
    {{rtk}}uv run --locked election-audit integrity-docs "$@"

# Phase 20 Tier 1 integrity checks over the bulk BU/RDV/signature archives.
integrity-check *args:
    {{rtk}}uv run --locked election-audit integrity-check "$@"

# Phase 22 section feature table v2 (sections, crosswalk units, ledger).
section-table *args:
    {{rtk}}uv run --locked election-audit section-table "$@"

# Benchmark read orders or stage certified raw objects onto a new verified root.
stage-sources *args:
    {{rtk}}uv run --locked election-audit stage-sources "$@"

# Open the local marimo notebook gallery against an explicit dataset.
dashboard *args:
    {{rtk}}uv run --locked --extra dashboard election-audit dashboard "$@"

# Export a checksummed portable exploration dataset.
dashboard-export *args:
    {{rtk}}uv run --locked election-audit dashboard-export "$@"

# Verify binary BU linkage and electoral evidence.
electoral-verify *args:
    {{rtk}}uv run --locked --extra verification election-audit electoral-verify "$@"

# Review real operational rules over structural shards.
operational-review *args:
    {{rtk}}uv run --locked election-audit operational-review "$@"

# Produce harmonized feature ledgers.
features *args:
    {{rtk}}uv run --locked election-audit features "$@"

# Freeze a grouped research protocol and protected evaluation population.
research-protocol *args:
    {{rtk}}uv run --locked election-audit research-protocol "$@"

# Fit, evaluate or simulate a frozen research specification.
research-models *args:
    {{rtk}}uv run --locked --extra research election-audit research-models "$@"

# Build evidence packets and explicitly conditional impact scenarios.
investigations *args:
    {{rtk}}uv run --locked --extra research election-audit investigations "$@"
