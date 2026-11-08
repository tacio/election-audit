"""I6 prefix re-read: round-1 blocks of runoff logs checked line by line (Phase 20b).

Phase 21 kept one SHA-256 fingerprint per stream context segment, so I6
(``integrity-logs-v1``) could only say that a runoff log's round-1 block equals the
round-1 log's block when both have the same length. The last round-1 block of a
round-1 log keeps growing in the runoff log, and a few closed blocks differ in
length, so those were reported ``open_prefix_unverified`` or ``differs``.

This pass re-reads, from the certified staging, only objects the Phase 21 releases
already read (the protected/stress logs stay unread) and rebuilds each stream and
segment from the recorded line counts. Every rebuilt segment must reproduce its
recorded fingerprint and first-line hash before its prefix is trusted. For each
block pair whose lengths differ, the longer block's first N lines are hashed and
compared with the shorter block's fingerprint. Pairs that still differ are read on
both sides and described by their common prefix and suffix and digit-masked
templates of the differing lines; no voter, poll-worker or token value is exported.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import shutil
import time
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.national_migration import atomic, sha
from election_audit.semantic_pass import (
    DIGITS,
    HEXRUN,
    MAX_LINE,
    MAX_LINES,
    iso_reading,
    log_members,
    reading_seconds,
)
from election_audit.types import JSON

type Target = tuple[int, int, Collection[int], bool]
type LineRecord = tuple[str, str, str, str]

VERSION = "integrity-round1-prefix-v1"
CHUNK_OBJECTS = 2000
DETAIL_LINES = 5
MAX_CANDIDATES = 1000

BLOCKS_SQL = """
WITH o1 AS (
    SELECT object_sha256, path, witnesses_json FROM read_parquet($first_objects)
    WHERE status = 'complete'
), o2 AS (
    SELECT object_sha256, path, witnesses_json FROM read_parquet($runoff_objects)
    WHERE status = 'complete'
), w1 AS (
    SELECT object_sha256, path,
           array_to_string(unnest(from_json(witnesses_json, '[["VARCHAR"]]')), '/') AS w
    FROM o1
), w2 AS (
    SELECT object_sha256, path,
           array_to_string(unnest(from_json(witnesses_json, '[["VARCHAR"]]')), '/') AS w
    FROM o2
), s1 AS (
    SELECT *,
           coalesce(sum(lines) OVER (PARTITION BY object_sha256, stream_ordinal
                                     ORDER BY segment_ordinal
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)
               AS line_offset,
           row_number() OVER (PARTITION BY object_sha256, stream_ordinal
                              ORDER BY segment_ordinal DESC) = 1 AS is_last
    FROM read_parquet($first_segments) WHERE object_sha256 IN (SELECT object_sha256 FROM o1)
), s2 AS (
    SELECT *,
           coalesce(sum(lines) OVER (PARTITION BY object_sha256, stream_ordinal
                                     ORDER BY segment_ordinal
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)
               AS line_offset
    FROM read_parquet($runoff_segments) WHERE object_sha256 IN (SELECT object_sha256 FROM o2)
), b1 AS (
    SELECT w, path, s1.* FROM s1 JOIN w1 USING (object_sha256)
    WHERE context = 'official_round_1' AND ($ufs IS NULL OR list_contains($ufs, split_part(w, '/', 1)))
), b2 AS (
    SELECT w, path, s2.* FROM s2 JOIN w2 USING (object_sha256)
    WHERE context = 'official_round_1' AND ($ufs IS NULL OR list_contains($ufs, split_part(w, '/', 1)))
)
"""

PAIRS_SQL = (
    BLOCKS_SQL
    + """
SELECT b1.w, b1.device_id,
       b1.object_sha256, b1.path, b1.stream_ordinal, b1.segment_ordinal, b1.line_offset,
       b1.lines, b1.fingerprint, b1.first_line_sha256, b1.is_last,
       b2.object_sha256, b2.path, b2.stream_ordinal, b2.segment_ordinal, b2.line_offset,
       b2.lines, b2.fingerprint
FROM b1 JOIN b2 ON b1.w = b2.w AND b1.device_id = b2.device_id
               AND b1.first_line_sha256 = b2.first_line_sha256
WHERE NOT (b1.fingerprint = b2.fingerprint AND b1.lines = b2.lines)
ORDER BY ALL
"""
)

SECTIONS_SQL = (
    BLOCKS_SQL
    + """
, eq_blocks AS (
    SELECT b1.w, count(*) AS n FROM b1 JOIN b2
        ON b1.w = b2.w AND b1.device_id = b2.device_id
       AND b1.first_line_sha256 = b2.first_line_sha256
    WHERE b1.fingerprint = b2.fingerprint AND b1.lines = b2.lines GROUP BY ALL
), missing_blocks AS (
    SELECT w, count(*) AS n FROM b1 WHERE NOT EXISTS (
        SELECT 1 FROM b2 WHERE b1.w = b2.w AND b1.device_id = b2.device_id
                           AND b1.first_line_sha256 = b2.first_line_sha256)
    GROUP BY ALL
), round1_end AS (
    SELECT w, device_id, max(last_reading) AS last_reading FROM b1 GROUP BY ALL
), extra_blocks AS (
    SELECT b2.w, count(*) AS n,
           count(*) FILTER (WHERE b2.first_reading > e.last_reading) AS after_end,
           sum(b2.lines) AS lines
    FROM b2 LEFT JOIN round1_end e ON b2.w = e.w AND b2.device_id = e.device_id
    WHERE NOT EXISTS (
        SELECT 1 FROM b1 WHERE b1.w = b2.w AND b1.device_id = b2.device_id
                           AND b1.first_line_sha256 = b2.first_line_sha256)
    GROUP BY ALL
), devices AS (
    SELECT coalesce(d1.w, d2.w) AS w, count(d1.w) > 0 AS has_first, count(d2.w) > 0 AS has_runoff,
           count(*) FILTER (WHERE d1.w IS NOT NULL AND d2.w IS NOT NULL) > 0 AS common_device
    FROM (SELECT DISTINCT w, device_id FROM b1) d1
    FULL JOIN (SELECT DISTINCT w, device_id FROM b2) d2
        ON d1.w = d2.w AND d1.device_id = d2.device_id
    GROUP BY ALL
)
SELECT d.w, d.has_first, d.has_runoff, d.common_device,
       coalesce(e.n, 0), coalesce(m.n, 0), coalesce(x.n, 0),
       coalesce(x.after_end, 0), coalesce(x.lines, 0)
FROM devices d LEFT JOIN eq_blocks e USING (w) LEFT JOIN missing_blocks m USING (w)
     LEFT JOIN extra_blocks x USING (w)
ORDER BY 1
"""
)

PAIR_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("round1_object_sha256", pa.string()),
        ("round1_stream", pa.int32()),
        ("round1_segment", pa.int32()),
        ("round1_lines", pa.int64()),
        ("round1_is_last", pa.bool_()),
        ("runoff_object_sha256", pa.string()),
        ("runoff_stream", pa.int32()),
        ("runoff_segment", pa.int32()),
        ("runoff_lines", pa.int64()),
        # prefix_open | prefix_closed | runoff_prefix_of_round1 | differs | realignment_failed
        ("status", pa.string()),
        ("common_prefix", pa.int64()),
        ("realigned_lines", pa.int64()),  # round-1 lines found again after the difference
        ("runoff_tail_lines", pa.int64()),
        ("diff_kind", pa.string()),  # insertion_in_runoff | deletion_in_runoff | replacement
    ]
)

SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("i6_v1", pa.string()),
        ("i6", pa.string()),
        ("blocks_equal", pa.int32()),
        ("blocks_prefix_open", pa.int32()),
        ("blocks_prefix_closed", pa.int32()),
        ("blocks_runoff_prefix_of_round1", pa.int32()),
        ("blocks_differs", pa.int32()),
        ("blocks_missing_in_runoff", pa.int32()),
        ("blocks_extra_in_runoff", pa.int32()),
        ("extra_blocks_after_round1_log_end", pa.int32()),
        ("extra_block_lines", pa.int64()),
    ]
)


def template(application: str, message: str) -> tuple[str, str]:
    """The semantic pass's digit-masked vocabulary template."""
    return application, HEXRUN.sub("<hex>", DIGITS.sub("#", message))[:200]


class _Target:
    __slots__ = ("offset", "lines", "prefixes", "keep", "hash", "seen", "first", "found", "records")

    def __init__(self, offset: int, lines: int, prefixes: Collection[int], keep: bool) -> None:
        self.offset, self.lines, self.prefixes, self.keep = offset, lines, set(prefixes), keep
        self.hash, self.seen, self.first, self.found, self.records = (
            hashlib.sha256(),
            0,
            None,
            {},
            [],
        )


def scan(source: bytes, targets: dict[tuple[int, int], Target]) -> dict[tuple[int, int], JSON]:
    """Rebuild segments of one log object and hash the requested line ranges.

    ``targets`` maps ``(stream_ordinal, segment_ordinal)`` to ``(line_offset, lines,
    prefixes, keep)``. Streams and well-formed lines follow ``ObjectSummary.feed``
    exactly: a stream is a run of lines with the same member path and device, and
    lines with a wrong field count or an invalid reading are skipped. Returns, per
    target, the lines seen, the fingerprint, the first-line hash, the prefix hashes
    and, when ``keep``, one (line hash, reading, application, template) per line.
    """
    states = {key: _Target(*value) for key, value in targets.items()}
    by_stream = defaultdict(list)
    for (stream, _), state in states.items():
        by_stream[stream].append(state)
    stream, key, index, total, active = -1, None, 0, 0, ()
    for segments, body in log_members(source):
        parts = body.split(b"\n")
        last = parts.pop()
        for line in [x + b"\n" for x in parts] + ([last] if last else []):
            total += 1
            if len(line) > MAX_LINE or total > MAX_LINES:
                raise ValueError("Line bound exceeded")
            fields = line.rstrip(b"\r\n").split(b"\t")
            if len(fields) != 6:
                continue
            reading = reading_seconds(fields[0].decode("latin-1"))
            if reading is None:
                continue
            if (segments, fields[2]) != key:
                key = (segments, fields[2])
                stream += 1
                index = 0
                active = by_stream.get(stream, ())
            for state in active:
                if state.offset <= index < state.offset + state.lines:
                    if state.seen == 0:
                        state.first = hashlib.sha256(line).hexdigest()
                    state.hash.update(line)
                    state.seen += 1
                    if state.seen in state.prefixes:
                        state.found[state.seen] = state.hash.hexdigest()
                    if state.keep:
                        state.records.append(
                            (
                                hashlib.sha256(line).hexdigest(),
                                iso_reading(reading),
                                *template(fields[3].decode("latin-1"), fields[4].decode("latin-1")),
                            )
                        )
            index += 1
    return {
        key: {
            "seen": state.seen,
            "fingerprint": state.hash.hexdigest(),
            "first_line_sha256": state.first,
            "prefixes": state.found,
            "records": state.records,
        }
        for key, state in states.items()
    }


def read_object(staged_root: str | Path, path: str, object_sha256: str) -> bytes:
    body = (Path(staged_root) / path).read_bytes()
    if hashlib.sha256(body).hexdigest() != object_sha256:
        raise ValueError(f"Staged object differs from its certified hash: {path}")
    return body


def run_chunk(
    task: tuple[str, int, list[tuple[str, str, str, list[list[Any]]]]],
) -> tuple[int, int, int]:
    """Prefix hashes for one chunk of objects; written as one atomic JSON shard."""
    shard_dir, index, items = task
    results = []
    for staged_root, path, digest, targets in items:
        wanted = {
            (stream, segment): (offset, lines, prefixes, False)
            for stream, segment, offset, lines, prefixes in targets
        }
        try:
            found = scan(read_object(staged_root, path, digest), wanted)
        except Exception as exc:  # recorded per object
            results.append([digest, None, f"{type(exc).__name__}: {exc}"[:300]])
            continue
        results.append(
            [
                digest,
                [
                    [s, g, r["seen"], r["fingerprint"], r["first_line_sha256"], r["prefixes"]]
                    for (s, g), r in sorted(found.items())
                ],
                None,
            ]
        )
    atomic(Path(shard_dir) / f"{index:05d}.json", results)
    return index, len(items), sum(r[2] is not None for r in results)


def _init_worker() -> None:
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def _release(root: str | Path) -> tuple[Path, JSON]:
    """A finished semantic or logs release whose files still match its manifest."""
    release = Path(root).expanduser().absolute() / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if entry["sha256"] != sha(release / name):
            raise ValueError(f"Release file changed: {release / name}")
    return release, manifest


def _staged_root(semantic_root: str | Path) -> tuple[Path, JSON]:
    root = Path(semantic_root).expanduser().absolute()
    binding = json.loads((root / "binding.json").read_text())
    staged = Path(binding["staged_root"])
    if sha(staged / "staging-certificate.json") != binding["staging_certificate_sha256"]:
        raise ValueError(f"Staging certificate changed: {staged}")
    return staged, binding


def compare(pair: JSON, side_results: JSON) -> str:
    """Status of one block pair from the re-read results of its longer side."""
    l1, l2 = pair["round1_lines"], pair["runoff_lines"]
    if l1 == l2:
        return "differs"
    if l2 > l1:
        found = side_results.get((pair["runoff_object_sha256"], pair["r2_key"]))
        expected_full, expected_first, short_fp, n = (
            pair["runoff_fingerprint"],
            pair["first_line_sha256"],
            pair["round1_fingerprint"],
            l1,
        )
    else:
        found = side_results.get((pair["round1_object_sha256"], pair["r1_key"]))
        expected_full, expected_first, short_fp, n = (
            pair["round1_fingerprint"],
            pair["first_line_sha256"],
            pair["runoff_fingerprint"],
            l2,
        )
    if found is None:
        return "realignment_failed"
    seen, fingerprint, first, prefixes = found
    if (seen, fingerprint, first) != (max(l1, l2), expected_full, expected_first):
        return "realignment_failed"
    if prefixes.get(str(n), prefixes.get(n)) != short_fp:
        return "differs"
    if l2 < l1:
        return "runoff_prefix_of_round1"
    return "prefix_open" if pair["round1_is_last"] else "prefix_closed"


def _resume(a: Sequence[Any], b: Sequence[Any], k: int) -> int | None:
    """First j > k where all of ``a[k:]`` reappears in ``b`` starting at j, or None."""
    rest = len(a) - k
    if rest <= 0:
        return None
    candidates = 0
    for j in range(k + 1, len(b) - rest + 1):
        if b[j] == a[k]:
            candidates += 1
            if b[j : j + rest] == a[k:]:
                return j
            if candidates >= MAX_CANDIDATES:
                return None
    return None


def describe(
    r1_records: Sequence[Sequence[Any]], r2_records: Sequence[Sequence[Any]]
) -> tuple[int, int, str, JSON]:
    """Where two blocks part and whether the round-1 lines resume afterwards.

    ``insertion_in_runoff``: every round-1 line after the common prefix reappears,
    in order and contiguous, later in the runoff block. ``deletion_in_runoff``: the
    runoff block resumes with the round-1 block's last lines after skipping some.
    Otherwise ``replacement``, aligned on the common suffix. The runoff block may
    continue after the aligned lines (``runoff_tail_lines``), as an open block does.
    """
    a = [r[0] for r in r1_records]
    b = [r[0] for r in r2_records]
    limit = min(len(a), len(b))
    k = 0
    while k < limit and a[k] == b[k]:
        k += 1
    inserted = _resume(a, b, k)
    deleted = None
    if inserted is None and k < len(b):
        # a = prefix + removed + b[k : k + rest]: find the start of the kept tail in a.
        for j in range(k + 1, len(a)):
            rest = len(a) - j
            if rest <= len(b) - k and a[j] == b[k] and a[j:] == b[k : k + rest]:
                deleted = j
                break
    if inserted is not None:
        kind, r1_middle, r2_middle = "insertion_in_runoff", (k, k), (k, inserted)
        realigned = len(a) - k
        tail = len(b) - inserted - realigned
    elif deleted is not None:
        kind, r1_middle, r2_middle = "deletion_in_runoff", (k, deleted), (k, k)
        realigned = len(a) - deleted
        tail = len(b) - k - realigned
    else:
        m = 0
        while m < limit - k and a[len(a) - 1 - m] == b[len(b) - 1 - m]:
            m += 1
        kind, r1_middle, r2_middle = "replacement", (k, len(a) - m), (k, len(b) - m)
        realigned, tail = m, 0

    def side(records: Sequence[Sequence[Any]], span: tuple[int, int]) -> JSON:
        middle = records[span[0] : span[1]]
        return {
            "lines": len(middle),
            "first_reading": middle[0][1] if middle else None,
            "last_reading": middle[-1][1] if middle else None,
            "first_lines": [[r[1], r[2], r[3]] for r in middle[:DETAIL_LINES]],
            "templates": [
                [app, tpl, n]
                for (app, tpl), n in Counter((r[2], r[3]) for r in middle).most_common(10)
            ],
        }

    detail = {
        "last_common_reading": r1_records[k - 1][1] if k else None,
        "round1": side(r1_records, r1_middle),
        "runoff": side(r2_records, r2_middle),
        "runoff_tail_lines": tail,
        "runoff_tail_first_reading": r2_records[len(b) - tail][1] if tail else None,
    }
    return k, realigned, kind, detail


def run_prefix(
    logs_root: str | Path,
    semantic_root: str | Path,
    semantic_round1: str | Path,
    output: str | Path,
    *,
    workers: int = 4,
    ufs: Collection[str] | None = None,
    chunk_objects: int = CHUNK_OBJECTS,
    resume: bool = False,
    memory_limit: str = "2GB",
) -> JSON:
    """I6 with verified prefixes for every round-1 block pair of different length."""
    import duckdb

    output = Path(output).expanduser().absolute()
    if workers < 1 or workers > max(1, (os.cpu_count() or 2) // 2):
        raise ValueError("Workers must stay within half the CPUs")
    logs_release, logs_manifest = _release(logs_root)
    runoff, runoff_manifest = _release(semantic_root)
    first, first_manifest = _release(semantic_round1)
    if (runoff_manifest["round"], first_manifest["round"], logs_manifest["round"]) != (2, 1, 2):
        raise ValueError(
            "Give the round-2 logs release and the round-2 and round-1 semantic passes"
        )
    if logs_manifest["semantic_manifest_sha256"] != sha(runoff / "manifest.json") or logs_manifest[
        "semantic_round1_manifest_sha256"
    ] != sha(first / "manifest.json"):
        raise ValueError("The logs release was built from other semantic passes")
    staged = {}
    staged[2], runoff_binding = _staged_root(semantic_root)
    staged[1], first_binding = _staged_root(semantic_round1)
    if runoff_binding["round"] != 2 or first_binding["round"] != 1:
        raise ValueError("Staged roots belong to other rounds")
    binding = {
        "version": VERSION,
        "logs_manifest_sha256": sha(logs_release / "manifest.json"),
        "semantic_manifest_sha256": sha(runoff / "manifest.json"),
        "semantic_round1_manifest_sha256": sha(first / "manifest.json"),
        "staging_certificate_sha256": {
            "1": first_binding["staging_certificate_sha256"],
            "2": runoff_binding["staging_certificate_sha256"],
        },
        "ufs": sorted(ufs) if ufs else None,
        "chunk_objects": chunk_objects,
        "reads": "only objects the Phase 21 releases read (protected/stress logs stay unread); "
        "each staged object is re-hashed against its certified SHA-256",
    }
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new (or pass --resume): {output}")
    if resume and json.loads((output / "binding.json").read_bytes()) != binding:
        raise ValueError("Resume binding differs from the original pass")
    output.mkdir(parents=True, exist_ok=resume)
    atomic(output / "binding.json", binding)
    started = time.monotonic()
    status_path = output / "status.json"

    def report(stage: str, **extra: Any) -> None:
        atomic(
            status_path,
            {
                "stage": stage,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "pid": os.getpid(),
                **extra,
            },
        )

    report("planning")
    params = {
        "first_objects": str(first / "objects.parquet"),
        "runoff_objects": str(runoff / "objects.parquet"),
        "first_segments": str(first / "segments.parquet"),
        "runoff_segments": str(runoff / "segments.parquet"),
        "ufs": sorted(ufs) if ufs else None,
    }
    with duckdb.connect() as db:
        db.execute(f"SET memory_limit = '{memory_limit}'")
        db.execute("SET threads = 2")
        raw_pairs = db.execute(PAIRS_SQL, params).fetchall()
        section_rows = db.execute(SECTIONS_SQL, params).fetchall()
    pairs: list[JSON] = []
    for row in raw_pairs:
        (w, _device, o1, p1, st1, sg1, off1, l1, fp1, first_sha, is_last,
         o2, p2, st2, sg2, off2, l2, fp2) = row  # fmt: skip
        pairs.append(
            {
                "w": w,
                "round1_object_sha256": o1,
                "round1_path": p1,
                "r1_key": (st1, sg1),
                "r1_offset": off1,
                "round1_lines": l1,
                "round1_fingerprint": fp1,
                "first_line_sha256": first_sha,
                "round1_is_last": is_last,
                "runoff_object_sha256": o2,
                "runoff_path": p2,
                "r2_key": (st2, sg2),
                "r2_offset": off2,
                "runoff_lines": l2,
                "runoff_fingerprint": fp2,
            }
        )
    # One read per object: (round, object) -> {(stream, segment): (offset, lines, prefixes)}
    work: defaultdict[tuple[int, str, str], defaultdict[tuple[int, int], list[Any]]] = defaultdict(
        lambda: defaultdict(lambda: [None, None, set()])
    )
    for p in pairs:
        if p["runoff_lines"] > p["round1_lines"]:
            spec = work[(2, p["runoff_object_sha256"], p["runoff_path"])][p["r2_key"]]
            spec[0], spec[1] = p["r2_offset"], p["runoff_lines"]
            spec[2].add(p["round1_lines"])
        elif p["runoff_lines"] < p["round1_lines"]:
            spec = work[(1, p["round1_object_sha256"], p["round1_path"])][p["r1_key"]]
            spec[0], spec[1] = p["r1_offset"], p["round1_lines"]
            spec[2].add(p["runoff_lines"])
    items = [
        (
            str(staged[round_number]),
            path,
            digest,
            [[s, g, off, n, sorted(prefixes)] for (s, g), (off, n, prefixes) in sorted(t.items())],
        )
        for (round_number, digest, path), t in sorted(work.items())
    ]
    chunks = [items[i : i + chunk_objects] for i in range(0, len(items), chunk_objects)]
    shard_dir = output / "shards"
    shard_dir.mkdir(exist_ok=True)
    done = {int(p.stem) for p in shard_dir.glob("[0-9]*.json")}
    todo = [i for i in range(len(chunks)) if i not in done]
    completed = sum(len(chunks[i]) for i in done if i < len(chunks))
    errors, session_done = 0, 0
    report("reading", objects_total=len(items), objects_done=completed, pairs=len(pairs))
    with multiprocessing.get_context("spawn").Pool(
        workers, initializer=_init_worker, maxtasksperchild=50
    ) as pool:
        tasks = ((str(shard_dir), i, chunks[i]) for i in todo)
        for _, count, failed in pool.imap_unordered(run_chunk, tasks):
            completed += count
            session_done += count
            errors += failed
            elapsed = time.monotonic() - started
            rate = session_done / elapsed if elapsed else 0
            report(
                "reading",
                objects_total=len(items),
                objects_done=completed,
                pairs=len(pairs),
                errors_this_session=errors,
                objects_per_second=round(rate, 1),
                eta_hours=round((len(items) - completed) / rate / 3600, 2) if rate else None,
            )
    report("comparing", objects_total=len(items), pairs=len(pairs))
    side_results, object_errors = {}, {}
    for index in range(len(chunks)):
        for digest, found, error in json.loads((shard_dir / f"{index:05d}.json").read_text()):
            if error is not None:
                object_errors[digest] = error
                continue
            for stream, segment, seen, fingerprint, first_sha, prefixes in found:
                side_results[(digest, (stream, segment))] = (seen, fingerprint, first_sha, prefixes)
    for p in pairs:
        p["status"] = compare(p, side_results)
    # Line-level description of every pair that still differs: both sides are read.
    details = []
    differing = [p for p in pairs if p["status"] == "differs"]
    cache = {}

    def records(
        round_number: int, digest: str, path: str, key: tuple[int, int], offset: int, lines: int
    ) -> None:
        wanted = (round_number, digest)
        targets = cache.setdefault(wanted, {"path": path, "targets": {}})["targets"]
        targets[key] = (offset, lines, (), True)

    for p in differing:
        records(1, p["round1_object_sha256"], p["round1_path"], p["r1_key"], p["r1_offset"],
                p["round1_lines"])  # fmt: skip
        records(2, p["runoff_object_sha256"], p["runoff_path"], p["r2_key"], p["r2_offset"],
                p["runoff_lines"])  # fmt: skip
    read = {}
    for (round_number, digest), spec in sorted(cache.items()):
        body = read_object(staged[round_number], spec["path"], digest)
        for key, value in scan(body, spec["targets"]).items():
            read[(digest, key)] = value
    for p in differing:
        a = read[(p["round1_object_sha256"], p["r1_key"])]
        b = read[(p["runoff_object_sha256"], p["r2_key"])]
        if (a["seen"], a["fingerprint"], b["seen"], b["fingerprint"]) != (
            p["round1_lines"],
            p["round1_fingerprint"],
            p["runoff_lines"],
            p["runoff_fingerprint"],
        ):
            p["status"] = "realignment_failed"
            continue
        k, m, kind, detail = describe(a["records"], b["records"])
        p.update(
            common_prefix=k,
            realigned_lines=m,
            runoff_tail_lines=detail["runoff_tail_lines"],
            diff_kind=kind,
        )
        uf, municipality, zone, section = p["w"].split("/")
        details.append(
            {
                "uf": uf,
                "municipality": municipality,
                "zone": zone,
                "section": section,
                "round1_object_sha256": p["round1_object_sha256"],
                "runoff_object_sha256": p["runoff_object_sha256"],
                "round1_lines": p["round1_lines"],
                "runoff_lines": p["runoff_lines"],
                "round1_is_last": p["round1_is_last"],
                "common_prefix": k,
                "realigned_lines": m,
                "diff_kind": kind,
                **detail,
            }
        )
    # Sections: the I6 statuses of the logs release, revised with the re-read pairs.
    per_section = defaultdict(Counter)
    for p in pairs:
        per_section[p["w"]][p["status"]] += 1
    logs_rows = pq.read_table(
        logs_release / "sections.parquet", columns=["uf", "municipality", "zone", "section", "i6"]
    ).to_pylist()
    facts = {row[0]: row[1:] for row in section_rows}
    sections: list[JSON] = []
    for r in logs_rows:
        if ufs and r["uf"] not in ufs:
            continue
        w = "/".join((r["uf"], r["municipality"], r["zone"], r["section"]))
        counts = per_section.get(w, Counter())
        fact = facts.get(w)
        row = {**r, "i6_v1": r["i6"]}
        for name in (
            "blocks_equal",
            "blocks_prefix_open",
            "blocks_prefix_closed",
            "blocks_runoff_prefix_of_round1",
            "blocks_differs",
            "blocks_missing_in_runoff",
            "blocks_extra_in_runoff",
            "extra_blocks_after_round1_log_end",
            "extra_block_lines",
        ):
            row[name] = None
        if fact is not None and row["i6_v1"] not in (None, "round1_log_unavailable"):
            has_first, has_runoff, common, equal, missing, extra, after_end, extra_lines = fact
            row.update(
                blocks_equal=equal,
                blocks_prefix_open=counts["prefix_open"],
                blocks_prefix_closed=counts["prefix_closed"],
                blocks_runoff_prefix_of_round1=counts["runoff_prefix_of_round1"],
                blocks_differs=counts["differs"] + counts["realignment_failed"],
                blocks_missing_in_runoff=missing,
                blocks_extra_in_runoff=extra,
                extra_blocks_after_round1_log_end=after_end,
                extra_block_lines=extra_lines,
            )
            if not has_runoff:
                row["i6"] = "no_round1_block_in_runoff_log"
            elif not has_first:
                row["i6"] = "no_round1_log_block"
            elif not common:
                row["i6"] = "different_device"
            else:
                states = {s for s, n in counts.items() if n}
                if equal:
                    states.add("equal")
                if missing:
                    states.add("missing_in_runoff")
                if extra:
                    states.add("extra_in_runoff")
                if states <= {"equal", "prefix_open"} and counts["prefix_open"] <= 1:
                    row["i6"] = "equal_open_prefix_equal" if counts["prefix_open"] else "equal"
                else:
                    row["i6"] = "+".join(sorted(states))
        sections.append(row)
    final = output / ".release.tmp"
    shutil.rmtree(final, ignore_errors=True)
    final.mkdir()
    pair_rows = []
    for p in pairs:
        uf, municipality, zone, section = p["w"].split("/")
        pair_rows.append(
            {
                "uf": uf,
                "municipality": municipality,
                "zone": zone,
                "section": section,
                "round1_object_sha256": p["round1_object_sha256"],
                "round1_stream": p["r1_key"][0],
                "round1_segment": p["r1_key"][1],
                "round1_lines": p["round1_lines"],
                "round1_is_last": p["round1_is_last"],
                "runoff_object_sha256": p["runoff_object_sha256"],
                "runoff_stream": p["r2_key"][0],
                "runoff_segment": p["r2_key"][1],
                "runoff_lines": p["runoff_lines"],
                "status": p["status"],
                "common_prefix": p.get("common_prefix"),
                "realigned_lines": p.get("realigned_lines"),
                "runoff_tail_lines": p.get("runoff_tail_lines"),
                "diff_kind": p.get("diff_kind"),
            }
        )
    pq.write_table(
        pa.Table.from_pylist(pair_rows, schema=PAIR_SCHEMA), final / "pairs.parquet",
        compression="zstd",
    )  # fmt: skip
    pq.write_table(
        pa.Table.from_pylist(sections, schema=SECTION_SCHEMA), final / "sections.parquet",
        compression="zstd",
    )  # fmt: skip
    (final / "differences.jsonl").write_text(
        "".join(json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n" for d in details)
    )
    summary = {
        "objects_read": len(items),
        "object_errors": len(object_errors),
        "pairs": len(pairs),
        "pair_status": dict(Counter(p["status"] for p in pairs)),
        "pair_status_by_round1_last": {
            "last": dict(Counter(p["status"] for p in pairs if p["round1_is_last"])),
            "closed": dict(Counter(p["status"] for p in pairs if not p["round1_is_last"])),
        },
        "diff_kind": dict(Counter(d["diff_kind"] for d in details)),
        "sections": len(sections),
        "i6": dict(Counter(str(s["i6"]) for s in sections)),
        "i6_v1_to_i6": dict(
            Counter(f"{s['i6_v1']} -> {s['i6']}" for s in sections if s["i6_v1"] != s["i6"])
        ),
        "extra_blocks": sum(s["blocks_extra_in_runoff"] or 0 for s in sections),
        "extra_blocks_after_round1_log_end": sum(
            s["extra_blocks_after_round1_log_end"] or 0 for s in sections
        ),
    }
    result = {
        **binding,
        "summary": summary,
        "object_errors": dict(sorted(object_errors.items())),
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
    }
    atomic(final / "manifest.json", result)
    shutil.rmtree(output / "release", ignore_errors=True)
    os.replace(final, output / "release")
    report("finished", objects_total=len(items), pairs=len(pairs))
    return result
