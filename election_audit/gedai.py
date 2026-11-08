"""Phase 20b: urn loads in the BUs against TSE's published GEDAI preparation logs.

GEDAI-UE is the system that prepares the urns: it generates the load media (``mídia de
carga``) and records, per section, which urn was loaded with which load code. TSE publishes
its logs per UF (``log_gedai_<round>t_<UF>_<timestamp>.zip``), one package per preparation
computer, each holding the computer's log and a signature file. This check reads only these
lines (operator identifiers on other lines are never kept):

- ``Recebida``/``Transmitida a``/``Definida como atual a`` ``correspondência de seção:
  município M, zona Z, seção S, carga C, id urna U, mc X.``
- the same for ``correspondência de contingência`` (no section: urns held in reserve);
- ``Mídia de carga gerada. NS:N Z:Z | Seções (M:M) S S ...``.

Per section of a finished section pass, against the BU's load code, urn number and load-media
serial (``numeroSerieFC``):

- G1: the (section, load code, urn) correspondence is in a GEDAI log, or the (load code, urn)
  of a contingency urn is (registered to the section's zone, or to another one, as when a
  zone's reserve urns are prepared and registered elsewhere);
- G2: the BU's load-media serial equals the ``mc`` of that correspondence;
- G3: for a section correspondence, a load medium with that serial was generated for the
  section.

Logs of both rounds are read, and a match records which round's logs hold it. The signature
files of the GEDAI logs are not verified (format not reviewed).
"""

import contextlib
import io
import json
import os
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from collections.abc import Collection, Iterator, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import integrity_checks as ic
from election_audit.national_migration import atomic, sha
from election_audit.types import JSON, Row

VERSION = "integrity-gedai-v1"
ARCHIVE = re.compile(r"files/log_gedai_([12])t_([A-Z]{2})_(\d{12})\.zip")
CORRESPONDENCE = re.compile(
    r"(?:Recebida|Transmitida a|Definida como atual a) correspondência de (seção|contingência): "
    r"município (\d+), zona (\d+), (?:seção (\d+), )?carga (\d+), id urna (\d+), mc ([0-9A-F]+)\."
)
LOAD_MEDIUM = re.compile(r"Mídia de carga gerada\. NS:([0-9A-F]+) Z:(\d+) \|(.*)")
MUNICIPALITY_SECTIONS = re.compile(r"\(M:(\d+)\)((?: \d+)+)")
MAX_MEMBER = 256 * 1024**2
SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("package", pa.string()),
        # section | contingency | contingency_other_zone | absent | no_bu_load
        ("correspondence", pa.string()),
        ("rounds_json", pa.string()),  # GEDAI rounds whose logs hold the match
        ("medium", pa.string()),  # match | differs | null
        ("load_medium", pa.string()),  # covers_section | other_sections | absent | null
        ("failed_json", pa.string()),
    ]
)


def gedai_archives(root: Path, ufs: Collection[str] | None = None) -> list[Row]:
    """Complete GEDAI archives of one input root, each checked against its manifest."""
    uri = (root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    archives = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for path, digest, size, status in db.execute(
            "SELECT path, sha256, bytes, status FROM files ORDER BY path"
        ):
            match = ARCHIVE.fullmatch(path)
            if not match or (ufs and match[2].lower() not in ufs):
                continue
            if status != "complete" or sha(root / path) != digest:
                raise ValueError(f"GEDAI archive incomplete or changed: {path}")
            archives.append(
                {"round": int(match[1]), "uf": match[2].lower(), "path": path, "sha256": digest}
            )
    if not archives:
        raise ValueError(f"No GEDAI archives in {root}")
    return archives


def _read(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_MEMBER:
        raise ValueError(f"{info.filename} exceeds the member bound")
    return z.read(info)


def log_lines(path: Path) -> Iterator[tuple[str, str]]:
    """(computer package, message) for every line of every computer log in one archive."""
    with zipfile.ZipFile(path) as outer:
        for info in outer.infolist():
            if not info.filename.endswith("-log.jez"):
                continue
            with zipfile.ZipFile(io.BytesIO(_read(outer, info))) as package:
                for member in package.infolist():
                    if not member.filename.endswith("-log.jez"):
                        continue
                    with zipfile.ZipFile(io.BytesIO(_read(package, member))) as log:
                        for entry in log.infolist():
                            for line in _read(log, entry).decode("latin-1").splitlines():
                                fields = line.split("\t")
                                if len(fields) == 4:
                                    yield info.filename, fields[2]


def parse_archives(root: Path, archives: Sequence[Row]) -> JSON:
    """Correspondences and load media found in the archives, keyed for the section join."""
    sections: dict[tuple[str, str, str], set[tuple[str, str, str, int]]] = defaultdict(set)
    # Contingency urns by (load code, urn): the place they were registered to, medium, round.
    contingency: dict[tuple[str, str], set[tuple[str, str, str, int]]] = defaultdict(set)
    media: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    lines = Counter()
    for archive in archives:
        number = archive["round"]
        for _, message in log_lines(root / archive["path"]):
            lines[number] += 1
            if "correspondência de" in message and (found := CORRESPONDENCE.fullmatch(message)):
                kind, municipality, zone, section, load, urn, medium = found.groups()
                municipality, zone, urn = municipality.zfill(5), zone.zfill(4), urn.lstrip("0")
                if kind == "seção":
                    sections[(municipality, zone, section.zfill(4))].add(
                        (load, urn, medium, number)
                    )
                else:
                    contingency[(load, urn)].add((municipality, zone, medium, number))
            elif message.startswith("Mídia de carga gerada") and (
                found := LOAD_MEDIUM.fullmatch(message)
            ):
                serial, zone = found[1], found[2].zfill(4)
                for municipality, listed in MUNICIPALITY_SECTIONS.findall(found[3]):
                    for section in listed.split():
                        media[serial].add((municipality.zfill(5), zone, section.zfill(4)))
    return {"sections": sections, "contingency": contingency, "media": media, "lines": lines}


def section_rules(bu: Row, parsed: JSON) -> Row:
    """G1-G3 for one section's BU load fields."""
    if not bu.get("load_code") or not bu.get("urn_serial"):
        return {"correspondence": "no_bu_load", "failed_json": "[]"}
    key = (bu["municipality"], bu["zone"], bu["section"])
    load, urn = bu["load_code"], str(bu["urn_serial"]).lstrip("0")
    found = [v for v in parsed["sections"].get(key, ()) if (v[0], v[1]) == (load, urn)]
    kind = "section"
    if not found:
        places = parsed["contingency"].get((load, urn), set())
        found = [(load, urn, medium, number) for _, _, medium, number in places]
        here = any((m, z) == key[:2] for m, z, _, _ in places)
        kind = "absent" if not found else "contingency" if here else "contingency_other_zone"
    failed, medium, load_medium = [], None, None
    if kind == "absent":
        failed.append("G1")
    else:
        serial = (bu.get("flash_serial") or "").upper()
        medium = "match" if any(v[2] == serial for v in found) else "differs"
        if medium == "differs":
            failed.append("G2")
        if kind == "section":
            covered = parsed["media"].get(serial)
            load_medium = (
                "absent"
                if not covered
                else "covers_section"
                if key in covered
                else "other_sections"
            )
            if load_medium != "covers_section":  # contingency media list no sections
                failed.append("G3")
    return {
        "correspondence": kind,
        "rounds_json": json.dumps(sorted({v[3] for v in found}), separators=(",", ":")),
        "medium": medium,
        "load_medium": load_medium,
        "failed_json": json.dumps(failed, separators=(",", ":")),
    }


def run_gedai(
    sections_root: str | Path,
    gedai_roots: Sequence[str | Path],
    output: str | Path,
    *,
    ufs: Collection[str] | None = None,
) -> JSON:
    """G1-G3 per section of one round, against the GEDAI logs of the given input roots."""
    sections_root = Path(sections_root).expanduser().absolute()
    roots = [Path(r).expanduser().absolute() for r in gedai_roots]
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    release = sections_root / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if entry["sha256"] != sha(release / name):
            raise ValueError(f"Section release file changed: {name}")
    per_root = [(root, gedai_archives(root, ufs)) for root in roots]
    binding = {
        "version": VERSION,
        "round": manifest["round"],
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "gedai": {str(r): {a["path"]: a["sha256"] for a in arch} for r, arch in per_root},
        "kept": "correspondence and load-medium lines only; operator identifiers are not read "
        "into any output",
        "not_verified": "the GEDAI log signature files (format not reviewed)",
        "ufs": sorted(ufs) if ufs else None,
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    parsed: JSON = {"sections": defaultdict(set), "contingency": defaultdict(set)}
    parsed["media"], lines = defaultdict(set), Counter()
    for root, archives in per_root:
        part = parse_archives(root, archives)
        for name in ("sections", "contingency", "media"):
            for key, values in part[name].items():
                parsed[name][key] |= values
        lines.update(part["lines"])
    columns = ["uf", "municipality", "zone", "section", "package", "bu_status"]
    columns += ["urn_serial", "load_code", "flash_serial"]
    rows, issues = [], []
    table = pq.read_table(release / "sections.parquet", columns=columns)
    for bu in table.to_pylist():
        if ufs and bu["uf"] not in ufs:
            continue
        base = {k: bu[k] for k in ("uf", "municipality", "zone", "section", "package")}
        result = section_rules(bu, parsed)
        rows.append({**base, **result})
        failed = json.loads(result["failed_json"])
        if failed:
            issues.append(
                {
                    "check": "G",
                    "failed": failed,
                    **base,
                    "bu": {k: bu[k] for k in ("urn_serial", "load_code", "flash_serial")},
                    **{k: result.get(k) for k in ("correspondence", "medium", "load_medium")},
                }
            )
    final = output / ".release.tmp"
    final.mkdir()
    ic._write(final / "sections.parquet", rows, SECTION_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    summary = {
        "sections": len(rows),
        "gedai_lines_by_round": {str(k): v for k, v in sorted(lines.items())},
        "correspondence": dict(Counter(r["correspondence"] for r in rows)),
        "correspondence_by_package": dict(
            Counter(f"{r['package']}:{r['correspondence']}" for r in rows)
        ),
        "rounds": dict(Counter(r.get("rounds_json") or "n/a" for r in rows)),
        "medium": dict(Counter(str(r.get("medium")) for r in rows)),
        "load_medium": dict(Counter(str(r.get("load_medium")) for r in rows)),
        "failed": dict(Counter(r["failed_json"] for r in rows)),
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
