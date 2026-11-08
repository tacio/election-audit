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
import threading
import time
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import sevenzip
from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.operational_review import (
    PROMOTING_KINDS,
    SESSION_RULES,
    classify,
    keeps_round,
    rules_for,
)

VERSION = (
    "session-aggregates-v4"  # v2: int64 seconds; v3: device and clock columns; v4: sessions-v2
)
ADAPTER_VERSION = "real-operational-v1"
SHARD_OBJECTS = 500
VOCABULARY_LIMIT = 4000
MAX_DEPTH, MAX_MEMBERS, MAX_MEMBER, MAX_EXPANDED = 4, 10000, 128 * 1024**2, 512 * 1024**2
MAX_LINE, MAX_LINES = 65536, 2000000
BULK_ARCHIVE = re.compile(r"files/bu_imgbu_logjez_rdv_vscmr_(\d{4})_([12])t_([A-Z]{2})\.zip")
BULK_YEARS = (2022,)  # 2026 bulk archives hold the protected logs; 2026 reads the staging
URL = re.compile(r"/arquivo-urna/(\d+)/dados/([a-z]{2})/(\d+)/(\d+)/(\d+)/")
DIGITS = re.compile(r"[0-9]+")
HEXRUN = re.compile(r"\b[0-9A-Fa-f]{12,}\b")
MODEL_PREFIX = "Identificação do Modelo de Urna: "
VERSION_PREFIX = "Versão da aplicação: "
STAMP = r"(\d{2}/\d{2}/\d{4}) - (\d{2}:\d{2}:\d{2})"
ADH_SET = re.compile(rf"Ajuste de Data e Hora {STAMP} foi digitada pelo operador")
DST_SHIFT = "Horário da urna alterado devido a horário de verão"
CLOSE_FLOOR = re.compile(r"Encerramento só pode ser solicitado após as (\d{2}:\d{2}:\d{2}) horas")
TZ_SHIFT = re.compile(
    rf"Data e hora da urna alterada de {STAMP} para {STAMP} por ajuste de fuso horário"
)
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
        ("completion_gap_min_s", pa.int64()),
        ("completion_gap_median_s", pa.float32()),
        ("completion_gap_p90_s", pa.int64()),
        ("completion_gap_max_s", pa.int64()),
        ("reading_backsteps", pa.int32()),
        ("reading_backstep_max_s", pa.int64()),
        ("model", pa.string()),
        ("software_version", pa.string()),
        ("clock_adh_before", pa.int32()),
        ("clock_adh_shift_s_before", pa.int64()),
        ("clock_tz_shifts_before", pa.int32()),
        ("clock_tz_shift_s_before", pa.int64()),
        ("clock_dst_before", pa.int32()),
        ("configured_close", pa.string()),
        ("segment_ordinal", pa.int32()),
        ("started_before_election_day", pa.bool_()),
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


def iso_reading(seconds) -> str | None:
    if seconds is None:
        return None
    day, rest = divmod(seconds, 86400)
    if rest >= 86400:
        return None
    hour, rest = divmod(rest, 3600)
    minute, second = divmod(rest, 60)
    return f"{date.fromordinal(day).isoformat()}T{hour:02d}:{minute:02d}:{second:02d}"


def log_members(path):  # path, or the object's bytes
    """Yield (segments, body) for every bounded logd.dat member of a ZIP or 7z object."""
    totals = {"members": 0, "expanded": 0}

    def entries(handle):
        """(index, original name, body) for each file entry; directories are skipped."""
        if handle.read(len(sevenzip.MAGIC)) == sevenzip.MAGIC:  # 2022 logs
            handle.seek(0)
            data = handle.read(MAX_EXPANDED + 1)
            if len(data) > MAX_EXPANDED:
                raise ValueError("Expanded archive bound exceeded")
            for index, (name, body, is_dir) in enumerate(sevenzip.read(data, limit=MAX_MEMBER)):
                if not is_dir:
                    yield index, name, body
            return
        handle.seek(0)
        with zipfile.ZipFile(handle) as z:
            for index, entry in enumerate(z.infolist()):
                if entry.is_dir():
                    continue
                if entry.file_size > MAX_MEMBER:
                    raise ValueError("Member bound exceeded")
                with z.open(entry) as f:
                    yield index, entry.orig_filename, f.read(MAX_MEMBER + 1)

    def archive(handle, segments):
        if len(segments) > MAX_DEPTH:
            raise ValueError("Nested archive bound exceeded")
        occurrences = Counter()
        for index, original, body in entries(handle):
            totals["members"] += 1
            if totals["members"] > MAX_MEMBERS:
                raise ValueError("Member bound exceeded")
            occurrence = occurrences[original]
            occurrences[original] += 1
            nested = (*segments, (original, occurrence, index))
            totals["expanded"] += len(body)
            if len(body) > MAX_MEMBER or totals["expanded"] > MAX_EXPANDED:
                raise ValueError("Expanded archive bound exceeded")
            name = original.replace("\\", "/").rsplit("/", 1)[-1].lower()
            if name == "logd.dat":
                yield nested, body
            elif body[:2] == b"PK" or body[:6] == sevenzip.MAGIC or name.endswith((".jez", ".zip")):
                yield from archive(io.BytesIO(body), nested)

    if isinstance(path, bytes):
        yield from archive(io.BytesIO(path), ())
        return
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

    def __init__(self, object_sha256, round_number, year=2026) -> None:
        self.sha = object_sha256
        self.round = round_number
        self.rules = rules_for(year)
        self.election_day = date.fromisoformat(election_for_round(round_number, year).election_date)
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
        self.clock = {"model": None, "adh": 0, "adh_shift": 0, "tz": 0, "tz_shift": 0, "dst": 0}
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
            found = classify(application, message, self.rules)
            if len(self._classes) < 200000:
                self._classes[key] = found
        return found

    # ---- segments (context blocks inside one stream)
    def _open_segment(self, context, device, path) -> None:
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

    def _close_segment(self) -> None:
        if self.segment is not None:
            row = self.segment
            row["fingerprint"] = row.pop("hash").hexdigest()
            self.segments.append(row)
            self.segment = None

    # ---- sessions and cycles
    def _finish_cycle(self, state) -> None:
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

    def _finish_session(self, reason) -> None:
        self._finish_cycle("unresolved")
        session = self.session
        if session is not None:
            session["end_reason"] = reason
            session.pop("_early")
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

    def _device_clock(self, application, message, reading) -> None:
        """Device model and clock settings of the current stream, as read before a session."""
        clock = self.clock
        if message.startswith(MODEL_PREFIX):
            model = message[len(MODEL_PREFIX) :].strip()
            if re.fullmatch(r"UE[0-9]{4}", model):
                clock["model"] = model
                if self.session is not None and self.session["model"] is None:
                    self.session["model"] = model
        elif application == "ADH" and (found := ADH_SET.fullmatch(message)):
            typed = reading_seconds(f"{found[1]} {found[2]}")
            clock["adh"] += 1
            if typed is not None:
                clock["adh_shift"] += typed - reading
        elif message == DST_SHIFT:
            clock["dst"] += 1
        elif found := TZ_SHIFT.fullmatch(message):
            before = reading_seconds(f"{found[1]} {found[2]}")
            after = reading_seconds(f"{found[3]} {found[4]}")
            clock["tz"] += 1
            if before is not None and after is not None:
                clock["tz_shift"] += after - before

    def _new_stream(self, key, device, path) -> None:
        if self.stream is not None:
            self._finish_session("stream_end")
        self._close_segment()
        self.stream, self.phase = key, None
        self.clock = {"model": None, "adh": 0, "adh_shift": 0, "tz": 0, "tz_shift": 0, "dst": 0}
        self.stream_ordinal += 1
        self._segment_ordinal = 0
        self._last_reading = None
        self._open_segment("initial", device, path)

    def feed(self, segments, body) -> None:
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

    def _event(self, path, segments, line, reading, device, application, message) -> None:
        self.events += 1
        key = (segments, device)
        if key != self.stream:
            self._new_stream(key, device, path)
        kind, value = self._classify(application, message)
        self.kinds[kind] += 1
        if message.startswith(
            ("Identificação", "Ajuste de Data", "Data e hora da urna", "Horário da urna")
        ):
            self._device_clock(application, message, reading)
        template = self._template(application, message)
        if template in self.vocabulary or len(self.vocabulary) < VOCABULARY_LIMIT:
            self.vocabulary[template] += 1
        else:
            self.vocabulary_overflow += 1
        if kind == "official_round" or (
            kind == "context_reset"
            and not keeps_round(application, message, self.phase, self.rules)
        ):
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
            in_round = self.phase == value == self.round
            official = in_round and on_day
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
                "model": self.clock["model"],
                "software_version": None,
                "clock_adh_before": self.clock["adh"],
                "clock_adh_shift_s_before": self.clock["adh_shift"],
                "clock_tz_shifts_before": self.clock["tz"],
                "clock_tz_shift_s_before": self.clock["tz_shift"],
                "clock_dst_before": self.clock["dst"],
                "configured_close": None,
                "segment_ordinal": self.segment["segment_ordinal"],
                "started_before_election_day": False,
                "_early": in_round and reading < self.election_seconds,
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
        if (
            session is not None
            and application == "VOTA"
            and session["software_version"] is None
            and message.startswith(VERSION_PREFIX)
        ):
            session["software_version"] = message[len(VERSION_PREFIX) :].strip()[:80]
        if (
            session is not None
            and application == "VOTA"
            and session["configured_close"] is None
            and message.startswith("Encerramento só")
            and (found := CLOSE_FLOOR.fullmatch(message))
        ):
            session["configured_close"] = found[1]
        if (
            session is not None
            and session["_early"]
            and session["session_kind"] == "unresolved"
            and on_day
            and application == "VOTA"
            and kind in PROMOTING_KINDS
        ):
            session["session_kind"] = "official_vota"
            session["started_before_election_day"] = True
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

    def finish(self) -> None:
        if self.stream is not None:
            self._finish_session("stream_end")
        self._close_segment()


def summarize_object(source, object_sha256, round_number, year=2026):
    """Summarize one log object given as a path or as its bytes."""
    summary = ObjectSummary(object_sha256, round_number, year)
    for segments, body in log_members(source):
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


def bulk_archives(bulk_root, year, round_number, ufs=None):
    """Complete per-UF bulk archives of one round whose logs this pass may parse."""
    if year not in BULK_YEARS:
        raise ValueError(
            f"{year} logs are not read from bulk archives; 2026 uses the certified staging"
        )
    return verified_bulk_archives(bulk_root, year, round_number, ufs)


def verified_bulk_archives(bulk_root, year, round_number, ufs=None):
    """Complete per-UF bulk archives of one round, as recorded in the bulk manifest."""
    bulk_root = Path(bulk_root)
    uri = (bulk_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    archives = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for path, digest, size, status in db.execute(
            "SELECT path, sha256, bytes, status FROM files ORDER BY path"
        ):
            match = BULK_ARCHIVE.fullmatch(path)
            if not match or (int(match[1]), int(match[2])) != (year, round_number):
                continue
            uf = match[3].lower()
            if ufs and uf not in ufs:
                continue
            if status != "complete" or not digest:
                raise ValueError(f"Bulk archive is not complete: {path}")
            if (bulk_root / path).stat().st_size != size:
                raise ValueError(f"Bulk archive size differs from its manifest: {path}")
            archives.append({"uf": uf, "path": path, "sha256": digest, "bytes": size})
    if not archives:
        raise ValueError(f"No bulk archives for {year} round {round_number}")
    if not ufs and len(archives) != 28:
        raise ValueError(f"Expected 28 bulk archives (27 UFs and ZZ), found {len(archives)}")
    return archives


def bulk_work_list(bulk_root, archives, year, round_number, *, limit=None):
    """Log members of the bulk archives in physical (header offset) order, with witnesses."""
    pleito = int(election_for_round(round_number, year).pleito_code)
    member = re.compile(rf"o0*{pleito}-(\d{{5}})(\d{{4}})(\d{{4}})\.logjez")
    items = []
    for archive in archives:
        with zipfile.ZipFile(Path(bulk_root) / archive["path"]) as z:
            infos = sorted(
                (i for i in z.infolist() if i.filename.endswith(".logjez")),
                key=lambda i: i.header_offset,
            )
        for info in infos:
            match = member.fullmatch(info.filename)
            if not match:
                raise ValueError(f"Unexpected log member {info.filename!r} in {archive['path']}")
            items.append(
                {
                    "path": f"{archive['path']}!{info.filename}",
                    "archive": archive["path"],
                    "member": info.filename,
                    "sha256": None,
                    "witnesses": [[archive["uf"], *match.groups()]],
                    "package": None,
                }
            )
    return items[:limit] if limit is not None else items


def bulk_bodies(bulk_root, items):
    """Read members sequentially; zipfile checks each member's CRC at end of stream."""
    bodies, current, handle = [], None, None
    try:
        for item in items:
            if item["archive"] != current:
                if handle is not None:
                    handle.close()
                handle = zipfile.ZipFile(Path(bulk_root) / item["archive"])
                current = item["archive"]
            with handle.open(item["member"]) as f:
                bodies.append(f.read(MAX_EXPANDED + 1))
    finally:
        if handle is not None:
            handle.close()
    return bodies


# --------------------------------------------------------------------------- shards


def _write(path, rows, schema) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")


def run_shard(task):
    staged_root, round_number, shard_dir, index, items, bodies, year = task
    sessions, segments, objects, vocabulary = [], [], [], Counter()
    for position, item in enumerate(items):
        if bodies is None:
            source, digest = Path(staged_root) / item["path"], item["sha256"]
        else:  # bulk members arrive as bytes read in physical order by the parent
            source = bodies[position]
            digest = hashlib.sha256(source).hexdigest()
        row = {
            "object_sha256": digest,
            "path": item["path"],
            "witnesses_json": json.dumps(item["witnesses"], separators=(",", ":")),
            "package_status": item["package"],
        }
        try:
            if bodies is not None and len(source) > MAX_EXPANDED:
                raise ValueError("Object bound exceeded")
            summary = summarize_object(source, digest, round_number, year)
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


def _init_worker() -> None:
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def _rules_sha(year):
    return hashlib.sha256(json.dumps(rules_for(year), sort_keys=True).encode()).hexdigest()


def run_pass(
    staged_root,
    round_number,
    output,
    *,
    exclusions_path=None,
    workers=4,
    ufs=None,
    limit=None,
    resume=False,
    shard_objects=SHARD_OBJECTS,
    bulk_root=None,
    year=2026,
):
    """Sharded pass over a certified 2026 staging, or over the 2022 bulk archives."""
    output = Path(output).expanduser().absolute()
    if workers < 1 or workers > max(1, (os.cpu_count() or 2) // 2):
        raise ValueError("Workers must stay within half the CPUs")
    if (staged_root is None) == (bulk_root is None):
        raise ValueError("Give exactly one of a staged root or a bulk root")
    if bulk_root is None:
        if year != 2026 or exclusions_path is None:
            raise ValueError("A staged 2026 pass requires the protection exclusions")
        staged_root = Path(staged_root).expanduser().absolute()
        staging_certificate = json.loads((staged_root / "staging-certificate.json").read_bytes())
        if staging_certificate.get("round") != round_number:
            raise ValueError("Staged root belongs to another round")
        exclusions, exclusions_sha = load_exclusions(exclusions_path)
        binding = {
            "version": VERSION,
            "adapter_version": ADAPTER_VERSION,
            "rules_sha256": _rules_sha(year),
            "session_rules": SESSION_RULES,
            "round": round_number,
            "staged_root": str(staged_root),
            "staging_certificate_sha256": sha(staged_root / "staging-certificate.json"),
            "manifest_sha256": staging_certificate["manifest_sha256"],
            "exclusions_sha256": exclusions_sha,
            "ufs": sorted(ufs) if ufs else None,
            "limit": limit,
            "shard_objects": shard_objects,
        }
    else:
        if exclusions_path is not None:
            raise ValueError("Bulk passes read 2022 logs, which have no protected sections")
        bulk_root = Path(bulk_root).expanduser().absolute()
        archives = bulk_archives(bulk_root, year, round_number, set(ufs) if ufs else None)
        binding = {
            "version": VERSION,
            "adapter_version": ADAPTER_VERSION,
            "rules_sha256": _rules_sha(year),
            "session_rules": SESSION_RULES,
            "rules_version": rules_for(year)["version"],
            "year": year,
            "round": round_number,
            "bulk_root": str(bulk_root),
            "archives": {a["path"]: {"sha256": a["sha256"], "bytes": a["bytes"]} for a in archives},
            "exclusions": "none: 2022 is the negative control and has no protected sections",
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
    if bulk_root is None:
        items, excluded = work_list(
            staged_root,
            round_number,
            ufs=set(ufs) if ufs else None,
            exclusions=exclusions,
            limit=limit,
        )
    else:
        items, excluded = bulk_work_list(bulk_root, archives, year, round_number, limit=limit), 0
    shards = [items[i : i + shard_objects] for i in range(0, len(items), shard_objects)]
    done = {int(p.name) for p in shard_dir.iterdir() if p.name.isdigit()}
    todo = [i for i in range(len(shards)) if i not in done]
    # Bulk members are read by this process only, in physical order, and at most
    # workers + 2 shards of bytes are in flight at once.
    gate = threading.BoundedSemaphore(workers + 2)

    def tasks():
        for i in todo:
            if bulk_root is None:
                yield (str(staged_root), round_number, str(shard_dir), i, shards[i], None, year)
            else:
                gate.acquire()
                bodies = bulk_bodies(bulk_root, shards[i])
                yield (None, round_number, str(shard_dir), i, shards[i], bodies, year)

    started = time.monotonic()
    status = output / "status.json"
    completed_objects = sum(len(shards[i]) for i in done if i < len(shards))
    errors = 0

    def report(stage, **extra) -> None:
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
        for _, count, failed in pool.imap_unordered(run_shard, tasks()):
            if bulk_root is not None:
                gate.release()
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


def adapter_signatures(original, scratch, round_number, year=2026):
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
    result = review_object(
        structural, original, scratch / "review", round_number=round_number, year=year
    )

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


def equivalence(
    staged_root,
    round_number,
    output,
    *,
    exclusions_path=None,
    ufs,
    sample,
    seed=21,
    bulk_root=None,
    year=2026,
):
    """Compare the streaming pass with the event-level adapter on sampled objects."""
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    if (staged_root is None) == (bulk_root is None):
        raise ValueError("Give exactly one of a staged root or a bulk root")
    if bulk_root is None:
        if year != 2026 or exclusions_path is None:
            raise ValueError("A staged 2026 comparison requires the protection exclusions")
        staged_root = Path(staged_root).expanduser().absolute()
        exclusions, exclusions_sha = load_exclusions(exclusions_path)
        items, _ = work_list(staged_root, round_number, ufs=set(ufs), exclusions=exclusions)
        source = {"staging_certificate_sha256": sha(staged_root / "staging-certificate.json")}
    else:
        if exclusions_path is not None:
            raise ValueError("Bulk passes read 2022 logs, which have no protected sections")
        bulk_root = Path(bulk_root).expanduser().absolute()
        archives = bulk_archives(bulk_root, year, round_number, set(ufs))
        items, exclusions_sha = bulk_work_list(bulk_root, archives, year, round_number), None
        source = {
            "year": year,
            "rules_version": rules_for(year)["version"],
            "archives": {a["path"]: a["sha256"] for a in archives},
        }
    chosen = sorted(
        random.Random(seed).sample(items, min(sample, len(items))), key=lambda i: i["path"]
    )
    output.mkdir(parents=True)
    results = []
    for item in chosen:
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            if bulk_root is None:
                original, digest = staged_root / item["path"], item["sha256"]
            else:
                body = bulk_bodies(bulk_root, [item])[0]
                digest = hashlib.sha256(body).hexdigest()
                original = Path(scratch) / "object.logjez"
                original.write_bytes(body)
            record = {"object_sha256": digest, "witnesses": item["witnesses"]}
            started = time.monotonic()
            expected, adapter_counts = adapter_signatures(original, scratch, round_number, year)
            adapter_seconds = time.monotonic() - started
            started = time.monotonic()
            summary = summarize_object(original, digest, round_number, year)
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
        **source,
        "objects": len(results),
        "equal_objects": sum(r["equal"] for r in results),
        "completed_cycles": sum(r["completed"] for r in results),
        "adapter_seconds": round(sum(r["adapter_seconds"] for r in results), 1),
        "pass_seconds": round(sum(r["pass_seconds"] for r in results), 1),
        "results": results,
    }
    atomic(output / "equivalence.json", report)
    return report


def semantic_pass_main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit semantic-pass",
        description="Phase 21 streaming per-session aggregates from staged raw logs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run the sharded pass over a staged round.")
    check = commands.add_parser("equivalence", help="Compare with the event-level adapter.")
    for sub in (run, check):
        root = sub.add_mutually_exclusive_group(required=True)
        root.add_argument("--staged-root", help="Certified staged 2026 round root.")
        root.add_argument("--bulk-root", help="Verified bulk archive root (2022 only).")
        sub.add_argument("--year", type=int, choices=(2026, 2022), default=2026)
        sub.add_argument("--round", type=int, choices=(1, 2), required=True)
        sub.add_argument("--output", required=True, help="New output directory.")
        sub.add_argument("--exclusions", help="Protected/stress exclusions JSON (2026 only).")
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
            bulk_root=args.bulk_root,
            year=args.year,
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
            bulk_root=args.bulk_root,
            year=args.year,
        )
        print(json.dumps({k: result[k] for k in ("objects", "equal_objects", "completed_cycles")}))
    return 0
