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

- E3: after any error, no vote cycle (beyond the one in flight after a signing error) is
  completed in the urn's stream before GAP starts an application again, which repeats the
  start-up checks. The markers do not show restarts (a block is a context, not a boot), so
  each object holding an error is reread from its staged copy to find them. A dynamic-file
  error (``Erro na verificação de assinatura do arquivo - <name>.vsu``) that GAP follows, in
  the same start-up and before VOTA starts, with a completed synchronisation of the dynamic
  files (``Sincronização dos arquivos dinâmicos concluída com sucesso``) is
  ``recovered_by_sync`` and does not count for E3. That synchronisation never follows an
  ordinary start-up (0 of 1,810 official start-ups in 400 random round-1 objects); the log
  does not show the restored files verified again. The rule was written after reading the
  31 v2 failures (xr1-20261109 R4), which all had this shape; their raw counts stay in
  ``votes_without_restart``.

Votes later in the block and in later official blocks are counted as ``votes_later``.
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

VERSION = "integrity-signature-errors-v3"  # v3: dynamic-file errors recovered by sync (E3)
SEMANTIC_VERSION = "session-aggregates-v5"
RULES = {
    "E1": "no vote cycle completed in the same session after a verification error",
    "E2": "at most one vote cycle (the one in flight) completed in the same session after a "
    "signing error",
    "E3": "after an error, no vote cycle (one in flight after a signing error) completed in "
    "its urn's stream before GAP started an application again, which repeats the start-up "
    "checks; a dynamic-file (.vsu) verification error followed in its start-up, before VOTA "
    "starts, by a completed dynamic-file synchronisation is recovered and not counted",
}
DYNAMIC_FILE = re.compile(r"Erro na verificação de assinatura do arquivo - \S+\.vsu$")
SYNC_DONE = "Sincronização dos arquivos dinâmicos concluída com sucesso"
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
        ("votes_later", pa.int32()),  # max over errors: rest of the block and later blocks
        ("votes_without_restart_after_verification", pa.int32()),  # max over errors
        ("votes_without_restart_after_signing", pa.int32()),  # max over errors
        ("restart_unavailable", pa.int32()),  # errors whose object could not be reread
        ("recovered_by_sync", pa.int32()),  # errors not counted for E3
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
        ("votes_later", pa.int32()),
        ("votes_without_restart", pa.int32()),  # before the stream's next GAP start
        ("restart_line", pa.int64()),  # that GAP start's line; null when none follows
        ("recovered_by_sync", pa.bool_()),  # dynamic-file error, files resynchronised
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
        "votes_later": after_block - (same or 0) + later,
        "votes_without_restart": m.get("votes_without_restart"),
        "restart_line": m.get("restart_line"),
        "recovered_by_sync": m.get("recovered_by_sync"),
        "inconsistent": after_block < 0 or (same is not None and same < 0),
    }


def restart_evidence(source: bytes, errors: Sequence[Row]) -> dict[tuple[int, int], Row]:
    """Per error (stream, line): votes completed before its stream's next GAP start, its line,
    and whether a dynamic-file error was recovered by a synchronisation before VOTA started.

    Lines and streams are numbered as the semantic pass numbers them (every line counts; a
    stream is a run of well-formed lines with one member path and device), so a marker's line
    finds its place. A GAP application start makes the urn repeat its start-up checks; votes
    completed before one were cast without them (xr1-20261109-P4-03).
    """
    from election_audit.operational_review import RULES as LOG_RULES
    from election_audit.operational_review import classify
    from election_audit.semantic_pass import log_members, reading_seconds

    events: dict[int, list[tuple[int, str]]] = defaultdict(list)
    total, stream, key = 0, -1, None
    for segments, body in log_members(source):
        parts = body.split(b"\n")
        last = parts.pop()
        for line in [x + b"\n" for x in parts] + ([last] if last else []):
            total += 1
            fields = line.decode("latin-1").rstrip("\r\n").split("\t")
            if len(fields) != 6 or reading_seconds(fields[0]) is None:
                continue
            if (segments, fields[2]) != key:
                key, stream = (segments, fields[2]), stream + 1
            application, message = fields[3], fields[4]
            if application == "GAP" and message.startswith("Iniciando aplicação"):
                events[stream].append((total, "restart"))
            elif application == "GAP" and message.startswith(SYNC_DONE):
                events[stream].append((total, "sync"))
            elif application == "VOTA" and message.startswith("Iniciando aplicação"):
                events[stream].append((total, "vota"))
            elif application == "VOTA" and classify(application, message, LOG_RULES)[0] == (
                "completion"
            ):
                events[stream].append((total, "completion"))
    found = {}
    for e in errors:
        votes, restart, synced, started = 0, None, False, False
        for number, kind in events.get(e["stream_ordinal"], ()):
            if number <= e["line"]:
                continue
            if kind == "restart":
                restart = number
                break
            if kind == "sync" and not started and not votes:
                synced = True
            elif kind == "vota":
                started = True
            elif kind == "completion":
                votes += 1
        found[(e["stream_ordinal"], e["line"])] = {
            "votes_without_restart": votes,
            "restart_line": restart,
            "recovered_by_sync": bool(DYNAMIC_FILE.search(e.get("template", ""))) and synced,
        }
    return found


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
        for name in ("votes_same_session", "votes_later", "votes_without_restart"):
            # a shorter copy counts less
            if (counts[name] or 0) > (kept[name] or 0):
                kept[name] = counts[name]
        kept["inconsistent"] = kept["inconsistent"] or counts["inconsistent"]
        # copies log the same events: a sync in either copy happened
        kept["recovered_by_sync"] = kept["recovered_by_sync"] or counts["recovered_by_sync"]
    errors = list(distinct.values())

    def most(cls: str | None, name: str, among: Sequence[Row] = errors) -> int | None:
        values = [e[name] for e in among if cls in (None, e["class"]) and e[name] is not None]
        return max(values) if values else None

    same_verification = most("verification", "votes_same_session")
    same_signing = most("signing", "votes_same_session")
    counted = [e for e in errors if not e.get("recovered_by_sync")]
    unrestarted_verification = most("verification", "votes_without_restart", counted)
    unrestarted_signing = most("signing", "votes_without_restart", counted)
    # the row keeps the raw counts of every error, recovered ones included
    failed = []
    if same_verification:
        failed.append("E1")
    if same_signing and same_signing > 1:
        failed.append("E2")
    if unrestarted_verification or (unrestarted_signing and unrestarted_signing > 1):
        failed.append("E3")
    return {
        "errors": errors,
        "row": {
            "verification_errors": sum(e["class"] == "verification" for e in errors),
            "signing_errors": sum(e["class"] == "signing" for e in errors),
            "votes_same_session_after_verification": same_verification,
            "votes_same_session_after_signing": same_signing,
            "votes_later": most(None, "votes_later"),
            "votes_without_restart_after_verification": most(
                "verification", "votes_without_restart"
            ),
            "votes_without_restart_after_signing": most("signing", "votes_without_restart"),
            "restart_unavailable": sum(e["votes_without_restart"] is None for e in errors),
            "recovered_by_sync": sum(bool(e.get("recovered_by_sync")) for e in errors),
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
        "restart": "objects holding an official-round error are reread from the staged copy, "
        "checked against their certified hash, to find the stream's next GAP start",
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
    from election_audit.round1_prefix import _staged_root, read_object

    staged, _ = _staged_root(semantic.parent)
    paths = {
        o["object_sha256"]: o["path"]
        for o in pq.read_table(
            semantic / "objects.parquet", columns=["object_sha256", "path"]
        ).to_pylist()
        if o["object_sha256"] in by_object
    }
    context = f"official_round_{round_number}"
    reread = Counter()
    for digest, found in by_object.items():
        wanted = [m for m in found if m["context"] == context]
        if not wanted:
            continue
        try:
            evidence = restart_evidence(read_object(staged, paths[digest], digest), wanted)
        except OSError, KeyError, ValueError:  # the object stays unavailable, never zero
            reread["unavailable"] += 1
            continue
        reread["read"] += 1
        for m in wanted:
            m.update(evidence[(m["stream_ordinal"], m["line"])])
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
        "errors_followed_by_later_votes": dict(
            Counter(e["class"] for e in error_rows if e["votes_later"])
        ),
        "votes_without_restart": dict(
            Counter(
                f"{e['class']}:{e['votes_without_restart']}"
                for e in error_rows
                if e["votes_without_restart"] is not None
            )
        ),
        "errors_recovered_by_sync": dict(
            Counter(e["template"] for e in error_rows if e["recovered_by_sync"])
        ),
        "errors_restart_unavailable": sum(e["votes_without_restart"] is None for e in error_rows),
        "objects_reread": dict(reread),
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
