"""Coherent official reference sets, distinct from independently summed BUs."""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from election_audit.elections import election_for_round
from election_audit.electoral_verification import (
    BASE,
    VERSION,
    Evidence,
    _candidates,
    _json,
    _required,
    inspect_evidence,
)
from election_audit.source_inventory import ALL_UFS


def reference_metrics(ref):
    return {
        "principals": int(ref["s"]["st"]),
        "eligible_electors": int(ref["e"]["te"]),
        "attending_voters": int(ref["e"]["c"]),
        "abstaining_electors": int(ref["e"]["a"]),
        "total_presidential_ballots": int(ref["v"]["tv"]),
        "blank_votes": int(ref["v"]["vb"]),
        "null_votes": int(ref["v"]["vn"]),
        "technical_null_votes": int(ref["v"].get("vnt", 0)),
        **{"candidate_" + c: v["votes"] for c, v in _candidates(ref).items()},
    }


def final_reference(store, url, election, level, code):
    body, sha = store.get(url, "EA20_" + level)
    ref = json.loads(body)
    _required(
        (ref["ele"], ref["t"], ref["f"], ref["dv"])
        == (election.election_code, str(election.round), "o", "s"),
        "Reference election/visibility mismatch",
    )
    _required(ref["tpabr"] == level and ref["cdabr"] == code, "Reference geography mismatch")
    _required(ref["and"] == "f" and int(ref["s"]["snt"]) == 0, "Reference coverage incomplete")
    if level in {"uf", "br"}:
        _required(ref["tf"] == "s", "Reference lacks final totalization")
    return ref, sha


def _publish(store, summary, filename="summary.json"):
    directory = store.directory
    (directory / filename).write_text(_json(summary) + "\n")
    store.db.close()
    p = directory / "evidence.sqlite"
    with p.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    artifact = {
        "version": VERSION,
        "files": {"evidence.sqlite": {"sha256": sha, "bytes": p.stat().st_size}},
        "summary": summary,
    }
    (directory / "artifact.json").write_text(_json(artifact) + "\n")
    return summary


def national_references(output, *, round_number=2, download=False):
    if (Path(output) / "artifact.json").exists():
        return inspect_evidence(output)
    election = election_for_round(round_number)
    store = Evidence(output, allow_download=download)
    national, brsha = final_reference(
        store,
        f"{BASE}/ele2026/{election.election_code}/dados/br/br-c0001-e{int(election.election_code):06d}-u.json",
        election,
        "br",
        "br",
    )
    actual = Counter()
    pins = {"br": brsha}
    for uf in ALL_UFS:
        ref, sha = final_reference(
            store,
            f"{BASE}/ele2026/{election.election_code}/dados/{uf}/{uf}-c0001-e{int(election.election_code):06d}-u.json",
            election,
            "uf",
            uf,
        )
        actual.update(reference_metrics(ref))
        pins[uf] = sha
    expected = reference_metrics(national)
    differences = {k: {"UF_sum": actual[k], "BR": v} for k, v in expected.items() if actual[k] != v}
    candidates = _candidates(national)
    ordered = sorted(candidates, key=lambda c: (-candidates[c]["votes"], c))
    summary = {
        "version": "official-final-reference-set-v1",
        "election": election.as_dict(),
        "state": "reference_to_reference_matched" if not differences else "reference_difference",
        "references": pins,
        "reference_count": len(pins),
        "national_metrics": expected,
        "uf_sums": dict(actual),
        "differences": differences,
        "candidate_totals": candidates,
        "national_BU_reconciliation": "not_established",
        "independent_voter_intent": "not_established",
    }
    if len(ordered) == 2 and not differences:
        summary.update(
            {
                "leading_ballot": ordered[0],
                "trailing_ballot": ordered[1],
                "national_margin": candidates[ordered[0]]["votes"]
                - candidates[ordered[1]]["votes"],
            }
        )
    return _publish(store, summary)


def reconcile_hierarchy(parent, output, *, download=False):
    parent = Path(parent).resolve()
    checked = inspect_evidence(parent)
    if (Path(output) / "artifact.json").exists():
        return inspect_evidence(output)
    election = election_for_round(checked["election"]["round"])
    uf = checked["uf"]
    store = Evidence(output, allow_download=download)
    db = sqlite3.connect((parent / "evidence.sqlite").as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    for url, sha, role, path in db.execute(
        "SELECT o.url,o.sha256,o.role,s.path FROM observation o JOIN source_object s USING(sha256) WHERE o.role LIKE 'EA20_%'"
    ):
        store.keep((parent / path).read_bytes(), url, role, parent_sha256=sha)
    scopes = [("uf", "", "")]
    scopes.extend(
        ("mu", mu, "")
        for (mu,) in db.execute("SELECT DISTINCT municipality FROM section_result ORDER BY 1")
    )
    scopes.extend(
        ("zona", mu, zone)
        for mu, zone in db.execute(
            "SELECT DISTINCT municipality,zone FROM section_result ORDER BY 1,2"
        )
    )
    states = Counter()
    for level, mu, zone in scopes:
        stem = uf + mu + ("-z" + zone if zone else "")
        ref, sha = final_reference(
            store,
            f"{BASE}/ele2026/{election.election_code}/dados/{uf}/{stem}-c0001-e{int(election.election_code):06d}-u.json",
            election,
            level,
            {"uf": uf, "mu": mu, "zona": zone}[level],
        )
        conditions = []
        params = []
        if mu:
            conditions.append("municipality=?")
            params.append(mu)
        if zone:
            conditions.append("zone=?")
            params.append(zone)
        query = "SELECT state,payload FROM section_result" + (
            " WHERE " + " AND ".join(conditions) if conditions else ""
        )
        totals = Counter()
        unavailable = 0
        for state, payload in db.execute(query, params):
            if state != "content_verified":
                unavailable += 1
                continue
            row = json.loads(payload)
            totals["principals"] += 1
            totals.update(
                {
                    k: row[k]
                    for k in (
                        "eligible_electors",
                        "attending_voters",
                        "abstaining_electors",
                        "total_presidential_ballots",
                        "blank_votes",
                        "null_votes",
                    )
                }
            )
            totals.update(
                {
                    "candidate_" + c: v["count"]
                    for c, v in row["choices"].items()
                    if c.isdigit() and int(c) < 95
                }
            )
        expected = reference_metrics(ref)
        # Legal reclassification is a separate readiness condition, never inferred from raw nominal equality.
        expected.pop("technical_null_votes", None)
        complete = not unavailable and totals["principals"] == expected["principals"]
        differences = (
            {
                k: {"BU_sum": totals[k], "reference": v}
                for k, v in expected.items()
                if totals[k] != v
            }
            if complete
            else None
        )
        state = (
            "matched"
            if complete and not differences
            else "numeric_difference"
            if complete
            else "incomplete_population"
        )
        states[state] += 1
        store.db.execute(
            "INSERT INTO hierarchy VALUES(?,?,?,?,?)",
            (
                level,
                mu,
                zone,
                state,
                _json(
                    {
                        "actual": dict(totals),
                        "expected": expected,
                        "differences": differences,
                        "reference_sha256": sha,
                    }
                ),
            ),
        )
        store.db.commit()
    db.close()
    parentpin = json.loads((parent / "artifact.json").read_text())["files"]["evidence.sqlite"][
        "sha256"
    ]
    return _publish(
        store,
        {
            "version": "electoral-hierarchy-v1",
            "election": election.as_dict(),
            "uf": uf,
            "parent_database_sha256": parentpin,
            "comparisons": len(scopes),
            "states": dict(states),
            "national_BU_reconciliation": "not_established",
        },
    )


def references_main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("national", "hierarchy"))
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--parent", type=Path)
    p.add_argument("--round", type=int, choices=(1, 2), default=2)
    p.add_argument("--download", action="store_true")
    a = p.parse_args(argv)
    result = (
        national_references(a.output, round_number=a.round, download=a.download)
        if a.operation == "national"
        else reconcile_hierarchy(a.parent, a.output, download=a.download)
    )
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(references_main())
