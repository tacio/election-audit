"""Fused structural summaries and indexed forensic replay, without an event lake.

No official session, cycle, clock or electoral-result validity is inferred here.
Ordinary unsupported lines remain reproducible from immutable original/member/block
indexes. Individual line hashes are retained for selected anchors and errors, and
are derived on demand for every other physical line, rather than materialized.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from election_audit.archive_parsing import MESSAGES, PARSER_VERSION, ParseConfig, Segments, _Parser
from election_audit.national_migration import file_stat
from election_audit.national_relocation import relocated_root
from election_audit.source_inventory import identity
from election_audit.types import JSON, Row

VERSION = "source-operational-summary-v1"
BLOCK_LINES = 512
LEVELS = {"INFO", "WARN", "WARNING", "ERROR", "DEBUG", "TRACE", "FATAL"}
DEVICE = re.compile(r"[0-9]{1,32}\Z")
APPLICATION = re.compile(r"[A-Z][A-Z0-9_-]{0,31}\Z")
TIMESTAMP = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}\Z")


class SummaryBudgetExceeded(MemoryError):
    """Stop without publishing an incomplete/truncated diagnostic/evidence set."""


def timestamp(value: str) -> datetime:
    if not TIMESTAMP.fullmatch(value):
        raise ValueError("Invalid structural timestamp")
    # Same calendar validation as strptime, without its global locale/cache path.
    return datetime(
        int(value[6:10]),
        int(value[3:5]),
        int(value[:2]),
        int(value[11:13]),
        int(value[14:16]),
        int(value[17:19]),
    )


class SummaryParser(_Parser):
    def __init__(
        self,
        object_sha: str,
        directory: str | Path,
        *,
        output_limit: int = 32 * 1024**2,
        block_lines: int = BLOCK_LINES,
    ) -> None:
        super().__init__(object_sha, ParseConfig(), directory, None, None)
        self.output_limit, self.estimated_output, self.block_lines = output_limit, 0, block_lines
        self.members, self.blocks, self.anchors, self.errors = [], [], [], []
        self.diagnostics = Counter()
        self.current_member = None
        self.current_line_hash = None
        self.current_line_bytes = b""
        self.kinds = Counter()
        self.replay_window = None
        self.replayed = []
        self.segment_sizes = {}

    def member_buffer(self) -> IO[bytes]:
        # At most depth+1 buffers, each <=2 MiB RAM; larger members spill to the
        # bounded scratch root. CRC is checked before emitting lines, as before.
        return tempfile.SpooledTemporaryFile(max_size=2 * 1024**2, dir=str(self.directory))

    def retain(self, destination: list[Any], row: tuple[Any, ...]) -> None:
        self.estimated_output += 256 + sum(len(v) for v in row if isinstance(v, (str, bytes)))
        if self.estimated_output > self.output_limit:
            raise SummaryBudgetExceeded("Evidence/index output exceeds explicit per-object bound")
        destination.append(row)

    def line_hash(self) -> str | None:
        if self.current_line_hash is None:
            self.current_line_hash = hashlib.sha256(self.current_line_bytes).hexdigest()
        return self.current_line_hash

    def issue(
        self,
        code: str,
        segments: Segments,
        *,
        line: int | None = None,
        severity: str = "error",
        **details: Any,
    ) -> None:
        self.incomplete |= severity == "error"
        self.counts["issues_seen"] += 1
        self.diagnostics[(code, severity)] += 1
        if severity == "info" and code == "unsupported_message_class":
            self.counts["issues_aggregated"] += 1
            return
        self.counts["issues_written"] += 1
        # Account repeated long archive paths in error output, not just the tuple
        # shell. Otherwise a tiny ZIP with huge names could amplify diagnostics.
        key = tuple((s["member_name"], s["member_index"], s["occurrence"]) for s in segments)
        if key not in self.segment_sizes:
            self.segment_sizes[key] = len(json.dumps(segments, ensure_ascii=True))
        self.estimated_output += self.segment_sizes[key] + len(json.dumps(details))
        # Archive-level diagnostics also preserve their exact member locator.
        self.retain(
            self.errors,
            (
                code,
                severity,
                segments,
                line,
                details,
                self.line_hash()
                if line is not None
                and not (
                    code == "line_count_limit"
                    and len(self.current_line_bytes) > self.config.max_line_bytes
                    and not self.current_line_bytes.endswith(b"\n")
                )
                else None,
            ),
        )

    def lines(self, body: IO[bytes], segments: Segments) -> None:
        member = len(self.members)
        self.current_member = member
        first_sequence = self.counts["lines"] + 1
        n, valid, unknown, reversals, boundaries = 0, 0, 0, 0, 0
        first_time = last_time = min_time = max_time = previous = previous_stream = None
        block_start, block_unknown, block_events = 1, 0, 0
        block = hashlib.sha256()
        block_bytes = 0

        def finish_block() -> None:
            nonlocal block, block_start, block_unknown, block_events, block_bytes
            self.retain(
                self.blocks,
                (
                    member,
                    block_start,
                    n,
                    block.hexdigest(),
                    block_bytes,
                    block_events,
                    block_unknown,
                ),
            )
            block = hashlib.sha256()
            block_start, block_unknown, block_events, block_bytes = n + 1, 0, 0, 0

        while line := body.readline(self.config.max_line_bytes + 1):
            n += 1
            self.counts["lines"] += 1
            self.current_line_bytes = line
            self.current_line_hash = None
            block.update(line)
            block_bytes += len(line)
            if self.counts["lines"] > self.config.max_lines:
                self.issue("line_count_limit", segments, line=n, limit=self.config.max_lines)
                break
            if len(line) > self.config.max_line_bytes:
                physical_line_hash = hashlib.sha256(line)
                while not line.endswith(b"\n"):
                    line = body.readline(self.config.max_line_bytes + 1)
                    if not line:
                        break
                    block.update(line)
                    physical_line_hash.update(line)
                    block_bytes += len(line)
                self.current_line_hash = physical_line_hash.hexdigest()
                self.issue("line_size_limit", segments, line=n, limit=self.config.max_line_bytes)
            else:
                fields = line.decode("latin-1").rstrip("\r\n").split("\t")
                if len(fields) != 6:
                    self.issue("malformed_columns", segments, line=n, field_count=len(fields))
                else:
                    raw_time, level, device, app, message, _token = fields
                    try:
                        instant = timestamp(raw_time)
                    except ValueError:
                        self.issue("invalid_timestamp", segments, line=n)
                    else:
                        if not DEVICE.fullmatch(device) or not APPLICATION.fullmatch(app):
                            self.issue("invalid_device_or_application", segments, line=n)
                        else:
                            kind = MESSAGES.get(message, "unknown") if app == "VOTA" else "unknown"
                            if self.replay_window is not None:
                                replay_member, start, stop = self.replay_window
                                if member == replay_member and start <= n <= stop:
                                    locator = {
                                        "archive_segments": segments,
                                        "line_start": n,
                                        "line_end": n,
                                        "byte_start": None,
                                        "byte_end": None,
                                    }
                                    self.replayed.append(
                                        {
                                            "event_id": identity(
                                                "structural-event",
                                                [
                                                    self.sha,
                                                    locator,
                                                    PARSER_VERSION,
                                                    self.config.__dict__,
                                                ],
                                            ),
                                            "object_sha256": self.sha,
                                            "record_locator": locator,
                                            "source_sequence": self.counts["lines"],
                                            "source_line_sha256": self.line_hash(),
                                            "device_timestamp_raw": raw_time,
                                            "device_id_raw": device,
                                            "application": app,
                                            "level": level if level in LEVELS else "unknown",
                                            "event_kind": kind,
                                            "selection_state": "context_unresolved",
                                            "parser_version": PARSER_VERSION,
                                        }
                                    )
                            if kind == "unknown":
                                unknown += 1
                                block_unknown += 1
                                self.issue(
                                    "unsupported_message_class", segments, line=n, severity="info"
                                )
                            changed = previous_stream is not None and previous_stream != (
                                device,
                                app,
                            )
                            reversed_clock = previous is not None and instant < previous
                            boundaries += int(changed)
                            reversals += int(reversed_clock)
                            # Relevant events and context boundaries only. No message/token is retained.
                            if (
                                kind != "unknown"
                                or level in {"ERROR", "FATAL", "WARN", "WARNING"}
                                or changed
                                or reversed_clock
                                or valid == 0
                            ):
                                self.retain(
                                    self.anchors,
                                    (
                                        member,
                                        n,
                                        self.counts["lines"],
                                        self.line_hash(),
                                        raw_time,
                                        device,
                                        app,
                                        level if level in LEVELS else "unknown",
                                        kind,
                                        bool(changed),
                                        bool(reversed_clock),
                                    ),
                                )
                            valid += 1
                            block_events += 1
                            self.counts["events"] += 1
                            self.kinds[kind] += 1
                            first_time = first_time or raw_time
                            last_time = raw_time
                            min_time = min(min_time, instant) if min_time else instant
                            max_time = max(max_time, instant) if max_time else instant
                            previous, previous_stream = instant, (device, app)
            if n % self.block_lines == 0:
                finish_block()
        if n >= block_start:
            finish_block()
        self.retain(
            self.members,
            (
                member,
                segments,
                first_sequence,
                n,
                valid,
                unknown,
                first_time,
                last_time,
                min_time.isoformat() if min_time else None,
                max_time.isoformat() if max_time else None,
                reversals,
                boundaries,
            ),
        )
        self.current_line_hash = None

    def result(self) -> JSON:
        return {
            "version": VERSION,
            "object_sha256": self.sha,
            "source_parser_version": PARSER_VERSION,
            "parser_config": self.config.__dict__,
            "status": "partial" if self.incomplete else "complete",
            "counts": dict(self.counts),
            "event_kinds": dict(self.kinds),
            "diagnostics": [
                (code, severity, count)
                for (code, severity), count in sorted(self.diagnostics.items())
            ],
            "log_members": self.log_members,
            "members": self.members,
            "blocks": self.blocks,
            "anchors": self.anchors,
            "errors": self.errors,
            "readiness": {
                "structural_counts": "partial" if self.incomplete else "ready",
                "official_sessions": "unavailable",
                "absolute_clocks": "unavailable",
                "deduplicated_cycles": "unavailable",
                "electoral_features": "unavailable",
            },
            "evidence_policy": "all raw retained; unknown line hashes and arbitrary copy windows require indexed replay; no voter/token/message text retained",
        }


def summarize(
    row: Row,
    scratch: str | Path,
    *,
    output_limit: int = 32 * 1024**2,
    block_lines: int = BLOCK_LINES,
    _replay: tuple[int, int, int] | None = None,
) -> JSON:
    root = relocated_root(row["source_root"], row["path"], row["sha256"], row["bytes"])
    source = root / row["path"]
    before = file_stat(root, row["path"])
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024**2), b""):
                digest.update(chunk)
            if digest.hexdigest() != row["sha256"] or before[2] != row["bytes"]:
                raise ValueError("Verified source hash/length mismatch")
            stream.seek(0)
            with tempfile.TemporaryDirectory(prefix="summary-", dir=scratch) as directory:
                parser = SummaryParser(
                    row["sha256"], directory, output_limit=output_limit, block_lines=block_lines
                )
                parser.replay_window = _replay
                parser.archive(stream)
                if not parser.log_members:
                    parser.issue("missing_log_member", [])
                result = parser.result()
                if _replay is not None:
                    result["replayed"] = parser.replayed
            value = os.fstat(fd)
            after = (
                value.st_dev,
                value.st_ino,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )
            if before != after or file_stat(root, row["path"]) != before:
                raise ValueError("Source mutated during fused parsing")
            return result
    finally:
        os.close(fd)


def replay_lines(
    row: Row, scratch: str | Path, member_key: int, start: int, stop: int
) -> Iterator[JSON]:
    """Return a bounded exact forensic window, including hashes of unknown/error lines.

    This revalidates the raw source and archive and emits the same selected-field
    anchors; raw message/token text is never exposed. Full old event materialization
    remains available through process_compact_original on eligible explicit scopes.
    """
    if not (
        type(start) is int and type(stop) is int and 1 <= start <= stop and stop - start < 4096
    ):
        raise ValueError("Replay window must contain 1..4096 physical lines")
    result = summarize(row, scratch, _replay=(member_key, start, stop))
    if not 0 <= member_key < len(result["members"]):
        raise ValueError("Unknown replay member")
    yield from result["replayed"]
