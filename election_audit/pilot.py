"""Explicit bounded diagnostic selection; no acquisition, raw writes or BU claims."""

import argparse
import io
import json
import re
import shutil
import sqlite3
import time
import zipfile
from collections import Counter
from collections.abc import Collection
from contextlib import closing
from pathlib import Path

from election_audit.archive_parsing import MESSAGES, iter_event_witnesses, iter_parsing_issues
from election_audit.publication import PublicationError, ResourceConfig
from election_audit.release_tools import query_release, report_release
from election_audit.reproduction import describe_run, frozen_pipeline
from election_audit.snapshots import create_snapshot, inspect_snapshot
from election_audit.source_inventory import (
    BASE,
    DEFAULT_UFS,
    digest,
    hash_file,
    index_url,
    safe_source,
    utc_now,
)
from election_audit.types import JSON, Argv
from election_audit.walkthrough import write_json
from scripts.download_tse_logs import manifest_path, sections

SEED = "diagnostic-geographic-pilot-v1"
# Five macroregions, selected before observing any operational outcomes.
SAMPLED_UFS = ("ac", "al", "df", "es", "pr")
POOL_LIMIT = 100_000
MAX_SELECTED_BYTES = 64 * 1024**2


def select_pilot(
    root: str | Path,
    *,
    seed: str = SEED,
    sampled_ufs: Collection[str] = SAMPLED_UFS,
    pool_limit: int = POOL_LIMIT,
) -> JSON:
    """Read one WAL-consistent metadata view; hash only selected-UF small indexes.

    Each configured UF has an ordered bounded metadata pool. For sampled UFs,
    exact index principals qualify; deterministic hashes rank municipality/zone
    strata, then principals. Only the winning raw file gets existence/size checks.
    Remaining verified-byte checks happen in snapshot creation.
    """
    root = Path(root).resolve()
    if not set(sampled_ufs) <= set(DEFAULT_UFS) or pool_limit < 1:
        raise ValueError("Pilot UFs must be configured AC–RJ and pool limit positive")
    started = time.monotonic()
    selected, pools, exclusions, chosen_pools = [], {}, [], {}
    manifest = manifest_path(root).resolve()
    with closing(sqlite3.connect(manifest.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        # Establish read view before capture timestamp; no checkpoint/copy/lock.
        runs = [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY id")]
        captured_at = utc_now()
        for uf in DEFAULT_UFS:
            prefix = f"{BASE}/ele2026/arquivo-urna/3221/dados/{uf}/"
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT url,path,sha256,bytes FROM files WHERE url>=? AND url<? "
                    "AND (url LIKE '%-log.jez' OR url LIKE '%-log.dat') ORDER BY url LIMIT ?",
                    (prefix, prefix + "\uffff", pool_limit + 1),
                )
            ]
            truncated = len(rows) > pool_limit
            rows = rows[:pool_limit]
            pools[uf] = {
                "metadata_rows": len(rows),
                "pool_sha256": digest(rows),
                "truncated": truncated,
                "raw_existence": "not_checked_for_pool",
                "scope": "ordered_URL_metadata_pool_not_full_population"
                if truncated
                else "current_manifest_log_mappings",
            }
            if not rows:
                exclusions.append({"uf": uf, "reason": "no_current_log_mapping"})
            if uf not in sampled_ufs:
                continue
            chosen_pools[uf] = rows
            index = db.execute("SELECT * FROM files WHERE url=?", (index_url(uf),)).fetchone()
            if index is None:
                exclusions.append({"uf": uf, "reason": "index_missing"})
                continue
            path = safe_source(root, index["path"])
            if path.stat().st_size > 16 * 1024**2 or hash_file(path) != (
                index["sha256"],
                index["bytes"],
            ):
                raise PublicationError("Pilot index size/integrity bound failed")
            index_body = json.loads(path.read_bytes())
            principals = {
                tuple(row[:4])
                for row in sections(index_body, uf, "3221")
                if row[4].get("nsp", row[3]) == row[3]
            }
            candidates = []
            for row in rows:
                match = re.fullmatch(re.escape(prefix) + r"(\d{5})/(\d{4})/(\d{4})/.+", row["url"])
                if not match:
                    continue
                key = (uf, *match.groups())
                if key not in principals or not 0 < row["bytes"] <= MAX_SELECTED_BYTES:
                    continue
                stratum = key[:3]
                candidates.append(
                    (
                        digest([seed, "stratum", stratum]),
                        digest([seed, "principal", key]),
                        row["url"],
                        key,
                        row,
                    )
                )
            pools[uf]["eligible_principals"] = len({item[3] for item in candidates})
            pools[uf]["eligible_pool_sha256"] = digest(sorted({item[3] for item in candidates}))
            for stratum_rank, principal_rank, _, key, row in sorted(candidates):
                source = safe_source(root, row["path"])
                if not source.is_file() or source.stat().st_size != row["bytes"]:
                    exclusions.append({"key": key, "reason": "missing_or_size_changed"})
                    continue
                selected.append(
                    {
                        "section_key": key,
                        "stratum": key[:3],
                        "stratum_rank": stratum_rank,
                        "principal_rank": principal_rank,
                        "source": row,
                        "index_sha256": index["sha256"],
                    }
                )
                break
            else:
                exclusions.append({"uf": uf, "reason": "no_eligible_available_principal"})
        db.rollback()
    if not selected:
        raise PublicationError("No available eligible pilot principal")
    return {
        "version": "diagnostic-pilot-v1",
        "created_at": captured_at,
        "source_root": str(root),
        "manifest": str(manifest),
        "runs": runs,
        "seed": seed,
        "configured_ufs": list(DEFAULT_UFS),
        "sampled_ufs": list(sampled_ufs),
        "national_status": "partial_national",
        "pool_limit_per_uf": pool_limit,
        "pools": pools,
        "sampled_uf_pool_rows": chosen_pools,
        "selected": selected,
        "exclusions": exclusions,
        "selection_seconds": time.monotonic() - started,
        "sampling_limits": "diagnostic_only_one_principal_per_UF_hash_ranked_strata_not_probability_weighted_estimation; metadata_pool_availability_is_not_verified_bytes; snapshot_recaptures_live_view_and_checks_selected_bytes",
    }


PILOT_SQL = {
    "events": "SELECT event_kind, count(*) AS events FROM selected_event GROUP BY event_kind ORDER BY event_kind",
    "sessions": "SELECT session_kind, count(*) AS sessions FROM voting_session GROUP BY session_kind ORDER BY session_kind",
    "cycles": "SELECT completion_state, count(*) AS cycles FROM anonymous_cycle GROUP BY completion_state ORDER BY completion_state",
    "clocks": "SELECT clock_confidence, count(*) AS events FROM selected_event GROUP BY clock_confidence ORDER BY clock_confidence",
}


def review_original_messages(snapshot: Path) -> JSON:
    """Export fixed keyword counters from frozen bytes, never text or new semantics."""
    document = inspect_snapshot(snapshot, verify_objects=True)
    counters, dates, members = Counter(), Counter(), Counter()
    keywords = ("biometr", "cancel", "suspens", "reinici", "modelo de urna", "habilita")
    total_bytes = 0

    def visit(body: bytes, depth: int = 0) -> None:
        nonlocal total_bytes
        if depth > 4:
            raise PublicationError("Review nested depth exceeded")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000:
                raise PublicationError("Review member bound exceeded")
            for entry in entries:
                if entry.is_dir():
                    continue
                if entry.file_size > 128 * 1024**2:
                    raise PublicationError("Review member byte bound exceeded")
                total_bytes += entry.file_size
                if total_bytes > 512 * 1024**2:
                    raise PublicationError("Review total byte bound exceeded")
                raw = archive.read(entry)
                if entry.filename.lower().endswith((".zip", ".jez")):
                    try:
                        visit(raw, depth + 1)
                    except zipfile.BadZipFile:
                        counters["invalid_nested_archive"] += 1
                elif Path(entry.filename.replace("\\", "/")).name.lower() == "logd.dat":
                    members["logd.dat"] += 1
                    for line in raw.splitlines():
                        fields = line.decode("latin-1").split("\t")
                        if len(fields) != 6:
                            counters["malformed_shape"] += 1
                            continue
                        dates[fields[0][:10]] += 1
                        message = fields[4]
                        if fields[3] == "VOTA" and message in MESSAGES:
                            counters["exact_" + MESSAGES[message]] += 1
                        else:
                            counters["unsupported_or_other_application"] += 1
                            for word in keywords:
                                if word in message.lower():
                                    counters["diagnostic_keyword_" + word] += 1

    for row in document["payload"]["tables"]["source_object"]:
        path = safe_source(Path(snapshot), row["storage_locator"])
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic == b"PK\x03\x04":
            if path.stat().st_size > 512 * 1024**2:
                raise PublicationError("Review archive byte bound exceeded")
            visit(path.read_bytes())
    return {
        "version": "safe-real-message-review-v1",
        "fixed_keyword_counts": dict(counters),
        "naive_device_dates": dict(dates),
        "members": dict(members),
        "meaning": "keywords_are_diagnostics_not_decoded_events; mixed_dates_are_not_round_attribution",
        "free_text_exported": False,
        "new_semantic_adapter": False,
    }


def run_pilot(source: str | Path, output: str | Path) -> JSON:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    selection = select_pilot(source)
    write_json(output / "pilot-selection.json", selection)
    config = ResourceConfig()
    snapshot = create_snapshot(
        Path(source),
        output / "snapshots",
        [row["section_key"][0] for row in selection["selected"]],
        section_keys=[tuple(row["section_key"]) for row in selection["selected"]],
        reserve_bytes=config.reserve_bytes,
    )
    frozen = inspect_snapshot(snapshot, verify_objects=True)
    # If acquisition advanced between selection and freeze, preserve both views.
    # Frozen bytes and populations are authoritative for subsequent calculations.
    for row in selection["selected"]:
        matches = [
            check
            for check in frozen["payload"]["inventory"]["object_checks"]
            if check["url"] == row["source"]["url"]
        ]
        if not matches or matches[0]["state"] != "verified":
            raise PublicationError("Selected pilot log not verified in frozen snapshot")
    parsed, shards, release, pipeline_seconds = frozen_pipeline(snapshot, output, config=config)
    report_release(release, output / "reports" / "operational")
    descriptor = describe_run(
        output,
        snapshot,
        parsed,
        shards,
        [release],
        config=config,
        elapsed_seconds=time.monotonic() - started,
    )
    calculations = {name: query_release(release, sql) for name, sql in PILOT_SQL.items()}
    dates, applications, kinds, issues = Counter(), Counter(), Counter(), Counter()
    anchors = {}
    witnesses = 0
    for event in iter_event_witnesses(parsed):
        witnesses += 1
        dates[(event.get("device_timestamp_raw") or "unknown")[:10]] += 1
        applications[event.get("application") or "unknown"] += 1
        kinds[event["event_kind"]] += 1
        # At most one safe original locator/hash per decoded class, no raw text/IDs.
        anchors.setdefault(
            event["event_kind"],
            {
                key: event[key]
                for key in ("event_id", "object_sha256", "source_line_sha256", "record_locator")
            },
        )
    for issue in iter_parsing_issues(parsed):
        issues[issue["issue_code"]] += 1
    result = {
        "version": "diagnostic-pilot-v1",
        "synthetic": False,
        "national_status": "partial_national",
        "selected_principals": len(selection["selected"]),
        "selected_ufs": [row["section_key"][0] for row in selection["selected"]],
        "snapshot_id": frozen["snapshot"]["snapshot_id"],
        "coverage": frozen["payload"]["coverage_summary"],
        "event_witnesses": witnesses,
        "device_dates": dict(dates),
        "applications": dict(applications),
        "parsed_classes": dict(kinds),
        "parsing_issues": dict(issues),
        "safe_evidence_anchors": anchors,
        "sql": PILOT_SQL,
        "calculations": calculations,
        "pipeline_seconds": pipeline_seconds,
        "total_seconds": time.monotonic() - started,
        "stored_bytes": sum(path.stat().st_size for path in output.rglob("*") if path.is_file()),
        "free_bytes_after": shutil.disk_usage(output).free,
        "real_BU_validation": "unavailable_task_7.1_official_adapter_outstanding",
        "message_review": "three_exact_baseline_classes_only; unknown_text_not_exported; no_new_semantic_adapter_or_official_session_clock_claim",
        "limitations": [
            "diagnostic_sample_only",
            "no_probability_weighted_or_national_estimate",
            "source_dates_are_naive_not_round_attribution",
            "unresolved_sessions_and_clocks",
            "no_candidate_attribution",
            "unknown_messages_remain_unknown",
            "no_model_fitting_or_fraud_labels",
        ],
        "reproduction_descriptor": descriptor["version"],
        "original_message_review": review_original_messages(snapshot),
    }
    write_json(output / "pilot-results.json", result)
    for name, sql in PILOT_SQL.items():
        (output / "reports" / "operational" / f"pilot-{name}.sql").write_text(sql + ";\n")
    return result


def pilot_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_pilot(args.source, args.output), ensure_ascii=False, default=str))
    return 0
