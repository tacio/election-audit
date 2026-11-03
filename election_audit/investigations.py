"""Protected development investigations and explicitly conditional impact arithmetic."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from election_audit.research_evaluation import append_record, open_journal
from election_audit.research_protocol import hash_file, load_protocol, read_only
from election_audit.source_inventory import canonical, digest
from scripts.audit_statistics import (
    maximum_switch_margin_change,
    nonnegative_count,
    removal_contribution_bounds,
)

VERSION = "investigations-v1"


def _anchor(value):
    return (
        isinstance(value, dict)
        and isinstance(value.get("object_sha256"), str)
        and len(value["object_sha256"]) == 64
        and all(c in "0123456789abcdef" for c in value["object_sha256"])
        and isinstance(value.get("record_locator"), str)
        and bool(value["record_locator"])
    )


def _write(path, value):
    Path(path).write_bytes(canonical(value) + b"\n")


def _seal(directory, identity):
    files = {
        p.name: {"sha256": hash_file(p), "bytes": p.stat().st_size}
        for p in sorted(Path(directory).iterdir())
        if p.is_file() and p.name != "artifact.json"
    }
    _write(Path(directory) / "artifact.json", {"version": VERSION, **identity, "files": files})


def _check_features(features, protocol):
    doc = load_protocol(protocol)
    path = Path(features) / "features.sqlite"
    if hash_file(path) != doc["identity"]["feature_catalog_sha256"]:
        raise ValueError("Feature catalog differs from frozen protocol")
    return doc, path


def build_cases(features, protocol, evaluation, output, *, per_family=20, controls=100, seed=42):
    """Never inspect test outcomes; validate every supplied prediction's partition."""
    if (
        type(per_family) is not int
        or not 1 <= per_family <= 100
        or type(controls) is not int
        or not 0 <= controls <= 1000
    ):
        raise ValueError("Bounded positive case limits required")
    doc, catalog = _check_features(features, protocol)
    evaluation = Path(evaluation)
    ev = json.loads((evaluation / "evaluation.json").read_text())
    if (
        ev.get("stage") != "development"
        or ev.get("state") != "complete"
        or ev.get("protocol_id") != doc["protocol_id"]
        or ev.get("partition_id") != doc["partition_id"]
    ):
        raise ValueError("Cases require completed matching development evaluation")
    if hash_file(evaluation / "predictions.jsonl") != ev.get("predictions_sha256"):
        raise ValueError("Prediction evidence changed")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cases-", dir=output.parent) as temporary:
        stage = Path(temporary)
        with (
            closing(sqlite3.connect(stage / "selection.sqlite")) as work,
            read_only(catalog) as source,
            read_only(Path(protocol) / "research.sqlite") as partitions,
        ):
            source.row_factory = sqlite3.Row
            work.row_factory = sqlite3.Row
            work.executescript(
                "CREATE TABLE prediction(unit_key TEXT PRIMARY KEY, location TEXT, uf TEXT, direction TEXT, score REAL, rank TEXT, payload TEXT); CREATE TABLE selected(unit_key TEXT PRIMARY KEY, reason TEXT);"
            )
            with (evaluation / "predictions.jsonl").open() as stream:
                for line in stream:
                    row = json.loads(line)
                    key = row["unit_key"]
                    partition = partitions.execute(
                        "SELECT partition_name,stable_location_id FROM unit_partition WHERE unit_key=?",
                        (key,),
                    ).fetchone()
                    if not partition or partition[0] not in {
                        "training",
                        "calibration",
                        "development_inspected",
                    }:
                        raise ValueError(
                            "Protected, unknown or stress outcome in development predictions"
                        )
                    unit = source.execute("SELECT * FROM units WHERE unit_key=?", (key,)).fetchone()
                    if (
                        not unit
                        or not partition[1]
                        or row.get("model_run_id") != ev["model_run_id"]
                        or row.get("interpretation") != "descriptive_only"
                    ):
                        raise ValueError("Unlinked prediction or unsupported interpretation")
                    if not all(
                        isinstance(row.get(k), (float, int)) and math.isfinite(row[k])
                        for k in ("score", "signed_residual", "observed", "tail_rank")
                    ):
                        raise ValueError("Nonfinite prediction")
                    quantiles = row.get("quantiles")
                    if (
                        not isinstance(quantiles, list)
                        or len(quantiles) != 5
                        or any(
                            type(v) not in (int, float) or not math.isfinite(v) for v in quantiles
                        )
                        or quantiles != sorted(quantiles)
                        or row["score"] < 0
                        or not 0 <= row["tail_rank"] <= 1
                    ):
                        raise ValueError("Invalid quantile prediction or descriptive rank")
                    direction = "positive" if row["signed_residual"] >= 0 else "negative"
                    work.execute(
                        "INSERT INTO prediction VALUES(?,?,?,?,?,?,?)",
                        (
                            key,
                            partition[1],
                            unit["uf"],
                            direction,
                            row["score"],
                            digest([seed, partition[1], key]),
                            canonical(row).decode(),
                        ),
                    )
            for direction in ("positive", "negative"):
                work.execute(
                    "INSERT INTO selected SELECT unit_key,? FROM prediction WHERE direction=? ORDER BY score DESC,unit_key LIMIT ?",
                    ("ranked_" + direction, direction, per_family),
                )
            # Round-robin hash ranks within UFs avoids silently treating an AC pilot as national.
            uf_counts = [
                (r[0], 0) for r in work.execute("SELECT DISTINCT uf FROM prediction ORDER BY uf")
            ]
            selected_locations = set()
            for _ in range(controls):
                changed = False
                for uf, _ in uf_counts:
                    candidates = work.execute(
                        "SELECT p.unit_key,p.location FROM prediction p WHERE p.uf=? AND p.location NOT IN (SELECT p2.location FROM prediction p2 JOIN selected s ON s.unit_key=p2.unit_key) ORDER BY p.rank,p.unit_key LIMIT 1",
                        (uf,),
                    ).fetchone()
                    if candidates:
                        work.execute(
                            "INSERT INTO selected VALUES(?,?)", (candidates[0], "unflagged_control")
                        )
                        selected_locations.add(candidates[1])
                        changed = True
                        if len(selected_locations) >= controls:
                            break
                if not changed or len(selected_locations) >= controls:
                    break
            work.commit()
            counts = {}
            with (stage / "cases.jsonl").open("wb") as stream:
                for row in work.execute(
                    "SELECT p.unit_key,p.payload,s.reason,p.location FROM prediction p JOIN selected s ON s.unit_key=p.unit_key ORDER BY s.reason,p.unit_key"
                ):
                    prediction = json.loads(row[1])
                    unit = source.execute(
                        "SELECT * FROM units WHERE unit_key=?", (row[0],)
                    ).fetchone()
                    unit_payload = json.loads(unit["payload"])
                    packet = {
                        "case_id": digest([doc["protocol_id"], ev["model_run_id"], row[0], row[2]]),
                        "unit_key": row[0],
                        "stable_location_id": row[3],
                        "selection_reason": row[2],
                        "round": unit["round"],
                        "uf": unit["uf"],
                        "municipality_tse": unit["municipality_tse"],
                        "zone": unit["zone"],
                        "section": unit["section"],
                        "prediction": prediction,
                        "candidate_blinded": True,
                        "candidate_interpretation": "fixed model roles; no anonymous ballot attribution",
                        "source_snapshot_id": unit["source_snapshot_id"],
                        "lineage_keys": unit_payload.get("lineage_keys", {}),
                        "peer_definition": "frozen model training reference",
                        "multiplicity": "descriptive tail ranks; no fraud p-value",
                        "alternative_explanations": [
                            "sampling variability",
                            "local preference or electorate composition",
                            "administrative or source-data differences",
                        ],
                        "corroboration": [],
                        "conclusion": "unresolved",
                    }
                    stream.write(canonical(packet) + b"\n")
                    counts[row[2]] = counts.get(row[2], 0) + 1
        (stage / "selection.sqlite").unlink()
        summary = {
            "version": VERSION,
            "protocol_id": doc["protocol_id"],
            "partition_id": doc["partition_id"],
            "model_run_id": ev["model_run_id"],
            "predictions_sha256": ev["predictions_sha256"],
            "counts": counts,
            "seed": seed,
            "candidate_symmetric": True,
            "scope": "supplied development prediction population; not national",
            "independent_corroboration": "unavailable",
        }
        _write(stage / "summary.json", summary)
        _seal(stage, summary)
        stage.rename(output)
    return summary


def record_review(protocol, journal, case, *, conclusion, explanations, corroboration=()):
    if conclusion not in {"unresolved", "benign", "requires_review"} or not explanations:
        raise ValueError("Review needs supported conclusion and alternative explanations")
    if any(not _anchor(anchor) for anchor in corroboration):
        raise ValueError("Corroboration requires original source anchors")
    doc = load_protocol(protocol)
    with read_only(Path(protocol) / "research.sqlite") as source:
        partition = source.execute(
            "SELECT partition_name FROM unit_partition WHERE unit_key=?", (case["unit_key"],)
        ).fetchone()
    if not partition or partition[0] not in {"training", "calibration", "development_inspected"}:
        raise ValueError("Review would inspect protected or unknown outcome")
    payload = {
        "protocol_id": doc["protocol_id"],
        "partition_id": doc["partition_id"],
        "case_id": case["case_id"],
        "unit_key": case["unit_key"],
        "conclusion": conclusion,
        "alternative_explanations": list(explanations),
        "corroboration": list(corroboration),
        "candidate_blinded": True,
    }
    db = open_journal(journal, protocol)
    try:
        evidence_payload = {
            "protocol_id": doc["protocol_id"],
            "partition_id": doc["partition_id"],
            "case_id": case["case_id"],
            "unit_key": case["unit_key"],
            "case_payload_sha256": digest(case),
            "interpretation": "supplied development case evidence, not independent corroboration",
        }
        evidence_id = digest(["case-evidence", evidence_payload])
        append_record(db, evidence_id, "prediction", evidence_payload)
        rid = digest(["case-review", payload])
        append_record(db, rid, "investigation", payload, references=[evidence_id])
        db.commit()
        return rid
    finally:
        db.close()


def read_national_margin(path, candidate_a, candidate_b):
    body = Path(path).read_bytes()
    ref = json.loads(body)
    if any(
        ref.get(k) != v
        for k, v in {
            "ele": "6258",
            "t": "2",
            "f": "o",
            "tf": "s",
            "dv": "s",
            "tpabr": "br",
            "cdabr": "br",
            "and": "f",
        }.items()
    ):
        raise ValueError(
            "Need an official final visible BR presidential reference, not a UF margin"
        )
    choices = {
        c["n"]: int(c["vap"])
        for cargo in ref["carg"]
        if cargo["cd"] == "1"
        for a in cargo["agr"]
        for p in a["par"]
        for c in p["cand"]
    }
    if candidate_a == candidate_b or candidate_a not in choices or candidate_b not in choices:
        raise ValueError("Official candidate pair required")
    margin = choices[candidate_a] - choices[candidate_b]
    nonnegative_count(margin, "leading_margin")
    if sum(choices.values()) != int(ref["v"]["vvc"]):
        raise ValueError("National candidate reference accounting mismatch")
    return margin, {
        "object_sha256": hashlib.sha256(body).hexdigest(),
        "record_locator": "/carg/1; /v/vvc",
        "status": "official_published_reference; independent BU reconciliation still required",
    }


def conditional_scenario(document, *, national_reference=None):
    mechanism = document["mechanism"]
    if mechanism not in {"removal_exact", "removal_at_most", "switching_cap"}:
        raise ValueError("Unsupported mechanism")
    rows = document["population"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Explicit nonempty affected population required")
    seen = set()
    lower = upper = affected = excess = 0
    supported = True
    for row in rows:
        key = (row["round"], row["election"], row["principal_section_id"])
        if key in seen or key[:2] != (2, "6258"):
            raise ValueError("Overlapping principals or mixed contest/round population")
        seen.add(key)
        for field in ("a", "b", "other", "cap"):
            nonnegative_count(row[field], field)
        a, b, other, cap = (row[k] for k in ("a", "b", "other", "cap"))
        if cap > a + b + other:
            raise ValueError("Completed ballot cap exceeds principal ballots")
        supported &= (
            row.get("cap_unit") == "completed_presidential_ballots"
            and _anchor(row.get("cap_evidence"))
            and _anchor(row.get("counts_evidence"))
        )
        lo, hi = (
            (0, maximum_switch_margin_change(a, cap))
            if mechanism == "switching_cap"
            else removal_contribution_bounds(
                a, b, other, cap, at_most=mechanism == "removal_at_most"
            )
        )
        lower += lo
        upper += hi
        affected += cap
        if "expected_a" in row:
            expected = row["expected_a"]
            if (
                type(expected) not in (int, float)
                or not math.isfinite(expected)
                or not 0 <= expected <= a + b
            ):
                raise ValueError("Invalid fixed-turnout expected votes")
            excess += 2 * (a - expected)
    margin, margin_evidence = (
        read_national_margin(national_reference, document["candidate_a"], document["candidate_b"])
        if national_reference
        else (document.get("assumed_margin"), None)
    )
    if margin is not None:
        nonnegative_count(margin, "margin")
    return {
        "version": VERSION,
        "mechanism": mechanism,
        "affected_cap": affected,
        "margin_change_bounds": [lower, upper],
        "corrected_margin_bounds": [margin - upper, margin - lower] if margin is not None else None,
        "margin_status": "official_published_national_reference_not_independent_recount"
        if margin_evidence
        else "hypothetical_user_assumption"
        if margin is not None
        else "unavailable_national_margin",
        "margin_evidence": margin_evidence,
        "cap_status": "source_anchored_assertions_not_independently_certified"
        if supported
        else "hypothetical_caps",
        "baseline_relative_margin_excess": excess if all("expected_a" in r for r in rows) else None,
        "interpretation": "conditional arithmetic under stated mechanism; not fraudulent ballots or causal impact",
        "candidate_attribution": "unavailable_for_anonymous_cycles",
        "population_hash": digest(rows),
        "national_population_complete": False,
    }


def geographic_sensitivity(
    blocks, output, full_pipeline, *, pipeline_sha256, repetitions=200, seed=42
):
    """Resample whole geography and rerun the caller's full fit and selection."""
    blocks = sorted(set(blocks))
    if (
        not blocks
        or type(repetitions) is not int
        or repetitions < 2
        or not _anchor({"object_sha256": pipeline_sha256, "record_locator": "pipeline"})
    ):
        raise ValueError("Need blocks, repetitions and a pinned full-pipeline implementation")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    identity = {
        "version": VERSION,
        "blocks": blocks,
        "pipeline_sha256": pipeline_sha256,
        "repetitions": repetitions,
        "seed": seed,
    }
    config = output / "configuration.json"
    if (output / "artifact.json").exists():
        artifact = json.loads((output / "artifact.json").read_text())
        if any(artifact.get(k) != v for k, v in identity.items()):
            raise ValueError("Completed sensitivity configuration changed")
        for name, pin in artifact["files"].items():
            if Path(name).name != name or hash_file(output / name) != pin["sha256"]:
                raise ValueError("Completed sensitivity integrity mismatch")
        return json.loads((output / "summary.json").read_text())
    if config.exists() and json.loads(config.read_text()) != identity:
        raise ValueError("Sensitivity checkpoint configuration changed")
    _write(config, identity)
    values = []
    for iteration in range(repetitions):
        checkpoint = output / f"iteration-{iteration:04d}.json"
        rng = random.Random(seed + iteration)
        sampled = [rng.choice(blocks) for _ in blocks]
        if checkpoint.exists():
            result = json.loads(checkpoint.read_text())
            pin = result.pop("result_hash", None)
            if (
                pin != digest(result)
                or result.get("sampled_blocks") != sampled
                or result.get("pipeline_sha256") != pipeline_sha256
            ):
                raise ValueError("Sensitivity checkpoint provenance changed")
        else:
            run = full_pipeline(sampled, seed + iteration)
            if run.get("fit_rerun") is not True or run.get("selection_rerun") is not True:
                raise ValueError(
                    "Sensitivity requires full fit and selection, not selected residual bootstrap"
                )
            value = run.get("baseline_relative_excess")
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Nonfinite baseline-relative excess")
            result = {
                **run,
                "sampled_blocks": sampled,
                "pipeline_sha256": pipeline_sha256,
                "iteration": iteration,
            }
            _write(checkpoint, {**result, "result_hash": digest(result)})
        value = result.get("baseline_relative_excess")
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or result.get("fit_rerun") is not True
            or result.get("selection_rerun") is not True
        ):
            raise ValueError("Corrupted sensitivity checkpoint")
        values.append(value)
    ordered = sorted(values)
    summary = {
        "version": VERSION,
        "configuration_hash": digest(identity),
        "repetitions": repetitions,
        "baseline_relative_excess_median": ordered[len(ordered) // 2],
        "resampling_range": [
            ordered[int(0.025 * (len(ordered) - 1))],
            ordered[int(0.975 * (len(ordered) - 1))],
        ],
        "interpretation": "geographic full-pipeline sensitivity; not causal uncertainty or a national confidence interval",
    }
    _write(output / "summary.json", summary)
    _seal(output, identity)
    return summary


def export_cases_dataset(cases, protocol, output):
    from election_audit.dashboard_data import publish_dataset

    cases = Path(cases)
    artifact = json.loads((cases / "artifact.json").read_text())
    doc = load_protocol(protocol)
    if any(artifact.get(k) != doc[k] for k in ("protocol_id", "partition_id")):
        raise ValueError("Case export protocol mismatch")
    for name, pin in artifact["files"].items():
        if Path(name).name != name or hash_file(cases / name) != pin["sha256"]:
            raise ValueError("Case export source changed")

    def rows():
        with read_only(Path(protocol) / "research.sqlite") as partitions:
            with (cases / "cases.jsonl").open() as stream:
                for line in stream:
                    row = json.loads(line)
                    partition = partitions.execute(
                        "SELECT partition_name FROM unit_partition WHERE unit_key=?",
                        (row["unit_key"],),
                    ).fetchone()
                    if not partition or partition[0] not in {
                        "training",
                        "calibration",
                        "development_inspected",
                    }:
                        raise ValueError("Case export contains protected outcome")
                    yield {**row, "readiness": "descriptive_only"}

    return publish_dataset(
        {"investigations": rows()},
        output,
        release_id=digest(artifact),
        access_state="development_only",
        notes=[
            "Development-only case packets; independent corroboration unavailable; not fraud findings."
        ],
    )


def sensitivity_from_config(configuration, output):
    import importlib.util

    config = json.loads(Path(configuration).read_text())
    source = Path(config["pipeline_file"]).resolve()
    if hash_file(source) != config["pipeline_sha256"]:
        raise ValueError("Full-pipeline callback source changed")
    spec = importlib.util.spec_from_file_location("audit_review_pipeline", source)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load supplied local pipeline")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    callback = getattr(module, config.get("function", "full_pipeline"))
    return geographic_sensitivity(
        config["blocks"],
        output,
        lambda blocks, seed: callback(blocks, seed, config.get("pipeline_config", {})),
        pipeline_sha256=config["pipeline_sha256"],
        repetitions=config.get("repetitions", 200),
        seed=config.get("seed", 42),
    )


def investigations_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    cases = sub.add_parser("cases")
    for name in ("features", "protocol", "evaluation", "output"):
        cases.add_argument("--" + name, type=Path, required=True)
    cases.add_argument("--per-family", type=int, default=20)
    cases.add_argument("--controls", type=int, default=100)
    scenario = sub.add_parser("scenario")
    scenario.add_argument("input", type=Path)
    scenario.add_argument("--national-reference", type=Path)
    scenario.add_argument("--output", type=Path, required=True)
    sensitivity = sub.add_parser("sensitivity")
    sensitivity.add_argument("--configuration", type=Path, required=True)
    sensitivity.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "cases":
        result = build_cases(
            args.features,
            args.protocol,
            args.evaluation,
            args.output,
            per_family=args.per_family,
            controls=args.controls,
        )
    elif args.action == "scenario":
        if args.output.exists():
            raise FileExistsError(args.output)
        result = conditional_scenario(
            json.loads(args.input.read_text()), national_reference=args.national_reference
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _write(args.output, result)
    else:
        result = sensitivity_from_config(args.configuration, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(investigations_main())
