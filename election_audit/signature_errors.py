"""Phase 20b: votes recorded after a signature or integrity error in the urn logs (O19).

The semantic pass (``session-aggregates-v5``) keeps one ``signature_error`` marker per log line
whose template names a signature or integrity (``assinatura``, ``integridade``) together with a
failure (``erro``, ``falha``, ``inconsistente``), with its stream, block, session and the number
of vote cycles completed earlier in the same block. Two classes of error are told apart by the
template:

- ``verification``: a program or data signature that did not verify (the template says
  ``verifica``/``valida``: start-up checks of GAP, the VOTA self-check, the load media);
- ``signing``: the urn failed to sign a file it writes (``Erro na assinatura``, ``DoSign``,
  ``Erro ao inicializar assinatura``), usually because the external medium failed.

Both stop the urn (``Desligue a urna``). An urn switched on again repeats every start-up
signature check, so votes after a restart are counted, not failed. Over the round's official
blocks of each section's log:

- E1: no vote cycle is completed in the same session after a verification error (the urn did
  not go on voting without a restart);
- E2: at most one vote cycle is completed in the same session after a signing error: the
  voter's cycle in flight, whose completion line follows the error, as read in the two such
  logs of 2026.

Errors outside a session (start-up) have no session to continue: they are counted, with the
votes the urn recorded afterwards in the block and in later official blocks of the stream.
Copies of one block in both memories count once (device, block start, template, rank in
block), keeping the largest counts. Errors in other contexts (preparation, tests, the other
round's blocks) are counted in the summary only.
"""

import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import integrity_checks as ic
from election_audit.national_migration import atomic, sha
from election_audit.types import JSON, Row

VERSION = "integrity-signature-errors-v1"
SEMANTIC_VERSION = "session-aggregates-v5"
RULES = {
    "E1": "no vote cycle completed in the same session after a verification error",
    "E2": "at most one vote cycle (the one in flight) completed in the same session after a "
    "signing error",
}
VERIFICATION = re.compile(r"verifica|valida")
MARKER_SQL = """
SELECT m.object_sha256, m.stream_ordinal, m.segment_ordinal, m.session_ordinal, m.device_id,
       m.template, m.line, m.reading, m.completions_before, g.context,
       g.first_line_sha256 AS block_start,
       row_number() OVER (PARTITION BY m.object_sha256, m.stream_ordinal, m.segment_ordinal,
                                       m.template ORDER BY m.line) AS rank
FROM read_parquet($markers) m
JOIN read_parquet($segments) g USING (object_sha256, stream_ordinal, segment_ordinal)
WHERE m.kind = 'signature_error'
"""
SESSION_SQL = """
SELECT object_sha256, stream_ordinal, segment_ordinal, session_ordinal, session_kind,
       session_round,
       cycles_completed_biometric + cycles_completed_manual + cycles_completed_unknown AS done
FROM read_parquet($sessions)
WHERE object_sha256 IN (SELECT unnest($objects))
"""
SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("log", pa.string()),  # semantic | protected_or_unavailable | error
        ("verification_errors", pa.int32()),
        ("signing_errors", pa.int32()),
        ("votes_same_session_after_verification", pa.int32()),  # max over errors
        ("votes_same_session_after_signing", pa.int32()),  # max over errors
        ("votes_after_restart", pa.int32()),  # max over errors
        ("inconsistent_counts", pa.int32()),
        ("failed_json", pa.string()),
    ]
)
ERROR_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("class", pa.string()),  # verification | signing
        ("template", pa.string()),  # digit-masked
        ("reading", pa.string()),  # local urn clock
        ("in_session", pa.bool_()),
        ("votes_before", pa.int32()),  # earlier in the block
        ("votes_same_session", pa.int32()),  # null outside a session
        ("votes_after_restart", pa.int32()),
    ]
)


def error_class(template: str) -> str:
    return "verification" if VERIFICATION.search(template.lower()) else "signing"


def _query(release: Path, sql: str, params: dict, memory_limit: str) -> list[Row]:
    import duckdb

    with duckdb.connect() as db:
        db.execute(f"SET memory_limit = '{memory_limit}'")
        db.execute("SET threads = 2")
        cursor = db.execute(sql, params)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def error_counts(m: Row, sessions: Sequence[Row], round_number: int) -> Row:
    """Votes completed after one error marker: in its session, and after a restart."""
    stream = [
        s
        for s in sessions
        if (s["object_sha256"], s["stream_ordinal"]) == (m["object_sha256"], m["stream_ordinal"])
    ]
    block = [s for s in stream if s["segment_ordinal"] == m["segment_ordinal"]]
    after_block = sum(s["done"] for s in block) - m["completions_before"]
    same = None
    if m["session_ordinal"] is not None:
        upto = sum(s["done"] for s in block if s["session_ordinal"] <= m["session_ordinal"])
        same = upto - m["completions_before"]
    later = sum(
        s["done"]
        for s in stream
        if s["segment_ordinal"] > m["segment_ordinal"]
        and s["session_kind"] == "official_vota"
        and s["session_round"] == round_number
    )
    return {
        "class": error_class(m["template"]),
        "template": m["template"],
        "reading": m["reading"],
        "in_session": m["session_ordinal"] is not None,
        "votes_before": m["completions_before"],
        "votes_same_session": same,
        "votes_after_restart": after_block - (same or 0) + later,
        "inconsistent": after_block < 0 or (same is not None and same < 0),
    }


def section_rules(markers: Sequence[Row], sessions: Sequence[Row], round_number: int) -> JSON:
    """E1-E2 for one section from its error markers and all sessions of its objects."""
    context = f"official_round_{round_number}"
    distinct: dict[tuple, Row] = {}
    for m in sorted(markers, key=lambda m: (m["object_sha256"], m["stream_ordinal"], m["line"])):
        if m["context"] != context:
            continue
        counts = error_counts(m, sessions, round_number)
        key = (m["device_id"], m["block_start"], m["template"], m["rank"])
        kept = distinct.get(key)
        if kept is None:
            distinct[key] = counts
            continue
        for name in ("votes_same_session", "votes_after_restart"):  # a shorter copy counts less
            if (counts[name] or 0) > (kept[name] or 0):
                kept[name] = counts[name]
        kept["inconsistent"] = kept["inconsistent"] or counts["inconsistent"]
    errors = list(distinct.values())

    def most(cls: str | None, name: str) -> int | None:
        values = [e[name] for e in errors if cls in (None, e["class"]) and e[name] is not None]
        return max(values) if values else None

    same_verification = most("verification", "votes_same_session")
    same_signing = most("signing", "votes_same_session")
    failed = []
    if same_verification:
        failed.append("E1")
    if same_signing and same_signing > 1:
        failed.append("E2")
    return {
        "errors": errors,
        "row": {
            "verification_errors": sum(e["class"] == "verification" for e in errors),
            "signing_errors": sum(e["class"] == "signing" for e in errors),
            "votes_same_session_after_verification": same_verification,
            "votes_same_session_after_signing": same_signing,
            "votes_after_restart": most(None, "votes_after_restart"),
            "inconsistent_counts": sum(e["inconsistent"] for e in errors),
            "failed_json": json.dumps(failed, separators=(",", ":")),
        },
    }


def run_signature_errors(
    sections_root: str | Path,
    semantic_root: str | Path,
    output: str | Path,
    *,
    memory_limit: str = "2GB",
) -> JSON:
    """E1-E2 per section of one round."""
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
    round_number = manifest["round"]
    if semantic_manifest["round"] != round_number:
        raise ValueError("Semantic release and section release are different rounds")
    binding = {
        "version": VERSION,
        "round": round_number,
        "year": manifest["year"],
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "semantic_manifest_sha256": sha(semantic / "manifest.json"),
        "semantic_version": semantic_manifest["version"],
        "rules": RULES,
        "classes": "verification when the template says verifica/valida, otherwise signing",
        "copies": "an error copied across memories of one urn (same device, block start, "
        "template and rank in block) counts once, with its largest counts",
        "protected": "sections without a semantic-pass object are unavailable, never read",
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    markers = _query(
        semantic,
        MARKER_SQL,
        {
            "markers": str(semantic / "markers.parquet"),
            "segments": str(semantic / "segments.parquet"),
        },
        memory_limit,
    )
    by_object: dict[str, list[Row]] = defaultdict(list)
    for m in markers:
        by_object[m["object_sha256"]].append(m)
    sessions_by_object: dict[str, list[Row]] = defaultdict(list)
    for s in _query(
        semantic,
        SESSION_SQL,
        {"sessions": str(semantic / "sessions.parquet"), "objects": sorted(by_object)},
        memory_limit,
    ):
        sessions_by_object[s["object_sha256"]].append(s)
    sections = pq.read_table(
        release / "sections.parquet", columns=["uf", "municipality", "zone", "section"]
    ).to_pylist()
    witnesses = ic._witness_map(semantic)
    rows, error_rows, issues = [], [], []
    for s in sections:
        key = (s["uf"], s["municipality"], s["zone"], s["section"])
        base = dict(zip(("uf", "municipality", "zone", "section"), key, strict=True))
        objects = [o["object_sha256"] for o in witnesses.get(key, []) if o["status"] == "complete"]
        if not objects:
            state = "error" if witnesses.get(key) else "protected_or_unavailable"
            rows.append({**base, "log": state})
            continue
        result = section_rules(
            [m for o in objects for m in by_object.get(o, [])],
            [x for o in objects for x in sessions_by_object.get(o, [])],
            round_number,
        )
        row = result["row"]
        rows.append({**base, "log": "semantic", **row})
        error_rows += [
            {**base, **{k: v for k, v in e.items() if k != "inconsistent"}}
            for e in result["errors"]
        ]
        failed = json.loads(row["failed_json"])
        if failed or row["inconsistent_counts"]:
            issues.append(
                {
                    "check": "E",
                    "failed": failed,
                    **base,
                    **{k: row[k] for k in row if k != "failed_json"},
                    "errors": result["errors"],
                }
            )
    final = output / ".release.tmp"
    final.mkdir()
    ic._write(final / "sections.parquet", rows, SECTION_SCHEMA)
    ic._write(final / "errors.parquet", error_rows, ERROR_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    contexts = Counter(
        f"{m['context']}:{error_class(m['template'])}" for m in markers
    )  # every copy, all contexts
    summary = {
        "sections": len(rows),
        "log": dict(Counter(r["log"] for r in rows)),
        "failed": dict(Counter(r.get("failed_json") or "n/a" for r in rows)),
        "sections_with_errors": sum(
            1 for r in rows if r.get("verification_errors") or r.get("signing_errors")
        ),
        "errors": dict(
            Counter(
                f"{e['class']}:{'session' if e['in_session'] else 'startup'}" for e in error_rows
            )
        ),
        "errors_followed_by_votes_after_restart": dict(
            Counter(e["class"] for e in error_rows if e["votes_after_restart"])
        ),
        "votes_same_session": dict(
            Counter(
                f"{e['class']}:{e['votes_same_session']}"
                for e in error_rows
                if e["votes_same_session"] is not None
            )
        ),
        "inconsistent_counts": sum(r.get("inconsistent_counts") or 0 for r in rows),
        "markers_by_context": dict(sorted(contexts.items())),
        "templates": {
            cls: sorted({e["template"] for e in error_rows if e["class"] == cls})
            for cls in ("verification", "signing")
        },
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
