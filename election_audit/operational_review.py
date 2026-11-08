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
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import IO, Any
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import sevenzip
from election_audit.elections import election_for_round
from election_audit.national import _read_json, _verify_files, _write_json
from election_audit.source_inventory import canonical, digest, hash_file
from election_audit.types import JSON, Argv, Row

type RawEvent = tuple[JSON, str, str, str, str, str]

VERSION = "real-operational-v1"
RULES = json.loads(files("election_audit").joinpath("resources/real-log-rules.json").read_text())
RULES_2022 = json.loads(
    files("election_audit").joinpath("resources/real-log-rules-2022.json").read_text()
)
RULES_BY_YEAR = {2026: RULES, 2022: RULES_2022}
# The 2026 rules predate per-year templates; their markers stay here so the reviewed
# 2026 rules file, and every binding that hashes it, is unchanged.
TEMPLATES_2026 = {
    "official_round": {
        "1": "Iniciando aplicação - ELEIÇÃO OFICIAL PRIMEIRO TURNO - 1º turno",
        "2": "Iniciando aplicação - ELEIÇÃO OFICIAL SEGUNDO TURNO - 2º turno",
    },
    "session_start": {"1": "Iniciando aplicação - 1º turno", "2": "Iniciando aplicação - 2º turno"},
    "supported_software": "Versão da aplicação: 10.23.0.0 - Praia da Barra do Cahy",
    "operator_authorized": r"Mesário [0-9]{1,32} habilitou o eleitor",
}
CONTEST = re.compile(
    r"Voto confirmado para \[(?:Presidente|Governador|Senador|Deputado Federal"
    r"|Deputado Estadual|Deputado Distrital|Vereador|Prefeito)\]"
)


def rules_for(year: int) -> JSON:
    if year not in RULES_BY_YEAR:
        raise ValueError(f"No reviewed log rules for {year!r}")
    return RULES_BY_YEAR[year]


def _markers(rules: JSON) -> tuple[dict[str, int], dict[str, int], str, re.Pattern[str] | None]:
    templates = rules.get("templates", TEMPLATES_2026)
    operator = templates["operator_authorized"]
    return (
        {message: int(turn) for turn, message in templates["official_round"].items()},
        {message: int(turn) for turn, message in templates["session_start"].items()},
        templates["supported_software"],
        re.compile(operator) if operator else None,
    )


_MARKERS = {}


class Rows:
    def __init__(self, path: str | Path) -> None:
        self.writer = pq.ParquetWriter(
            path, pa.schema([("payload", pa.string())]), compression="zstd"
        )
        self.batch, self.count = [], 0

    def append(self, row: Row) -> None:
        self.batch.append(canonical(row).decode())
        self.count += 1
        if len(self.batch) >= 2048:
            self.flush()

    def flush(self) -> None:
        if self.batch:
            self.writer.write_table(pa.table({"payload": self.batch}))
            self.batch.clear()

    def close(self) -> None:
        self.flush()
        self.writer.close()


# Session rules shared by the event-level adapter and the streaming semantic pass.
# sessions-v2 (Phase 20b, 7 November 2026):
# - a GAP restart line that names the round already in effect ("Iniciando aplicação -
#   1º turno" in 2026) keeps that round's context: after a mid-day restart the urn does
#   not repeat the official-round marker, so a reset there dropped every later vote;
# - a session of the round's context that started before election day (an urn switched
#   on the day before and left running) becomes official at its first voting event on
#   election day, and is flagged ``started_before_election_day``.
SESSION_RULES = "sessions-v2"
PROMOTING_KINDS = frozenset(
    {
        "manual_request",
        "method_biometric",
        "authorization",
        "completion",
        "suspension_full",
        "suspension_partial",
        "resumption",
        "authorization_failed",
        "session_closing",
    }
)


def keeps_round(application: str, message: str, phase: int | None, rules: JSON = RULES) -> bool:
    """True when a GAP restart line names the round whose context is in effect."""
    if application != "GAP" or phase is None:
        return False
    markers = _MARKERS.get(rules["version"])
    if markers is None:
        markers = _MARKERS[rules["version"]] = _markers(rules)
    return markers[1].get(message) == phase


def classify(application: str, message: str, rules: JSON = RULES) -> tuple[str, Any]:
    """Full matches only; variable fields are never retained in returned semantics."""
    markers = _MARKERS.get(rules["version"])
    if markers is None:
        markers = _MARKERS[rules["version"]] = _markers(rules)
    official, starts, software, operator = markers
    if application == "GAP":
        if message in official:
            return "official_round", official[message]
        if message.startswith("Iniciando aplicação"):
            return "context_reset", None
    if application != "VOTA":
        return "other_application", None
    if message in rules["exact"]:
        return rules["exact"][message], None
    if message in starts:
        return "session_start", starts[message]
    if message == software:
        return "supported_software", None
    if operator is not None and operator.fullmatch(message):
        return "operator_authorized", None
    if CONTEST.fullmatch(message):
        return "contest_confirmation", None
    return "unknown", None


def raw_events(path: str | Path) -> Iterator[RawEvent]:
    """Read only validated log members; repeat original locators including occurrences."""
    total, members, sequence = 0, 0, 0

    def entries(handle: IO[bytes]) -> Iterator[tuple[int, str, int, Iterator[bytes]]]:
        """(index, original name, chunk iterator); 2022 logs are 7z, 2026 logs ZIP."""
        if handle.read(len(sevenzip.MAGIC)) == sevenzip.MAGIC:
            handle.seek(0)
            data = handle.read(512 * 1024**2 + 1)
            if len(data) > 512 * 1024**2:
                raise ValueError("Expanded archive bound exceeded")
            for index, (name, body, is_dir) in enumerate(sevenzip.read(data, limit=128 * 1024**2)):
                if not is_dir:
                    yield index, name, len(body), iter((body,))
            return
        handle.seek(0)
        with zipfile.ZipFile(handle) as z:
            for index, entry in enumerate(z.infolist()):
                if entry.is_dir():
                    continue
                with z.open(entry) as f:
                    yield (
                        index,
                        entry.orig_filename,
                        entry.file_size,
                        iter(lambda: f.read(65536), b""),
                    )

    def archive(handle: IO[bytes], segments: Sequence[JSON] = ()) -> Iterator[RawEvent]:
        nonlocal total, members, sequence
        if len(segments) > 4:
            raise ValueError("Nested archive bound exceeded")
        occurrences = Counter()
        for index, original, size, chunks in entries(handle):
            members += 1
            if members > 10000 or size > 128 * 1024**2:
                raise ValueError("Member bound exceeded")
            occurrence = occurrences[original]
            occurrences[original] += 1
            nested = [
                *segments,
                {
                    "member_name": original,
                    "occurrence": occurrence,
                    "member_index": index,
                },
            ]
            with tempfile.TemporaryFile() as content:
                for body in chunks:
                    total += len(body)
                    if total > 512 * 1024**2:
                        raise ValueError("Expanded archive bound exceeded")
                    content.write(body)
                content.seek(0)
                magic = content.read(4)
                content.seek(0)
                name = original.replace("\\", "/").rsplit("/", 1)[-1].lower()
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
                elif (
                    magic.startswith(b"PK")
                    or magic == sevenzip.MAGIC[:4]
                    or name.endswith((".jez", ".zip"))
                ):
                    yield from archive(content, nested)

    with Path(path).open("rb") as f:
        yield from archive(f)


def _clock(clock: JSON | None, reading: datetime, event_id: str) -> datetime | None:
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


def review_object(
    structural: str | Path,
    original: str | Path,
    output: str | Path,
    *,
    round_number: int = 2,
    clock: JSON | None = None,
    witnesses: Iterable[Row] = (),
    year: int = 2026,
) -> Path:
    """Bounded disk join against structural hashes and deterministic real semantics."""
    structural, original, output = Path(structural), Path(original), Path(output)
    document = _read_json(structural / "artifact.json")
    _verify_files(structural, document)
    if hash_file(original) != (document["object_sha256"], document["source_bytes"]):
        raise ValueError("Original source hash/size mismatch")
    e = election_for_round(round_number, year)
    rules = rules_for(year)
    key = digest(
        [VERSION, document["object_sha256"], round_number, digest(rules), clock, list(witnesses)]
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
        stream = None
        # Open session and cycle state; finish_* rebind them with nonlocal.
        session: dict[str, Any] | None = None
        pending: dict[str, Any] | None = None
        phase, phase_anchor, software = None, None, False
        fingerprint, stream_count = hashlib.sha256(), 0

        def finish_cycle(state: str, event: Row | None = None) -> None:
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

        def finish_session(reason: str) -> None:
            nonlocal session, software
            finish_cycle("unresolved")
            if session:
                session.pop("_early", None)
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

        def finish_stream() -> None:
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
            kind, value = classify(app, message, rules)
            reading = datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S")
            normalized = _clock(clock, reading, row["event_id"])
            if kind == "official_round" or (
                kind == "context_reset" and not keeps_round(app, message, phase, rules)
            ):
                finish_session("context_transition")
                phase, phase_anchor = value, row["event_id"] if kind == "official_round" else None
            on_day = reading.date().isoformat() == e.election_date
            if kind == "session_start":
                finish_session("application_restart")
                in_round = phase == value == round_number
                official = in_round and on_day
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
                    "started_before_election_day": False,
                    "_early": in_round and reading.date().isoformat() < e.election_date,
                }
            if (
                session
                and session["_early"]
                and session["session_kind"] == "unresolved"
                and on_day
                and app == "VOTA"
                and kind in PROMOTING_KINDS
            ):
                session["session_kind"] = "official_vota"
                session["started_before_election_day"] = True
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
                "rules_version": rules["version"],
                "rules_sha256": digest(rules),
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
                # A local name for the open cycle: ty does not narrow `pending`, which
                # finish_cycle() rebinds with nonlocal.
                current = pending = (
                    pending
                    if pending is not None
                    else {
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
                )
                current["method"] = "biometric"
            elif kind == "authorization":
                if pending and pending["authorized"]:
                    finish_cycle("unresolved")
                current = pending = (
                    pending
                    if pending is not None
                    else {
                        "session_id": session["session_id"],
                        "method": "unknown",
                        "manual_request": False,
                        "operator": False,
                        "interrupted": False,
                        "unknown": False,
                    }
                )
                current.update(start_id=row["event_id"], start_clock=normalized, authorized=True)
                if current["manual_request"] and current["operator"]:
                    current["method"] = "manual"
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
            "rules_sha256": digest(rules),
            "source_guide": rules["source_url"],
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


def review_national(
    store: str | Path,
    output: str | Path,
    *,
    round_number: int = 2,
    max_objects: int | None = None,
    clock_evidence: JSON | None = None,
) -> JSON:
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


def operational_review_main(argv: Argv = None) -> int:
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
