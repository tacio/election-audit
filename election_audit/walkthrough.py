"""Small, explicitly synthetic frozen-input walkthrough shipped with the wheel."""

import io
import json
import sqlite3
import zipfile
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

from election_audit.publication import SCHEMA, open_release
from election_audit.source_inventory import (
    aux_url,
    canonical,
    hash_file,
    index_url,
    section_directory,
)
from election_audit.types import JSON, Row, one

SYNTHETIC_AT = "2026-10-29T00:00:00+00:00"


def write_json(path: Path, value: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")
    return path


def archive(members: Iterable[tuple[str, bytes]]) -> bytes:
    """Deterministic ZIP metadata, independent of wall clock and host permissions."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as output:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 25, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    return stream.getvalue()


def synthetic_source(root: Path) -> Path:
    """Create only tiny local source fixtures; no downloader or test imports."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    database = root / "manifest.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.executescript("""
          CREATE TABLE files(url TEXT PRIMARY KEY,path TEXT,sha256 TEXT,bytes INTEGER,
                             fetched_at TEXT,etag TEXT,last_modified TEXT);
          CREATE TABLE runs(id TEXT PRIMARY KEY,started_at TEXT,finished_at TEXT,status TEXT);
          CREATE TABLE sections(run TEXT,uf TEXT,municipality TEXT,zone TEXT,section TEXT,
                                status TEXT,metadata TEXT,details TEXT,
                                PRIMARY KEY(run,uf,municipality,zone,section));
          CREATE TABLE logs(run TEXT,uf TEXT,municipality TEXT,zone TEXT,section TEXT,
                            url TEXT,package_status TEXT,package_hash TEXT,filename TEXT,
                            PRIMARY KEY(run,url));
        """)
        db.execute("INSERT INTO runs VALUES (?,?,?,'synthetic')", (SYNTHETIC_AT,) * 3)

        def save(url: str, body: bytes | JSON) -> None:
            import hashlib

            raw = body if isinstance(body, bytes) else canonical(body)
            sha = hashlib.sha256(raw).hexdigest()
            relative = f"objects/{sha[:2]}/{sha}"
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            db.execute(
                "INSERT INTO files VALUES (?,?,?,?,?,NULL,NULL)",
                (url, relative, sha, len(raw), SYNTHETIC_AT),
            )

        save(
            index_url("ac"),
            {
                "f": "o",
                "cdp": "3221",
                "abr": [
                    {
                        "cd": "ac",
                        "mu": [
                            {
                                "cd": "01120",
                                "zon": [
                                    {
                                        "cd": "0001",
                                        "sec": [
                                            {"ns": "0001", "da": "synthetic"},
                                            {"ns": "0002", "nsp": "0001"},
                                            {"ns": "0003", "da": "synthetic"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )

        def line(
            message: str, time: str = "08:00:00", date: str = "25/10/2026", device: str = "1234"
        ) -> bytes:
            return f"{date} {time}\tINFO\t{device}\tVOTA\t{message}\t\n".encode("latin-1")

        first = [
            line("Eleitor foi habilitado", date="04/10/2026"),
            line("Eleitor foi habilitado"),
            line("O voto do eleitor foi computado", "08:01:00"),
            line("Solicitação de dado pessoal do eleitor para habilitação manual", "08:02:00"),
            line("DEMO_CANCELAMENTO", "08:02:10"),
        ]
        # Exact copied history in another archive member, plus replacement device.
        replacement = [
            line("Eleitor foi habilitado", "08:03:00", device="5678"),
            line("O voto do eleitor foi computado", "08:04:00", device="5678"),
        ]
        nested = archive([("logd.dat", b"".join(first))])
        body = archive(
            [
                ("history.zip", nested),
                ("copy/logd.dat", b"".join(first[1:3])),
                ("replacement/logd.dat", b"".join(replacement)),
                ("malformed.zip", b"synthetic malformed nested archive"),
            ]
        )
        key = ("ac", "01120", "0001", "0001")
        filename = "synthetic-log.jez"
        url = section_directory(key) + "/demo/" + filename
        save(url, body)
        save(
            aux_url(key),
            {
                "f": "o",
                "hashes": [
                    {
                        "hash": "demo",
                        "st": "Totalizado",
                        "arq": [
                            {"nm": filename, "tp": "log"},
                        ],
                    }
                ],
            },
        )
        db.execute(
            "INSERT INTO sections VALUES (?,?,?,?,?,?,?,NULL)",
            (
                SYNTHETIC_AT,
                *key,
                "downloaded",
                json.dumps({"ns": "0001"}),
            ),
        )
        db.execute(
            "INSERT INTO logs VALUES (?,?,?,?,?,?,?,?,?)",
            (
                SYNTHETIC_AT,
                *key,
                url,
                "Totalizado",
                "demo",
                filename,
            ),
        )
        db.commit()
    return root


def synthetic_evidence(parsed: Path) -> JSON:
    from election_audit.archive_parsing import inspect_parse, iter_event_witnesses

    document = inspect_parse(parsed)
    events = list({r["event_id"]: r for r in iter_event_witnesses(parsed)}.values())
    section = next(r for r in document["context_tables"]["section"] if r["section_code"] == "0001")

    def member(event: Row) -> str:
        return event["record_locator"]["archive_segments"][0]["member_name"]

    def claim(group: list[Row], **values: Any) -> JSON:
        return {
            "rule_id": "SYNTHETIC-reviewed-v1",
            "review_state": "reviewed",
            "evidence": [
                {"event_id": r["event_id"], "source_line_sha256": r["source_line_sha256"]}
                for r in group
            ],
            **values,
        }

    history = sorted(
        [r for r in events if member(r) == "history.zip"], key=lambda r: r["source_sequence"]
    )
    copied = sorted(
        [r for r in events if member(r) == "copy/logd.dat"], key=lambda r: r["source_sequence"]
    )
    replacement = sorted(
        [r for r in events if member(r) == "replacement/logd.dat"],
        key=lambda r: r["source_sequence"],
    )
    segments = []
    for group, serial in ((history, "1234"), (replacement, "5678")):
        segments.append(
            claim(
                group,
                event_ids=[r["event_id"] for r in group],
                session_kind="official_vota",
                principal_section_id=section["section_id"],
                election_id=section["election_id"],
                serial=serial,
                start_reason="replacement" if serial == "5678" else "opening",
                end_reason="unknown" if serial == "5678" else "replacement",
            )
        )
    return {
        "version": "operational-evidence-v1",
        "segments": segments,
        "copies": [
            claim(
                history[1:3] + copied,
                canonical_event_ids=[r["event_id"] for r in history[1:3]],
                copied_event_ids=[r["event_id"] for r in copied],
            )
        ],
        "semantics": [claim([history[4]], event_id=history[4]["event_id"], kind="cancellation")],
        # Deliberately omit timezone/continuity claims: unknown remains unknown.
        "clocks": [],
    }


def normalized_demo(parent: Path, directory: str | Path) -> Path:
    """Known 10/20 turnout with fully synthetic normalized-only evidence."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with open_release(parent) as db:
        section = json.loads(
            one(db.execute("SELECT payload FROM section WHERE section_code='0001'").fetchone())[0]
        )
        snapshot = one(db.execute("SELECT snapshot_id FROM snapshot LIMIT 1").fetchone())[0]

    def row(name: str, **values: Any) -> Row:
        result = {key: values.get(key) for key in SCHEMA[name]["fields"]}
        result["field_states"] = {key: "unknown" for key, value in result.items() if value is None}
        return result

    data = {
        "contest": [
            row(
                "contest",
                contest_id="demo-president",
                election_id=section["election_id"],
                cargo_code="0001",
                jurisdiction_code="br",
            )
        ],
        "candidacy": [
            row(
                "candidacy",
                candidacy_id="demo-a",
                contest_id="demo-president",
                official_candidate_id="SYNTHETIC-a",
                ballot_number="11",
            )
        ],
        "vote_choice": [
            row(
                "vote_choice",
                vote_choice_id=kind,
                contest_id="demo-president",
                choice_code=kind,
                choice_kind=kind,
                candidacy_id="demo-a" if kind == "candidate" else None,
            )
            for kind in ("candidate", "blank", "null", "special", "unresolved")
        ],
        "result_version": [
            row(
                "result_version",
                result_version_id="demo-v",
                principal_section_id=section["section_id"],
                contest_id="demo-president",
                result_status="totalized",
            )
        ],
        "section_contest_totals": [
            row(
                "section_contest_totals",
                result_version_id="demo-v",
                eligible_electors=20,
                attending_voters=10,
                abstaining_electors=10,
                total_presidential_ballots=10,
                valid_candidate_votes=10,
                blank_votes=0,
                null_votes=0,
                special_votes=0,
                unresolved_votes=0,
            )
        ],
        "vote_choice_count": [
            row(
                "vote_choice_count",
                result_version_id="demo-v",
                vote_choice_id=kind,
                vote_count=10 if kind == "candidate" else 0,
            )
            for kind in ("candidate", "blank", "null", "special", "unresolved")
        ],
    }
    # Status evidence is the exact synthetic normalized result-version line.
    status = directory / "result_version.jsonl"
    status.write_bytes(b"".join(canonical(r) + b"\n" for r in data["result_version"]))
    data["result_evidence"] = [
        {
            "result_version_id": "demo-v",
            "snapshot_id": snapshot,
            "status_evidence": {
                "object_sha256": hash_file(status)[0],
                "record_locator": "synthetic result_version.jsonl line 1",
            },
            "official_target": True,
            "complete_choices": True,
            "expected_choice_ids": ["candidate", "blank", "null", "special", "unresolved"],
            "supersedes": [],
            "supersession_evidence": {},
        }
    ]
    sources = []
    for name, rows in data.items():
        path = directory / f"{name}.jsonl"
        path.write_bytes(b"".join(canonical(r) + b"\n" for r in rows))
        sources.append(
            {
                "path": path.name,
                "sha256": hash_file(path)[0],
                "table": name,
                "format": "jsonl",
                "encoding": "utf-8",
                "official_url": "fixture://SYNTHETIC/" + name,
                "observed_at": SYNTHETIC_AT,
                "schema_evidence": ["synthetic normalized contract; no verified official BU"],
            }
        )
    return write_json(
        directory / "bundle.json",
        {
            "adapter": "electoral-normalized-v1",
            "verification_status": "normalized_only",
            "sources": sources,
        },
    )


def analysis_config(parent: Path, directory: Path) -> tuple[Path, Path, list[Path]]:
    """Persist partitions then a complete registered null result, without fitting."""
    from election_audit.analysis import publish_analysis
    from election_audit.release_tools import query_release

    directory = Path(directory)
    specification = {
        "version": "audit-analysis-v1",
        "cutoff_at": SYNTHETIC_AT,
        "partition": {
            "version": "location-partition-v1",
            "seed": "SYNTHETIC-demo-v1",
            "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
            "links": [],
            "municipal_holdout": [],
        },
        "records": [],
    }
    first_config = write_json(directory / "partition.json", specification)
    first = publish_analysis(parent, first_config, directory.parent / "warehouse")
    partition = query_release(first, "SELECT partition_id FROM partition_plan")["rows"][0][0]
    snapshot = query_release(first, "SELECT snapshot_id FROM snapshot LIMIT 1")["rows"][0][0]
    case = {
        "outcome": "turnout",
        "subgroup": "all",
        "window": "election_day",
        "scale": "location",
        "model_variant": "no_first_round",
        "historical_comparison": "none",
    }

    def record(
        identifier: str,
        kind: str,
        payload: JSON,
        run: str | None = None,
        references: Iterable[str] = (),
    ) -> JSON:
        return {
            "record_id": identifier,
            "version": "analysis-ledger-v1",
            "record_kind": kind,
            "analysis_run_id": run,
            "created_at": SYNTHETIC_AT,
            "references": list(references),
            "payload": payload,
        }

    specification["records"] = [
        record(
            "demo-protocol",
            "protocol",
            {
                "state": "frozen",
                "question": "conditional_unusualness",
                "partition_id": partition,
                "family": [case],
            },
        ),
        record(
            "demo-model",
            "model_config",
            {
                "estimator": "empirical_median_MAD",
                "hyperparameters": {},
                "seed": "SYNTHETIC",
                "fitted": False,
            },
        ),
        record(
            "demo-run",
            "analysis_run",
            {
                "protocol_id": "demo-protocol",
                "snapshot_ids": [snapshot],
                "source_configuration": {"feature_version": "audit-features-v1"},
                "model_config_ids": ["demo-model"],
            },
            references=("demo-protocol", "demo-model"),
        ),
        record(
            "demo-null",
            "exploration",
            {
                **case,
                "protocol_id": "demo-protocol",
                "family_status": "frozen",
                "result": None,
                "null_result": True,
            },
            run="demo-run",
        ),
        record(
            "demo-complete",
            "analysis_snapshot",
            {
                "exploration_ids": ["demo-null"],
                "status": "complete",
                "all_explorations_recorded": True,
            },
            run="demo-run",
        ),
    ]
    final_config = write_json(directory / "ledger.json", specification)
    final = publish_analysis(first, final_config, directory.parent / "warehouse")
    return first, final, [first_config, final_config]
