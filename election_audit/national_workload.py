"""Disk-backed, protected-scope structural processing with explicit external custody.

The immutable scope retains every frozen source observation. Its separate SQLite
work ledger only schedules nonexcluded content; protected bodies are never opened.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

from election_audit.archive_parsing import PARSER_VERSION, ParseConfig
from election_audit.national import (
    DIAGNOSTIC_POLICY,
    _destinations,
    _lock,
    _read_json,
    _sync_dir,
    _verify_files,
    _write_json,
)
from election_audit.national_storage import (
    FORMAT,
    iter_compact,
    process_compact_original,
    registered_original,
    resolve_original,
)
from election_audit.national_tuning import (
    code_pins,
    configure_production,
    recommendation,
    save_state,
)
from election_audit.source_inventory import ALL_UFS, digest, hash_file, utc_now

VERSION = "national-compact-workload-v1"

LAUNCHER = """from pathlib import Path
import hashlib,json,os,sys
directory=Path(__file__).resolve().parent
body=(directory/"workload.json").read_bytes()
if hashlib.sha256(body).hexdigest() != (directory/"workload.json.sha256").read_text().strip():
    raise ValueError("Frozen workload checksum mismatch")
spec=json.loads(body)
for name,expected in spec["runtime_files"].items():
    target=directory/"runtime"/name
    if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
        raise ValueError("Frozen runtime changed")
action=sys.argv[1] if len(sys.argv)>1 else "status"
if action not in ("run","status","preflight"):
    raise ValueError("Frozen launcher accepts run, status or preflight")
if action=="run":
    scratch=Path(spec["scratch"])/spec["job_id"]
    scratch.mkdir(parents=True,exist_ok=True)
    os.environ["SQLITE_TMPDIR"]=str(scratch)
sys.path.insert(0,str(directory/"runtime"))
from election_audit.national_workload import main
main([action,str(directory),*sys.argv[2:]])
"""


def _connection(path, *, readonly=False):
    db = sqlite3.connect(
        Path(path).resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rwc"), uri=True
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA cache_size=-16384")
    db.execute("PRAGMA temp_store=FILE")
    if not readonly:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
    return db


def _mount(path):
    path = Path(path).resolve()
    while not path.is_mount():
        path = path.parent
    return path


def _exclusions(path, round_number):
    path = Path(path)
    if path.stat().st_size > 16 * 1024**2:
        raise ValueError("Exclusions exceed bounded metadata allowance")
    doc = _read_json(path)
    if doc["version"] != "structural-sample-exclusions-v1" or doc["round"] != round_number:
        raise ValueError("Protected exclusions do not match source round")
    keys = doc["section_keys"]
    if not isinstance(keys, list) or len(keys) > 100000:
        raise ValueError("Need bounded explicit protected-section exclusions")
    for key in keys:
        if not isinstance(key, list) or len(key) != 4 or any(not isinstance(s, str) for s in key):
            raise ValueError("Malformed exclusion key")
        if key[0] not in ALL_UFS or any(
            not s.isascii() or not s.isdigit() or len(s) != n
            for s, n in zip(key[1:], (5, 4, 4), strict=True)
        ):
            raise ValueError("Malformed exclusion geography")
    return doc


def _attach_scope(db, profile, exclusions):
    db.execute(
        "ATTACH DATABASE ? AS profile", ((Path(profile) / "profile.sqlite").as_uri() + "?mode=ro",)
    )
    db.execute(
        "CREATE TEMP TABLE excluded(uf TEXT,municipality TEXT,zone TEXT,section TEXT,PRIMARY KEY(uf,municipality,zone,section))"
    )
    db.executemany("INSERT OR IGNORE INTO excluded VALUES(?,?,?,?)", exclusions["section_keys"])
    db.execute(
        "CREATE TEMP TABLE protected_content AS SELECT DISTINCT s.sha256 FROM profile.sources s WHERE EXISTS(SELECT 1 FROM excluded e WHERE e.uf=s.uf AND e.municipality=s.municipality AND e.zone=s.zone AND e.section=s.section)"
    )
    db.execute("CREATE UNIQUE INDEX protected_sha ON protected_content(sha256)")


def prepare(
    profile,
    exclusions,
    tuning_config,
    output,
    store,
    scratch,
    *,
    output_budget_bytes=256 * 1024**3,
    future_budget_bytes=256 * 1024**3,
    source_growth_budget_bytes=0,
    volume_anchor=None,
    reuse_stores=(),
    relocation_registry=None,
):
    profile, exclusions, tuning_config, output, store, scratch = (
        Path(p).resolve() for p in (profile, exclusions, tuning_config, output, store, scratch)
    )
    if output.exists():
        raise ValueError("Workload configuration directory must be new")
    if (
        type(output_budget_bytes) is not int
        or output_budget_bytes < 2 * 1024**2
        or future_budget_bytes < 0
        or source_growth_budget_bytes < 0
    ):
        raise ValueError("Need explicit positive output and nonnegative future allocation")
    doc = _read_json(profile / "profile.json")
    if doc["source_run"]["status"] != "finished":
        raise ValueError("Only completed frozen source populations may be scheduled")
    expected = doc["files"]["profile.sqlite"]
    if hash_file(profile / "profile.sqlite") != (expected["sha256"], expected["bytes"]):
        raise ValueError("Frozen source metadata changed")
    excluded = _exclusions(exclusions, doc["source"]["round"])
    selected = recommendation(tuning_config)
    relocation = None
    if relocation_registry is not None:
        from election_audit.national_relocation import configure

        registry_path = Path(relocation_registry).absolute()
        relocation = {"path": str(registry_path), "sha256": hash_file(registry_path)[0]}
        configure(relocation["path"], relocation["sha256"])
    _destinations({"sources": [doc["source"]]}, store, scratch)
    if output == store or output.is_relative_to(store):
        raise ValueError("Keep small workspace configuration separate from durable work store")
    with closing(sqlite3.connect(":memory:", uri=True)) as db:
        _attach_scope(db, profile, excluded)
        total, protected = db.execute(
            "SELECT count(*),sum(EXISTS(SELECT 1 FROM protected_content p WHERE p.sha256=s.sha256)) FROM profile.sources s"
        ).fetchone()
        eligible_content = db.execute(
            "SELECT count(DISTINCT s.sha256) FROM profile.sources s WHERE NOT EXISTS(SELECT 1 FROM protected_content p WHERE p.sha256=s.sha256)"
        ).fetchone()[0]
    package = Path(__file__).resolve().parent
    runtime_paths = sorted(
        [*package.glob("*.py"), *(p for p in (package / "resources").rglob("*") if p.is_file())]
    )
    runtime_sources = {
        str(Path("election_audit") / p.relative_to(package)): p for p in runtime_paths
    }
    # Source/coverage adapters import these passive helpers. Freeze their source
    # too so a later collector edit cannot change a resumed audit's import closure.
    for relative in (
        "scripts/__init__.py",
        "scripts/download_tse_logs.py",
        "pyproject.toml",
        "uv.lock",
    ):
        source = package.parent / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError("Required runtime dependency is unavailable")
        runtime_sources[relative] = source
    runtime_files = {relative: hash_file(source)[0] for relative, source in runtime_sources.items()}
    spec = {
        "version": VERSION,
        "profile": str(profile),
        "profile_json_sha256": hash_file(profile / "profile.json")[0],
        "profile_sqlite": expected,
        "source": doc["source"],
        "source_run": doc["source_run"],
        "source_rows_sha256": doc["source_rows_sha256"],
        "exclusions": str(exclusions),
        "exclusions_sha256": hash_file(exclusions)[0],
        "scope": {
            "source_observations": total,
            "excluded_observations": protected or 0,
            "eligible_observations": total - (protected or 0),
            "eligible_unique_content": eligible_content,
        },
        "store": str(store),
        "scratch": str(scratch),
        "volume_anchor": str(Path(volume_anchor).resolve() if volume_anchor else _mount(store)),
        "reuse_stores": [str(Path(p).resolve()) for p in reuse_stores],
        "relocation_registry": relocation,
        "tuning_config": str(tuning_config),
        "tuning_sha256": hash_file(tuning_config)[0],
        "batch_rows": selected["event_batch_rows"],
        "resources": selected["resources"],
        "output_budget_bytes": output_budget_bytes,
        "future_derived_budget_bytes": future_budget_bytes,
        "source_growth_budget_bytes": source_growth_budget_bytes,
        "metadata_allowance_bytes": min(2 * 1024**3, output_budget_bytes // 4),
        "code": code_pins(),
        "orchestrator_sha256": hash_file(Path(__file__))[0],
        "runtime_files": runtime_files,
        "inspection_policy": "automated structural preprocessing only; existing protected/stress locations excluded before body/cache access; no case-level outcome inspection; prior development registries remain binding; unassigned identity grants no test eligibility",
        "original_custody": "registered external collector CAS retained and verified; no raw copies; reused checkpoint stores remain explicit external dependencies",
        "scientific_eligibility": "unavailable_structural_only",
        "created_at": utc_now(),
    }
    spec["job_id"] = digest(spec)
    output.mkdir(parents=True)
    snapshots = output / "code-snapshot"
    snapshots.mkdir()
    for name, sha in {**spec["code"], "national_workload.py": spec["orchestrator_sha256"]}.items():
        dest = snapshots / name
        dest.write_bytes(Path(__file__).with_name(name).read_bytes())
        if hash_file(dest)[0] != sha:
            raise ValueError("Code changed while preparing workload")
        with dest.open("rb") as stream:
            os.fsync(stream.fileno())
    _sync_dir(snapshots)
    for relative, sha in runtime_files.items():
        source = runtime_sources[relative]
        dest = output / "runtime" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        if hash_file(dest)[0] != sha:
            raise ValueError("Runtime source changed during preparation")
        with dest.open("rb") as stream:
            os.fsync(stream.fileno())
    for path in sorted((p for p in (output / "runtime").rglob("*") if p.is_dir()), reverse=True):
        _sync_dir(path)
    _sync_dir(output / "runtime")
    launcher = output / "run_frozen.py"
    launcher.write_text(LAUNCHER)
    with launcher.open("rb") as stream:
        os.fsync(stream.fileno())
    _write_json(output / "workload.json", spec)
    return spec


def _load(directory):
    spec = _read_json(Path(directory) / "workload.json")
    if (
        spec["version"] != VERSION
        or digest({k: v for k, v in spec.items() if k != "job_id"}) != spec["job_id"]
    ):
        raise ValueError("Workload identity mismatch")
    if spec["code"] != code_pins() or spec["orchestrator_sha256"] != hash_file(Path(__file__))[0]:
        raise ValueError(
            "Workload code changed; preserve old run and prepare a new reviewed specification"
        )
    if hash_file(Path(spec["exclusions"]))[0] != spec["exclusions_sha256"]:
        raise ValueError("Protected exclusion registry changed")
    if hash_file(Path(spec["tuning_config"]))[0] != spec["tuning_sha256"]:
        raise ValueError("Pinned tuning configuration changed")
    if spec.get("relocation_registry"):
        from election_audit.national_relocation import configure

        configure(spec["relocation_registry"]["path"], spec["relocation_registry"]["sha256"])
    return spec


def _requirements(spec, spent, devices):
    policy = spec["resources"]
    roles = {
        "store": (
            policy["hdd_reserve_bytes"],
            max(0, spec["output_budget_bytes"] - spent) + spec["future_derived_budget_bytes"],
        ),
        "source": (policy["hdd_reserve_bytes"], spec["source_growth_budget_bytes"]),
        "scratch": (policy["ssd_reserve_bytes"], policy["scratch_budget_bytes"]),
    }
    groups = {}
    for role, (reserve, allowance) in roles.items():
        group = groups.setdefault(devices[role], [0, 0])
        group[0] = max(group[0], reserve)
        group[1] += allowance
    return {role: sum(groups[device]) for role, device in devices.items()}


def _capacity(spec, spent):
    volume = Path(spec["volume_anchor"])
    if not volume.is_mount():
        raise OSError("Declared output volume is not mounted; refusing fallback writes")
    if _mount(Path(spec["store"])) != volume:
        raise OSError("Output store is not on its declared mounted volume")
    free = shutil.disk_usage(volume).free
    scratch = Path(spec["scratch"])
    while not scratch.exists():
        scratch = scratch.parent
    scratch_free = shutil.disk_usage(scratch).free
    source_path = Path(spec["source"]["root"])
    source_free = shutil.disk_usage(source_path).free
    required = _requirements(
        spec,
        spent,
        {
            "store": volume.stat().st_dev,
            "source": source_path.stat().st_dev,
            "scratch": scratch.stat().st_dev,
        },
    )
    if (
        free < required["store"]
        or scratch_free < required["scratch"]
        or source_free < required["source"]
    ):
        raise OSError("Workload output/future/scratch capacity allowance is not available")
    parent = Path(spec["store"])
    while not parent.exists():
        parent = parent.parent
    return {
        "job_id": spec["job_id"],
        "scope": spec["scope"],
        "store_free_bytes": free,
        "store_required_bytes": required["store"],
        "future_derived_reserved_bytes": spec["future_derived_budget_bytes"],
        "scratch_free_bytes": scratch_free,
        "scratch_required_bytes": required["scratch"],
        "source_free_bytes": source_free,
        "source_growth_reserved_bytes": spec["source_growth_budget_bytes"],
        "source_required_bytes": required["source"],
        "volume_anchor": str(volume),
        "capacity": "passed",
        "write_access": os.access(parent, os.W_OK),
        "existing_output_parent": str(parent),
        "full_national_complete": False,
    }


def preflight(directory):
    spec = _load(directory)
    spent = 0
    work = Path(spec["store"]) / "work.sqlite"
    if work.exists():
        with closing(_connection(work, readonly=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='counters'").fetchone():
                row = db.execute(
                    "SELECT value FROM counters WHERE name='allocated_new_artifacts'"
                ).fetchone()
                spent = row[0] if row is not None else 0
    return _capacity(spec, spent)


def _allocated(directory):
    directory = Path(directory)
    return directory.stat().st_blocks * 512 + sum(
        p.stat().st_blocks * 512 for p in directory.rglob("*")
    )


def initialise(directory):
    directory = Path(directory).resolve()
    spec = _load(directory)
    preflight(directory)
    store = Path(spec["store"])
    store.mkdir(parents=True, exist_ok=True)
    marker = store / "store-root.json"
    if marker.exists():
        if _read_json(marker)["job_id"] != spec["job_id"]:
            raise ValueError("Store belongs to a different frozen workload")
    else:
        if any(p.name != ".locks" for p in store.iterdir()):
            raise ValueError("Unowned nonempty store; refusing to alter existing data")
        _write_json(
            marker,
            {
                "version": VERSION,
                "job_id": spec["job_id"],
                "source_rows_sha256": spec["source_rows_sha256"],
            },
        )
    for path in store.glob(".scope-*"):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Unexpected unpublished scope entry")
        shutil.rmtree(path)
    target = store / "scope"
    if target.exists():
        scope = _read_json(target / "scope.json")
        if scope["job_id"] != spec["job_id"]:
            raise ValueError("Store already belongs to another frozen workload")
        _verify_files(target, scope)
        return target
    profile = Path(spec["profile"])
    if hash_file(profile / "profile.json")[0] != spec["profile_json_sha256"] or hash_file(
        profile / "profile.sqlite"
    ) != (spec["profile_sqlite"]["sha256"], spec["profile_sqlite"]["bytes"]):
        raise ValueError("Frozen workload source metadata changed")
    excluded = _exclusions(spec["exclusions"], spec["source"]["round"])
    staging = Path(tempfile.mkdtemp(prefix=".scope-", dir=store))
    try:
        with closing(sqlite3.connect(staging / "observations.sqlite", uri=True)) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            _attach_scope(db, profile, excluded)
            db.execute(
                "CREATE TABLE observations AS SELECT s.*, CASE WHEN EXISTS(SELECT 1 FROM protected_content p WHERE p.sha256=s.sha256) THEN 'excluded_protected_or_stress' ELSE 'eligible_structural_preprocessing' END AS processing_scope FROM profile.sources s"
            )
            db.execute("CREATE UNIQUE INDEX observation_url ON observations(url)")
            db.execute("CREATE INDEX observation_sha ON observations(sha256)")
            db.commit()
            counts = dict(
                db.execute(
                    "SELECT processing_scope,count(*) FROM observations GROUP BY processing_scope"
                )
            )
        with (staging / "observations.sqlite").open("rb") as stream:
            os.fsync(stream.fileno())
        _write_json(
            staging / "scope.json",
            {
                "version": VERSION,
                "job_id": spec["job_id"],
                "scope_counts": counts,
                "files": {
                    "observations.sqlite": dict(
                        zip(
                            ("sha256", "bytes"),
                            hash_file(staging / "observations.sqlite"),
                            strict=True,
                        )
                    )
                },
                "source_rows_sha256": spec["source_rows_sha256"],
                "exclusions_sha256": spec["exclusions_sha256"],
                "excluded_bodies_opened": 0,
            },
        )
        staging.rename(target)
        _sync_dir(store)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return target


def _ledger(store, scope):
    path = Path(store) / "work.sqlite"
    db = _connection(path)
    db.execute(
        "ATTACH DATABASE ? AS frozen",
        ((Path(scope) / "observations.sqlite").as_uri() + "?mode=ro",),
    )
    db.executescript(
        "CREATE TABLE IF NOT EXISTS work(sha256 TEXT PRIMARY KEY,url TEXT NOT NULL,status TEXT NOT NULL,artifact TEXT,origin TEXT,allocated_bytes INTEGER DEFAULT 0,events INTEGER DEFAULT 0,issues INTEGER DEFAULT 0,parser_status TEXT); CREATE INDEX IF NOT EXISTS work_status ON work(status,sha256); CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,sha256 TEXT,at TEXT,state TEXT,error_type TEXT); CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY,value INTEGER NOT NULL);"
    )
    if not db.execute("SELECT 1 FROM counters WHERE name='initialised'").fetchone():
        db.execute(
            "INSERT INTO work(sha256,url,status) SELECT sha256,min(url),'pending' FROM frozen.observations WHERE processing_scope='eligible_structural_preprocessing' GROUP BY sha256"
        )
        db.executemany(
            "INSERT INTO counters VALUES (?,?)",
            [
                ("initialised", 1),
                ("completed", 0),
                ("failed", 0),
                ("partial", 0),
                ("allocated_new_artifacts", 0),
                ("events", 0),
                ("issues", 0),
                ("reused_external", 0),
            ],
        )
        db.commit()
    db.execute("UPDATE work SET status='pending' WHERE status='running'")
    db.commit()
    return db


def _reuse(row, roots):
    key = digest([row["sha256"], FORMAT, DIAGNOSTIC_POLICY, ParseConfig().__dict__])
    for root in roots:
        root = Path(root).resolve()
        path = root / "compact" / key[:2] / key
        if not path.exists():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError("Reuse checkpoint escapes its declared store")
        doc = _read_json(path / "checkpoint.json")
        if (
            doc["version"] != FORMAT
            or doc["object_sha256"] != row["sha256"]
            or doc["diagnostic_policy"] != DIAGNOSTIC_POLICY
            or doc["parser"]["parser_version"] != PARSER_VERSION
            or doc["parser"]["config"] != ParseConfig().__dict__
        ):
            raise ValueError("Reuse checkpoint has incompatible structural identity")
        registered_original(row)
        _verify_files(path, doc)
        resolve_original(doc["original_reference"])
        return path
    return None


def status(directory):
    spec = _load(directory)
    store = Path(spec["store"])
    if not (store / "work.sqlite").exists():
        return {
            "job_id": spec["job_id"],
            "state": "not_started",
            "scope": spec["scope"],
            "full_national_complete": False,
        }
    with closing(_connection(store / "work.sqlite", readonly=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='counters'").fetchone():
            return {
                "job_id": spec["job_id"],
                "state": "initialising",
                "scope": spec["scope"],
                "full_national_complete": False,
            }
        counters = dict(db.execute("SELECT name,value FROM counters"))
        counts = dict(db.execute("SELECT status,count(*) FROM work GROUP BY status"))
    if not counters.get("initialised"):
        return {
            "job_id": spec["job_id"],
            "state": "initialising",
            "scope": spec["scope"],
            "full_national_complete": False,
        }
    completed = counters["completed"]
    complete = completed == spec["scope"]["eligible_unique_content"] and not counters["failed"]
    return {
        "job_id": spec["job_id"],
        "state": "eligible_scope_complete" if complete else "incomplete",
        "scope": spec["scope"],
        "work_status": counts,
        "counters": counters,
        "full_national_complete": False,
        "coverage_limit": "existing protected/stress source observations excluded; first round not scheduled; structural processing grants no scientific eligibility",
    }


def iter_observations(directory):
    """Stream every source witness, including excluded/pending/failed unknowns.

    This reads metadata only. Counts are null until an artifact is complete; a
    partial parser status never grants scientific eligibility. Consumers aggregate
    content before joining publisher witnesses to avoid multiplying event counts.
    """
    spec = _load(directory)
    store = Path(spec["store"])
    if not (store / "work.sqlite").exists():
        raise ValueError("Initialise the frozen workload scope before reading observations")
    with closing(_connection(store / "work.sqlite", readonly=True)) as db:
        db.execute(
            "ATTACH DATABASE ? AS frozen",
            ((store / "scope/observations.sqlite").as_uri() + "?mode=ro",),
        )
        for row in db.execute(
            "SELECT s.*, CASE WHEN s.processing_scope='excluded_protected_or_stress' THEN 'deferred_protected_or_stress' ELSE coalesce(w.status,'pending') END AS work_state,w.artifact,w.origin,w.parser_status,CASE WHEN w.status='complete' THEN w.events ELSE NULL END AS events,CASE WHEN w.status='complete' THEN w.issues ELSE NULL END AS issues FROM frozen.observations s LEFT JOIN work w USING(sha256) ORDER BY s.url"
        ):
            yield {
                **dict(row),
                "round": spec["source"]["round"],
                "job_id": spec["job_id"],
                "scientific_eligibility": "unavailable_structural_only",
            }


def run(directory, *, max_objects=None, retry_failed=False):
    directory = Path(directory).resolve()
    spec = _load(directory)
    if max_objects is not None and (type(max_objects) is not int or max_objects < 1):
        raise ValueError("max_objects must be positive")
    preflight(directory)
    configure_production(spec["resources"])
    store, scratch = Path(spec["store"]), Path(spec["scratch"]) / spec["job_id"]
    with _lock(store, "national"), _lock(directory, "workload"):
        scope = initialise(directory)
        with closing(_ledger(store, scope)) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if (
                _allocated(scope)
                + sum(p.stat().st_blocks * 512 for p in store.glob("work.sqlite*"))
                > spec["metadata_allowance_bytes"]
            ):
                raise OSError("Frozen scope/work ledger exceeds explicit metadata allowance")
            scratch.mkdir(parents=True, exist_ok=True)
            # Both roots are private to this pinned job; the exclusive lock proves
            # no worker can own these unpublished temporaries after an interruption.
            for path in scratch.glob("compact-object-*"):
                if path.is_symlink() or not path.is_dir():
                    raise ValueError("Unexpected private scratch entry")
                shutil.rmtree(path)
            for path in (store / "compact").glob("*/.compact-*"):
                if path.is_symlink() or not path.is_dir():
                    raise ValueError("Unexpected unpublished checkpoint entry")
                shutil.rmtree(path)
            if retry_failed:
                failed = db.execute("SELECT count(*) FROM work WHERE status='failed'").fetchone()[0]
                db.execute("UPDATE work SET status='pending' WHERE status='failed'")
                db.execute("UPDATE counters SET value=value-? WHERE name='failed'", (failed,))
                db.commit()
            started, processed = time.monotonic(), 0
            while max_objects is None or processed < max_objects:
                row = db.execute(
                    "SELECT s.* FROM work w JOIN frozen.observations s ON s.url=w.url WHERE w.status='pending' ORDER BY w.sha256 LIMIT 1"
                ).fetchone()
                if row is None:
                    break
                row = dict(row)
                if row["processing_scope"] != "eligible_structural_preprocessing":
                    raise ValueError("Protected body access prevented by frozen scope")
                row["source_root"] = spec["source"]["root"]
                spent = db.execute(
                    "SELECT value FROM counters WHERE name='allocated_new_artifacts'"
                ).fetchone()[0]
                remaining = spec["output_budget_bytes"] - spec["metadata_allowance_bytes"] - spent
                if remaining <= 1024**2:
                    break
                _capacity(spec, spent)
                db.execute("UPDATE work SET status='running' WHERE sha256=?", (row["sha256"],))
                db.execute(
                    "INSERT INTO attempts(sha256,at,state) VALUES(?,?,'started')",
                    (row["sha256"], utc_now()),
                )
                db.commit()
                try:
                    artifact = _reuse(row, spec["reuse_stores"])
                    external = artifact is not None
                    if artifact is None:
                        artifact = process_compact_original(
                            row,
                            store,
                            scratch,
                            output_budget_bytes=remaining,
                            batch_rows=spec["batch_rows"],
                        )
                    doc = _read_json(artifact / "checkpoint.json")
                    if (
                        not external
                        and sum(1 for _ in iter_compact(artifact / "events"))
                        != doc["counts"]["events"]
                    ):
                        raise ValueError("Published logical event stream count differs")
                    charge = 0 if external else _allocated(artifact)
                    if charge > remaining:
                        raise OSError("Allocated checkpoint exceeds remaining output allowance")
                    partial = int(doc["parser"]["status"] != "complete")
                    db.execute(
                        "UPDATE work SET status='complete',artifact=?,origin=?,allocated_bytes=?,events=?,issues=?,parser_status=? WHERE sha256=?",
                        (
                            str(artifact),
                            "external_verified_checkpoint" if external else "this_store",
                            charge,
                            doc["counts"]["events"],
                            doc["counts"]["issues"],
                            doc["parser"]["status"],
                            row["sha256"],
                        ),
                    )
                    for key, value in {
                        "completed": 1,
                        "allocated_new_artifacts": charge,
                        "events": doc["counts"]["events"],
                        "issues": doc["counts"]["issues"],
                        "partial": partial,
                        "reused_external": int(external),
                    }.items():
                        db.execute("UPDATE counters SET value=value+? WHERE name=?", (value, key))
                    db.execute(
                        "INSERT INTO attempts(sha256,at,state) VALUES(?,?,'completed')",
                        (row["sha256"], utc_now()),
                    )
                    db.commit()
                except BaseException as exc:
                    db.execute("UPDATE work SET status='failed' WHERE sha256=?", (row["sha256"],))
                    db.execute("UPDATE counters SET value=value+1 WHERE name='failed'")
                    db.execute(
                        "INSERT INTO attempts(sha256,at,state,error_type) VALUES(?,?,'failed',?)",
                        (row["sha256"], utc_now(), type(exc).__name__),
                    )
                    db.commit()
                    save_state(
                        directory / "progress.json",
                        {
                            **status(directory),
                            "run_state": "stopped_failure",
                            "error_type": type(exc).__name__,
                            "at": utc_now(),
                            "pid": os.getpid(),
                        },
                    )
                    raise
                processed += 1
                if processed % 25 == 0:
                    progress = {
                        **status(directory),
                        "at": utc_now(),
                        "pid": os.getpid(),
                        "objects_this_attempt": processed,
                        "elapsed_this_attempt_seconds": time.monotonic() - started,
                    }
                    save_state(directory / "progress.json", progress)
                    print(
                        json.dumps(
                            {
                                "completed": progress["counters"]["completed"],
                                "eligible": spec["scope"]["eligible_unique_content"],
                                "allocated_new_bytes": progress["counters"][
                                    "allocated_new_artifacts"
                                ],
                            }
                        ),
                        flush=True,
                    )
            result = {
                **status(directory),
                "at": utc_now(),
                "pid": os.getpid(),
                "objects_this_attempt": processed,
                "elapsed_this_attempt_seconds": time.monotonic() - started,
            }
            save_state(directory / "progress.json", result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("prepare")
    for name in ("profile", "exclusions", "tuning-config", "output", "store", "scratch"):
        setup.add_argument("--" + name, required=True)
    setup.add_argument("--volume-anchor")
    setup.add_argument("--reuse-store", action="append", default=[])
    setup.add_argument("--output-budget-gib", type=float, default=256)
    setup.add_argument("--future-budget-gib", type=float, default=256)
    setup.add_argument("--source-growth-gib", type=float, default=0)
    for action in ("preflight", "status", "run"):
        child = sub.add_parser(action)
        child.add_argument("directory")
        if action == "run":
            child.add_argument("--max-objects", type=int)
            child.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        result = prepare(
            args.profile,
            args.exclusions,
            args.tuning_config,
            args.output,
            args.store,
            args.scratch,
            output_budget_bytes=int(args.output_budget_gib * 1024**3),
            future_budget_bytes=int(args.future_budget_gib * 1024**3),
            source_growth_budget_bytes=int(args.source_growth_gib * 1024**3),
            volume_anchor=args.volume_anchor,
            reuse_stores=args.reuse_store,
        )
        result = {"job_id": result["job_id"], "scope": result["scope"]}
    elif args.action == "run":
        result = run(args.directory, max_objects=args.max_objects, retry_failed=args.retry_failed)
    elif args.action == "status":
        result = status(args.directory)
    else:
        result = preflight(args.directory)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
