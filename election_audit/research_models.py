"""Frozen, candidate-symmetric conditional models; scores are descriptive, never fraud labels."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from election_audit.research_evaluation import (
    append_record,
    open_journal,
    record_evaluation_units,
    record_final_evaluation,
)
from election_audit.research_protocol import hash_file, load_protocol, read_only
from election_audit.source_inventory import canonical, digest
from election_audit.types import JSON, Argv, Row

VERSION = "research-models-v1"
TARGETS = {
    "turnout": ("turnout_target", "turnout"),
    "candidate_a_share": ("candidate_share_target", "candidate_a_share"),
    "candidate_b_share": ("candidate_share_target", "candidate_b_share"),
    "blank_share": ("blank_null_targets", "blank_share"),
    "null_share": ("blank_null_targets", "null_share"),
    "operational_duration": ("cycle_duration_gap", "duration"),
    "operational_gap": ("cycle_duration_gap", "gap"),
}
QUANTILES = [0.025, 0.25, 0.5, 0.75, 0.975]


def _catalog(feature_release: str | Path, protocol: JSON) -> Path:
    root = Path(feature_release).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    spec = manifest["catalog"]
    path = (root / spec["path"]).resolve()
    if not path.is_relative_to(root) or hash_file(path) != spec["sha256"]:
        raise ValueError("Changed or unsafe feature catalogue")
    identity = protocol["identity"]
    if (
        manifest["release_id"] != identity["feature_release_id"]
        or spec["sha256"] != identity["feature_catalog_sha256"]
    ):
        raise ValueError("Features differ from frozen protocol")
    return path


def _rows(
    features: str | Path,
    protocol_path: str | Path,
    document: JSON,
    target: str,
    partitions: Iterable[str],
    variant: str,
) -> Iterator[Row]:
    feature_id, component = TARGETS[target]
    catalog = _catalog(features, document)
    with read_only(catalog) as db:
        db.execute(
            "ATTACH DATABASE ? AS protocol",
            (str((Path(protocol_path) / "research.sqlite").resolve()),),
        )
        query = (
            "SELECT u.*, f.value AS outcome, f.numerator, f.denominator\n          FROM units u JOIN features f USING(unit_key)\n          JOIN protocol.unit_partition p USING(unit_key)\n          WHERE f.feature_id=? AND f.component=? AND f.readiness_state='ready'\n          AND p.source_ready=1 AND p.partition_name IN ("
            + ",".join(("?" for _ in partitions))
            + ") ORDER BY u.unit_key"
        )
        for row in db.execute(query, (feature_id, component, *partitions)):
            r = dict(row)
            if r["round"] != 2 or r["outcome"] is None or (not math.isfinite(r["outcome"])):
                continue
            context = {
                "uf": r["uf"],
                "municipality": r["uf"] + ":" + r["municipality_tse"],
                "zone": r["zone"],
            }
            electorate = db.execute(
                "SELECT value FROM features WHERE unit_key=? AND feature_id='peer_covariates' AND component='electorate' AND readiness_state='ready'",
                (r["unit_key"],),
            ).fetchone()
            if electorate and electorate[0] is not None:
                context["electorate"] = float(electorate[0])
            if variant == "current_cycle":
                previous = db.execute(
                    "SELECT f.value FROM units u JOIN features f USING(unit_key)\n                  WHERE u.stable_location_id=? AND u.round=1 AND f.feature_id=? AND f.component=?\n                  AND f.readiness_state='ready' ORDER BY u.unit_key",
                    (r["stable_location_id"], feature_id, component),
                ).fetchall()
                if not previous:
                    continue
                context["first_round_location_mean"] = sum((p[0] for p in previous)) / len(previous)
            if variant == "operational_adjusted":
                extra = json.loads(r["payload"])
                if not extra.get("software_version") or not extra.get("device_model"):
                    continue
                context.update(
                    {
                        "software_version": str(extra["software_version"]),
                        "device_model": str(extra["device_model"]),
                    }
                )
            yield {
                "unit_key": r["unit_key"],
                "group": context["municipality"],
                "stable_location_id": r["stable_location_id"],
                "context": context,
                "y": float(r["outcome"]),
                "numerator": r["numerator"],
                "denominator": r["denominator"],
            }


def _predict(model: Any, matrix: Any) -> Any:
    """The pinned QRF release needs dense prediction input; bound conversion by row."""
    import numpy as np

    output = []
    for start in range(0, matrix.shape[0], 64):
        block = matrix[start : start + 64]
        if hasattr(block, "toarray"):
            block = block.toarray()
        output.append(model.predict(block, quantiles=QUANTILES))
    return np.concatenate(output) if output else np.empty((0, len(QUANTILES)))


def _loss(y: Any, predictions: Any) -> float:
    import numpy as np

    error = np.asarray(y)[:, None] - predictions
    return float(
        np.mean(np.maximum(np.asarray(QUANTILES) * error, (np.asarray(QUANTILES) - 1) * error))
    )


def _baseline(training: Sequence[Row], rows: Sequence[Row]) -> Any:
    import numpy as np

    all_values = [r["y"] for r in training]
    result = []
    for row in rows:
        peers = [t for t in training if t["context"]["uf"] == row["context"]["uf"]]
        if "electorate" in row["context"]:
            peers = sorted(
                peers,
                key=lambda t: abs(t["context"].get("electorate", 0) - row["context"]["electorate"]),
            )[:100]
        values = [p["y"] for p in peers] or all_values
        result.append(np.quantile(values, QUANTILES))
    return np.asarray(result)


def _score(y: Any, predictions: Any) -> Any:
    import numpy as np

    p = np.asarray(predictions)
    values = np.asarray(y)
    scale = np.maximum(p[:, 3] - p[:, 1], 1e-06)
    return np.maximum(np.maximum(p[:, 0] - values, values - p[:, 4]), 0) / scale


def fit_models(
    features: str | Path,
    protocol: str | Path,
    output: str | Path,
    *,
    target: str = "turnout",
    variant: str = "no_first_round",
    max_rows: int = 500000,
) -> JSON:
    """Load compact eligible matrices only; test/stress outcomes are never selected."""
    import numpy as np
    from quantile_forest import RandomForestQuantileRegressor
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.model_selection import GroupKFold

    document = load_protocol(protocol)
    if target not in TARGETS or variant not in document["identity"]["design"]["variants"]:
        raise ValueError("Unknown frozen target or variant")
    if max_rows < 1:
        raise ValueError("Positive matrix bound required")
    partitions = {}
    for name in ("training", "calibration"):
        rows = []
        for row in _rows(features, protocol, document, target, [name], variant):
            if len(rows) >= max_rows:
                raise ValueError("Matrix resource bound reached; no partial fit")
            rows.append(row)
        partitions[name] = rows
    train, cal = (partitions["training"], partitions["calibration"])
    if len(train) < 3 or not cal or len({r["group"] for r in train}) < 3:
        raise ValueError("Need eligible training/calibration and three training municipalities")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".models-", dir=output.parent))
    try:
        design = document["identity"]["design"]
        forest = design["forest"]
        seed = design["seed"]
        y = np.asarray([r["y"] for r in train])
        groups = [r["group"] for r in train]
        contexts = [r["context"] for r in train]
        cv = {}
        baseline_cv = []
        for leaf in forest["min_samples_leaf"]:
            losses = []
            for ti, vi in GroupKFold(n_splits=3).split(contexts, y, groups):
                vec = DictVectorizer(sparse=True)
                x = vec.fit_transform([contexts[i] for i in ti])
                model = RandomForestQuantileRegressor(
                    n_estimators=forest["n_estimators"],
                    max_depth=forest["max_depth"],
                    min_samples_leaf=leaf,
                    n_jobs=forest["n_jobs"],
                    random_state=seed,
                )
                model.fit(x, y[ti])
                prediction = _predict(model, vec.transform([contexts[i] for i in vi]))
                losses.append(_loss(y[vi], prediction))
                if leaf == forest["min_samples_leaf"][0]:
                    baseline_cv.append(
                        _loss(y[vi], _baseline([train[i] for i in ti], [train[i] for i in vi]))
                    )
            cv[str(leaf)] = float(np.mean(losses))
        leaf = min(forest["min_samples_leaf"], key=lambda n: (cv[str(n)], n))
        vectorizer = DictVectorizer(sparse=True)
        x = vectorizer.fit_transform(contexts)
        model = RandomForestQuantileRegressor(
            n_estimators=forest["n_estimators"],
            max_depth=forest["max_depth"],
            min_samples_leaf=leaf,
            n_jobs=forest["n_jobs"],
            random_state=seed,
        )
        model.fit(x, y)
        pred = _predict(model, vectorizer.transform([r["context"] for r in cal]))
        baseline = _baseline(train, cal)
        observed = [r["y"] for r in cal]
        calibration_scores = _score(observed, pred)
        baseline_scores = _score(observed, baseline)
        chosen = "forest" if cv[str(leaf)] < float(np.mean(baseline_cv)) else "baseline"
        config = {
            "version": VERSION,
            "protocol_id": document["protocol_id"],
            "partition_id": document["partition_id"],
            "feature_catalog_sha256": document["identity"]["feature_catalog_sha256"],
            "target": target,
            "variant": variant,
            "quantiles": QUANTILES,
            "forest": forest,
            "selected_leaf": leaf,
            "seed": seed,
            "training_units_sha256": digest([r["unit_key"] for r in train]),
            "calibration_units_sha256": digest([r["unit_key"] for r in cal]),
        }
        run_id = digest(config)
        artifact = {
            "config": config,
            "training": train,
            "model": model,
            "vectorizer": vectorizer,
            "calibration_scores": calibration_scores if chosen == "forest" else baseline_scores,
            "chosen": chosen,
        }
        with (staging / "model.pickle").open("wb") as stream:
            pickle.dump(artifact, stream, protocol=5)
        metrics = {
            "training_n": len(train),
            "calibration_n": len(cal),
            "cv_quantile_loss": cv,
            "forest_loss": _loss(observed, pred),
            "baseline_loss": _loss(observed, baseline),
            "selected_estimator": chosen,
            "forest_coverage": float(
                np.mean((np.asarray(observed) >= pred[:, 0]) & (np.asarray(observed) <= pred[:, 4]))
            ),
            "score_interpretation": "descriptive_tail_rank; no exchangeability or fraud inference",
        }
        manifest = {
            "version": VERSION,
            "run_id": run_id,
            "config": config,
            "metrics": metrics,
            "model_sha256": hash_file(staging / "model.pickle"),
            "source_status": "synthetic"
            if document["identity"].get("synthetic")
            else "feature_release_as_declared",
        }
        (staging / "model.json").write_bytes(canonical(manifest) + b"\n")
        journal = open_journal(staging / "journal.sqlite", protocol)
        append_record(
            journal,
            run_id,
            "model_run",
            {
                "protocol_id": document["protocol_id"],
                "partition_id": document["partition_id"],
                "fitted": True,
                "state": "complete",
                "config": config,
                "metrics": metrics,
                "model_sha256": manifest["model_sha256"],
            },
        )
        journal.commit()
        journal.close()
        staging.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(staging)
        raise


def _load_model(path: str | Path) -> tuple[JSON, Any]:
    path = Path(path)
    manifest = json.loads((path / "model.json").read_text())
    if (
        hash_file(path / "model.pickle") != manifest["model_sha256"]
        or digest(manifest["config"]) != manifest["run_id"]
    ):
        raise ValueError("Model artifact integrity mismatch")
    with (path / "model.pickle").open("rb") as stream:
        model = pickle.load(stream)
    return (manifest, model)


def evaluate_models(
    features: str | Path,
    protocol: str | Path,
    model_path: str | Path,
    output: str | Path,
    *,
    final: bool = False,
) -> JSON:
    import numpy as np

    document = load_protocol(protocol)
    manifest, model = _load_model(model_path)
    config = manifest["config"]
    if (
        config["protocol_id"] != document["protocol_id"]
        or config["partition_id"] != document["partition_id"]
    ):
        raise ValueError("Model/protocol mismatch")
    stage = "final" if final else "development"
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    journal = open_journal(Path(model_path) / "journal.sqlite", protocol)
    identity = {
        "protocol_id": document["protocol_id"],
        "partition_id": document["partition_id"],
        "model_run_id": manifest["run_id"],
        "stage": stage,
    }
    identity["state"] = "complete"
    access_id = digest([identity, "access"])
    evaluation_id = digest([identity, "evaluation"])
    if final:
        if journal.execute("SELECT 1 FROM ledger WHERE record_kind='final_evaluation'").fetchone():
            raise ValueError("Final evaluation already complete")
        append_record(journal, access_id, "test_access", identity, references=[manifest["run_id"]])
        record_evaluation_units(
            journal,
            access_id,
            (
                r[0]
                for r in journal.execute(
                    "SELECT unit_key FROM unit_partition WHERE partition_name='test'"
                )
            ),
            access=True,
        )
        journal.commit()
    rows = _rows(
        features,
        protocol,
        document,
        config["target"],
        ["test"] if final else ["calibration"],
        config["variant"],
    )
    n = 0
    sumloss = 0.0
    with (output / "predictions.jsonl").open("wb") as stream:
        for row in rows:
            p = (
                _predict(model["model"], model["vectorizer"].transform([row["context"]]))
                if model["chosen"] == "forest"
                else _baseline(model["training"], [row])
            )
            score = float(_score([row["y"]], p)[0])
            cal = np.asarray(model["calibration_scores"])
            rank = float((1 + np.sum(cal >= score)) / (len(cal) + 1))
            record = {
                "unit_key": row["unit_key"],
                "observed": row["y"],
                "quantiles": p[0].tolist(),
                "signed_residual": float(row["y"] - p[0, 2]),
                "score": score,
                "tail_rank": rank,
                "interpretation": "descriptive_only",
                "model_run_id": manifest["run_id"],
            }
            stream.write(canonical(record) + b"\n")
            n += 1
            sumloss += _loss([row["y"]], p)
    payload = {
        **identity,
        "state": "complete",
        "eligible_predictions": n,
        "quantile_loss": sumloss / n if n else None,
        "predictions_sha256": hash_file(output / "predictions.jsonl"),
        "missing_outcomes": "protected units without eligible target retained in evaluation population; no outcome imputation",
    }
    append_record(
        journal,
        evaluation_id,
        "evaluation",
        payload,
        references=[manifest["run_id"], access_id] if final else [manifest["run_id"]],
    )
    if final:
        record_evaluation_units(
            journal,
            evaluation_id,
            (
                r[0]
                for r in journal.execute(
                    "SELECT unit_key FROM unit_partition WHERE partition_name='test'"
                )
            ),
        )
        record_final_evaluation(
            journal,
            digest([identity, "final"]),
            model_run_id=manifest["run_id"],
            evaluation_id=evaluation_id,
            access_id=access_id,
        )
    journal.commit()
    journal.close()
    (output / "evaluation.json").write_bytes(canonical(payload) + b"\n")
    return payload


def simulate_models(
    features: str | Path, protocol: str | Path, model_path: str | Path, output: str | Path
) -> JSON:
    """Frozen synthetic sensitivity experiments on calibration outcomes; no source writes."""
    import numpy as np

    doc = load_protocol(protocol)
    manifest, model = _load_model(model_path)
    if manifest["config"]["protocol_id"] != doc["protocol_id"]:
        raise ValueError("Model/protocol mismatch")
    rows = list(
        _rows(
            features,
            protocol,
            doc,
            manifest["config"]["target"],
            ["calibration"],
            manifest["config"]["variant"],
        )
    )
    if not rows:
        raise ValueError("No eligible calibration population")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    spec = doc["identity"]["design"]["simulations"]
    original = np.asarray([r["y"] for r in rows])
    groups = sorted({r["group"] for r in rows})
    predictions = (
        _predict(model["model"], model["vectorizer"].transform([r["context"] for r in rows]))
        if model["chosen"] == "forest"
        else _baseline(model["training"], rows)
    )
    threshold = float(np.quantile(model["calibration_scores"], 0.95))
    with (output / "simulations.jsonl").open("wb") as stream:
        for mechanism in spec["mechanisms"]:
            for concentration in spec["concentration"]:
                for fraction in spec["affected_fractions"]:
                    for repetition in range(spec["repetitions"]):
                        rng = np.random.default_rng(spec["seed"] + repetition)
                        mask: Any = np.zeros(len(rows), dtype=bool)
                        if fraction:
                            if concentration == "dispersed":
                                mask[
                                    rng.choice(
                                        len(rows), max(1, int(len(rows) * fraction)), replace=False
                                    )
                                ] = True
                            else:
                                chosen = set(
                                    rng.choice(
                                        groups, max(1, int(len(groups) * fraction)), replace=False
                                    )
                                )
                                mask = np.asarray([r["group"] in chosen for r in rows], dtype=bool)
                        changed = original.copy()
                        if mechanism in {"additions", "duplicated_history"}:
                            changed[mask] += 0.05 * np.maximum(1, np.abs(changed[mask]))
                        elif mechanism in {"switching", "turnout_reduction", "missing_history"}:
                            changed[mask] -= 0.05 * np.maximum(1, np.abs(changed[mask]))
                        else:
                            changed[mask] += 60.0
                        flagged = _score(changed, predictions) > threshold
                        result = {
                            "mechanism": mechanism,
                            "concentration": concentration,
                            "fraction": fraction,
                            "repetition": repetition,
                            "affected": int(mask.sum()),
                            "detected": int((flagged & mask).sum()),
                            "false_alarms": int((flagged & ~mask).sum()),
                            "population": len(rows),
                            "interpretation": "synthetic feature perturbation sensitivity; no refitting; not ballot-mechanism power",
                        }
                        stream.write(canonical(result) + b"\n")
    result = {
        "version": VERSION,
        "protocol_id": doc["protocol_id"],
        "model_run_id": manifest["run_id"],
        "simulation_sha256": hash_file(output / "simulations.jsonl"),
        "limits": "feature perturbations only; full ballot/session mechanism injection and refit power remain separate validation",
    }
    (output / "simulation.json").write_bytes(canonical(result) + b"\n")
    return result


def perturb_mechanism(
    records: Sequence[Row], mechanism: str, *, seed: int, fraction: float, concentration: float
) -> Sequence[Row]:
    """Transform reconciled anonymous counts or sanitized histories on independent copies."""
    import copy

    import numpy as np

    if mechanism not in {
        "additions",
        "switching",
        "turnout_reduction",
        "duplicated_history",
        "missing_history",
        "clock_error",
    }:
        raise ValueError("Unknown mechanism")
    if not 0 <= fraction <= 1 or concentration not in {"dispersed", "municipal"}:
        raise ValueError("Invalid injection scope")
    result = copy.deepcopy(records)
    rng = np.random.default_rng(seed)
    if concentration == "municipal":
        groups = sorted({r["group"] for r in records})
        chosen = (
            set(
                rng.choice(
                    groups, min(len(groups), max(1, int(len(groups) * fraction))), replace=False
                )
            )
            if fraction
            else set()
        )
        selected = {i for i, r in enumerate(records) if r["group"] in chosen}
    else:
        selected = (
            set(
                rng.choice(
                    len(records),
                    min(len(records), max(1, int(len(records) * fraction))),
                    replace=False,
                ).tolist()
            )
            if fraction and records
            else set()
        )
    for i, row in enumerate(result):
        row["injected"] = False
        if i not in selected:
            continue
        if mechanism in {"additions", "switching", "turnout_reduction"}:
            for key in ("a", "b", "other", "electorate"):
                if type(row.get(key)) is not int or row[key] < 0:
                    raise ValueError("Mechanism requires reconciled nonnegative ballot counts")
            if row["a"] + row["b"] + row["other"] > row["electorate"]:
                raise ValueError("Ballots exceed electorate")
            q = max(1, int(0.05 * (row["a"] + row["b"] + row["other"])))
            if mechanism == "additions":
                q = min(q, row["electorate"] - row["a"] - row["b"] - row["other"])
                row["a"] += q
            elif mechanism == "switching":
                q = min(q, row["b"])
                row["b"] -= q
                row["a"] += q
            else:
                q = min(q, row["b"])
                row["b"] -= q
            row["injected"] = bool(q)
        else:
            events = row.get("events")
            if not isinstance(events, list) or not events:
                raise ValueError("Log mechanism requires a nonempty sanitized event history")
            if any((set(e) - {"kind", "timestamp", "duration"} for e in events)):
                raise ValueError("Unredacted/unsupported event fields")
            if mechanism == "duplicated_history":
                row["events"] = events + copy.deepcopy(events)
            elif mechanism == "missing_history":
                row["events"] = events[: len(events) // 2]
            else:
                for event in row["events"]:
                    if type(event.get("timestamp")) not in (int, float):
                        raise ValueError("Clock injection requires numeric sanitized time")
                    event["timestamp"] += 60
            row["injected"] = True
    return result


def run_mechanism_validation(
    training: Sequence[Row],
    calibration: Sequence[Row],
    evaluation: Sequence[Row],
    output: str | Path,
    *,
    fit_calibrate_score: Callable[..., list[bool]],
    callback_id: str,
    specification: JSON,
    max_experiments: int | None = None,
) -> JSON:
    """Resume per-mechanism/seed refit experiments; callback must run the complete estimator pipeline.

    The caller supplies development-only populations. All callback inputs are independent
    copies; callbacks return one boolean signal per evaluation unit. No protected test
    population is read by this API. Statistical fraud conclusions are never generated.
    """
    import copy

    if not callback_id or not callable(fit_calibrate_score):
        raise ValueError("A pinned refit callback identity is required")
    identity = {
        "version": VERSION,
        "callback_id": callback_id,
        "specification": specification,
        "training_sha256": digest(training),
        "calibration_sha256": digest(calibration),
        "evaluation_sha256": digest(evaluation),
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(output / "simulations.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS identity(payload TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS experiment(id TEXT PRIMARY KEY,payload TEXT)")
    prior = db.execute("SELECT payload FROM identity").fetchone()
    if prior and prior[0] != canonical(identity).decode():
        db.close()
        raise ValueError("Resume inputs/refit callback differ")
    if not prior:
        db.execute("INSERT INTO identity VALUES(?)", (canonical(identity).decode(),))
        db.commit()
    newly_completed = 0
    for mechanism in specification["mechanisms"]:
        for concentration in specification["concentration"]:
            for fraction in specification["affected_fractions"]:
                for repetition in range(specification["repetitions"]):
                    setting = {
                        "mechanism": mechanism,
                        "concentration": concentration,
                        "fraction": fraction,
                        "seed": specification["seed"] + repetition,
                    }
                    key = digest(setting)
                    if db.execute("SELECT 1 FROM experiment WHERE id=?", (key,)).fetchone():
                        continue
                    if max_experiments is not None and newly_completed >= max_experiments:
                        continue
                    try:
                        arguments = {
                            "mechanism": mechanism,
                            "concentration": concentration,
                            "fraction": fraction,
                        }
                        train = perturb_mechanism(training, seed=setting["seed"], **arguments)
                        cal = perturb_mechanism(
                            calibration, seed=setting["seed"] + 10000, **arguments
                        )
                        test = perturb_mechanism(
                            evaluation, seed=setting["seed"] + 20000, **arguments
                        )
                        flags = list(
                            fit_calibrate_score(
                                copy.deepcopy(train),
                                copy.deepcopy(cal),
                                copy.deepcopy(test),
                                setting["seed"],
                            )
                        )
                        if len(flags) != len(test) or any((type(f) is not bool for f in flags)):
                            raise ValueError(
                                "Refit callback requires exactly one boolean signal per evaluation unit"
                            )
                        affected = sum((bool(r["injected"]) for r in test))
                        result = {
                            **setting,
                            "state": "complete",
                            "affected": affected,
                            "detected": sum((f and r["injected"] for f, r in zip(flags, test))),
                            "false_alarms": sum(
                                (f and (not r["injected"]) for f, r in zip(flags, test))
                            ),
                            "evaluation_n": len(test),
                            "interpretation": "specified synthetic mechanism and complete supplied refit pipeline only",
                        }
                    except ValueError as exc:
                        result = {**setting, "state": "unavailable", "reason": str(exc)}
                    db.execute(
                        "INSERT INTO experiment VALUES(?,?)", (key, canonical(result).decode())
                    )
                    db.commit()
                    newly_completed += 1
    counts = dict(
        db.execute("SELECT json_extract(payload,'$.state'),count(*) FROM experiment GROUP BY 1")
    )
    db.close()
    result = {
        "identity": identity,
        "states": counts,
        "database_sha256": hash_file(output / "simulations.sqlite"),
    }
    (output / "validation.json").write_bytes(canonical(result) + b"\n")
    return result


def _count_outcome(row: Row, target: str) -> float | None:
    total = row["a"] + row["b"] + row["other"]
    if target == "turnout":
        return total / row["electorate"] if row["electorate"] else None
    if target in {"candidate_a_share", "candidate_b_share"}:
        valid = row["a"] + row["b"]
        return row["a" if target == "candidate_a_share" else "b"] / valid if valid else None
    if target in {"blank_share", "null_share"}:
        return row["blank" if target == "blank_share" else "null"] / total if total else None
    events = row.get("events", [])
    if target == "operational_duration":
        values = [e["duration"] for e in events if type(e.get("duration")) in (int, float)]
    else:
        values = [
            b["timestamp"] - a["timestamp"]
            for a, b in zip(events, events[1:])
            if "timestamp" in a and "timestamp" in b and b["timestamp"] >= a["timestamp"]
        ]
    if not values:
        return None
    return sum(values) / len(values)


def mechanism_refit_callback(manifest: JSON) -> Callable[..., list[bool]]:
    """Repeat leaf selection, estimator choice, fitting and calibration after each injection."""

    def refit(
        training: Sequence[Row], calibration: Sequence[Row], evaluation: Sequence[Row], seed: int
    ) -> list[bool]:
        import numpy as np
        from quantile_forest import RandomForestQuantileRegressor
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.model_selection import GroupKFold

        target = manifest["config"]["target"]
        spec = manifest["config"]["forest"]

        def transform(rows: Iterable[Row]) -> list[JSON]:
            result = []
            for row in rows:
                value = _count_outcome(row, target)
                if value is None:
                    raise ValueError("Injected target has zero/missing denominator")
                context = dict(row["context"])
                context["electorate"] = row["electorate"]
                result.append({**row, "context": context, "y": value})
            return result

        train, cal, test = map(transform, (training, calibration, evaluation))
        y = np.asarray([r["y"] for r in train])
        groups = [r["group"] for r in train]
        if len(set(groups)) < 3:
            raise ValueError("Refit validation needs three training municipalities")
        losses = {}
        base = []
        for leaf in spec["min_samples_leaf"]:
            errors = []
            for ti, vi in GroupKFold(3).split(train, y, groups):
                tr = [train[i] for i in ti]
                va = [train[i] for i in vi]
                vector = DictVectorizer(sparse=True)
                x = vector.fit_transform([r["context"] for r in tr])
                forest = RandomForestQuantileRegressor(
                    n_estimators=spec["n_estimators"],
                    max_depth=spec["max_depth"],
                    min_samples_leaf=leaf,
                    n_jobs=spec["n_jobs"],
                    random_state=seed,
                )
                forest.fit(x, y[ti])
                errors.append(
                    _loss(y[vi], _predict(forest, vector.transform([r["context"] for r in va])))
                )
                if leaf == spec["min_samples_leaf"][0]:
                    base.append(_loss(y[vi], _baseline(tr, va)))
            losses[leaf] = float(np.mean(errors))
        leaf = min(losses, key=lambda n: (losses[n], n))
        if losses[leaf] < float(np.mean(base)):
            vector = DictVectorizer(sparse=True)
            x = vector.fit_transform([r["context"] for r in train])
            forest = RandomForestQuantileRegressor(
                n_estimators=spec["n_estimators"],
                max_depth=spec["max_depth"],
                min_samples_leaf=leaf,
                n_jobs=spec["n_jobs"],
                random_state=seed,
            )
            forest.fit(x, y)
            cp = _predict(forest, vector.transform([r["context"] for r in cal]))
            tp = _predict(forest, vector.transform([r["context"] for r in test]))
        else:
            cp = _baseline(train, cal)
            tp = _baseline(train, test)
        threshold = float(np.quantile(_score([r["y"] for r in cal], cp), 0.95))
        return [bool(v) for v in (_score([r["y"] for r in test], tp) > threshold)]

    return refit


def validate_mechanisms(
    features: str | Path,
    protocol: str | Path,
    model_path: str | Path,
    output: str | Path,
    *,
    max_experiments: int | None = None,
    histories: str | Path | None = None,
    repetitions: int | None = None,
) -> JSON:
    """Refit on reconciled development-copy injections, never the protected test set."""
    document = load_protocol(protocol)
    manifest, _ = _load_model(model_path)
    if manifest["config"]["protocol_id"] != document["protocol_id"]:
        raise ValueError("Model/protocol mismatch")
    event_map = {}
    if histories:
        for line in Path(histories).read_text().splitlines():
            row = json.loads(line)
            if set(row) != {"unit_key", "events"}:
                raise ValueError("Sanitized histories require exact unit_key/events")
            event_map[row["unit_key"]] = row["events"]
    target = manifest["config"]["target"]
    variant = manifest["config"]["variant"]
    populations = []
    with read_only(_catalog(features, document)) as db:
        for partition in ("training", "calibration"):
            result = []
            for row in _rows(features, protocol, document, target, [partition], variant):
                raw = db.execute(
                    "SELECT payload FROM counts WHERE unit_key=?", (row["unit_key"],)
                ).fetchone()
                if not raw:
                    raise ValueError("No reconciled count evidence for mechanism validation")
                counts = json.loads(raw[0])
                choices = counts.get("choices", {})
                if not counts.get("complete_choices") or not counts.get(
                    "legal_final_counts_ready", True
                ):
                    raise ValueError("Unresolved choice/destination evidence")

                def value(code: str) -> Any:
                    entry = choices.get(code)
                    return entry.get("count") if isinstance(entry, dict) else entry

                a, b = value("13"), value("22")
                if type(a) is not int or type(b) is not int:
                    raise ValueError("Explicit 13/22 runoff counts required")
                total = counts["total_presidential_ballots"]
                result.append(
                    {
                        **row,
                        "a": a,
                        "b": b,
                        "other": total - a - b,
                        "electorate": counts["eligible_electors"],
                        "blank": counts["blank_votes"],
                        "null": counts["null_votes"],
                        "events": event_map.get(row["unit_key"], []),
                    }
                )
            populations.append(result)
    training, development = populations
    cal = [r for r in development if int(digest(r["stable_location_id"]), 16) % 2 == 0]
    evaluation = [r for r in development if int(digest(r["stable_location_id"]), 16) % 2 == 1]
    if not cal or not evaluation:
        raise ValueError("Need separate development calibration and injection evaluation locations")
    spec = dict(document["identity"]["design"]["simulations"])
    if repetitions is not None:
        if not 1 <= repetitions <= spec["repetitions"]:
            raise ValueError("Invalid bounded repetition subset")
        spec["repetitions"] = repetitions
    callback_id = digest(
        [
            VERSION,
            "full-QRF-count-refit",
            manifest["config"],
            hash_file(__file__),
            hash_file(histories) if histories else None,
        ]
    )
    return run_mechanism_validation(
        training,
        cal,
        evaluation,
        output,
        fit_calibrate_score=mechanism_refit_callback(manifest),
        callback_id=callback_id,
        specification=spec,
        max_experiments=max_experiments,
    )


def research_models_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["fit", "evaluate", "simulate", "validate-mechanisms"])
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--target", choices=TARGETS, default="turnout")
    parser.add_argument("--variant", default="no_first_round")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--max-experiments", type=int)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--sanitized-histories", type=Path)
    args = parser.parse_args(argv)
    if args.action == "fit":
        result = fit_models(
            args.features, args.protocol, args.output, target=args.target, variant=args.variant
        )
    elif not args.model:
        parser.error("--model required for evaluate/simulate")
    elif args.action == "validate-mechanisms":
        result = validate_mechanisms(
            args.features,
            args.protocol,
            args.model,
            args.output,
            max_experiments=args.max_experiments,
            histories=args.sanitized_histories,
            repetitions=args.repetitions,
        )
    elif args.action == "evaluate":
        result = evaluate_models(
            args.features, args.protocol, args.model, args.output, final=args.final
        )
    else:
        result = simulate_models(args.features, args.protocol, args.model, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(research_models_main())
