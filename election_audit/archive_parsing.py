"""Bounded structural parsing of frozen JEZ/ZIP objects; no electoral reconstruction.

Content artifacts contain no publisher context. Snapshot observations and package
witnesses live in a separate publication, so byte deduplication loses no lineage.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import uuid
import zipfile
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from election_audit import sevenzip
from election_audit.snapshots import _fsync_directory, inspect_snapshot, snapshot_tables
from election_audit.source_inventory import canonical, digest, hash_file, identity, safe_source

PARSER_VERSION = "jez-structural-v1"
ARTIFACT_FORMAT = "election-audit-parse-v1"
PUBLICATION_FORMAT = "election-audit-parse-publication-v1"
MESSAGES = {
    "O voto do eleitor foi computado": "completion_message",
    "Eleitor foi habilitado": "authorization_message",
    "Solicitação de dado pessoal do eleitor para habilitação manual": "manual_request_message",
}


@dataclass(frozen=True)
class ParseConfig:
    """All behavior limits participate in cache identity; byte limits are inclusive."""

    max_archive_bytes: int = 512 * 1024**2
    max_member_bytes: int = 128 * 1024**2
    max_total_bytes: int = 512 * 1024**2
    max_directory_bytes: int = 4 * 1024**2
    max_members: int = 10000
    max_depth: int = 4
    max_line_bytes: int = 65536
    max_lines: int = 2000000
    max_issues: int = 10000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ValueError("Parser limits must be positive integers")


class ParseError(ValueError):
    """Invalid artifact or unsafe output/input placement."""


def _locator(segments, line=None):
    return {
        "archive_segments": segments,
        "line_start": line,
        "line_end": line,
        "byte_start": None,
        "byte_end": None,
    }


def _json_line(handle, row):
    handle.write(canonical(row) + b"\n")


class _Parser:
    def __init__(self, object_sha256, config, directory, events, issues):
        self.sha = object_sha256
        self.config = config
        self.directory = directory
        self.events = events
        self.issues = issues
        self.counts = Counter()
        self.incomplete = False
        self.log_members = 0

    def member_buffer(self):
        """Seekable member storage; subclasses may provide a bounded RAM spool."""
        return tempfile.TemporaryFile(dir=self.directory)

    def issue(self, code, segments, *, line=None, severity="error", **details):
        # No exception text, raw messages, line samples, tokens or personal IDs.
        self.incomplete |= severity == "error"
        self.counts["issues_seen"] += 1
        if self.counts["issues_written"] >= self.config.max_issues:
            if self.counts["issues_written"] == self.config.max_issues:
                self.incomplete = True
                _json_line(
                    self.issues,
                    {
                        "issue_code": "diagnostic_limit",
                        "severity": "error",
                        "record_locator": _locator([]),
                        "details": {"limit": self.config.max_issues},
                    },
                )
                self.counts["issues_written"] += 1
            return
        _json_line(
            self.issues,
            {
                "issue_code": code,
                "severity": severity,
                "record_locator": _locator(segments, line),
                "details": details,
            },
        )
        self.counts["issues_written"] += 1

    def _directory_guard(self, stream, segments):
        # ZipFile loads its central directory into memory. Bound it BEFORE opening.
        stream.seek(0, 2)
        length = stream.tell()
        if length > self.config.max_archive_bytes:
            self.issue("archive_size_limit", segments, limit=self.config.max_archive_bytes)
            return False
        stream.seek(max(0, length - 65557))
        tail = stream.read(65557)
        offset = len(tail)
        while True:
            offset = tail.rfind(b"PK\x05\x06", 0, offset)
            if offset < 0:
                break
            if len(tail) - offset >= 22:
                comment_length = struct.unpack("<H", tail[offset + 20 : offset + 22])[0]
                if offset + 22 + comment_length == len(tail):
                    break
        if offset < 0:
            self.issue("invalid_archive", segments)
            return False
        _, disk, central_disk, on_disk, count, size, start, comment = struct.unpack(
            "<4s4H2LH", tail[offset : offset + 22]
        )
        if offset + 22 + comment != len(tail):
            self.issue("invalid_archive", segments)
            return False
        if disk or central_disk or on_disk != count:
            self.issue("unsupported_multidisk_archive", segments)
            return False
        if count == 65535 or size == 0xFFFFFFFF or start == 0xFFFFFFFF:
            self.issue("unsupported_zip64_archive", segments)
            return False
        if size > self.config.max_directory_bytes:
            self.issue("directory_size_limit", segments, limit=self.config.max_directory_bytes)
            return False
        # Count actual directory records too: a lying EOCD must not bypass the guard.
        if count + self.counts["members"] > self.config.max_members:
            self.issue("member_count_limit", segments, limit=self.config.max_members)
            return False
        # Validate lengths/counts in the bounded central-directory byte range.
        absolute_end = max(0, length - 65557) + offset
        if start + size != absolute_end:
            self.issue("unsupported_or_invalid_directory", segments)
            return False
        stream.seek(start)
        remaining, actual_count = size, 0
        while remaining:
            header = stream.read(46)
            if len(header) != 46 or header[:4] != b"PK\x01\x02":
                self.issue("invalid_archive", segments)
                return False
            extra_length = sum(struct.unpack("<3H", header[28:34]))
            remaining -= 46 + extra_length
            if remaining < 0:
                self.issue("invalid_archive", segments)
                return False
            stream.seek(extra_length, 1)
            actual_count += 1
            if actual_count + self.counts["members"] > self.config.max_members:
                self.issue("member_count_limit", segments, limit=self.config.max_members)
                return False
        if count != actual_count:
            self.issue("invalid_archive", segments)
            return False
        stream.seek(0)
        return True

    def archive(self, stream, segments=()):
        segments = list(segments)
        if len(segments) > self.config.max_depth:
            self.issue("archive_depth_limit", segments, limit=self.config.max_depth)
            return
        stream.seek(0)
        magic = stream.read(len(sevenzip.MAGIC))
        stream.seek(0)
        if magic == sevenzip.MAGIC:
            self.archive_7z(stream, segments)
            return
        if not self._directory_guard(stream, segments):
            return
        try:
            with zipfile.ZipFile(stream) as archive:
                occurrences = Counter()
                for index, member in enumerate(archive.infolist()):
                    self.counts["members"] += 1
                    original_name = member.orig_filename
                    occurrence = occurrences[original_name]
                    occurrences[original_name] += 1
                    nested = [
                        *segments,
                        {
                            "member_name": original_name,
                            "occurrence": occurrence,
                            "member_index": index,
                        },
                    ]
                    if self.counts["members"] > self.config.max_members:
                        self.issue("member_count_limit", nested, limit=self.config.max_members)
                        break
                    if member.file_size > self.config.max_member_bytes:
                        self.issue("member_size_limit", nested, limit=self.config.max_member_bytes)
                        continue
                    if (
                        member.file_size + self.counts["expanded_bytes"]
                        > self.config.max_total_bytes
                    ):
                        self.issue("expanded_size_limit", nested, limit=self.config.max_total_bytes)
                        continue
                    # Seekable nested ZIPs use disk, never archive-sized memory buffers.
                    with self.member_buffer() as body:
                        try:
                            with archive.open(member) as source:
                                size = 0
                                while chunk := source.read(65536):
                                    size += len(chunk)
                                    self.counts["expanded_bytes"] += len(chunk)
                                    if (
                                        size > self.config.max_member_bytes
                                        or self.counts["expanded_bytes"]
                                        > self.config.max_total_bytes
                                    ):
                                        self.issue(
                                            "expanded_size_limit",
                                            nested,
                                            limit=self.config.max_total_bytes,
                                        )
                                        break
                                    body.write(chunk)
                                else:
                                    if size != member.file_size:
                                        self.issue("member_size_mismatch", nested)
                                        continue
                                    self.counts["verified_members"] += 1
                                    body.seek(0)
                                    prefix = body.read(4)
                                    body.seek(0)
                                    name = (
                                        original_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
                                    )
                                    if name == "logd.dat":
                                        self.log_members += 1
                                        self.lines(body, nested)
                                    elif prefix.startswith(b"PK") or name.endswith(
                                        (".jez", ".zip")
                                    ):
                                        self.archive(body, nested)
                        except (
                            zipfile.BadZipFile,
                            RuntimeError,
                            NotImplementedError,
                            EOFError,
                            zlib.error,
                        ):
                            self.issue("member_integrity_error", nested)
        except zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, ValueError:
            self.issue("invalid_archive", segments)

    def archive_7z(self, stream, segments):
        """2022 logs are 7z archives; the same bounds and issue codes apply."""
        stream.seek(0, 2)
        if stream.tell() > self.config.max_archive_bytes:
            self.issue("archive_size_limit", segments, limit=self.config.max_archive_bytes)
            return
        stream.seek(0)
        try:
            entries = sevenzip.read(stream.read(), limit=self.config.max_member_bytes)
        except sevenzip.SevenZipError:
            self.issue("invalid_archive", segments)
            return
        occurrences = Counter()
        for index, (original_name, content, _is_dir) in enumerate(entries):
            self.counts["members"] += 1
            occurrence = occurrences[original_name]
            occurrences[original_name] += 1
            nested = [
                *segments,
                {"member_name": original_name, "occurrence": occurrence, "member_index": index},
            ]
            if self.counts["members"] > self.config.max_members:
                self.issue("member_count_limit", nested, limit=self.config.max_members)
                break
            if len(content) > self.config.max_member_bytes:
                self.issue("member_size_limit", nested, limit=self.config.max_member_bytes)
                continue
            if len(content) + self.counts["expanded_bytes"] > self.config.max_total_bytes:
                self.issue("expanded_size_limit", nested, limit=self.config.max_total_bytes)
                continue
            self.counts["expanded_bytes"] += len(content)
            self.counts["verified_members"] += 1
            name = original_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
            with self.member_buffer() as body:
                body.write(content)
                body.seek(0)
                if name == "logd.dat":
                    self.log_members += 1
                    self.lines(body, nested)
                elif (
                    content[:2] == b"PK"
                    or content[:6] == sevenzip.MAGIC
                    or name.endswith((".jez", ".zip"))
                ):
                    self.archive(body, nested)

    def lines(self, body, segments):
        line_number = 0
        while line := body.readline(self.config.max_line_bytes + 1):
            line_number += 1
            self.counts["lines"] += 1
            if self.counts["lines"] > self.config.max_lines:
                self.issue(
                    "line_count_limit", segments, line=line_number, limit=self.config.max_lines
                )
                return
            if len(line) > self.config.max_line_bytes:
                while not line.endswith(b"\n"):
                    line = body.readline(self.config.max_line_bytes + 1)
                    if not line:
                        break
                self.issue(
                    "line_size_limit", segments, line=line_number, limit=self.config.max_line_bytes
                )
                continue
            fields = line.decode("latin-1").rstrip("\r\n").split("\t")
            if len(fields) != 6:
                self.issue("malformed_columns", segments, line=line_number, field_count=len(fields))
                continue
            timestamp, level, device, app, message, _token = fields
            try:
                if not re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", timestamp):
                    raise ValueError
                datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                self.issue("invalid_timestamp", segments, line=line_number)
                continue
            # Only the dedicated device and application columns are selected.
            if not re.fullmatch(r"[0-9]{1,32}", device) or not re.fullmatch(
                r"[A-Z][A-Z0-9_-]{0,31}", app
            ):
                self.issue("invalid_device_or_application", segments, line=line_number)
                continue
            kind = MESSAGES.get(message, "unknown") if app == "VOTA" else "unknown"
            if kind == "unknown":
                self.issue("unsupported_message_class", segments, line=line_number, severity="info")
            locator = _locator(segments, line_number)
            _json_line(
                self.events,
                {
                    "event_id": identity(
                        "structural-event", [self.sha, locator, PARSER_VERSION, asdict(self.config)]
                    ),
                    "object_sha256": self.sha,
                    "record_locator": locator,
                    "source_sequence": self.counts["lines"],
                    "source_line_sha256": hashlib.sha256(line).hexdigest(),
                    "device_timestamp_raw": timestamp,
                    "device_id_raw": device,
                    "application": app,
                    "level": level
                    if level in {"INFO", "WARN", "WARNING", "ERROR", "DEBUG", "TRACE", "FATAL"}
                    else "unknown",
                    "event_kind": kind,
                    "selection_state": "context_unresolved",
                    "parser_version": PARSER_VERSION,
                },
            )
            self.counts["events"] += 1


def _write_checked(directory, name, value):
    encoded = canonical(value) + b"\n"
    with (directory / name).open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    with (directory / (name + ".sha256")).open("x") as stream:
        stream.write(hashlib.sha256(encoded).hexdigest() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_checked(directory, name):
    try:
        body = (directory / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != (directory / (name + ".sha256")).read_text().strip():
            raise ParseError("Derived metadata checksum mismatch")
        return json.loads(body)
    except (OSError, ValueError) as exc:
        raise ParseError("Incomplete or corrupt derived metadata") from exc


def inspect_artifact(path):
    """Verify metadata, cache identity and every streamed artifact on each cache hit."""
    path = Path(path)
    document = _read_checked(path, "artifact.json")
    try:
        key = digest([document["object_sha256"], document["parser_version"], document["config"]])
        if (
            document["format_version"] != ARTIFACT_FORMAT
            or key != document["cache_key"]
            or path.name != key
        ):
            raise ParseError("Derived cache identity mismatch")
        ParseConfig(**document["config"])
        for name in ("events.jsonl", "issues.jsonl"):
            sha, length = hash_file(path / name)
            if {"sha256": sha, "byte_length": length} != document["files"][name]:
                raise ParseError("Derived content checksum mismatch")
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise ParseError("Invalid or corrupt content artifact") from exc
    return document


def parse_object(source, store, *, config=None, expected_sha256=None):
    """Parse one immutable object into store/cache/KEY; return (path, cache_hit).

    Internal/fixture API: production callers use parse_snapshot, which checks
    frozen membership and never reads live acquisition inventory paths.
    """
    source, store = Path(source).resolve(), Path(store).resolve()
    config = config or ParseConfig()
    sha, _length = hash_file(source)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ParseError("Frozen object digest mismatch")
    key = digest([sha, PARSER_VERSION, asdict(config)])
    cache = store / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / key
    with (cache / f".parse-{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            try:
                inspect_artifact(target)
                return target, True
            except ParseError:
                # Preserve corrupt evidence; a completed immutable artifact is never patched.
                target.rename(cache / f".corrupt-{key}-{uuid.uuid4().hex}")
                _fsync_directory(cache)
        temporary = Path(tempfile.mkdtemp(prefix=".parse-building-", dir=cache))
        try:
            with (
                (temporary / "events.jsonl").open("xb") as events,
                (temporary / "issues.jsonl").open("xb") as issues,
            ):
                parser = _Parser(sha, config, temporary, events, issues)
                with source.open("rb") as original:
                    parser.archive(original)
                if not parser.log_members:
                    parser.issue("missing_log_member", [])
                for stream in (events, issues):
                    stream.flush()
                    os.fsync(stream.fileno())
            # Verify the exact source again; mutation can never publish under an old hash.
            if hash_file(source)[0] != sha:
                raise ParseError("Input changed during parsing")
            files = {}
            for name in ("events.jsonl", "issues.jsonl"):
                file_sha, length = hash_file(temporary / name)
                files[name] = {"sha256": file_sha, "byte_length": length}
            _write_checked(
                temporary,
                "artifact.json",
                {
                    "format_version": ARTIFACT_FORMAT,
                    "cache_key": key,
                    "object_sha256": sha,
                    "parser_version": PARSER_VERSION,
                    "config": asdict(config),
                    "files": files,
                    "counts": dict(parser.counts),
                    "log_members": parser.log_members,
                    "status": "partial" if parser.incomplete else "complete",
                    "interpretation": "structural messages only; sessions, rounds and votes unresolved",
                },
            )
            _fsync_directory(temporary)
            temporary.rename(target)
            _fsync_directory(cache)
        except BaseException:
            shutil.rmtree(temporary)
            raise
    return target, False


def _is_log_name(name):
    return name.lower().endswith(("log.dat", ".jez", ".zip"))


def parse_snapshot(snapshot, store, *, config=None, workers=4):
    """Publish frozen snapshot associations separately from reusable content cache."""
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ParseError("Parser workers must be between 1 and 64")
    snapshot, store = Path(snapshot).resolve(), Path(store).resolve()
    if snapshot.name == "snapshot.json":
        snapshot = snapshot.parent
    if store == snapshot or store.is_relative_to(snapshot):
        raise ParseError("Derived store must be outside the immutable snapshot")
    document = inspect_snapshot(snapshot, verify_objects=True)
    # Never write to the original acquisition root, even if explicitly requested.
    raw_root = Path(document["payload"]["inventory"]["source_root"]).resolve()
    if store == raw_root or store.is_relative_to(raw_root):
        raise ParseError("Derived store must be outside the acquisition root")
    tables = snapshot_tables(document)
    config = config or ParseConfig()
    observations = {row["observation_id"]: row for row in tables["source_observation"]}
    selected = {
        row["observation_id"]
        for row in observations.values()
        if _is_log_name(unquote(urlsplit(row["official_url"]).path))
    }
    assets = tables.get("package_asset", [])
    selected.update(row["asset_observation_id"] for row in assets if _is_log_name(row["filename"]))
    selected.discard(None)
    hashes = {observations[key]["object_sha256"] for key in selected}
    hashes.discard(None)

    def parse_row(row):
        path, _hit = parse_object(
            safe_source(snapshot, row["storage_locator"]),
            store,
            config=config,
            expected_sha256=row["object_sha256"],
        )
        return {"object_sha256": row["object_sha256"], "cache_key": path.name}

    objects = sorted(
        (row for row in tables["source_object"] if row["object_sha256"] in hashes),
        key=lambda row: row["object_sha256"],
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        artifacts = list(executor.map(parse_row, objects, buffersize=workers))
    associations = []
    for row in observations.values():
        if row["observation_id"] in selected or row["object_sha256"] in hashes:
            associations.append(
                {
                    "observation": row,
                    "package_assets": [
                        asset
                        for asset in assets
                        if asset["asset_observation_id"] == row["observation_id"]
                    ],
                }
            )
    publication = {
        "format_version": PUBLICATION_FORMAT,
        "snapshot_id": document["snapshot"]["snapshot_id"],
        "snapshot_inventory_sha256": document["snapshot"]["inventory_sha256"],
        "parser_version": PARSER_VERSION,
        "config": asdict(config),
        "artifacts": artifacts,
        "associations": associations,
        "historical_advertisements": document["payload"]["inventory"]["historical_advertisements"],
        "context_tables": {
            name: tables.get(name, [])
            for name in (
                "election",
                "section",
                "source_package",
                "package_observation",
                "section_composition",
                "coverage_ledger",
                "source_object",
                "source_observation",
                "snapshot",
                "snapshot_observation",
                "package_asset",
                "location",
            )
        },
        "unobserved_package_assets": [
            row
            for row in assets
            if _is_log_name(row["filename"]) and row["asset_observation_id"] is None
        ],
        "population_scope": document["snapshot"]["population_scope"],
        "coverage_summary": document["payload"]["coverage_summary"],
        "section_evidence": document["payload"]["section_evidence"],
        "context_lineage": tables.get("record_lineage", []),
    }
    key = digest(publication)
    directory = store / "parses"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    with (directory / ".publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            if inspect_parse(target) != publication:
                raise ParseError("Existing parse publication identity mismatch")
            return target
        temporary = Path(tempfile.mkdtemp(prefix=".parse-building-", dir=directory))
        try:
            _write_checked(temporary, "parse.json", publication)
            _fsync_directory(temporary)
            temporary.rename(target)
            _fsync_directory(directory)
        except BaseException:
            shutil.rmtree(temporary)
            raise
    return target


def inspect_parse(path, *, object_sha256=None):
    """Verify a publication and its cached content without opening any snapshot/raw input."""
    path = Path(path)
    document = _read_checked(path, "parse.json")
    try:
        if document["format_version"] != PUBLICATION_FORMAT or digest(document) != path.name:
            raise ParseError("Parse publication identity mismatch")
        selected = None if object_sha256 is None else set(object_sha256)
        if selected is not None and not selected <= {
            item["object_sha256"] for item in document["artifacts"]
        }:
            raise ParseError("Unknown selected parse object")
        for artifact in document["artifacts"]:
            if selected is not None and artifact["object_sha256"] not in selected:
                continue
            parsed = inspect_artifact(path.parent.parent / "cache" / artifact["cache_key"])
            if (
                parsed["object_sha256"] != artifact["object_sha256"]
                or parsed["parser_version"] != document["parser_version"]
                or parsed["config"] != document["config"]
            ):
                raise ParseError("Parse content reference mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise ParseError("Invalid parse publication") from exc
    return document


class FrozenParseReader:
    """Load verified immutable publication metadata once for bounded content groups.

    Each group verifies its content files once, then exposes event/issue streams.
    Keep this reader alive across shard publications to avoid reloading metadata.
    The document is read-only by convention; callers must never mutate it.
    """

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.document = inspect_parse(self.path, object_sha256=[])
        self.artifacts = {item["object_sha256"]: item for item in self.document["artifacts"]}
        self.associations = {}
        for row in self.document["associations"]:
            self.associations.setdefault(row["observation"]["object_sha256"], []).append(row)

    def group(self, object_sha256=None):
        selected = set(self.artifacts) if object_sha256 is None else set(object_sha256)
        if not selected <= self.artifacts.keys():
            raise ParseError("Unknown selected parse object")
        artifacts = [self.artifacts[key] for key in sorted(selected)]
        for artifact in artifacts:
            parsed = inspect_artifact(self.path.parent.parent / "cache" / artifact["cache_key"])
            if (parsed["object_sha256"], parsed["parser_version"], parsed["config"]) != (
                artifact["object_sha256"],
                self.document["parser_version"],
                self.document["config"],
            ):
                raise ParseError("Parse content reference mismatch")
        return (
            _event_witnesses(self.path, self.document, artifacts, self.associations),
            _parsing_issues(self.path, self.document, artifacts),
        )


def _rows(path):
    with Path(path).open("rb") as stream:
        for line in stream:
            yield json.loads(line)


def iter_event_witnesses(path, *, object_sha256=None):
    """Stream one witness per original observation/line, retaining all package assets.

    Content event_id is shared by identical bytes; witness_event_id is scoped to
    snapshot+observation. Neither identity deduplicates by message or timestamp.
    """
    path = Path(path)
    selected = None if object_sha256 is None else set(object_sha256)
    document = inspect_parse(path, object_sha256=selected)
    artifacts = [
        item
        for item in document["artifacts"]
        if selected is None or item["object_sha256"] in selected
    ]
    associations = {}
    for row in document["associations"]:
        associations.setdefault(row["observation"]["object_sha256"], []).append(row)
    yield from _event_witnesses(path, document, artifacts, associations)


def _event_witnesses(path, document, artifacts, associations):
    for artifact in artifacts:
        for event in _rows(path.parent.parent / "cache" / artifact["cache_key"] / "events.jsonl"):
            for association in associations.get(artifact["object_sha256"], []):
                observation_id = association["observation"]["observation_id"]
                yield {
                    **event,
                    "snapshot_id": document["snapshot_id"],
                    "observation_id": observation_id,
                    "witness_event_id": identity(
                        "event-witness",
                        [document["snapshot_id"], observation_id, event["event_id"]],
                    ),
                    "package_assets": association["package_assets"],
                }


def iter_lineage(path):
    """Contract-shaped original-record links, one per event witness/observation."""
    for event in iter_event_witnesses(path):
        yield {
            "derived_table": "parsed_event_witness",
            "derived_key": canonical([event["witness_event_id"]]).decode(),
            "object_sha256": event["object_sha256"],
            "record_locator": canonical(event["record_locator"]).decode(),
            "transformation_version": PARSER_VERSION,
            "observation_id": event["observation_id"],
            "lineage_role": "input",
        }


def iter_parsing_issues(path, *, object_sha256=None):
    """Stream snapshot-bound parsing_issue contract rows from content diagnostics."""
    path = Path(path)
    selected = None if object_sha256 is None else set(object_sha256)
    document = inspect_parse(path, object_sha256=selected)
    artifacts = [
        item
        for item in document["artifacts"]
        if selected is None or item["object_sha256"] in selected
    ]
    yield from _parsing_issues(path, document, artifacts)


def _parsing_issues(path, document, artifacts):
    for artifact in artifacts:
        for index, issue in enumerate(
            _rows(path.parent.parent / "cache" / artifact["cache_key"] / "issues.jsonl")
        ):
            yield {
                "issue_id": identity(
                    "parsing-issue", [document["snapshot_id"], artifact["cache_key"], index]
                ),
                "snapshot_id": document["snapshot_id"],
                "object_sha256": artifact["object_sha256"],
                "record_locator": canonical(issue["record_locator"]).decode(),
                "issue_code": issue["issue_code"],
                "severity": issue["severity"],
                "details": canonical(issue["details"]).decode(),
            }


def parse_main(argv=None):
    parser = argparse.ArgumentParser(description="Parse frozen JEZ/ZIP logs into structural events")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--store", type=Path, required=True)
    for name, value in asdict(ParseConfig()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=value)
    args = parser.parse_args(argv)
    try:
        config = ParseConfig(**{name: getattr(args, name) for name in asdict(ParseConfig())})
        result = parse_snapshot(args.snapshot, args.store, config=config, workers=args.workers)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(result)
    return 0
