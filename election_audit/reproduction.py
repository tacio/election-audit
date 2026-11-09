"""Frozen-input reproduction and whitelisted, relocatable offline review bundles."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Any

from election_audit.archive_parsing import FrozenParseReader, inspect_parse, parse_snapshot
from election_audit.derivatives import publish_derivative, release_layers
from election_audit.publication import (
    PublicationError,
    ResourceConfig,
    inspect_release,
    open_release,
    publish_release,
)
from election_audit.reconstruction import reconstruct_parse
from election_audit.release_tools import report_release, validate_release
from election_audit.snapshots import create_snapshot, inspect_snapshot
from election_audit.source_inventory import canonical, digest, hash_file, utc_now
from election_audit.types import JSON, Argv
from election_audit.walkthrough import (
    analysis_config,
    normalized_demo,
    synthetic_evidence,
    synthetic_source,
    write_json,
)

VERSION = "offline-reproduction-v1"
EXCLUDED = {".git", ".aws", ".codex", ".agents", ".venv", ".local-state", "__pycache__"}


def _copy_tree(source: Path, destination: Path) -> None:
    """Reject links before copytree can dereference them; walk explicit trees only."""
    for directory, folders, files in os.walk(source, followlinks=False):
        folders[:] = [name for name in folders if name not in EXCLUDED]
        for name in [*folders, *files]:
            if (Path(directory) / name).is_symlink():
                raise PublicationError("Review source must not contain symlinks")
    if Path(source).is_symlink():
        raise PublicationError("Review source must not contain symlinks")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*EXCLUDED, "*.pyc"))


def relative_file(root: Path, locator: str) -> Path:
    candidate = Path(locator)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PublicationError("Review locator must be confined and relative")
    target = (Path(root) / candidate).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise PublicationError("Review locator escapes bundle")
    return target


def runtime() -> JSON:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "packages": {
            name: metadata.version(name) for name in ("duckdb", "pyarrow", "election-audit")
        },
        "git": "unavailable_no_commit_claim",
        "implementation_sha256": {
            str(path.relative_to(Path(__file__).parent)): hash_file(path)[0]
            for path in sorted(Path(__file__).parent.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".json"}
        },
    }


def logical_results(release: Path, identities: Mapping[str, str]) -> JSON:
    """Multiset digests normalize only explicit parent_release_id provenance.

    Exact unmodified logical/physical pins remain in each release manifest. Fresh
    DuckDB container bytes and derivative parent-manifest pins can differ. Stage
    tokens compare equal scientific payloads while preserving that distinction.
    """
    document = inspect_release(release)

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: identities.get(item, item) if key == "parent_release_id" else normalize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    result = {}
    with open_release(release, _verified_document=document) as db:
        for table in sorted(document.get("combined_tables", document["tables"])):
            count, total = 0, 0
            cursor = db.execute(f'SELECT payload FROM "{table}"')
            while batch := cursor.fetchmany(2048):
                for (payload,) in batch:
                    raw = canonical(normalize(json.loads(payload)))
                    total = (total + int.from_bytes(hashlib.sha256(raw).digest(), "big")) % (
                        1 << 256
                    )
                    count += 1
            result[table] = {"rows": count, "logical_sha256": digest([count, total])}
    return result


def frozen_pipeline(
    snapshot: Path,
    output: str | Path,
    *,
    config: ResourceConfig | None = None,
    evidence: Any = None,
    object_groups: list[list[str]] | None = None,
) -> tuple[Path, list[Path], Path, float]:
    """Usable bounded API; repeated calls resume immutable parse/shard/release hits."""
    config = config or ResourceConfig()
    output = Path(output)
    started = time.monotonic()
    parsed = parse_snapshot(snapshot, output / "parsed", workers=config.parser_workers)
    reader = FrozenParseReader(parsed)
    groups = object_groups or [[r["object_sha256"]] for r in reader.document["artifacts"]]
    if not groups:
        raise PublicationError("No acquired frozen log object in selected population")
    shards = [
        reconstruct_parse(
            parsed,
            output / "operational",
            evidence=evidence,
            object_sha256=group,
            max_events=config.max_events,
            reader=reader,
        )
        for group in groups
    ]
    release = publish_release(shards, output / "warehouse", config=config)
    return parsed, shards, release, time.monotonic() - started


def describe_run(
    root: Path,
    snapshot: Path,
    parsed: Path,
    shards: Sequence[Path],
    releases: Sequence[Path],
    *,
    config: ResourceConfig,
    evidence: Any = None,
    steps: Sequence[JSON] = (),
    synthetic: bool = False,
    elapsed_seconds: float | None = None,
) -> JSON:
    root = Path(root).resolve()
    identities = {release.name: f"stage:{index}" for index, release in enumerate(releases)}
    descriptors = []
    for release in releases:
        validation = validate_release(release)
        descriptors.append(
            {
                "locator": str(release.relative_to(root)),
                "release_id": release.name,
                "validation": validation,
                "results": logical_results(release, identities),
            }
        )
    descriptor = {
        "version": VERSION,
        "created_at": utc_now(),
        "synthetic": synthetic,
        "national_status": "partial_national",
        "snapshot": str(snapshot.relative_to(root)),
        "parse_id": parsed.name,
        "object_groups": [
            json.loads((p / "reconstruction.json").read_text())["object_sha256"] for p in shards
        ],
        "evidence": evidence,
        "resource_config": asdict(config),
        "steps": list(steps),
        "stages": descriptors,
        "runtime": runtime(),
        "elapsed_seconds": elapsed_seconds,
        "electoral_validation": "unavailable_verified_official_TSE_BU_adapter_outstanding_task_7.1",
        "assumptions": "review_assertions_are_not_independent_semantic_certification",
        "challenging_evidence": [
            "official_message_dictionary",
            "clock_rules",
            "session_boundaries",
            "missing_UFs_and_ZZ",
            "official_BU_and_corrections",
        ],
        "reproduction_identity": "frozen_input_and_normalized_logical_results; container_bytes_and_creation_times_may_differ",
    }
    write_json(root / "reproduction.json", descriptor)
    return descriptor


# The synthetic demo writes about 12 MiB; the national reserve (10 GiB) and spill cap (8 GiB)
# would refuse it on small disks (xr1-20261109-P8-07). It needs 2 GiB free.
DEMO_RESOURCES = {"spill_bytes": 1024**3, "reserve_bytes": 1024**3}


def demo(output: str | Path) -> JSON:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = ResourceConfig(**DEMO_RESOURCES)
    started = time.monotonic()
    raw = synthetic_source(output / "synthetic-source")
    snapshot = create_snapshot(
        raw, output / "snapshots", ["ac"], reserve_bytes=config.reserve_bytes
    )
    parsed = parse_snapshot(snapshot, output / "parsed", workers=config.parser_workers)
    evidence = synthetic_evidence(parsed)
    write_json(output / "inputs" / "evidence.json", evidence)
    groups = [[r["object_sha256"] for r in inspect_parse(parsed)["artifacts"]]]
    parsed, shards, base, _ = frozen_pipeline(
        snapshot, output, config=config, evidence=evidence, object_groups=groups
    )
    bundle = normalized_demo(base, output / "inputs" / "electoral")
    electoral = publish_derivative(base, bundle, output / "warehouse", config=config)
    partition, final, configs = analysis_config(electoral, output / "inputs")
    report_release(base, output / "reports" / "operational")
    report_release(electoral, output / "reports" / "electoral")
    report_release(final, output / "reports" / "analysis")
    steps = [
        {"kind": "electoral", "bundle": str(bundle.relative_to(output))},
        *[{"kind": "analysis", "bundle": str(path.relative_to(output))} for path in configs],
    ]
    descriptor = describe_run(
        output,
        snapshot,
        parsed,
        shards,
        [base, electoral, partition, final],
        config=config,
        evidence="inputs/evidence.json",
        steps=steps,
        synthetic=True,
        elapsed_seconds=time.monotonic() - started,
    )
    expected = {
        "expected_members": 3,
        "expected_unique_principals": 2,
        "attending_voters": 10,
        "eligible_electors": 20,
        "turnout": 0.5,
        "fitted_models": 0,
        "scientifically_eligible_features": 0,
        "identity_links": "unavailable",
        "registered_null_results": 1,
    }
    write_json(output / "synthetic-expectations.json", expected)
    return descriptor


def file_pins(root: Path) -> dict[str, JSON]:
    pins = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise PublicationError("Review bundle must not contain symlinks")
        if path.is_file():
            sha, size = hash_file(path)
            pins[str(path.relative_to(root))] = {"sha256": sha, "bytes": size}
    return pins


def verify_bundle(bundle: str | Path) -> JSON:
    bundle = Path(bundle).resolve()
    raw = (bundle / "review-bundle.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (bundle / "review-bundle.sha256").read_text().strip():
        raise PublicationError("Review manifest checksum mismatch")
    manifest = json.loads(raw)
    if manifest.get("version") != VERSION:
        raise PublicationError("Unsupported review bundle")
    actual = file_pins(bundle)
    actual.pop("review-bundle.json", None)
    actual.pop("review-bundle.sha256", None)
    if actual != manifest["files"]:
        raise PublicationError("Review bundle file inventory/hash mismatch")
    run = bundle / "run"
    descriptor = json.loads((run / "reproduction.json").read_text())
    inspect_snapshot(relative_file(run, descriptor["snapshot"]), verify_objects=True)
    for stage in descriptor["stages"]:
        validate_release(relative_file(run, stage["locator"]))
    from scripts.check_docs import FENCES, META, fence_signature

    for report in (run / "reports").rglob("*.en.md"):
        counterpart = report.with_name(report.name.replace(".en.md", ".pt-BR.md"))
        if not counterpart.is_file():
            raise PublicationError("Review report language counterpart missing")
        en, pt = report.read_text(), counterpart.read_text()
        left, right = META.search(en), META.search(pt)
        if (
            not left
            or not right
            or left.groups()[:2] != right.groups()[:2]
            or left.group(3) != "en"
            or right.group(3) != "pt-BR"
        ):
            raise PublicationError("Review report paired metadata mismatch")
        if [fence_signature(block) for block in FENCES.findall(en)] != [
            fence_signature(block) for block in FENCES.findall(pt)
        ]:
            raise PublicationError("Review report paired calculation fences mismatch")
    return manifest


def review_bundle(
    run: str | Path, output: str | Path, *, source_root: str | Path | None = None
) -> Path:
    """Export only declared inputs, frozen stages/chain, reports and source whitelist."""
    run, output = Path(run).resolve(), Path(output).resolve()
    descriptor = json.loads((run / "reproduction.json").read_text())
    if output.is_relative_to(run) or run.is_relative_to(output):
        raise PublicationError("Bundle and run must be disjoint")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    staging = Path(tempfile.mkdtemp(prefix=".review-building-", dir=output.parent))
    try:
        target = staging / "run"
        target.mkdir()
        snapshot = relative_file(run, descriptor["snapshot"])
        inspect_snapshot(snapshot, verify_objects=True)
        _copy_tree(snapshot, target / descriptor["snapshot"])
        for stage in descriptor["stages"]:
            release = relative_file(run, stage["locator"])
            for parent, _ in release_layers(release, inspect_release(release)):
                destination = target / parent.relative_to(run)
                if not destination.exists():
                    _copy_tree(parent, destination)
        # Only explicit generated inputs/reports; never raw source/live SQLite.
        for name in ("inputs", "reports"):
            if (run / name).exists():
                _copy_tree(run / name, target / name)
        for name in (
            "reproduction.json",
            "synthetic-expectations.json",
            "pilot-selection.json",
            "pilot-results.json",
        ):
            if (run / name).exists():
                shutil.copyfile(run / name, target / name)
        repository = Path(source_root or Path(__file__).resolve().parents[1])
        code = staging / "source"
        code.mkdir()
        for name in ("election_audit", "scripts", "tests", "docs", "research"):
            if (repository / name).exists():
                _copy_tree(repository / name, code / name)
        for name in (
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            ".gitignore",
            "justfile",
            "README.md",
            "README.pt-BR.md",
        ):
            if (repository / name).is_file():
                if (repository / name).is_symlink():
                    raise PublicationError("Review source must not contain symlinks")
                shutil.copyfile(repository / name, code / name)
        # Included artifact input hashes, code and lock are exact; no Git invented.
        manifest = {
            "version": VERSION,
            "created_at": utc_now(),
            "runtime": runtime(),
            "dependency_install": "offline requires preinstalled locked dependencies or a populated uv cache; cache/wheels are not bundled",
            "files": file_pins(staging),
        }
        write_json(staging / "review-bundle.json", manifest)
        (staging / "review-bundle.sha256").write_text(
            hash_file(staging / "review-bundle.json")[0] + "\n"
        )
        verify_bundle(staging)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output


def reproduce(bundle: str | Path, output: str | Path) -> JSON:
    """Verify relocated evidence, replay frozen inputs into a fresh directory."""
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    verify_bundle(bundle)
    # Reproduction executes installed code, never arbitrary bundle instructions.
    # Require that implementation to match the checked bundled source first.
    repository = Path(__file__).resolve().parents[1]
    for package in ("election_audit", "scripts"):
        for saved in sorted((bundle / "source" / package).rglob("*")):
            if saved.is_file() and saved.suffix in {".py", ".json"}:
                current = repository / saved.relative_to(bundle / "source")
                if not current.is_file() or hash_file(current) != hash_file(saved):
                    raise PublicationError(
                        "Reproduction implementation differs from bundled source; run from bundle/source"
                    )
    if output.is_relative_to(bundle) or bundle.is_relative_to(output):
        raise PublicationError("Reproduction output must be outside bundle")
    output.mkdir(parents=True, exist_ok=False)
    run = bundle / "run"
    descriptor = json.loads((run / "reproduction.json").read_text())
    evidence = (
        json.loads(relative_file(run, descriptor["evidence"]).read_text())
        if descriptor["evidence"]
        else None
    )
    config = ResourceConfig(**descriptor["resource_config"])
    parsed, _, parent, elapsed = frozen_pipeline(
        relative_file(run, descriptor["snapshot"]),
        output,
        config=config,
        evidence=evidence,
        object_groups=descriptor["object_groups"],
    )
    releases = [parent]
    from election_audit.analysis import publish_analysis

    for step in descriptor["steps"]:
        publisher = {"analysis": publish_analysis, "electoral": publish_derivative}.get(
            step["kind"]
        )
        if publisher is None:
            raise PublicationError("Unknown reproduction step")
        parent = publisher(
            parent, relative_file(run, step["bundle"]), output / "warehouse", config=config
        )
        releases.append(parent)
    identities = {
        stage["release_id"]: f"stage:{index}" for index, stage in enumerate(descriptor["stages"])
    }
    identities.update({path.name: f"stage:{index}" for index, path in enumerate(releases)})
    matches = []
    for path, expected in zip(releases, descriptor["stages"], strict=True):
        validate_release(path)
        actual = logical_results(path, identities)
        if actual != expected["results"]:
            differing = [name for name in actual if actual[name] != expected["results"].get(name)]
            raise PublicationError(f"Reproduction logical results mismatch: {differing}")
        matches.append(
            {
                "original": expected["release_id"],
                "reproduced": path.name,
                "tables": len(actual),
                "logical_results": "matched",
            }
        )
    if parsed.name != descriptor["parse_id"]:
        raise PublicationError("Reproduction parse identity mismatch")
    report_release(parent, output / "reports")
    result = {
        "version": VERSION,
        "verified_at": utc_now(),
        "runtime": runtime(),
        "parse_identity": "matched",
        "stages": matches,
        "pipeline_seconds": elapsed,
        "source_runtime": descriptor["runtime"],
        "status": "passed",
    }
    write_json(output / "reproduction-result.json", result)
    return result


def reproduction_main(command: str, argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    if command == "backfill":
        parser.add_argument("snapshot", type=Path)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--max-events", type=int, default=100_000)
        args = parser.parse_args(argv)
        config = ResourceConfig(max_events=args.max_events)
        parsed, shards, release, elapsed = frozen_pipeline(
            args.snapshot, args.output, config=config
        )
        result = {
            "release": str(release),
            "parse_id": parsed.name,
            "shards": len(shards),
            "pipeline_seconds": elapsed,
            "validation": validate_release(release),
        }
    elif command == "demo":
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args(argv)
        result = demo(args.output)
    elif command == "review-bundle":
        parser.add_argument("run", type=Path)
        parser.add_argument("--output", type=Path)
        parser.add_argument("--verify", action="store_true")
        args = parser.parse_args(argv)
        if args.verify:
            manifest = verify_bundle(args.run)
            result = {"status": "passed", "files": len(manifest["files"])}
        elif args.output:
            result = {"bundle": str(review_bundle(args.run, args.output))}
        else:
            parser.error("--output or --verify is required")
    else:
        parser.add_argument("bundle", type=Path)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args(argv)
        result = reproduce(args.bundle, args.output)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0
