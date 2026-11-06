"""Thin command adapters; the original script interfaces remain authoritative."""

import argparse
import platform
import shutil
import sqlite3
import sys
from importlib import import_module, metadata


def doctor():
    """Report local runtime readiness without opening acquisition data."""
    print(f"Python: {platform.python_version()}")
    print(f"SQLite: {sqlite3.sqlite_version}")
    ready = True
    for package in ("election-audit", "duckdb", "pyarrow", "ruff"):
        try:
            print(f"{package}: {metadata.version(package)}")
        except metadata.PackageNotFoundError:
            print(f"{package}: MISSING")
            ready = False
    for executable in ("uv", "just"):
        path = shutil.which(executable)
        print(f"{executable}: {path or 'MISSING'}")
        ready = ready and path is not None
    return 0 if ready else 1


def main(argv=None):
    """Forward script options unchanged, including each script's --help."""
    args = list(sys.argv[1:] if argv is None else argv)
    extension_commands = {
        "national": ("election_audit.national", "national_main"),
        "electoral-verify": ("election_audit.electoral_verification", "electoral_verify_main"),
        "operational-review": ("election_audit.operational_review", "operational_review_main"),
        "features": ("election_audit.features", "features_main"),
        "research-protocol": ("election_audit.research_protocol", "research_protocol_main"),
        "research-models": ("election_audit.research_models", "research_models_main"),
        "investigations": ("election_audit.investigations", "investigations_main"),
        "dashboard": ("election_audit.dashboard", "dashboard_main"),
        "dashboard-export": ("election_audit.dashboard", "dashboard_export_main"),
        "stage-sources": ("election_audit.source_staging", "stage_sources_main"),
        "bulk-download": ("election_audit.bulk_acquisition", "bulk_download_main"),
        "semantic-pass": ("election_audit.semantic_pass", "semantic_pass_main"),
        "sa-logs": ("election_audit.sa_logs", "sa_logs_main"),
        "results-hierarchy": ("election_audit.results_hierarchy", "results_hierarchy_main"),
        "integrity-docs": ("election_audit.integrity_documents", "integrity_documents_main"),
        "integrity-check": ("election_audit.integrity_checks", "integrity_check_main"),
        "section-table": ("election_audit.section_table", "section_table_main"),
    }
    if args and args[0] in extension_commands:
        module, function = extension_commands[args[0]]
        return getattr(import_module(module), function)(args[1:])
    if args and args[0] == "pilot":
        from election_audit.pilot import pilot_main

        return pilot_main(args[1:])
    if args and args[0] in ("demo", "reproduce", "review-bundle", "backfill"):
        from election_audit.reproduction import reproduction_main

        return reproduction_main(args[0], args[1:])
    if args and args[0] == "analyze":
        from election_audit.analysis import analysis_main

        return analysis_main(args[1:])
    if args and args[0] == "import-results":
        from election_audit.derivatives import derivative_main

        return derivative_main(args[1:])
    if args and args[0] in ("build", "validate", "query", "report"):
        from election_audit.release_tools import release_main

        return release_main(args[0], args[1:])
    if args and args[0] == "reconstruct":
        from election_audit.reconstruction import reconstruction_main

        return reconstruction_main(args[1:])
    if args and args[0] == "parse":
        from election_audit.archive_parsing import parse_main

        return parse_main(args[1:])
    if args and args[0] in ("snapshot", "snapshot-inspect"):
        from election_audit.snapshots import inspect_main, snapshot_main

        return (snapshot_main if args[0] == "snapshot" else inspect_main)(args[1:])
    commands = {
        "download": "scripts.download_tse_logs",
        "resume": "scripts.download_tse_logs",
        "inspect": "scripts.inspect_tse_logs",
    }
    if args and args[0] in commands:
        command, *forwarded = args
        if command == "resume":
            forwarded.insert(0, "--missing-only")
        original = sys.argv
        try:
            sys.argv = [f"election-audit {command}", *forwarded]
            result = import_module(commands[command]).main()
        finally:
            sys.argv = original
        return result
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            *commands,
            *extension_commands,
            "doctor",
            "snapshot",
            "snapshot-inspect",
            "parse",
            "reconstruct",
            "build",
            "validate",
            "query",
            "report",
            "import-results",
            "analyze",
            "demo",
            "reproduce",
            "review-bundle",
            "pilot",
            "backfill",
        ],
    )
    parsed = parser.parse_args(args)
    if parsed.command == "doctor":
        return doctor()
    return 0
