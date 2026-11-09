"""Phase 20b: the zerésima (zero-vote report) in every published log, against the votes.

Before polls open each urn prints the zerésima, a report that every count is zero. The
semantic pass (``session-aggregates-v5``) keeps one marker row per zerésima or readiness line,
with its stream, block, session, local clock reading and the number of vote cycles completed
earlier in the same block. This check reads those markers for the round's official blocks of
each section's log and applies:

- Z1: a section whose official blocks hold completed votes has a zerésima (``Gerando
  relatório [ZERÉSIMA] [INÍCIO]``); a log without official votes (no voting urn in the
  publication) is counted as ``no_official_votes``, not failed;
- Z2: no vote cycle was completed before the first zerésima of its stream (file order);
- Z3: every zerésima is dated on the election day (urn clock reading);
- Z4: no zerésima after a vote cycle was completed earlier in its stream (file order). An urn
  restarted before voting prints a new zerésima, and a replacement urn prints its own: several
  zerésimas per section are counted (by urn), not failed;
- Z5: no ``Urna pronta para receber votos`` before the first zerésima of its stream;
- Z6 (v3, xr1-20261109-P4-10): an urn with completed votes but no zerésima of its own starts
  its first voting session after another urn of the section printed one (urn clocks). This
  tests the premise under which such urns are not failed: that they replaced an urn that
  printed the zerésima. A session or zerésima without a reading is counted as unknown.

Counts per stream (votes before, readiness lines before) take the largest stream of the
section, so a block kept in both memories is not counted twice.

Copies of one block kept in both memories of an urn count once: a marker's identity is the
device, the block's first line and its rank among the block's markers of that kind. Urns with
completed votes but no zerésima of their own are counted, not failed: a contingency urn takes
over a section whose zerésima the replaced urn printed. Sections without a semantic-pass object
(protected, SA, unpublished) are unavailable and never read.
"""

import json
import os
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import integrity_checks as ic
from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.section_table import distinct_sessions
from election_audit.types import JSON, Row

VERSION = "integrity-zeresima-v3"  # v3: Z6, the replacement premise
SEMANTIC_VERSION = "session-aggregates-v5"
RULES = {
    "Z1": "a section with completed votes in its official blocks has a zerésima",
    "Z2": "no vote cycle completed before the first zerésima of its stream (file order)",
    "Z3": "every zerésima is dated on the election day",
    "Z4": "no zerésima after a vote cycle completed earlier in its stream (file order)",
    "Z5": "no 'Urna pronta para receber votos' before the first zerésima of its stream",
    "Z6": "an urn voting without its own zerésima starts voting after another urn printed one "
    "(urn clocks)",
}
MARKER_SQL = """
SELECT m.object_sha256, m.stream_ordinal, m.segment_ordinal, m.device_id, m.kind, m.line,
       m.reading, m.completions_before, g.first_line_sha256 AS block_start,
       row_number() OVER (PARTITION BY m.object_sha256, m.stream_ordinal, m.segment_ordinal,
                                       m.kind ORDER BY m.line) AS rank
FROM read_parquet($markers) m
JOIN read_parquet($segments) g USING (object_sha256, stream_ordinal, segment_ordinal)
WHERE g.context = $context AND m.kind IN ('zeresima_start', 'ready')
"""
SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("log", pa.string()),  # semantic | protected_or_unavailable | error
        ("zeresimas", pa.int32()),
        ("votes_before_first", pa.int32()),
        ("zeresimas_off_day", pa.int32()),
        ("ready_before_zeresima", pa.int32()),
        ("devices_with_votes", pa.int32()),
        ("devices_with_votes_without_zeresima", pa.int32()),
        ("zeresima_devices", pa.int32()),
        ("zeresimas_after_votes", pa.int32()),
        ("devices_voting_before_any_zeresima", pa.int32()),  # Z6
        ("devices_replacement_order_unknown", pa.int32()),  # Z6 without a reading
        ("failed_json", pa.string()),
    ]
)


def _markers(release: Path, round_number: int, memory_limit: str) -> dict[str, list[Row]]:
    import duckdb

    with duckdb.connect() as db:
        db.execute(f"SET memory_limit = '{memory_limit}'")
        db.execute("SET threads = 2")
        cursor = db.execute(
            MARKER_SQL,
            {
                "markers": str(release / "markers.parquet"),
                "segments": str(release / "segments.parquet"),
                "context": f"official_round_{round_number}",
            },
        )
        names = [d[0] for d in cursor.description]
        out = defaultdict(list)
        for values in cursor.fetchall():
            row = dict(zip(names, values, strict=True))
            out[row["object_sha256"]].append(row)
    return out


def _completed(session: Row) -> int:
    return sum(session[f"cycles_completed_{m}"] for m in ("biometric", "manual", "unknown"))


def section_rules(
    markers: Sequence[Row],
    sessions: Sequence[Row],
    election_date: str,
    stream_sessions: Sequence[Row] | None = None,
) -> Row:
    """Z1-Z5 for one section from its round markers and its distinct official sessions.

    ``stream_sessions`` are all official sessions of the section's objects, memory copies
    included, for the counts per stream (default: ``sessions``).
    """
    stream_sessions = sessions if stream_sessions is None else stream_sessions
    distinct: dict[tuple[str, str, str, int], Row] = {}
    for m in sorted(markers, key=lambda m: (m["object_sha256"], m["stream_ordinal"])):
        distinct.setdefault((m["device_id"], m["block_start"], m["kind"], m["rank"]), m)
    zeresimas = [m for m in distinct.values() if m["kind"] == "zeresima_start"]
    streams: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for m in markers:
        streams[(m["object_sha256"], m["stream_ordinal"])].append(m)

    def votes_before_marker(m: Row) -> int:
        return m["completions_before"] + sum(  # earlier official blocks of the same stream
            _completed(s)
            for s in stream_sessions
            if s["object_sha256"] == m["object_sha256"]
            and s["stream_ordinal"] == m["stream_ordinal"]
            and s["segment_ordinal"] < m["segment_ordinal"]
        )

    votes_before = ready_before = after_votes = 0
    for found in streams.values():
        own = sorted((m for m in found if m["kind"] == "zeresima_start"), key=lambda m: m["line"])
        if not own:
            continue
        first = own[0]
        votes_before = max(votes_before, votes_before_marker(first))
        later = sum(1 for m in own[1:] if votes_before_marker(m))
        after_votes = max(after_votes, later)  # a memory copy repeats its stream
        early = sum(1 for m in found if m["kind"] == "ready" and m["line"] < first["line"])
        ready_before = max(ready_before, early)  # a memory copy repeats its stream
    off_day = sum(1 for m in zeresimas if (m["reading"] or "")[:10] != election_date)
    voting = Counter()
    for s in sessions:
        voting[s["device_id"]] += _completed(s)
    devices = {d for d, n in voting.items() if n}
    with_zeresima = {m["device_id"] for m in zeresimas}
    first_zeresima = min((m["reading"] for m in zeresimas if m["reading"]), default=None)
    early_replacements = unknown_order = 0
    for device in devices - with_zeresima:
        starts = [
            s.get("start_reading") for s in sessions if s["device_id"] == device and _completed(s)
        ]
        known = [x for x in starts if x]
        if first_zeresima is None or not starts or len(known) != len(starts):
            unknown_order += 1
        elif min(known) < first_zeresima:
            early_replacements += 1
    failed = []
    if devices and not zeresimas:
        failed.append("Z1")
    if votes_before:
        failed.append("Z2")
    if off_day:
        failed.append("Z3")
    if after_votes:
        failed.append("Z4")
    if ready_before:
        failed.append("Z5")
    if early_replacements:
        failed.append("Z6")
    return {
        "zeresimas": len(zeresimas),
        "votes_before_first": votes_before if zeresimas else None,
        "zeresimas_off_day": off_day,
        "ready_before_zeresima": ready_before,
        "devices_with_votes": len(devices),
        "devices_with_votes_without_zeresima": len(devices - with_zeresima),
        "zeresima_devices": len(with_zeresima),
        "zeresimas_after_votes": after_votes,
        "devices_voting_before_any_zeresima": early_replacements,
        "devices_replacement_order_unknown": unknown_order,
        "failed_json": json.dumps(failed, separators=(",", ":")),
    }


def run_zeresima(
    sections_root: str | Path,
    semantic_root: str | Path,
    output: str | Path,
    *,
    memory_limit: str = "2GB",
) -> JSON:
    """Z1-Z5 per section of one round."""
    sections_root = Path(sections_root).expanduser().absolute()
    semantic = Path(semantic_root).expanduser().absolute() / "release"
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    release = sections_root / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    semantic_manifest = json.loads((semantic / "manifest.json").read_text())
    for root, entries in ((release, manifest), (semantic, semantic_manifest)):
        for name, entry in entries["files"].items():
            if entry["sha256"] != sha(root / name):
                raise ValueError(f"Release file changed: {root / name}")
    if semantic_manifest["version"] != SEMANTIC_VERSION:
        raise ValueError(f"Expected a {SEMANTIC_VERSION} release")
    round_number, year = manifest["round"], manifest["year"]
    if semantic_manifest["round"] != round_number:
        raise ValueError("Semantic release and section release are different rounds")
    election = election_for_round(round_number, year)
    binding = {
        "version": VERSION,
        "round": round_number,
        "year": year,
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "semantic_manifest_sha256": sha(semantic / "manifest.json"),
        "semantic_version": semantic_manifest["version"],
        "rules": RULES,
        "copies": "a marker copied across memories of one urn (same device, block start, kind "
        "and rank in block) counts once; official sessions as in the section table",
        "protected": "sections without a semantic-pass object are unavailable, never read",
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    sections = pq.read_table(
        release / "sections.parquet", columns=["uf", "municipality", "zone", "section"]
    ).to_pylist()
    witnesses = ic._witness_map(semantic)
    digests = {o["object_sha256"] for objs in witnesses.values() for o in objs}
    official = ic._official(semantic, digests, round_number)
    markers = _markers(semantic, round_number, memory_limit)
    rows, issues = [], []
    for s in sections:
        key = (s["uf"], s["municipality"], s["zone"], s["section"])
        base = dict(zip(("uf", "municipality", "zone", "section"), key, strict=True))
        objects = [o for o in witnesses.get(key, []) if o["status"] == "complete"]
        if not objects:
            state = "error" if witnesses.get(key) else "protected_or_unavailable"
            rows.append({**base, "log": state})
            continue
        every = [x for o in objects for x in official.get(o["object_sha256"], [])]
        found, _ = distinct_sessions(every)
        row = section_rules(
            [m for o in objects for m in markers.get(o["object_sha256"], [])],
            found,
            election.election_date,
            every,
        )
        rows.append({**base, "log": "semantic", **row})
        failed = json.loads(row["failed_json"])
        if failed:
            issues.append(
                {
                    "check": "Z",
                    "failed": failed,
                    **base,
                    **{k: row[k] for k in row if k != "failed_json"},
                }
            )
    final = output / ".release.tmp"
    final.mkdir()
    ic._write(final / "sections.parquet", rows, SECTION_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    other = pq.read_table(
        semantic / "markers.parquet", columns=["kind", "template"], filters=[("kind", "=", "other")]
    ).to_pylist()
    summary = {
        "sections": len(rows),
        "log": dict(Counter(r["log"] for r in rows)),
        "failed": dict(Counter(r.get("failed_json") or "n/a" for r in rows)),
        "rule_failures": dict(
            Counter(f for r in rows for f in json.loads(r.get("failed_json") or "[]"))
        ),
        "zeresimas": dict(Counter(str(r.get("zeresimas")) for r in rows)),
        "zeresima_devices": dict(Counter(str(r.get("zeresima_devices")) for r in rows)),
        "no_official_votes": sum(
            1 for r in rows if r["log"] == "semantic" and not r["devices_with_votes"]
        ),
        "sections_with_devices_without_zeresima": dict(
            Counter(
                str(r["devices_with_votes_without_zeresima"])
                for r in rows
                if r.get("devices_with_votes_without_zeresima")
            )
        ),
        "devices_replacement_order_unknown": sum(
            r.get("devices_replacement_order_unknown") or 0 for r in rows
        ),
        "other_zeresima_templates": dict(Counter(r["template"] for r in other)),
    }
    result = {
        **binding,
        "summary": summary,
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
    }
    atomic(final / "manifest.json", result)
    os.replace(final, output / "release")
    return result
