"""Disk-backed BWEB/binary BU linkage and external hierarchy evidence."""

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from election_audit.binary_bu import decode_bu
from election_audit.elections import ElectionDescriptor, election_for_round
from election_audit.types import JSON, Argv, Row


def member_sections(principal: str, raw: str) -> list[str]:
    """Sorted members of a principal section from DS_SECOES_AGREGADAS, [] when TSE marks the
    composition unknown (#NE#, -3). An empty string means no aggregation; it never becomes a
    member section 0000 (xr1-20261109-P5-10). Raises ValueError on duplicates."""
    from election_audit.features import verified_member_sections

    return verified_member_sections(principal, {"composition_raw": raw})


VERSION = "electoral-verification-v1"
BASE = "https://resultados.tse.jus.br/oficial"


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _required(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


class Evidence:
    def __init__(self, directory: str | Path, *, allow_download: bool = False) -> None:
        self.directory = Path(directory)
        self.allow_download = allow_download
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "objects").mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.directory / "evidence.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS source_object(sha256 TEXT PRIMARY KEY, bytes INTEGER, path TEXT);
        CREATE TABLE IF NOT EXISTS observation(url TEXT,sha256 TEXT,observed_at TEXT,role TEXT,payload TEXT,PRIMARY KEY(url,sha256));
        CREATE TABLE IF NOT EXISTS bweb(municipality TEXT,zone TEXT,section TEXT,line INTEGER,choice TEXT,count INTEGER,payload TEXT,PRIMARY KEY(municipality,zone,section,choice));
        CREATE TABLE IF NOT EXISTS section_result(uf TEXT,municipality TEXT,zone TEXT,section TEXT,round INTEGER,state TEXT,payload TEXT,PRIMARY KEY(uf,municipality,zone,section,round));
        CREATE TABLE IF NOT EXISTS choice_count(uf TEXT,municipality TEXT,zone TEXT,section TEXT,round INTEGER,choice TEXT,count INTEGER,origin TEXT,PRIMARY KEY(uf,municipality,zone,section,round,choice));
        CREATE TABLE IF NOT EXISTS hierarchy(level TEXT,municipality TEXT,zone TEXT,state TEXT,payload TEXT,PRIMARY KEY(level,municipality,zone));
        CREATE TABLE IF NOT EXISTS run(identity TEXT PRIMARY KEY,payload TEXT);
        """)

    def keep(self, body: bytes, url: str, role: str, **extra: Any) -> tuple[bytes, str]:
        digest = _sha(body)
        path = self.directory / "objects" / digest
        if path.exists():
            _required(_sha(path.read_bytes()) == digest, "Preserved source corruption")
        else:
            temp = path.with_suffix(".part")
            temp.write_bytes(body)
            temp.replace(path)
        self.db.execute(
            "INSERT OR IGNORE INTO source_object VALUES(?,?,?)",
            (digest, len(body), "objects/" + digest),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO observation VALUES(?,?,?,?,?)",
            (url, digest, datetime.now(timezone.utc).isoformat(), role, _json(extra)),
        )
        self.db.commit()
        return body, digest

    def get(self, url: str, role: str) -> tuple[bytes, str]:
        row = self.db.execute(
            "SELECT o.sha256,s.path,s.bytes FROM observation o JOIN source_object s USING(sha256) WHERE url=? ORDER BY observed_at DESC LIMIT 1",
            (url,),
        ).fetchone()
        if row:
            body = (self.directory / row["path"]).read_bytes()
            _required(
                _sha(body) == row["sha256"] and len(body) == row["bytes"],
                "Evidence cache corruption",
            )
            return body, row["sha256"]
        _required(self.allow_download, "Missing evidence: " + url)
        _required(urlsplit(url).hostname == "resultados.tse.jus.br", "Nonofficial fetch URL")
        _required(shutil.disk_usage(self.directory).free > 10 * 1024**3, "Disk reserve reached")
        with urlopen(
            Request(url, headers={"User-Agent": "election-audit bounded verification"}), timeout=30
        ) as response:
            _required(
                urlsplit(response.url).hostname == "resultados.tse.jus.br", "Unexpected redirect"
            )
            body = response.read(4 * 1024**2 + 1)
            _required(len(body) <= 4 * 1024**2, "Source byte bound")
            extra = {
                "status": response.status,
                "headers": dict(response.headers),
                "retrieval_url": response.url,
            }
        time.sleep(0.125)
        return self.keep(body, url, role, **extra)

    def import_pilot(self, directory: str | Path) -> None:
        directory = Path(directory)
        for spec in json.loads((directory / "sources.json").read_text()):
            url = spec.get("url")
            if not url or urlsplit(url).hostname != "resultados.tse.jus.br":
                continue
            p = (directory / spec["path"]).resolve()
            _required(p.is_relative_to(directory.resolve()), "Escaping pilot source")
            body = p.read_bytes()
            _required(
                _sha(body) == spec["sha256"] and len(body) == spec["bytes"],
                "Pilot source hash mismatch",
            )
            self.keep(body, url, spec["role"], original_observation=spec)

    def import_manifest(
        self, manifest: str | Path, root: str | Path, election: ElectionDescriptor, uf: str
    ) -> None:
        root = Path(root).resolve()
        with sqlite3.connect(Path(manifest).resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            prefix = f"{BASE}/ele2026/arquivo-urna/{election.pleito_code}/dados/{uf}/"
            for row in db.execute(
                "SELECT * FROM files WHERE url>=? AND url<?", (prefix, prefix + "\uffff")
            ):
                if not row["url"].endswith("-aux.json"):
                    continue
                path = (root / row["path"]).resolve()
                _required(path.is_relative_to(root), "Escaping raw source")
                body = path.read_bytes()
                _required(
                    _sha(body) == row["sha256"] and len(body) == row["bytes"],
                    "Manifest source mismatch",
                )
                self.keep(body, row["url"], "EA18", manifest_record=dict(row))
            db.rollback()


def read_bweb(
    store: Evidence, archive: str | Path, expected_sha: str, election: ElectionDescriptor, uf: str
) -> None:
    # Stream the CSV, retaining only one section's records in Python during verification.
    path = Path(archive)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024**2), b""):
            h.update(chunk)
    _required(h.hexdigest() == expected_sha, "BWEB archive hash mismatch")
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        _required(len(names) == 1, "Expected one BWEB CSV")
        with z.open(names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
            for line, r in enumerate(reader, 2):
                if r["CD_CARGO_PERGUNTA"] != "1":
                    continue
                _required(
                    (r["SG_UF"].lower(), r["CD_ELEICAO"], r["CD_PLEITO"], int(r["NR_TURNO"]))
                    == (uf, election.election_code, election.pleito_code, election.round),
                    "BWEB round/election/UF mismatch",
                )
                key = (r["CD_MUNICIPIO"].zfill(5), r["NR_ZONA"].zfill(4), r["NR_SECAO"].zfill(4))
                count = int(r["QT_VOTOS"])
                _required(count >= 0, "Negative/missing vote count")
                old = store.db.execute(
                    "SELECT count,payload FROM bweb WHERE municipality=? AND zone=? AND section=? AND choice=?",
                    (*key, r["NR_VOTAVEL"]),
                ).fetchone()
                if old:
                    _required(
                        old["count"] == count and json.loads(old["payload"]) == r,
                        "Contradictory repeated BWEB record",
                    )
                else:
                    store.db.execute(
                        "INSERT INTO bweb VALUES(?,?,?,?,?,?,?)",
                        (*key, line, r["NR_VOTAVEL"], count, _json(r)),
                    )
        store.db.commit()


def _candidates(reference: JSON) -> dict[str, JSON]:
    rows = [
        c
        for cargo in reference["carg"]
        if cargo["cd"] == "1"
        for a in cargo["agr"]
        for p in a["par"]
        for c in p["cand"]
    ]
    return {
        c["n"]: {
            "votes": int(c["vap"]),
            "destination": c.get("dvt"),
            "official_id": c.get("sqcand"),
        }
        for c in rows
    }


def verify_section(records: list[Row], binary: Row, candidates: dict[str, JSON]) -> JSON:
    r = records[0]
    fields = (
        "QT_APTOS",
        "QT_COMPARECIMENTO",
        "QT_ABSTENCOES",
        "NR_URNA_EFETIVADA",
        "NR_LOCAL_VOTACAO",
        "DT_EMISSAO_BU",
        "DS_SECOES_AGREGADAS",
    )
    _required(
        all(all(x[f] == r[f] for f in fields) for x in records), "Conflicting BWEB section metadata"
    )
    key = (r["CD_MUNICIPIO"].zfill(5), r["NR_ZONA"].zfill(4), r["NR_SECAO"].zfill(4))
    _required(
        binary["key"] == key
        and binary["local"] == r["NR_LOCAL_VOTACAO"].zfill(4)
        and binary["urn_serial"] == r["NR_URNA_EFETIVADA"],
        "Binary/BWEB section/local/urn identity mismatch",
    )
    emitted = datetime.strptime(r["DT_EMISSAO_BU"], "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")
    _required(emitted == binary["emitted_raw"], "Binary/BWEB emission mismatch")
    observed = {x["NR_VOTAVEL"]: int(x["QT_VOTOS"]) for x in records}
    _required(
        all(
            (x["CD_TIPO_VOTAVEL"], x["NR_VOTAVEL"])
            in {("1", c) for c in candidates} | {("2", "95"), ("3", "96")}
            for x in records
        ),
        "Unsupported BWEB category/destination",
    )
    expected = set(candidates) | {"95", "96", "special:no_candidate"}
    _required(
        set(binary["choices"]) <= expected and set(observed) <= expected, "Unknown contest choice"
    )
    _required(
        all(observed.get(c, 0) == binary["choices"].get(c, 0) for c in expected),
        "Binary/BWEB choice mismatch",
    )
    attendance = int(r["QT_COMPARECIMENTO"])
    eligible = int(r["QT_APTOS"])
    abstention = int(r["QT_ABSTENCOES"])
    _required(
        sum(observed.values()) == attendance == binary["attending_voters"]
        and eligible == binary["eligible_electors"]
        and attendance + abstention == eligible,
        "BWEB/binary arithmetic mismatch",
    )
    try:
        members = member_sections(key[2], r["DS_SECOES_AGREGADAS"])
    except ValueError:
        members = []
        _required(False, "Duplicate principal/member composition")
    choices: dict[str, Any] = {
        c: {
            "count": binary["choices"].get(c, 0),
            "origin": "BWEB_observed"
            if c in observed
            else "binary_observed"
            if c in binary["choices"]
            else "derived_zero_exhaustive_binary_accounting",
        }
        for c in sorted(expected)
    }
    return {
        "eligible_electors": eligible,
        "attending_voters": attendance,
        "abstaining_electors": abstention,
        "total_presidential_ballots": attendance,
        "raw_nominal_votes": sum(v["count"] for c, v in choices.items() if c in candidates),
        "valid_candidate_votes": sum(
            v["count"]
            for c, v in choices.items()
            if c in candidates and candidates[c]["destination"] == "Válido"
        ),
        "blank_votes": choices["95"]["count"],
        "null_votes": choices["96"]["count"],
        "special_votes": choices["special:no_candidate"]["count"],
        "unresolved_votes": 0,
        "choices": choices,
        "complete_choices": True,
        "member_sections": members or None,  # None: TSE marks the composition unknown
        "composition_raw": r["DS_SECOES_AGREGADAS"],
        "location_code": r["NR_LOCAL_VOTACAO"].zfill(4),
        "binary_link": "exact_identity_and_counts_match",
        "schema_provenance": binary["schema_provenance"],
        "signature_status": binary["signature_status"],
        "candidate_destinations": candidates,
        "legal_final_counts_ready": all(c["destination"] == "Válido" for c in candidates.values()),
    }


def inspect_evidence(directory: str | Path) -> JSON:
    """Verify a completed artifact without reopening its SQLite database writable."""
    directory = Path(directory).resolve()
    artifact = json.loads((directory / "artifact.json").read_text())
    _required(artifact["version"] == VERSION, "Unsupported electoral artifact")
    for name, spec in artifact["files"].items():
        path = (directory / name).resolve()
        _required(path.is_relative_to(directory), "Escaping electoral artifact")
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024**2), b""):
                h.update(chunk)
        _required(
            h.hexdigest() == spec["sha256"] and path.stat().st_size == spec["bytes"],
            "Electoral artifact hash mismatch",
        )
    database = directory / "evidence.sqlite"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        for sha, length, relative in db.execute("SELECT sha256,bytes,path FROM source_object"):
            path = (directory / relative).resolve()
            _required(path.is_relative_to(directory), "Escaping electoral source")
            body = path.read_bytes()
            _required(_sha(body) == sha and len(body) == length, "Electoral source hash mismatch")
    return artifact["summary"]


def verify(
    archive: str | Path,
    archive_sha: str,
    output: str | Path,
    *,
    round_number: int = 2,
    uf: str = "ac",
    pilot: str | Path | None = None,
    manifest: str | Path | None = None,
    root: str | Path | None = None,
    download: bool = False,
) -> JSON:
    election = election_for_round(round_number)
    _required(re.fullmatch("[a-z]{2}", uf) is not None, "Invalid UF")
    if (Path(output) / "artifact.json").exists():
        completed = inspect_evidence(output)
        _required(
            completed["archive_sha256"] == archive_sha
            and completed["election"] == election.as_dict()
            and completed["uf"] == uf,
            "Completed artifact source mismatch",
        )
        return completed
    store = Evidence(output, allow_download=download)
    identity = {
        "version": VERSION,
        "archive_sha256": archive_sha,
        "election": election.as_dict(),
        "uf": uf,
    }
    key = _sha(_json(identity).encode())
    old = store.db.execute("SELECT identity FROM run").fetchone()
    _required(old is None or old[0] == key, "Output belongs to another immutable source")
    store.db.execute("INSERT OR IGNORE INTO run VALUES(?,?)", (key, _json(identity)))
    store.db.commit()
    if pilot:
        store.import_pilot(pilot)
    if manifest:
        _required(root is not None, "Manifest requires raw root")
        assert root is not None  # checked by _required
        store.import_manifest(manifest, root, election, uf)
    read_bweb(store, archive, archive_sha, election, uf)
    refbody, refsha = store.get(
        f"{BASE}/ele2026/{election.election_code}/dados/{uf}/{uf}-c0001-e{int(election.election_code):06d}-u.json",
        "EA20_uf",
    )
    ref = json.loads(refbody)
    _required(
        (ref["ele"], ref["t"], ref["f"], ref["tf"], ref["dv"])
        == (election.election_code, str(election.round), "o", "s", "s"),
        "Reference not official final visible target",
    )
    candidates = _candidates(ref)
    keys = store.db.execute("SELECT DISTINCT municipality,zone,section FROM bweb ORDER BY 1,2,3")
    for n, keyrow in enumerate(keys, 1):
        mu, zone, sec = keyrow
        previous = store.db.execute(
            "SELECT state,payload FROM section_result WHERE uf=? AND municipality=? AND zone=? AND section=? AND round=?",
            (uf, mu, zone, sec, election.round),
        ).fetchone()
        if previous and previous[0] == "content_verified":
            result = json.loads(previous["payload"])
            if "member_sections" not in result:
                result["member_sections"] = member_sections(sec, result["composition_raw"]) or None
                store.db.execute(
                    "UPDATE section_result SET payload=? WHERE uf=? AND municipality=? AND zone=? AND section=? AND round=?",
                    (_json(result), uf, mu, zone, sec, election.round),
                )
                store.db.commit()
            continue
        records = [
            json.loads(r[0])
            for r in store.db.execute(
                "SELECT payload FROM bweb WHERE municipality=? AND zone=? AND section=? ORDER BY choice",
                (mu, zone, sec),
            )
        ]
        try:
            directory = (
                f"{BASE}/ele2026/arquivo-urna/{election.pleito_code}/dados/{uf}/{mu}/{zone}/{sec}"
            )
            auxbody, auxsha = store.get(
                f"{directory}/p{int(election.pleito_code):06d}-{uf}-m{mu}-z{zone}-s{sec}-aux.json",
                "EA18",
            )
            aux = json.loads(auxbody)
            _required(aux["f"] == "o" and aux["st"] == "Totalizada", "Section not totalized")
            groups = [g for g in aux["hashes"] if g["st"] == "Totalizado"]
            _required(len(groups) == 1, "Conflicting/missing totalized package")
            group = groups[0]
            assets = [a for a in group["arq"] if a["tp"] == "bu"]
            _required(
                len(assets) == 1
                and Path(assets[0]["nm"]).name == assets[0]["nm"]
                and group["hash"].isalnum(),
                "Ambiguous BU asset",
            )
            raw, busha = store.get(f"{directory}/{group['hash']}/{assets[0]['nm']}", "binary_BU")
            result = verify_section(records, decode_bu(raw, election), candidates)
            result.update(
                {
                    "binary_sha256": busha,
                    "aux_sha256": auxsha,
                    "package_id": group["hash"],
                    "reference_sha256": refsha,
                    "BWEB_archive_sha256": archive_sha,
                }
            )
            state = "content_verified"
            for choice, v in result["choices"].items():
                store.db.execute(
                    "INSERT OR REPLACE INTO choice_count VALUES(?,?,?,?,?,?,?,?)",
                    (uf, mu, zone, sec, election.round, choice, v["count"], v["origin"]),
                )
        except (ValueError, KeyError, OSError) as exc:
            result = {"reason": str(exc), "complete_choices": False, "binary_link": "unavailable"}
            state = "unavailable"
        store.db.execute(
            "INSERT OR REPLACE INTO section_result VALUES(?,?,?,?,?,?,?)",
            (uf, mu, zone, sec, election.round, state, _json(result)),
        )
        store.db.commit()
        if n % 100 == 0:
            print(f"verified section {n}", flush=True)
    counts = dict(store.db.execute("SELECT state,count(*) FROM section_result GROUP BY state"))
    totals = Counter()
    for row in store.db.execute(
        "SELECT payload FROM section_result WHERE state='content_verified'"
    ):
        r = json.loads(row[0])
        totals.update(
            {
                k: r[k]
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
            {"candidate_" + c: v["count"] for c, v in r["choices"].items() if c in candidates}
        )
    expected = {
        "eligible_electors": int(ref["e"]["te"]),
        "attending_voters": int(ref["e"]["c"]),
        "abstaining_electors": int(ref["e"]["a"]),
        "total_presidential_ballots": int(ref["v"]["tv"]),
        "blank_votes": int(ref["v"]["vb"]),
        "null_votes": int(ref["v"]["vn"]),
        **{"candidate_" + c: v["votes"] for c, v in candidates.items()},
    }
    complete = counts.get("content_verified", 0) == int(ref["s"]["st"]) and not counts.get(
        "unavailable", 0
    )
    differences = (
        {k: {"observed": totals[k], "reference": v} for k, v in expected.items() if totals[k] != v}
        if complete
        else None
    )
    store.db.execute(
        "INSERT OR REPLACE INTO hierarchy VALUES(?,?,?,?,?)",
        (
            "uf",
            "",
            "",
            "matched"
            if complete and not differences
            else "numeric_difference"
            if complete
            else "incomplete_population",
            _json(
                {
                    "observed": dict(totals),
                    "reference": expected,
                    "differences": differences,
                    "reference_sha256": refsha,
                }
            ),
        ),
    )
    store.db.commit()
    summary = {
        **identity,
        "release_id": key,
        "section_states": counts,
        "hierarchy": "matched" if complete and not differences else "unresolved",
        "source_objects": store.db.execute("SELECT count(*) FROM source_object").fetchone()[0],
        "database": "evidence.sqlite",
        "schema_provenance": "reviewed_public_mirror_original_TSE_ZIP_unavailable_HTTP403",
        "signature_status": "not_verified",
        "RDV_status": "not_verified",
        "v1_releases_changed": False,
    }
    (Path(output) / "summary.json").write_text(_json(summary) + "\n")
    store.db.close()
    h = hashlib.sha256()
    database = Path(output) / "evidence.sqlite"
    with database.open("rb") as f:
        for chunk in iter(lambda: f.read(1024**2), b""):
            h.update(chunk)
    artifact = {
        "version": VERSION,
        "release_id": key,
        "files": {"evidence.sqlite": {"sha256": h.hexdigest(), "bytes": database.stat().st_size}},
        "summary": summary,
    }
    (Path(output) / "artifact.json").write_text(_json(artifact) + "\n")
    return summary


def electoral_verify_main(argv: Argv = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--archive-sha256", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--round", type=int, choices=(1, 2), default=2)
    p.add_argument("--uf", default="ac")
    p.add_argument("--pilot", type=Path)
    p.add_argument("--source-manifest", type=Path)
    p.add_argument("--source-root", type=Path)
    p.add_argument("--download", action="store_true")
    a = p.parse_args(argv)
    print(
        _json(
            verify(
                a.archive,
                a.archive_sha256,
                a.output,
                round_number=a.round,
                uf=a.uf,
                pilot=a.pilot,
                manifest=a.source_manifest,
                root=a.source_root,
                download=a.download,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(electoral_verify_main())
