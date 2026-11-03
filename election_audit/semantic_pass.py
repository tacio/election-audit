"""Phase 21 streaming semantic pass: per-session aggregates straight from raw logs.

The pass reads each certified log object once from a staged root, applies the
reviewed message rules of ``operational_review`` (``real-operational-v1``) with the
same session and anonymous vote-cycle state machine, and keeps only aggregates:

- one row per session (cycle counts by state and authorization method,
  interruptions, manual requests, reading-hour histogram, completion cadence,
  backward clock steps, first/last readings);
- one row per stream context segment (line count and byte fingerprint, used to
  compare first-round blocks embedded in runoff logs with first-round logs);
- a digit-masked message-template vocabulary;
- one row per object with status, counts and section witnesses.

Readings are local urn clock readings, never normalized times. Voter, poll-worker
and authenticator values are not exported: the sixth (token) field is dropped and
every digit run in a vocabulary template is masked. Protected/stress sections stay
unread. ``equivalence`` re-runs the event-level adapter on a sample and compares
the two session by session before any national run.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import multiprocessing
import os
import random
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.operational_review import RULES, classify

VERSION = "session-aggregates-v1"
ADAPTER_VERSION = "real-operational-v1"
SHARD_OBJECTS = 500
VOCABULARY_LIMIT = 4000
MAX_DEPTH, MAX_MEMBERS, MAX_MEMBER, MAX_EXPANDED = 4, 10000, 128 * 1024**2, 512 * 1024**2
MAX_LINE, MAX_LINES = 65536, 2000000
URL = re.compile(r"/arquivo-urna/(\d+)/dados/([a-z]{2})/(\d+)/(\d+)/(\d+)/")
DIGITS = re.compile(r"[0-9]+")
HEXRUN = re.compile(r"\b[0-9A-Fa-f]{12,}\b")
CYCLE_STATES = ("completed", "suspended", "cancelled", "unresolved")
METHODS = ("biometric", "manual", "unknown")

SESSION_SCHEMA = pa.schema(
    [
        ("object_sha256", pa.string()),
        ("session_ordinal", pa.int32()),
        ("stream_ordinal", pa.int32()),
        ("member_path", pa.string()),
        ("device_id", pa.string()),
        ("session_kind", pa.string()),
        ("session_round", pa.int8()),
        ("phase", pa.int8()),
        ("software_supported", pa.bool_()),
        ("end_reason", pa.string()),
        ("start_reading", pa.string()),
        ("end_reading", pa.string()),
        ("closing_reading", pa.string()),
        ("events", pa.int64()),
        ("active_events", pa.int64()),
        ("active_unknown_events", pa.int64()),
        *[(f"cycles_{state}_{method}", pa.int32()) for state in CYCLE_STATES for method in METHODS],
        ("completed_interrupted", pa.int32()),
        ("manual_requests", pa.int32()),
        ("suspensions_partial", pa.int32()),
        ("resumptions", pa.int32()),
        ("authorization_failures", pa.int32()),
        ("orphan_completions", pa.int32()),
        ("first_completion_reading", pa.string()),
        ("last_completion_reading", pa.string()),
        ("completions_by_reading_hour", pa.list_(pa.int32())),
        ("completion_gaps", pa.int32()),
        ("completion_gap_min_s", pa.int32()),
        ("completion_gap_median_s", pa.float32()),
        ("completion_gap_p90_s", pa.int32()),
        ("completion_gap_max_s", pa.int32()),
        ("reading_backsteps", pa.int32()),
        ("reading_backstep_max_s", pa.int32()),
    ]
)
SEGMENT_SCHEMA = pa.schema(
    [
        ("object_sha256", pa.string()),
        ("stream_ordinal", pa.int32()),
        ("segment_ordinal", pa.int32()),
        ("member_path", pa.string()),
        ("device_id", pa.string()),
        ("context", pa.string()),
        ("lines", pa.int64()),
        ("fingerprint", pa.string()),
        ("first_line_sha256", pa.string()),
        ("last_line_sha256", pa.string()),
        ("first_reading", pa.string()),
        ("last_reading", pa.string()),
    ]
)
OBJECT_SCHEMA = pa.schema(
    [
        ("object_sha256", pa.string()),
        ("path", pa.string()),
        ("status", pa.string()),
        ("error", pa.string()),
        ("witnesses_json", pa.string()),
        ("package_status", pa.string()),
        ("lines", pa.int64()),
        ("events", pa.int64()),
        ("malformed_lines", pa.int64()),
        ("log_members", pa.int32()),
        ("streams", pa.int32()),
        ("sessions", pa.int32()),
        ("official_sessions", pa.int32()),
        ("kind_counts_json", pa.string()),
        ("vocabulary_overflow", pa.int64()),
    ]
)


# --------------------------------------------------------------------------- reading


_DATES = {}


def reading_seconds(timestamp):
    """Seconds since 0001-01-01 for a ``dd/mm/YYYY HH:MM:SS`` reading, or None."""
    if len(timestamp) != 19 or timestamp[2] != "/" or timestamp[5] != "/":
        return None
    day = timestamp[:10]
    base = _DATES.get(day, False)
    if base is False:
        try:
            base = date(int(day[6:10]), int(day[3:5]), int(day[0:2])).toordinal() * 86400
        except ValueError:
            base = None
        if len(_DATES) < 100000:
            _DATES[day] = base
    if base is None or timestamp[10] != " " or timestamp[13] != ":" or timestamp[16] != ":":
        return None
    parts = timestamp[11:13], timestamp[14:16], timestamp[17:19]
    if not all(part.isascii() and part.isdigit() for part in parts):
        return None
    hour, minute, second = (int(part) for part in parts)
    if hour > 23 or minute > 59 or second > 61:
        return None
    return base + hour * 3600 + minute * 60 + second


def iso_reading(seconds):
    if seconds is None:
        return None
    day, rest = divmod(seconds, 86400)
    if rest >= 86400:
        return None
    hour, rest = divmod(rest, 3600)
    minute, second = divmod(rest, 60)
    return f"{date.fromordinal(day).isoformat()}T{hour:02d}:{minute:02d}:{second:02d}"


def log_members(path):
    """Yield (segments, member path, line iterator) for every bounded logd.dat member."""
    totals = {"members": 0, "expanded": 0, "lines": 0}

    def archive(handle, segments):
        if len(segments) > MAX_DEPTH:
            raise ValueError("Nested archive bound exceeded")
        with zipfile.ZipFile(handle) as z:
            occurrences = Counter()
            for index, entry in enumerate(z.infolist()):
                if entry.is_dir():
                    continue
                totals["members"] += 1
                if totals["members"] > MAX_MEMBERS or entry.file_size > MAX_MEMBER:
                    raise ValueError("Member bound exceeded")
                occurrence = occurrences[entry.orig_filename]
                occurrences[entry.orig_filename] += 1
                nested = (*segments, (entry.orig_filename, occurrence, index))
                with z.open(entry) as f:
                    body = f.read(MAX_MEMBER + 1)
                totals["expanded"] += len(body)
                if len(body) > MAX_MEMBER or totals["expanded"] > MAX_EXPANDED:
                    raise ValueError("Expanded archive bound exceeded")
                name = entry.orig_filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if name == "logd.dat":
                    yield nested, body
                elif body[:2] == b"PK" or name.endswith((".jez", ".zip")):
                    yield from archive(io.BytesIO(body), nested)

    with Path(path).open("rb") as f:
        yield from archive(f, ())


def member_path(segments):
    return "/".join(f"{name}#{occurrence}" for name, occurrence, _ in segments)


# --------------------------------------------------------------------------- state


def _gap_stats(gaps):
    if not gaps:
        return 0, None, None, None, None
    gaps = sorted(gaps)
    n = len(gaps)
    median = (gaps[(n - 1) // 2] + gaps[n // 2]) / 2
    p90 = gaps[min(n - 1, int(0.9 * (n - 1) + 0.5))]
    return n, gaps[0], median, p90, gaps[-1]


class ObjectSummary:
    """Mirror of ``operational_review.review_object``'s session/cycle machine."""

    def __init__(self, object_sha256, round_number):
        self.sha = object_sha256
        self.round = round_number
        self.election_day = date.fromisoformat(election_for_round(round_number).election_date)
        self.election_seconds = self.election_day.toordinal() * 86400
        self.sessions, self.segments = [], []
        self.kinds, self.vocabulary = Counter(), Counter()
        self.vocabulary_overflow = 0
        self.lines = self.events = self.malformed = self.members = 0
        self.orphans_without_session = 0
        self.stream_ordinal = -1
        self.stream = self.session = self.pending = self.segment = None
        self.phase = None
        self.software = False
        self._templates, self._classes = {}, {}

    # ---- vocabulary and classification caches
    def _template(self, application, message):
        key = (application, message)
        found = self._templates.get(key)
        if found is None:
            found = (application, HEXRUN.sub("<hex>", DIGITS.sub("#", message))[:200])
            if len(self._templates) < 200000:
                self._templates[key] = found
        return found

    def _classify(self, application, message):
        key = (application, message)
        found = self._classes.get(key)
        if found is None:
            found = classify(application, message)
            if len(self._classes) < 200000:
                self._classes[key] = found
        return found

    # ---- segments (context blocks inside one stream)
    def _open_segment(self, context, device, path):
        self._close_segment()
        self.segment = {
            "object_sha256": self.sha,
            "stream_ordinal": self.stream_ordinal,
            "segment_ordinal": self._segment_ordinal,
            "member_path": path,
            "device_id": device,
            "context": context,
            "lines": 0,
            "hash": hashlib.sha256(),
            "first_line_sha256": None,
            "last_line_sha256": None,
            "first_reading": None,
            "last_reading": None,
        }
        self._segment_ordinal += 1

    def _close_segment(self):
        if self.segment is not None:
            row = self.segment
            row["fingerprint"] = row.pop("hash").hexdigest()
            self.segments.append(row)
            self.segment = None

    # ---- sessions and cycles
    def _finish_cycle(self, state):
        pending = self.pending
        if pending is None:
            if state == "completed" and self.session is not None:
                self.session["orphan_completions"] += 1
            elif state == "completed":
                self.orphans_without_session += 1
            return
        session = pending["session"]
        session[f"cycles_{state}_{pending['method']}"] += 1
        if state == "completed" and pending["interrupted"]:
            session["completed_interrupted"] += 1
        self.pending = None

    def _finish_session(self, reason):
        self._finish_cycle("unresolved")
        session = self.session
        if session is not None:
            session["end_reason"] = reason
            completions = session.pop("_completions")
            gaps, backsteps = [], []
            for earlier, later in zip(completions, completions[1:]):
                (gaps if later >= earlier else backsteps).append(later - earlier)
            n, low, median, p90, high = _gap_stats(gaps)
            session.update(
                completion_gaps=n,
                completion_gap_min_s=low,
                completion_gap_median_s=median,
                completion_gap_p90_s=p90,
                completion_gap_max_s=high,
                first_completion_reading=iso_reading(completions[0]) if completions else None,
                last_completion_reading=iso_reading(completions[-1]) if completions else None,
            )
            for key in ("start_reading", "end_reading", "closing_reading"):
                session[key] = iso_reading(session[key])
            self.sessions.append(session)
        self.session, self.software = None, False

    def _new_stream(self, key, device, path):
        if self.stream is not None:
            self._finish_session("stream_end")
        self._close_segment()
        self.stream, self.phase = key, None
        self.stream_ordinal += 1
        self._segment_ordinal = 0
        self._last_reading = None
        self._open_segment("initial", device, path)

    def feed(self, segments, body):
        """Process one logd.dat member body."""
        self.members += 1
        path = member_path(segments)
        # Split on LF only, exactly like iterating the member file in the adapter.
        lines = body.split(b"\n")
        last = lines.pop()
        for line in [x + b"\n" for x in lines] + ([last] if last else []):
            self.lines += 1
            if len(line) > MAX_LINE or self.lines > MAX_LINES:
                raise ValueError("Line bound exceeded")
            fields = line.decode("latin-1").rstrip("\r\n").split("\t")
            if len(fields) != 6:
                self.malformed += 1
                continue
            timestamp, _level, device, application, message, _token = fields
            reading = reading_seconds(timestamp)
            if reading is None:
                self.malformed += 1
                continue
            self._event(path, segments, line, reading, device, application, message)

    def _event(self, path, segments, line, reading, device, application, message):
        self.events += 1
        key = (segments, device)
        if key != self.stream:
            self._new_stream(key, device, path)
        kind, value = self._classify(application, message)
        self.kinds[kind] += 1
        template = self._template(application, message)
        if template in self.vocabulary or len(self.vocabulary) < VOCABULARY_LIMIT:
            self.vocabulary[template] += 1
        else:
            self.vocabulary_overflow += 1
        if kind in ("official_round", "context_reset"):
            self._finish_session("context_transition")
            self.phase = value
            self._open_segment(
                f"official_round_{value}" if kind == "official_round" else "other_context",
                device,
                path,
            )
        segment = self.segment
        line_sha = hashlib.sha256(line).hexdigest()
        segment["hash"].update(line)
        segment["lines"] += 1
        if segment["first_line_sha256"] is None:
            segment["first_line_sha256"] = line_sha
            segment["first_reading"] = iso_reading(reading)
        segment["last_line_sha256"] = line_sha
        segment["last_reading"] = iso_reading(reading)
        on_day = self.election_seconds <= reading < self.election_seconds + 86400
        if kind == "session_start":
            self._finish_session("application_restart")
            official = self.phase == value == self.round and on_day
            self.session = {
                "object_sha256": self.sha,
                "session_ordinal": len(self.sessions),
                "stream_ordinal": self.stream_ordinal,
                "member_path": path,
                "device_id": device,
                "session_kind": "official_vota" if official else "unresolved",
                "session_round": value,
                "phase": self.phase,
                "software_supported": False,
                "end_reason": None,
                "start_reading": reading,
                "end_reading": reading,
                "closing_reading": None,
                "events": 0,
                "active_events": 0,
                "active_unknown_events": 0,
                **{f"cycles_{s}_{m}": 0 for s in CYCLE_STATES for m in METHODS},
                "completed_interrupted": 0,
                "manual_requests": 0,
                "suspensions_partial": 0,
                "resumptions": 0,
                "authorization_failures": 0,
                "orphan_completions": 0,
                "completions_by_reading_hour": [0] * 24,
                "reading_backsteps": 0,
                "reading_backstep_max_s": None,
                "_completions": [],
            }
            self._last_reading = None
        session = self.session
        if session is not None:
            session["events"] += 1
            session["end_reading"] = reading
            if self._last_reading is not None and reading < self._last_reading:
                step = self._last_reading - reading
                session["reading_backsteps"] += 1
                session["reading_backstep_max_s"] = max(
                    step, session["reading_backstep_max_s"] or 0
                )
            self._last_reading = reading
        if kind == "supported_software" and session is not None:
            self.software, session["software_supported"] = True, True
        active = (
            session is not None
            and session["session_kind"] == "official_vota"
            and self.software
            and on_day
            and application == "VOTA"
        )
        if not active:
            return
        session["active_events"] += 1
        pending = self.pending
        if kind == "manual_request":
            session["manual_requests"] += 1
            if pending:
                self._finish_cycle("unresolved")
            self.pending = {
                "session": session,
                "method": "unknown",
                "manual_request": True,
                "operator": False,
                "authorized": False,
                "interrupted": False,
            }
        elif kind == "operator_authorized" and pending and pending["manual_request"]:
            pending["operator"] = True
        elif kind == "method_biometric":
            if pending is None:
                self.pending = pending = {
                    "session": session,
                    "method": "biometric",
                    "manual_request": False,
                    "operator": False,
                    "authorized": False,
                    "interrupted": False,
                }
            pending["method"] = "biometric"
        elif kind == "authorization":
            if pending and pending["authorized"]:
                self._finish_cycle("unresolved")
                pending = None
            if pending is None:
                self.pending = pending = {
                    "session": session,
                    "method": "unknown",
                    "manual_request": False,
                    "operator": False,
                    "interrupted": False,
                }
            pending["authorized"] = True
            if pending["manual_request"] and pending["operator"]:
                pending["method"] = "manual"
        elif kind == "completion":
            if pending and pending["authorized"]:
                self._finish_cycle("completed")
                session["_completions"].append(reading)
                session["completions_by_reading_hour"][(reading % 86400) // 3600] += 1
            else:
                session["orphan_completions"] += 1
        elif kind == "suspension_full":
            self._finish_cycle("suspended")
        elif kind in ("suspension_partial", "resumption"):
            session["suspensions_partial" if kind == "suspension_partial" else "resumptions"] += 1
            if pending:
                pending["interrupted"] = True
        elif kind == "authorization_failed":
            session["authorization_failures"] += 1
            self._finish_cycle("cancelled")
        elif kind == "session_closing":
            session["closing_reading"] = reading
            self._finish_cycle("unresolved")
        elif kind == "application_exit":
            self._finish_session("application_exit")
        elif kind == "unknown":
            session["active_unknown_events"] += 1

    def finish(self):
        if self.stream is not None:
            self._finish_session("stream_end")
        self._close_segment()


def summarize_object(path, object_sha256, round_number):
    summary = ObjectSummary(object_sha256, round_number)
    for segments, body in log_members(path):
        summary.feed(segments, body)
    summary.finish()
    return summary


# --------------------------------------------------------------------------- work list


def load_exclusions(path):
    value = json.loads(Path(path).read_bytes())
    return {tuple(key) for key in value["section_keys"]}, sha(path)


def work_list(staged_root, round_number, *, ufs=None, exclusions=frozenset(), limit=None):
    """Distinct log objects with their section witnesses; excluded sections removed."""
    manifest = Path(staged_root) / "manifest.sqlite"
    uri = manifest.resolve().as_uri() + "?mode=ro&immutable=1"
    pleito = int(election_for_round(round_number).pleito_code)
    objects, excluded = {}, set()
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        status = dict(db.execute("SELECT url, package_status FROM logs"))
        for url, path, digest in db.execute(
            "SELECT url, path, sha256 FROM files WHERE path LIKE '%.jez' ORDER BY path, url"
        ):
            match = URL.search(url)
            if not match or int(match.group(1)) != pleito:
                raise ValueError(f"Manifest URL outside round {round_number}: {url}")
            key = match.group(2, 3, 4, 5)
            if key in exclusions:
                excluded.add(path)
            entry = objects.setdefault(
                path, {"path": path, "sha256": digest, "witnesses": [], "package": set()}
            )
            entry["witnesses"].append(list(key))
            if url in status and status[url]:
                entry["package"].add(status[url])
    items = []
    for path in sorted(objects):
        entry = objects[path]
        if path in excluded:
            continue
        if ufs and not any(w[0] in ufs for w in entry["witnesses"]):
            continue
        entry["package"] = ",".join(sorted(entry["package"])) or None
        items.append(entry)
    if limit is not None:
        items = items[:limit]
    return items, len(excluded)


# --------------------------------------------------------------------------- shards


def _write(path, rows, schema):
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")


def run_shard(task):
    staged_root, round_number, shard_dir, index, items = task
    sessions, segments, objects, vocabulary = [], [], [], Counter()
    for item in items:
        row = {
            "object_sha256": item["sha256"],
            "path": item["path"],
            "witnesses_json": json.dumps(item["witnesses"], separators=(",", ":")),
            "package_status": item["package"],
        }
        try:
            summary = summarize_object(
                Path(staged_root) / item["path"], item["sha256"], round_number
            )
        except Exception as exc:  # recorded per object; the pass continues
            row.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500])
            objects.append(row)
            continue
        sessions.extend(summary.sessions)
        segments.extend(summary.segments)
        for (application, template), count in summary.vocabulary.items():
            vocabulary[(application, template)] += count
        row.update(
            status="complete",
            error=None,
            lines=summary.lines,
            events=summary.events,
            malformed_lines=summary.malformed,
            log_members=summary.members,
            streams=summary.stream_ordinal + 1,
            sessions=len(summary.sessions),
            official_sessions=sum(s["session_kind"] == "official_vota" for s in summary.sessions),
            kind_counts_json=json.dumps(dict(sorted(summary.kinds.items())), separators=(",", ":")),
            vocabulary_overflow=summary.vocabulary_overflow,
        )
        objects.append(row)
    temporary = Path(shard_dir) / f".{index:05d}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir()
    _write(temporary / "sessions.parquet", sessions, SESSION_SCHEMA)
    _write(temporary / "segments.parquet", segments, SEGMENT_SCHEMA)
    _write(temporary / "objects.parquet", objects, OBJECT_SCHEMA)
    (temporary / "vocabulary.json").write_text(
        json.dumps(sorted([a, t, c] for (a, t), c in vocabulary.items()))
    )
    final = Path(shard_dir) / f"{index:05d}"
    os.replace(temporary, final)
    return index, len(items), sum(o["status"] == "error" for o in objects)


def _init_worker():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def run_pass(
    staged_root,
    round_number,
    output,
    *,
    exclusions_path,
    workers=4,
    ufs=None,
    limit=None,
    resume=False,
    shard_objects=SHARD_OBJECTS,
):
    staged_root = Path(staged_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if workers < 1 or workers > max(1, (os.cpu_count() or 2) // 2):
        raise ValueError("Workers must stay within half the CPUs")
    staging_certificate = json.loads((staged_root / "staging-certificate.json").read_bytes())
    if staging_certificate.get("round") != round_number:
        raise ValueError("Staged root belongs to another round")
    exclusions, exclusions_sha = load_exclusions(exclusions_path)
    binding = {
        "version": VERSION,
        "adapter_version": ADAPTER_VERSION,
        "rules_sha256": hashlib.sha256(json.dumps(RULES, sort_keys=True).encode()).hexdigest(),
        "round": round_number,
        "staged_root": str(staged_root),
        "staging_certificate_sha256": sha(staged_root / "staging-certificate.json"),
        "manifest_sha256": staging_certificate["manifest_sha256"],
        "exclusions_sha256": exclusions_sha,
        "ufs": sorted(ufs) if ufs else None,
        "limit": limit,
        "shard_objects": shard_objects,
    }
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new (or pass --resume): {output}")
    if resume:
        previous = json.loads((output / "binding.json").read_bytes())
        if previous != binding:
            raise ValueError("Resume binding differs from the original pass")
    output.mkdir(parents=True, exist_ok=resume)
    atomic(output / "binding.json", binding)
    shard_dir = output / "shards"
    shard_dir.mkdir(exist_ok=True)
    items, excluded = work_list(
        staged_root, round_number, ufs=set(ufs) if ufs else None, exclusions=exclusions, limit=limit
    )
    shards = [items[i : i + shard_objects] for i in range(0, len(items), shard_objects)]
    done = {int(p.name) for p in shard_dir.iterdir() if p.name.isdigit()}
    tasks = [
        (str(staged_root), round_number, str(shard_dir), i, shard)
        for i, shard in enumerate(shards)
        if i not in done
    ]
    started = time.monotonic()
    status = output / "status.json"
    completed_objects = sum(len(shards[i]) for i in done if i < len(shards))
    errors = 0

    def report(stage, **extra):
        elapsed = time.monotonic() - started
        atomic(
            status,
            {
                "stage": stage,
                "objects_total": len(items),
                "objects_done": completed_objects,
                "shards_total": len(shards),
                "excluded_objects": excluded,
                "errors_this_session": errors,
                "elapsed_seconds": round(elapsed, 1),
                "pid": os.getpid(),
                **extra,
            },
        )

    report("running")
    session_done = 0
    with multiprocessing.get_context("spawn").Pool(
        workers, initializer=_init_worker, maxtasksperchild=50
    ) as pool:
        for _, count, failed in pool.imap_unordered(run_shard, tasks):
            completed_objects += count
            session_done += count
            errors += failed
            elapsed = time.monotonic() - started
            rate = session_done / elapsed if elapsed else 0
            report(
                "running",
                objects_per_second=round(rate, 1),
                eta_hours=round((len(items) - completed_objects) / rate / 3600, 2)
                if rate
                else None,
            )
    report("merging")
    result = merge(output, shards, binding, excluded)
    report("finished", **{k: result[k] for k in ("objects", "errors", "sessions")})
    return result


def merge(output, shards, binding, excluded):
    """Concatenate shards into the release tables and write a checksummed manifest."""
    release = output / "release"
    shutil.rmtree(release, ignore_errors=True)
    temporary = output / ".release.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir()
    counts = {}
    for name, schema in (
        ("sessions", SESSION_SCHEMA),
        ("segments", SEGMENT_SCHEMA),
        ("objects", OBJECT_SCHEMA),
    ):
        with pq.ParquetWriter(temporary / f"{name}.parquet", schema, compression="zstd") as w:
            rows = 0
            for index in range(len(shards)):
                table = pq.read_table(output / "shards" / f"{index:05d}" / f"{name}.parquet")
                w.write_table(table)
                rows += table.num_rows
        counts[name] = rows
    vocabulary = Counter()
    for index in range(len(shards)):
        for application, template, count in json.loads(
            (output / "shards" / f"{index:05d}" / "vocabulary.json").read_text()
        ):
            vocabulary[(application, template)] += count
    rows = [
        {"application": a, "template": t, "events": c}
        for (a, t), c in sorted(vocabulary.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    pq.write_table(
        pa.Table.from_pylist(
            rows,
            schema=pa.schema(
                [("application", pa.string()), ("template", pa.string()), ("events", pa.int64())]
            ),
        ),
        temporary / "vocabulary.parquet",
        compression="zstd",
    )
    objects = pq.read_table(temporary / "objects.parquet", columns=["status"]).column(0)
    errors = sum(1 for value in objects.to_pylist() if value != "complete")
    files = {
        p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(temporary.iterdir())
    }
    manifest = {
        **binding,
        "objects": counts["objects"],
        "errors": errors,
        "excluded_objects": excluded,
        "sessions": counts["sessions"],
        "segments": counts["segments"],
        "vocabulary_templates": len(rows),
        "files": files,
        "readings": "local urn clock readings; not normalized times",
        "candidate_attribution": "unavailable_anonymous_cycle",
        "attendance_reconciliation": "not performed (Phase 20/22)",
    }
    atomic(temporary / "manifest.json", manifest)
    os.replace(temporary, release)
    return manifest


# --------------------------------------------------------------------------- equivalence


def adapter_signatures(original, scratch, round_number):
    """Run the Phase 13 event-level adapter on one object and reduce it to signatures."""
    from election_audit.archive_parsing import inspect_artifact, parse_object
    from election_audit.national import _compact_jsonl, _write_json
    from election_audit.operational_review import review_object
    from election_audit.source_inventory import hash_file

    scratch = Path(scratch)
    object_sha = hash_file(original)[0]
    parsed, _ = parse_object(original, scratch / "parse", expected_sha256=object_sha)
    inspect_artifact(parsed)
    structural = scratch / "structural"
    structural.mkdir()
    for name in ("events", "issues"):
        _compact_jsonl(parsed / (name + ".jsonl"), structural / (name + ".parquet"), 2048)
    specs = {
        f: dict(zip(("sha256", "bytes"), hash_file(structural / f), strict=True))
        for f in ("events.parquet", "issues.parquet")
    }
    _write_json(
        structural / "artifact.json",
        {
            "object_sha256": object_sha,
            "source_bytes": Path(original).stat().st_size,
            "files": specs,
        },
    )
    result = review_object(structural, original, scratch / "review", round_number=round_number)

    def rows(name):
        table = pq.read_table(result / f"{name}.parquet").column(0).to_pylist()
        return [json.loads(r) for r in table]

    cycles = Counter()
    for cycle in rows("cycles"):
        cycles[
            (
                cycle["session_id"],
                cycle["completion_state"],
                cycle["authorization_method"],
                cycle["interrupted"] and cycle["completion_state"] == "completed",
            )
        ] += 1
    signatures = []
    for session in rows("sessions"):
        mine = Counter()
        for (sid, state, method, interrupted), n in cycles.items():
            if sid == session["session_id"]:
                mine[f"cycles_{state}_{method}"] += n
                if interrupted:
                    mine["completed_interrupted"] += n
        signatures.append(
            {
                "session_kind": session["session_kind"],
                "end_reason": session["end_reason"],
                "closing": session["closing_event_id"] is not None,
                "software_supported": session["software_supported"],
                "cycles": dict(sorted(mine.items())),
            }
        )
    counts = json.loads((result / "artifact.json").read_text())["counts"]
    return signatures, counts


def pass_signatures(summary):
    signatures = []
    for session in summary.sessions:
        cycles = {
            f"cycles_{s}_{m}": session[f"cycles_{s}_{m}"]
            for s in CYCLE_STATES
            for m in METHODS
            if session[f"cycles_{s}_{m}"]
        }
        if session["completed_interrupted"]:
            cycles["completed_interrupted"] = session["completed_interrupted"]
        signatures.append(
            {
                "session_kind": session["session_kind"],
                "end_reason": session["end_reason"],
                "closing": session["closing_reading"] is not None,
                "software_supported": session["software_supported"],
                "cycles": dict(sorted(cycles.items())),
            }
        )
    return signatures


def equivalence(staged_root, round_number, output, *, exclusions_path, ufs, sample, seed=21):
    """Compare the streaming pass with the event-level adapter on sampled objects."""
    staged_root = Path(staged_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    exclusions, exclusions_sha = load_exclusions(exclusions_path)
    items, _ = work_list(staged_root, round_number, ufs=set(ufs), exclusions=exclusions)
    chosen = sorted(
        random.Random(seed).sample(items, min(sample, len(items))), key=lambda i: i["path"]
    )
    output.mkdir(parents=True)
    results = []
    for item in chosen:
        original = staged_root / item["path"]
        record = {"object_sha256": item["sha256"], "witnesses": item["witnesses"]}
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            started = time.monotonic()
            expected, adapter_counts = adapter_signatures(original, scratch, round_number)
            adapter_seconds = time.monotonic() - started
        started = time.monotonic()
        summary = summarize_object(original, item["sha256"], round_number)
        pass_seconds = time.monotonic() - started
        observed = pass_signatures(summary)
        orphan_pass = sum(s["orphan_completions"] for s in summary.sessions) + (
            summary.orphans_without_session
        )
        manual_pass = sum(s["manual_requests"] for s in summary.sessions)
        record.update(
            sessions=len(observed),
            equal_sessions=expected == observed,
            orphan_completions=[adapter_counts.get("orphan_completions", 0), orphan_pass],
            manual_requests=[adapter_counts.get("manual_requests", 0), manual_pass],
            completed=sum(v for s in observed for k, v in s["cycles"].items() if "completed_" in k),
            adapter_seconds=round(adapter_seconds, 3),
            pass_seconds=round(pass_seconds, 3),
        )
        record["equal"] = (
            record["equal_sessions"]
            and record["orphan_completions"][0] == record["orphan_completions"][1]
            and record["manual_requests"][0] == record["manual_requests"][1]
        )
        if not record["equal"]:
            record["adapter"], record["pass"] = expected, observed
        results.append(record)
        print(
            json.dumps({k: record[k] for k in ("object_sha256", "equal", "sessions")}), flush=True
        )
    report = {
        "version": VERSION + "-equivalence",
        "round": round_number,
        "ufs": sorted(ufs),
        "seed": seed,
        "exclusions_sha256": exclusions_sha,
        "staging_certificate_sha256": sha(staged_root / "staging-certificate.json"),
        "objects": len(results),
        "equal_objects": sum(r["equal"] for r in results),
        "completed_cycles": sum(r["completed"] for r in results),
        "adapter_seconds": round(sum(r["adapter_seconds"] for r in results), 1),
        "pass_seconds": round(sum(r["pass_seconds"] for r in results), 1),
        "results": results,
    }
    atomic(output / "equivalence.json", report)
    return report


def semantic_pass_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="election-audit semantic-pass",
        description="Phase 21 streaming per-session aggregates from staged raw logs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run the sharded pass over a staged round.")
    check = commands.add_parser("equivalence", help="Compare with the event-level adapter.")
    for sub in (run, check):
        sub.add_argument("--staged-root", required=True, help="Certified staged round root.")
        sub.add_argument("--round", type=int, choices=(1, 2), required=True)
        sub.add_argument("--output", required=True, help="New output directory.")
        sub.add_argument("--exclusions", required=True, help="Protected/stress exclusions JSON.")
        sub.add_argument("--uf", action="append", help="Restrict to these UFs (lowercase).")
    run.add_argument("--workers", type=int, default=4, help="Worker processes.")
    run.add_argument("--limit", type=int, help="Process only the first N objects.")
    run.add_argument("--resume", action="store_true", help="Resume the same pass.")
    check.add_argument("--sample", type=int, default=50, help="Objects to compare.")
    check.add_argument("--seed", type=int, default=21, help="Sample seed.")
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_pass(
            args.staged_root,
            args.round,
            args.output,
            exclusions_path=args.exclusions,
            workers=args.workers,
            ufs=args.uf,
            limit=args.limit,
            resume=args.resume,
        )
        print(json.dumps({k: result[k] for k in ("objects", "errors", "sessions", "segments")}))
    else:
        if not args.uf:
            parser.error("equivalence needs --uf (development data only)")
        result = equivalence(
            args.staged_root,
            args.round,
            args.output,
            exclusions_path=args.exclusions,
            ufs=args.uf,
            sample=args.sample,
            seed=args.seed,
        )
        print(json.dumps({k: result[k] for k in ("objects", "equal_objects", "completed_cycles")}))
    return 0
