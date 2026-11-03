"""Stream real operational evidence from frozen national structural objects.

Semantic observations are distinct from completeness, clock and BU reconciliation.
No raw messages, voter identifiers, authenticators or candidate choices are emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.elections import election_for_round
from election_audit.national import _read_json, _verify_files, _write_json
from election_audit.source_inventory import canonical, digest, hash_file

VERSION = "real-operational-v1"
RULES = json.loads(files("election_audit").joinpath("resources/real-log-rules.json").read_text())


class Rows:
    def __init__(self, path):
        self.writer = pq.ParquetWriter(
            path, pa.schema([("payload", pa.string())]), compression="zstd"
        )
        self.batch, self.count = [], 0

    def append(self, row):
        self.batch.append(canonical(row).decode())
        self.count += 1
        if len(self.batch) >= 2048:
            self.flush()

    def flush(self):
        if self.batch:
            self.writer.write_table(pa.table({"payload": self.batch}))
            self.batch.clear()

    def close(self):
        self.flush()
        self.writer.close()


def classify(application, message):
    """Full matches only; variable fields are never retained in returned semantics."""
    if application == "GAP":
        for turn, label in ((1, "PRIMEIRO"), (2, "SEGUNDO")):
            if message == f"Iniciando aplicação - ELEIÇÃO OFICIAL {label} TURNO - {turn}º turno":
                return "official_round", turn
        if message.startswith("Iniciando aplicação"):
            return "context_reset", None
    if application != "VOTA":
        return "other_application", None
    if message in RULES["exact"]:
        return RULES["exact"][message], None
    if message in ("Iniciando aplicação - 1º turno", "Iniciando aplicação - 2º turno"):
        return "session_start", int(message[-8])
    if message == "Versão da aplicação: 10.23.0.0 - Praia da Barra do Cahy":
        return "supported_software", None
    if re.fullmatch(r"Mesário [0-9]{1,32} habilitou o eleitor", message):
        return "operator_authorized", None
    if re.fullmatch(
        r"Voto confirmado para \[(?:Presidente|Governador|Senador|Deputado Federal|Deputado Estadual|Deputado Distrital|Vereador|Prefeito)\]",
        message,
    ):
        return "contest_confirmation", None
    return "unknown", None


def raw_events(path):
    """Read only validated log members; repeat original locators including occurrences."""
    total, members, sequence = 0, 0, 0

    def archive(handle, segments=()):
        nonlocal total, members, sequence
        if len(segments) > 4:
            raise ValueError("Nested archive bound exceeded")
        with zipfile.ZipFile(handle) as z:
            occurrences = Counter()
            for index, entry in enumerate(z.infolist()):
                if entry.is_dir():
                    continue
                members += 1
                if members > 10000 or entry.file_size > 128 * 1024**2:
                    raise ValueError("Member bound exceeded")
                occurrence = occurrences[entry.orig_filename]
                occurrences[entry.orig_filename] += 1
                nested = [
                    *segments,
                    {
                        "member_name": entry.orig_filename,
                        "occurrence": occurrence,
                        "member_index": index,
                    },
                ]
                with tempfile.TemporaryFile() as content:
                    with z.open(entry) as f:
                        while body := f.read(65536):
                            total += len(body)
                            if total > 512 * 1024**2:
                                raise ValueError("Expanded archive bound exceeded")
                            content.write(body)
                    content.seek(0)
                    magic = content.read(4)
                    content.seek(0)
                    name = entry.orig_filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
                    if name == "logd.dat":
                        for number, line in enumerate(content, 1):
                            sequence += 1
                            if len(line) > 65536 or sequence > 2000000:
                                raise ValueError("Line bound exceeded")
                            fields = line.decode("latin-1").rstrip("\r\n").split("\t")
                            if len(fields) != 6:
                                continue
                            timestamp, _level, device, application, message, _token = fields
                            try:
                                datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S")
                            except ValueError:
                                continue
                            locator = {
                                "archive_segments": nested,
                                "line_start": number,
                                "line_end": number,
                                "byte_start": None,
                                "byte_end": None,
                            }
                            yield (
                                locator,
                                hashlib.sha256(line).hexdigest(),
                                timestamp,
                                device,
                                application,
                                message,
                            )
                    elif magic.startswith(b"PK") or name.endswith((".jez", ".zip")):
                        yield from archive(content, nested)

    with Path(path).open("rb") as f:
        yield from archive(f)


def _clock(clock, reading, event_id):
    if not clock or event_id not in clock["evidence"]["event_ids"]:
        return None
    if set(clock) != {"timezone", "adjustment_seconds", "continuity", "evidence"}:
        raise ValueError("Clock needs explicit timezone/adjustment/continuity/evidence")
    if clock["continuity"] is not True or not clock["evidence"]:
        return None
    zone = ZoneInfo(clock["timezone"])
    local = reading + timedelta(seconds=clock["adjustment_seconds"])
    first, second = local.replace(tzinfo=zone, fold=0), local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    return first


def review_object(structural, original, output, *, round_number=2, clock=None, witnesses=()):
    """Bounded disk join against structural hashes and deterministic real semantics."""
    structural, original, output = Path(structural), Path(original), Path(output)
    document = _read_json(structural / "artifact.json")
    _verify_files(structural, document)
    if hash_file(original) != (document["object_sha256"], document["source_bytes"]):
        raise ValueError("Original source hash/size mismatch")
    e = election_for_round(round_number)
    key = digest(
        [VERSION, document["object_sha256"], round_number, digest(RULES), clock, list(witnesses)]
    )
    target = output / key
    if target.exists():
        result = _read_json(target / "artifact.json")
        _verify_files(target, result)
        return target
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".operational-", dir=output))
    writers = {
        name: Rows(staging / (name + ".parquet")) for name in ("events", "cycles", "sessions")
    }
    db = sqlite3.connect(staging / "review.sqlite")
    db.execute("CREATE TABLE structural(locator TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    db.execute(
        "CREATE TABLE stream_fingerprint(stream TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,events INTEGER NOT NULL)"
    )
    db.execute(
        "CREATE TABLE copy_candidate(left_stream TEXT,right_stream TEXT,fingerprint TEXT,PRIMARY KEY(left_stream,right_stream))"
    )
    counts = Counter()
    try:
        for batch in pq.ParquetFile(structural / "events.parquet").iter_batches(batch_size=2048):
            for encoded in batch.column(0).to_pylist():
                row = json.loads(encoded)
                db.execute(
                    "INSERT INTO structural VALUES (?,?)",
                    (canonical(row["record_locator"]).decode(), encoded),
                )
        if clock:
            evidence = clock.get("evidence", {})
            if (
                set(evidence) != {"review_state", "rule_id", "event_ids", "anchors"}
                or evidence["review_state"] != "reviewed"
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", evidence["rule_id"])
            ):
                raise ValueError("Clock requires reviewed rule and exact event/hash anchors")
            if not evidence["event_ids"] or len(set(evidence["event_ids"])) != len(
                evidence["event_ids"]
            ):
                raise ValueError("Clock interval requires unique exact events")
            clock_rows = []
            for event_id in evidence["event_ids"]:
                found = db.execute(
                    "SELECT payload FROM structural WHERE json_extract(payload,'$.event_id')=?",
                    (event_id,),
                ).fetchone()
                if not found:
                    raise ValueError("Clock references unknown event")
                clock_rows.append(json.loads(found[0]))
            streams = {
                canonical([r["record_locator"]["archive_segments"], r["device_id_raw"]])
                for r in clock_rows
            }
            lines = [r["record_locator"]["line_start"] for r in clock_rows]
            if len(streams) != 1 or lines != list(range(lines[0], lines[0] + len(lines))):
                raise ValueError("Clock interval must preserve consecutive source lines")
            indexed = {r["event_id"]: r["source_line_sha256"] for r in clock_rows}
            if not evidence["anchors"] or any(
                set(a) != {"event_id", "source_line_sha256"}
                or indexed.get(a["event_id"]) != a["source_line_sha256"]
                for a in evidence["anchors"]
            ):
                raise ValueError("Clock anchor mismatch")
        stream, session, pending = None, None, None
        phase, phase_anchor, software = None, None, False
        fingerprint, stream_count = hashlib.sha256(), 0

        def finish_cycle(state, event=None):
            nonlocal pending
            if pending is None:
                if state == "completed":
                    counts["orphan_completions"] += 1
                return
            duration = None
            if (
                state == "completed"
                and not pending["interrupted"]
                and not pending["unknown"]
                and pending["start_clock"]
                and event
                and event["clock"]
            ):
                seconds = (event["clock"] - pending["start_clock"]).total_seconds()
                duration = seconds if seconds >= 0 else None
            end = event["row"]["event_id"] if event else None
            result = {
                "cycle_id": digest([key, pending["start_id"], end, state]),
                "session_id": pending["session_id"],
                "round": round_number,
                "completion_state": state,
                "authorization_method": pending["method"],
                "interrupted": pending["interrupted"],
                "duration_seconds": duration,
                "duration_readiness": "ready"
                if duration is not None
                else "unavailable_clock_or_transition",
                "start_event_id": pending["start_id"],
                "end_event_id": end,
                "candidate_attribution": "unavailable_anonymous_cycle",
            }
            writers["cycles"].append(result)
            counts["cycles_" + state] += 1
            if session:
                session["cycles_" + state] = session.get("cycles_" + state, 0) + 1
            pending = None

        def finish_session(reason):
            nonlocal session, software
            finish_cycle("unresolved")
            if session:
                session["end_reason"] = reason
                session["count_readiness"] = (
                    "observed_official_cycles_not_attendance_reconciled"
                    if session["session_kind"] == "official_vota"
                    else "unavailable_context"
                )
                session["exposure_seconds"] = None
                session["exposure_readiness"] = (
                    "unavailable_unique_opening_closing_and_interruptions_required"
                )
                writers["sessions"].append(session)
                counts["sessions_" + session["session_kind"]] += 1
            session, software = None, False

        def finish_stream():
            if stream is not None:
                finish_session("stream_end")
                db.execute(
                    "INSERT INTO stream_fingerprint VALUES (?,?,?)",
                    (stream, fingerprint.hexdigest(), stream_count),
                )

        for locator, line_hash, timestamp, device, app, message in raw_events(original):
            found = db.execute(
                "SELECT payload FROM structural WHERE locator=?", (canonical(locator).decode(),)
            ).fetchone()
            if not found:
                continue
            row = json.loads(found[0])
            if row["source_line_sha256"] != line_hash:
                raise ValueError("Structural/original line mismatch")
            current = canonical([locator["archive_segments"], device]).decode()
            if current != stream:
                finish_stream()
                stream, phase, phase_anchor = current, None, None
                fingerprint, stream_count = hashlib.sha256(), 0
            fingerprint.update(bytes.fromhex(line_hash))
            stream_count += 1
            kind, value = classify(app, message)
            reading = datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S")
            normalized = _clock(clock, reading, row["event_id"])
            if kind in ("official_round", "context_reset"):
                finish_session("context_transition")
                phase, phase_anchor = value, row["event_id"] if kind == "official_round" else None
            if kind == "session_start":
                finish_session("application_restart")
                official = (
                    phase == value == round_number and reading.date().isoformat() == e.election_date
                )
                session = {
                    "session_id": digest([key, row["event_id"]]),
                    "round": round_number,
                    "object_sha256": document["object_sha256"],
                    "session_kind": "official_vota" if official else "unresolved",
                    "phase_anchor": phase_anchor,
                    "start_event_id": row["event_id"],
                    "closing_event_id": None,
                    "software_supported": False,
                    "witnesses": list(witnesses),
                    "clock_readiness": "reviewed_rule" if normalized else "unavailable",
                }
            if kind == "supported_software" and session:
                software, session["software_supported"] = True, True
            active = (
                session
                and session["session_kind"] == "official_vota"
                and software
                and reading.date().isoformat() == e.election_date
                and app == "VOTA"
            )
            safe = {
                **row,
                "real_kind": kind,
                "rules_version": RULES["version"],
                "rules_sha256": digest(RULES),
                "session_id": session["session_id"] if session else None,
                "selection_state": "official_anchored" if active else "unresolved_or_other_context",
                "normalized_at": normalized.isoformat() if normalized else None,
            }
            writers["events"].append(safe)
            counts["events_" + kind] += 1
            if not active:
                continue
            event = {"row": row, "clock": normalized}
            if kind == "manual_request":
                counts["manual_requests"] += 1
                if pending:
                    finish_cycle("unresolved")
                pending = {
                    "session_id": session["session_id"],
                    "start_id": row["event_id"],
                    "start_clock": None,
                    "method": "unknown",
                    "manual_request": True,
                    "operator": False,
                    "authorized": False,
                    "interrupted": False,
                    "unknown": False,
                }
            elif kind == "operator_authorized" and pending and pending["manual_request"]:
                pending["operator"] = True
            elif kind == "method_biometric":
                if pending is None:
                    pending = {
                        "session_id": session["session_id"],
                        "start_id": row["event_id"],
                        "start_clock": None,
                        "method": "biometric",
                        "manual_request": False,
                        "operator": False,
                        "authorized": False,
                        "interrupted": False,
                        "unknown": False,
                    }
                pending["method"] = "biometric"
            elif kind == "authorization":
                if pending and pending["authorized"]:
                    finish_cycle("unresolved")
                if pending is None:
                    pending = {
                        "session_id": session["session_id"],
                        "method": "unknown",
                        "manual_request": False,
                        "operator": False,
                        "interrupted": False,
                        "unknown": False,
                    }
                pending.update(start_id=row["event_id"], start_clock=normalized, authorized=True)
                if pending["manual_request"] and pending["operator"]:
                    pending["method"] = "manual"
            elif kind == "completion":
                if pending and pending["authorized"]:
                    finish_cycle("completed", event)
                else:
                    counts["orphan_completions"] += 1
            elif kind == "suspension_full":
                finish_cycle("suspended", event)
            elif kind in ("suspension_partial", "resumption") and pending:
                pending["interrupted"] = True
            elif kind == "authorization_failed":
                finish_cycle("cancelled", event)
            elif kind == "session_closing":
                session["closing_event_id"] = row["event_id"]
                finish_cycle("unresolved", event)
            elif kind == "application_exit":
                finish_session("application_exit")
            elif kind == "unknown" and pending:
                pending["unknown"] = True
        finish_stream()
        db.execute(
            "INSERT INTO copy_candidate SELECT a.stream,b.stream,a.fingerprint FROM stream_fingerprint a JOIN stream_fingerprint b ON a.fingerprint=b.fingerprint AND a.events=b.events WHERE a.stream<b.stream AND a.events>=2"
        )
        duplicate_count = db.execute("SELECT count(*) FROM copy_candidate").fetchone()[0]
        db.commit()
        for writer in writers.values():
            writer.close()
        db.close()
        specs = {
            name: dict(zip(("sha256", "bytes"), hash_file(staging / name), strict=True))
            for name in ("events.parquet", "cycles.parquet", "sessions.parquet", "review.sqlite")
        }
        result = {
            "version": VERSION,
            "round": round_number,
            "object_sha256": document["object_sha256"],
            "rules_sha256": digest(RULES),
            "source_guide": RULES["source_url"],
            "counts": dict(counts),
            "files": specs,
            "copy_candidates": duplicate_count,
            "eligibility": "observed_cycles_only; BU attendance and cross-object history reconciliation required",
            "clock_rule": clock,
            "candidate_attribution": "unavailable",
            "cross_object_overlap": "requires_group_review",
        }
        _write_json(staging / "artifact.json", result)
        staging.rename(target)
        return target
    except BaseException:
        db.close()
        for writer in writers.values():
            try:
                writer.close()
            except Exception:
                pass
        shutil.rmtree(staging, ignore_errors=True)
        raise


def review_national(store, output, *, round_number=2, max_objects=None, clock_evidence=None):
    """Review bounded structural groups; disk census preserves every publisher witness."""
    store, output = Path(store), Path(output)
    clock_evidence = clock_evidence or {}
    processed, examples = 0, []
    output.mkdir(parents=True, exist_ok=True)
    index = sqlite3.connect(output / "review-index.sqlite")
    index.execute(
        "CREATE TABLE IF NOT EXISTS stream(object_sha256 TEXT, stream TEXT, fingerprint TEXT, events INTEGER, PRIMARY KEY(object_sha256,stream))"
    )
    index.execute("CREATE INDEX IF NOT EXISTS fingerprint_index ON stream(fingerprint,events)")
    for artifact in sorted((store / "structural").glob("*/*/artifact.json")):
        if max_objects is not None and processed >= max_objects:
            break
        doc = _read_json(artifact)
        sha = doc["object_sha256"]
        witnesses = []
        for census in (store / "censuses").glob("*/census.sqlite"):
            with sqlite3.connect(census.resolve().as_uri() + "?mode=ro", uri=True) as db:
                for uf, url in db.execute(
                    "SELECT uf,url FROM file_observation WHERE round=? AND sha256=?",
                    (round_number, sha),
                ):
                    witnesses.append({"uf": uf, "url": url, "census_id": census.parent.name})
        if not witnesses:
            continue
        original = store / "objects" / sha[:2] / sha
        result = review_object(
            artifact.parent,
            original,
            output,
            round_number=round_number,
            clock=clock_evidence.get(sha),
            witnesses=witnesses,
        )
        with sqlite3.connect(result / "review.sqlite") as source_index:
            for stream, fingerprint, events in source_index.execute(
                "SELECT stream,fingerprint,events FROM stream_fingerprint"
            ):
                index.execute(
                    "INSERT OR REPLACE INTO stream VALUES (?,?,?,?)",
                    (sha, stream, fingerprint, events),
                )
        index.commit()
        processed += 1
        if len(examples) < 20:
            examples.append(str(result))
    cross_copies = index.execute(
        "SELECT count(*) FROM stream a JOIN stream b ON a.fingerprint=b.fingerprint AND a.events=b.events WHERE a.object_sha256<b.object_sha256 AND a.events>=2"
    ).fetchone()[0]
    index.close()
    return {
        "version": VERSION,
        "processed_objects": processed,
        "example_artifacts": examples,
        "cross_object_copy_candidates": cross_copies,
        "national_complete": False,
        "remaining": [
            "BU attendance reconciliation",
            "cross-object copy/replacement grouping",
            "reviewed clocks where absent",
        ],
    }


def operational_review_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--round", type=int, choices=(1, 2), default=2)
    parser.add_argument("--max-objects", type=int)
    parser.add_argument("--clock-evidence", type=Path)
    args = parser.parse_args(argv)
    if args.max_objects is not None and args.max_objects < 1:
        parser.error("max-objects must be positive")
    clocks = json.loads(args.clock_evidence.read_text()) if args.clock_evidence else None
    print(
        json.dumps(
            review_national(
                args.store,
                args.output,
                round_number=args.round,
                max_objects=args.max_objects,
                clock_evidence=clocks,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(operational_review_main())
