"""Launch the portable marimo audit workspace or export a curated dataset."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def dashboard_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset")
    parser.add_argument("--port", type=int, default=2718)
    parser.add_argument("--edit", action="store_true")
    parser.add_argument("--export-release", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.export_release:
        if not args.output:
            parser.error("--export-release requires --output")
        from election_audit.dashboard_data import export_release

        print(export_release(args.export_release, args.output))
        return 0
    if not args.dataset or not 1 <= args.port <= 65535:
        parser.error("Supply --dataset and a valid port")
    from election_audit.dashboard_data import AuditDataset

    AuditDataset.open(args.dataset)
    environment = os.environ.copy()
    environment["ELECTION_AUDIT_DATASET"] = args.dataset
    notebooks = Path(__file__).parent / "notebooks"
    command = [
        sys.executable,
        "-m",
        "marimo",
        "edit" if args.edit else "run",
        str(notebooks),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    return subprocess.call(command, env=environment)


def dashboard_export_main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export a curated, portable dashboard dataset")
    parser.add_argument("release", type=Path, nargs="?")
    parser.add_argument("--features", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--operations", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.features:
        if args.release or not args.protocol:
            parser.error("--features requires --protocol and excludes positional release")
        from election_audit.dashboard_development import export_development

        result = export_development(
            args.features,
            args.protocol,
            args.output,
            predictions=args.predictions,
            cases=args.cases,
            operations=args.operations,
        )
    else:
        if not args.release or args.protocol or args.predictions or args.cases or args.operations:
            parser.error("Supply a release, or --features with --protocol")
        from election_audit.dashboard_data import export_release

        result = export_release(args.release, args.output)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(dashboard_main())
