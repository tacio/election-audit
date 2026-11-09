"""Phase 22 section feature table v2: one row per principal section and round, per year.

Inputs are frozen releases and pinned input roots:

- BWEB (presidential rows only) for results, composition and BU metadata;
- the voter profile by section and the polling-place table (electorate datasets);
- the semantic pass (``session-aggregates-v4``) of each round, for operational
  measures, device model, software version and clock evidence;
- for 2026, the Phase 20 integrity releases (I1-I9 status and BU-side device fields).

Outputs (``section-features-v2``):

- ``sections.parquet``: keys, composition, polling place, covariates, device, clock
  rule, integrity status and one availability state (with a reason) per measure family;
- ``units.parquet``: the cross-round crosswalk. A harmonized unit is a connected
  component of registered sections linked to their principal section in either
  round, so aggregation changes between rounds never mix voters across units;
- ``ledger.json``: population counts by round, UF, model and availability;
- ``restricted/``: results (counts by vote type and votable number) and operational
  measures per section, and the same summed per harmonized unit. Before the Phase 23
  freeze they are read by code only; development UFs excepted.

Nothing is imputed: a missing or unresolved value stays null with a reason.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import zipfile
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from election_audit.elections import election_for_round
from election_audit.features import verified_member_sections
from election_audit.national_migration import atomic, sha
from election_audit.source_inventory import digest
from election_audit.types import JSON, Argv, Row, one

if TYPE_CHECKING:
    import duckdb
type Connection = duckdb.DuckDBPyConnection

VERSION = "section-features-v4"
SESSIONS_VERSION = "session-aggregates-v4"
BWEB_FILE = re.compile(r"files/bweb_([12])t_([A-Z]{2})_\d{12}\.zip")
PROFILE_FILE = re.compile(r"files/perfil_eleitor_secao_(\d{4})_([A-Z]{2})\.zip")
PLACES_FILE = re.compile(r"files/eleitorado_local_votacao_(\d{4})\.zip")
KEY = ("uf", "municipality", "zone", "section")

# Legal time zones (Decreto 2.784/1913, Art. 2, as amended by Lei 12.876/2013), as the
# offset of local time from Brasília time in hours. Voting closes at 17:00 Brasília time
# in Brazil (urn clocks run on local time) and at 17:00 local time abroad (ZZ).
# Amazonas is split by a line, not by municipality: TRE-AM lists the municipalities west of
# it (resources/am-acre-time-municipalities.json). The urns' configured closing times must
# agree with that list; where none was printed, the list alone sets the closing hour.
UF_OFFSET = {**{uf: -1 for uf in ("mt", "ms", "ro", "rr")}, "ac": -2}
NORONHA = ("pe", "fernando de noronha")
CLOSE_RULES = {
    "law_uf": "17:00 Brasília time converted with the UF's single legal zone",
    "law_noronha": "Fernando de Noronha, first zone: 18:00 local",
    "abroad": "abroad (ZZ): 17:00 local",
    "am_configured": "Amazonas: the configured closing time the municipality's urns printed, "
    "when every observation in the year agrees and matches TRE-AM's list",
    "am_list": "Amazonas, no configured closing time printed: TRE-AM's list of municipalities on "
    "Acre time (15:00 local), 16:00 local elsewhere",
    "unresolved": "no rule applies (Amazonas closing times that disagree with each other or with "
    "TRE-AM's list); time-of-day measures unavailable",
}

AGE_BANDS = (
    ("16_17", 16, 17),
    ("18_24", 18, 24),
    ("25_34", 25, 34),
    ("35_44", 35, 44),
    ("45_59", 45, 59),
    ("60_69", 60, 69),
    ("70_plus", 70, 999),
)
SCHOOLING = range(1, 9)  # 1 illiterate ... 8 higher education complete; others unknown


# --------------------------------------------------------------------------- inputs


def _manifest_files(root: str | Path, pattern: re.Pattern[str]) -> list[Row]:
    """Complete files of an input root matching ``pattern``, size-checked."""
    root = Path(root)
    uri = (root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    found = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for path, digest_, size, status in db.execute(
            "SELECT path, sha256, bytes, status FROM files ORDER BY path"
        ):
            match = pattern.fullmatch(path)
            if not match:
                continue
            if status != "complete" or not digest_:
                raise ValueError(f"Input file is not complete: {path}")
            if (root / path).stat().st_size != size:
                raise ValueError(f"Input file size differs from its manifest: {path}")
            if (
                sha(root / path) != digest_
            ):  # xr1-20261109-P0-01: the bytes read are the bytes pinned
                raise ValueError(f"Input file differs from its manifest digest: {path}")
            found.append({"path": path, "sha256": digest_, "bytes": size, "match": match})
    return found


def _stream_csv(
    archive: str | Path,
    member: str,
    columns: Sequence[str],
    rename: Mapping[str, str] | None = None,
) -> Iterator[pa.Table]:
    """Yield arrow batches of selected string columns of one CSV member."""
    with zipfile.ZipFile(archive) as z, z.open(member) as stream:
        reader = pacsv.open_csv(
            stream,
            read_options=pacsv.ReadOptions(encoding="latin-1", block_size=16 * 1024**2),
            parse_options=pacsv.ParseOptions(delimiter=";"),
            convert_options=pacsv.ConvertOptions(
                include_columns=list(columns),
                column_types={c: pa.string() for c in columns},
            ),
        )
        for batch in reader:
            table = pa.Table.from_batches([batch])
            if rename:
                table = table.rename_columns([rename.get(c, c) for c in table.column_names])
            yield table


def _csv_members(archive: str | Path, exclude: Collection[str] = ()) -> list[str]:
    with zipfile.ZipFile(archive) as z:
        return [
            n
            for n in z.namelist()
            if n.lower().endswith(".csv") and not any(x in n for x in exclude)
        ]


def _insert(db: Connection, table: str, name: str) -> None:
    db.register("batch", table)
    db.execute(f"INSERT INTO {name} SELECT * FROM batch")
    db.unregister("batch")


# BWEB, presidential rows. 2022 names two columns differently.
BWEB_FIELDS = (
    "SG_UF CD_MUNICIPIO NR_ZONA NR_SECAO NR_LOCAL_VOTACAO CD_CARGO_PERGUNTA CD_TIPO_VOTAVEL "
    "NR_VOTAVEL QT_VOTOS QT_APTOS QT_COMPARECIMENTO QT_ABSTENCOES DS_TIPO_URNA NR_URNA_EFETIVADA "
    "DT_ABERTURA DT_ENCERRAMENTO DT_EMISSAO_BU DT_BU_RECEBIDO NR_JUNTA_APURADORA"
).split()
BWEB_YEAR_FIELDS = {
    2026: {"DS_SECOES_AGREGADAS": "members_raw", "QT_ELEI_BIOM_SEM_HABILITACAO": "biometric_nh"},
    2022: {"DS_AGREGADAS": "members_raw", "QT_ELEITORES_BIOMETRIA_NH": "biometric_nh"},
}


def load_bweb(
    db: Connection, root: str | Path, year: int, round_number: int, ufs: Collection[str] | None
) -> list[Row]:
    files = [
        f
        for f in _manifest_files(root, BWEB_FILE)
        if int(f["match"][1]) == round_number and (not ufs or f["match"][2].lower() in ufs)
    ]
    if not files or (not ufs and len(files) != 28):
        raise ValueError(f"Expected 28 BWEB archives for round {round_number}, found {len(files)}")
    extra = BWEB_YEAR_FIELDS[year]
    columns = [*BWEB_FIELDS, *extra]
    table = f"bweb{round_number}"
    db.execute(f"CREATE TABLE {table} ({', '.join(f'{extra.get(c, c)} VARCHAR' for c in columns)})")
    for f in files:
        archive = Path(root) / f["path"]
        (member,) = _csv_members(archive)
        for batch in _stream_csv(archive, member, columns, extra):
            batch = batch.select([extra.get(c, c) for c in columns])
            batch = batch.filter(pa.compute.equal(batch["CD_CARGO_PERGUNTA"], "1"))
            if batch.num_rows:
                _insert(db, batch, table)
    return [{k: f[k] for k in ("path", "sha256", "bytes")} for f in files]


def _when(column: str) -> str:
    return (
        f"strftime(coalesce(try_strptime({column}, '%Y-%m-%d %H:%M:%S'), "
        f"try_strptime({column}, '%d/%m/%Y %H:%M:%S')), '%Y-%m-%dT%H:%M:%S')"
    )


def _single(expression: str) -> str:
    """The value when all rows agree, else NULL (variants are counted separately)."""
    return f"CASE WHEN count(DISTINCT {expression}) = 1 THEN min({expression}) END"


def results_sql(round_number: int) -> str:
    k = (
        "lower(SG_UF) AS uf, lpad(CD_MUNICIPIO, 5, '0') AS municipality, "
        "lpad(NR_ZONA, 4, '0') AS zone, lpad(NR_SECAO, 4, '0') AS section"
    )
    meta = {
        "location": "lpad(NR_LOCAL_VOTACAO, 4, '0')",
        "members_raw": "members_raw",
        "urn_kind": "DS_TIPO_URNA",
        "urn_serial": "NR_URNA_EFETIVADA",
        "opened_at": _when("DT_ABERTURA"),
        "closed_at": _when("DT_ENCERRAMENTO"),
        "emitted_at": _when("DT_EMISSAO_BU"),
        "received_at": _when("DT_BU_RECEBIDO"),
        "junta": "NR_JUNTA_APURADORA",
    }
    counts = {
        "eligible": "QT_APTOS",
        "attendance": "QT_COMPARECIMENTO",
        "abstentions": "QT_ABSTENCOES",
        "biometric_nh": "biometric_nh",
    }
    singles = ",\n".join(f"{_single(v)} AS {n}" for n, v in meta.items())
    count_singles = ",\n".join(
        f"CAST({_single(f'TRY_CAST({v} AS BIGINT)')} AS BIGINT) AS {n}" for n, v in counts.items()
    )
    variants = " + ".join(
        f"(count(DISTINCT {v}) > 1)::INTEGER" for v in [*meta.values(), *counts.values()]
    )
    return f"""
    CREATE TABLE results{round_number} AS
    WITH b AS (SELECT {k}, * FROM bweb{round_number})
    SELECT uf, municipality, zone, section, count(*) AS bweb_rows,
           {singles},
           {count_singles},
           {variants} AS metadata_variants,
           CAST(sum(TRY_CAST(QT_VOTOS AS BIGINT)) FILTER (WHERE CD_TIPO_VOTAVEL = '1') AS BIGINT) AS nominal,
           CAST(sum(TRY_CAST(QT_VOTOS AS BIGINT)) FILTER (WHERE CD_TIPO_VOTAVEL = '2') AS BIGINT) AS blank,
           CAST(sum(TRY_CAST(QT_VOTOS AS BIGINT)) FILTER (WHERE CD_TIPO_VOTAVEL = '3') AS BIGINT) AS null_votes,
           CAST(sum(TRY_CAST(QT_VOTOS AS BIGINT)) FILTER (WHERE CD_TIPO_VOTAVEL NOT IN ('1', '2', '3')) AS BIGINT) AS other_votes,
           count(*) FILTER (WHERE TRY_CAST(QT_VOTOS AS BIGINT) IS NULL) AS unparsed_votes
    FROM b GROUP BY ALL;
    CREATE TABLE votes{round_number} AS
    SELECT {k}, CAST(CD_TIPO_VOTAVEL AS INTEGER) AS vote_type, CAST(NR_VOTAVEL AS INTEGER) AS number,
           CAST(sum(TRY_CAST(QT_VOTOS AS BIGINT)) AS BIGINT) AS votes
    FROM bweb{round_number} GROUP BY ALL;
    DROP TABLE bweb{round_number};
    """


def compositions(db: Connection, round_number: int) -> int:
    """Member sections of each principal, from the BWEB composition text."""
    rows, errors = [], 0
    for uf, municipality, zone, section, raw in db.execute(
        f"SELECT uf, municipality, zone, section, members_raw FROM results{round_number}"
    ).fetchall():
        try:
            members = verified_member_sections(section, {"composition_raw": raw})
        except ValueError:
            members, errors = [], errors + 1
        if not members:  # unknown composition: the principal alone is certain
            members = [section]
        for member in members:
            rows.append((uf, municipality, zone, section, member, raw is None))
    db.execute(
        f"CREATE TABLE members{round_number} (uf VARCHAR, municipality VARCHAR, zone VARCHAR, "
        "section VARCHAR, member VARCHAR, composition_unknown BOOLEAN)"
    )
    if rows:
        db.executemany(f"INSERT INTO members{round_number} VALUES (?, ?, ?, ?, ?, ?)", rows)
    return errors


PROFILE_FIELDS = {
    2026: "QT_ELEITORES",
    2022: "QT_ELEITORES_PERFIL",
}


def load_profile(
    db: Connection, root: str | Path, year: int, ufs: Collection[str] | None
) -> list[Row]:
    files = [
        f
        for f in _manifest_files(root, PROFILE_FILE)
        if int(f["match"][1]) == year and (not ufs or f["match"][2].lower() in ufs)
    ]
    if not files or (not ufs and len(files) != 28):
        raise ValueError(f"Expected 28 voter-profile archives for {year}, found {len(files)}")
    total = PROFILE_FIELDS[year]
    columns = [
        "SG_UF",
        "CD_MUNICIPIO",
        "NR_ZONA",
        "NR_SECAO",
        "CD_GENERO",
        "CD_FAIXA_ETARIA",
        "CD_GRAU_ESCOLARIDADE",
        total,
        "QT_ELEITORES_BIOMETRIA",
        "QT_ELEITORES_DEFICIENCIA",
    ]
    db.execute(f"CREATE TABLE profile_raw ({', '.join(f'{c} VARCHAR' for c in columns)})")
    for f in files:
        archive = Path(root) / f["path"]
        for member in _csv_members(archive):
            for batch in _stream_csv(archive, member, columns):
                _insert(db, batch.select(columns), "profile_raw")
    n = f"TRY_CAST({total} AS BIGINT)"
    age = "TRY_CAST(CD_FAIXA_ETARIA AS INTEGER) // 100"
    school = "TRY_CAST(CD_GRAU_ESCOLARIDADE AS INTEGER)"
    parts = [
        f"sum({n}) AS electors",
        f"sum({n}) FILTER (WHERE CD_GENERO = '4') AS female",
        f"sum({n}) FILTER (WHERE CD_GENERO = '2') AS male",
        f"sum({n}) FILTER (WHERE CD_GENERO NOT IN ('2', '4')) AS sex_unknown",
        *[
            f"sum({n}) FILTER (WHERE {age} BETWEEN {lo} AND {hi}) AS age_{name}"
            for name, lo, hi in AGE_BANDS
        ],
        f"sum({n}) FILTER (WHERE {age} IS NULL OR {age} < 16) AS age_unknown",
        *[f"sum({n}) FILTER (WHERE {school} = {code}) AS school_{code}" for code in SCHOOLING],
        f"sum({n}) FILTER (WHERE {school} IS NULL OR {school} NOT BETWEEN 1 AND 8) AS school_unknown",
        "sum(TRY_CAST(QT_ELEITORES_BIOMETRIA AS BIGINT)) AS biometric_enrolled",
        "sum(TRY_CAST(QT_ELEITORES_DEFICIENCIA AS BIGINT)) AS with_disability",
        f"count(*) FILTER (WHERE {n} IS NULL) AS unparsed_rows",
    ]
    db.execute(f"""
        CREATE TABLE profile AS
        SELECT lower(SG_UF) AS uf, lpad(CD_MUNICIPIO, 5, '0') AS municipality,
               lpad(NR_ZONA, 4, '0') AS zone, lpad(NR_SECAO, 4, '0') AS section,
               {", ".join(f"CAST({expr} AS BIGINT) AS {name}" for expr, name in (p.rsplit(" AS ", 1) for p in parts))}
        FROM profile_raw GROUP BY ALL;
        DROP TABLE profile_raw;
    """)
    return [{k: f[k] for k in ("path", "sha256", "bytes")} for f in files]


PROFILE_COLUMNS = (
    "electors",
    "female",
    "male",
    "sex_unknown",
    *[f"age_{name}" for name, _, _ in AGE_BANDS],
    "age_unknown",
    *[f"school_{code}" for code in SCHOOLING],
    "school_unknown",
    "biometric_enrolled",
    "with_disability",
)

PLACE_FIELDS = (
    "NR_TURNO SG_UF CD_MUNICIPIO NM_MUNICIPIO NR_ZONA NR_SECAO CD_TIPO_SECAO_AGREGADA "
    "NR_SECAO_PRINCIPAL NR_LOCAL_VOTACAO DS_TIPO_LOCAL NR_LATITUDE NR_LONGITUDE DS_SITU_SECAO "
    "DS_SITU_SECAO_ACESSIBILIDADE QT_ELEITOR_SECAO"
).split()


def load_places(
    db: Connection, root: str | Path, year: int, ufs: Collection[str] | None
) -> list[Row]:
    files = [f for f in _manifest_files(root, PLACES_FILE) if int(f["match"][1]) == year]
    if len(files) != 1:
        raise ValueError(f"Expected one polling-place archive for {year}, found {len(files)}")
    archive = Path(root) / files[0]["path"]
    db.execute(f"CREATE TABLE places_raw ({', '.join(f'{c} VARCHAR' for c in PLACE_FIELDS)})")
    for member in _csv_members(archive, exclude=("BRASIL",)):
        for batch in _stream_csv(archive, member, PLACE_FIELDS):
            batch = batch.select(PLACE_FIELDS)
            if ufs:
                lowered = pa.compute.utf8_lower(batch["SG_UF"])
                batch = batch.filter(pa.compute.is_in(lowered, pa.array(sorted(ufs))))
            if batch.num_rows:
                _insert(db, batch, "places_raw")
    db.execute("""
        CREATE TABLE places AS
        SELECT DISTINCT CAST(NR_TURNO AS INTEGER) AS round, lower(SG_UF) AS uf,
               lpad(CD_MUNICIPIO, 5, '0') AS municipality, upper(trim(NM_MUNICIPIO)) AS municipality_name,
               lpad(NR_ZONA, 4, '0') AS zone, lpad(NR_SECAO, 4, '0') AS section,
               CD_TIPO_SECAO_AGREGADA AS aggregation_type,
               CASE WHEN TRY_CAST(NR_SECAO_PRINCIPAL AS INTEGER) > 0
                    THEN lpad(NR_SECAO_PRINCIPAL, 4, '0') END AS principal,
               lpad(NR_LOCAL_VOTACAO, 4, '0') AS location, DS_TIPO_LOCAL AS location_type,
               NR_LATITUDE AS latitude, NR_LONGITUDE AS longitude, DS_SITU_SECAO AS section_status,
               DS_SITU_SECAO_ACESSIBILIDADE AS accessibility,
               TRY_CAST(QT_ELEITOR_SECAO AS BIGINT) AS place_electors
        FROM places_raw;
        DROP TABLE places_raw;
    """)
    return [{k: files[0][k] for k in ("path", "sha256", "bytes")}]


# --------------------------------------------------------------------------- sessions

SESSION_COLUMNS = (
    "object_sha256 stream_ordinal session_ordinal segment_ordinal device_id session_kind "
    "session_round start_reading end_reading closing_reading reading_backsteps "
    "reading_backstep_max_s orphan_completions manual_requests authorization_failures "
    "completed_interrupted first_completion_reading last_completion_reading "
    "completions_by_reading_hour completion_gap_max_s model software_version clock_adh_before "
    "clock_adh_shift_s_before clock_tz_shifts_before clock_tz_shift_s_before clock_dst_before "
    "configured_close"
).split()
CYCLE_STATES = ("completed", "suspended", "cancelled", "unresolved")
METHODS = ("biometric", "manual", "unknown")

SESSIONS_SQL = """
CREATE TABLE witnessed AS
SELECT object_sha256, status, w[1] AS uf, w[2] AS municipality, w[3] AS zone, w[4] AS section
FROM (SELECT object_sha256, status, unnest(from_json(witnesses_json, '[["VARCHAR"]]')) AS w
      FROM read_parquet($objects));
CREATE TABLE official AS
WITH s AS (
    SELECT {columns}, {cycles},
           row_number() OVER (PARTITION BY object_sha256, stream_ordinal, segment_ordinal
                              ORDER BY session_ordinal) AS rank_in_segment
    FROM read_parquet($sessions)
    WHERE session_kind = 'official_vota' AND session_round = $round
)
SELECT w.uf, w.municipality, w.zone, w.section, s.*, g.first_line_sha256 AS block_start,
       g.lines AS block_lines
FROM s JOIN witnessed w USING (object_sha256)
LEFT JOIN (SELECT object_sha256, stream_ordinal, segment_ordinal, first_line_sha256, lines
           FROM read_parquet($segments)) g USING (object_sha256, stream_ordinal, segment_ordinal);
"""


def _copy_key(s: Row) -> tuple[Any, ...]:
    """Copies of one physical session: same device, same block start, same rank in block."""
    if s["block_start"] is None:
        return ("unlinked", s["object_sha256"], s["stream_ordinal"], s["session_ordinal"])
    return (s["device_id"], s["block_start"], s["rank_in_segment"])


def _completed(s: Row) -> int:
    return sum(s[f"cycles_completed_{m}"] for m in METHODS)


def distinct_sessions(sessions: Iterable[Row]) -> tuple[list[Row], int]:
    """Copies of one physical session counted once, by block lineage.

    Each copy group keeps the copy with the longest block, then the most completed cycles.
    Returns the kept sessions in start order and the number of groups whose copies disagree
    on completed cycles. Sessions need ``block_start``, ``block_lines`` and
    ``rank_in_segment`` (see ``SESSIONS_SQL``).
    """
    groups = defaultdict(list)
    for s in sessions:
        groups[_copy_key(s)].append(s)
    kept, conflicts = [], 0
    for copies in groups.values():
        copies.sort(
            key=lambda s: (
                -(s["block_lines"] or 0),
                -_completed(s),
                s["object_sha256"],
                s["stream_ordinal"],
            )
        )
        best = copies[0]
        if any(_completed(c) > _completed(best) for c in copies[1:]):
            conflicts += 1
        kept.append(best)
    kept.sort(key=lambda s: (s["start_reading"] or "", s["object_sha256"], s["session_ordinal"]))
    return kept, conflicts


def section_operations(sessions: Sequence[Row]) -> JSON:
    """Deduplicate copied sessions by block lineage and aggregate one section's sessions."""
    kept, conflicts = distinct_sessions(sessions)
    out = {
        "official_sessions_raw": len(sessions),
        "official_sessions": len(kept),
        "copies_removed": len(sessions) - len(kept),
        "copy_conflicts": conflicts,
        "unlinked_sessions": sum(1 for s in kept if s["block_start"] is None),
        "devices": len({s["device_id"] for s in kept}),
    }
    for state in CYCLE_STATES:
        for method in METHODS:
            out[f"{state}_{method}"] = sum(s[f"cycles_{state}_{method}"] for s in kept)
    for name in (
        "orphan_completions",
        "manual_requests",
        "authorization_failures",
        "completed_interrupted",
        "reading_backsteps",
    ):
        out[name] = sum(s[name] or 0 for s in kept)
    out["reading_backstep_max_s"] = max((s["reading_backstep_max_s"] or 0 for s in kept), default=0)
    hours = [0] * 24
    for s in kept:
        for i, v in enumerate(s["completions_by_reading_hour"] or []):
            hours[i] += v
    out["completions_by_hour"] = hours
    firsts = [s["first_completion_reading"] for s in kept if s["first_completion_reading"]]
    lasts = [s["last_completion_reading"] for s in kept if s["last_completion_reading"]]
    out["first_completion_reading"] = min(firsts) if firsts else None
    out["last_completion_reading"] = max(lasts) if lasts else None
    out["closing_reading"] = kept[-1]["closing_reading"] if kept else None
    out["active_seconds"] = sum(
        _seconds(s["last_completion_reading"]) - _seconds(s["first_completion_reading"])
        for s in kept
        if s["first_completion_reading"] and s["last_completion_reading"]
    )
    out["completion_gap_max_s"] = max(
        (s["completion_gap_max_s"] for s in kept if s["completion_gap_max_s"] is not None),
        default=None,
    )
    out["session_dates"] = sorted({(s["start_reading"] or "")[:10] for s in kept})
    models = sorted({s["model"] for s in kept if s["model"]})
    versions = sorted({s["software_version"] for s in kept if s["software_version"]})
    closes = sorted({s["configured_close"] for s in kept if s["configured_close"]})
    out["log_models"] = models
    out["last_model"] = kept[-1]["model"] if kept else None
    out["log_software_versions"] = versions
    out["configured_close"] = closes
    out["clock_adh"] = max((s["clock_adh_before"] or 0 for s in kept), default=0)
    out["clock_adh_shift_s"] = sum(s["clock_adh_shift_s_before"] or 0 for s in kept)
    out["clock_tz_shifts"] = max((s["clock_tz_shifts_before"] or 0 for s in kept), default=0)
    out["clock_tz_shift_s"] = max((s["clock_tz_shift_s_before"] or 0 for s in kept), default=0)
    out["clock_dst"] = max((s["clock_dst_before"] or 0 for s in kept), default=0)
    spans = sorted((s["start_reading"], s["end_reading"]) for s in kept if s["start_reading"])
    out["overlapping_sessions"] = sum(
        1 for a, b in zip(spans, spans[1:]) if a[1] is not None and b[0] < a[1]
    )
    return out


def _seconds(reading: str) -> int:
    """Seconds of day for an ISO reading (sessions never cross midnight once on-day)."""
    return int(reading[11:13]) * 3600 + int(reading[14:16]) * 60 + int(reading[17:19])


def load_operations(db: Connection, release: str | Path, round_number: int) -> JSON:
    """Witness and official-session tables of one round (kept in DuckDB)."""
    release = Path(release) / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    if manifest.get("version") != SESSIONS_VERSION:
        raise ValueError(f"Expected a {SESSIONS_VERSION} release, found {manifest.get('version')}")
    if manifest.get("round") != round_number:
        raise ValueError(f"Semantic release is round {manifest.get('round')}, not {round_number}")
    columns = ", ".join(SESSION_COLUMNS)
    cycles = ", ".join(f"cycles_{s}_{m}" for s in CYCLE_STATES for m in METHODS)
    parameters = {
        "objects": str(release / "objects.parquet"),
        "sessions": str(release / "sessions.parquet"),
        "segments": str(release / "segments.parquet"),
        "round": round_number,
    }
    sql = SESSIONS_SQL.format(columns=columns, cycles=cycles)
    sql = sql.replace("TABLE witnessed", f"TABLE witnessed{round_number}")
    sql = sql.replace("JOIN witnessed w", f"JOIN witnessed{round_number} w")
    sql = sql.replace("TABLE official", f"TABLE official{round_number}")
    for statement in sql.split(";\n"):
        if statement.strip():
            used = {k: v for k, v in parameters.items() if f"${k}" in statement}
            db.execute(statement, used)
    return {
        "path": str(release.parent),
        "version": manifest["version"],
        "files": {
            name: manifest["files"][name]["sha256"]
            for name in ("objects.parquet", "sessions.parquet", "segments.parquet")
        },
    }


def uf_operations(
    db: Connection, round_number: int, uf: str, municipalities: Sequence[str]
) -> tuple[dict[tuple[str, ...], Any], dict[tuple[str, ...], JSON]]:
    """Witness statuses and deduplicated operations of some of one UF's municipalities."""
    witnessed = defaultdict(set)
    for municipality, zone, section, status in db.execute(
        f"SELECT municipality, zone, section, status FROM witnessed{round_number} WHERE {CHUNK}",
        [uf, municipalities],
    ).fetchall():
        witnessed[(uf, municipality, zone, section)].add(status)
    operations, current, sessions = {}, None, []
    cursor = db.execute(
        f"SELECT * FROM official{round_number} WHERE {CHUNK} "
        "ORDER BY municipality, zone, section, object_sha256, session_ordinal",
        [uf, municipalities],
    )
    names = [d[0] for d in cursor.description]
    while batch := cursor.fetchmany(65536):
        for row in batch:
            s = dict(zip(names, row))
            key = tuple(s[k] for k in KEY)
            if key != current:
                if sessions:
                    operations[current] = section_operations(sessions)
                current, sessions = key, []
            sessions.append(s)
    if sessions:
        operations[current] = section_operations(sessions)
    return witnessed, operations


# --------------------------------------------------------------------------- clock rule


@lru_cache(maxsize=1)
def am_acre_time() -> frozenset[str]:
    """TSE codes of the Amazonas municipalities on Acre time (UTC-5), per TRE-AM."""
    raw = files("election_audit").joinpath("resources/am-acre-time-municipalities.json")
    return frozenset(json.loads(raw.read_bytes())["municipalities"])


def close_rules(
    sections: Iterable[Row], municipality_names: Mapping[tuple[str, str], str]
) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Expected closing hour (local clock) per (uf, municipality), with the rule used."""
    observed = defaultdict(set)
    for row in sections:
        for close in row["configured_close"] or []:
            observed[(row["uf"], row["municipality"])].add(close)
    rules = {}
    for key in {(r["uf"], r["municipality"]) for r in sections}:
        uf, _ = key
        name = (municipality_names.get(key) or "").lower()
        if uf == "zz":
            rules[key] = ("abroad", "17:00:00")
        elif (uf, name) == NORONHA:
            rules[key] = ("law_noronha", "18:00:00")
        elif uf == "am":
            values = observed.get(key, set())
            listed = "15:00:00" if key[1] in am_acre_time() else "16:00:00"
            if not values:
                rules[key] = ("am_list", listed)
            elif values == {listed}:
                rules[key] = ("am_configured", listed)
            else:
                rules[key] = ("unresolved", None)
        else:
            rules[key] = ("law_uf", f"{17 + UF_OFFSET.get(uf, 0):02d}:00:00")
    return rules


def clock_state(operations: JSON | None, expected: str | None, election_date: str) -> str:
    """Classify a section's clock evidence; time-of-day measures need ok or adjusted."""
    if operations is None or not operations["official_sessions"]:
        return "no_sessions"
    if expected is None:
        return "no_close_rule"
    if any(d != election_date for d in operations["session_dates"]):
        return "off_election_date"
    if operations["reading_backsteps"]:
        return "backstep"
    if operations["overlapping_sessions"]:
        return "overlap"
    if any(c != expected for c in operations["configured_close"]):
        return "close_conflict"
    if operations["clock_adh"] or operations["clock_tz_shifts"] or operations["clock_dst"]:
        return "adjusted"
    return "ok"


# --------------------------------------------------------------------------- integrity

INTEGRITY_COLUMNS = (
    "bu_model",
    "bu_software",
    "bu_urn_type",
    "bu_status",
    "i1_signature",
    "i1_hash_mismatches",
    "i1_chain_failed",
    "i2",
    "i2_counts_differ",
    "i3_differ",
    "i3_unmatched",
    "i5",
    "i5_biometric",
    "i6",
    "i7_failed_json",
    "i9_expected_is_effective",
)


def load_integrity(db: Connection, roots: Mapping[str, str | Path], round_number: int) -> JSON:
    """Phase 20 per-section status and BU-side device fields (2026), one table per round."""
    sections = Path(roots["sections"]) / "release" / "sections.parquet"
    logs = Path(roots["logs"]) / "release" / "sections.parquet"
    contests = Path(roots["bweb"]) / "release" / "contests.parquet"
    corr = Path(roots["correspondence"]) / "release" / "sections.parquet"
    db.execute(f"""
        CREATE TABLE integrity{round_number} AS
        WITH bu AS (
            SELECT uf, municipality, zone, section,
                   upper(split_part(equipment, '/', 1)) AS bu_model, software_version AS bu_software,
                   urn_type AS bu_urn_type, bu_status, i1_signature_math AS i1_signature,
                   i1_hash_mismatches, chain_failed AS i1_chain_failed, i3_differ, i3_unmatched
            FROM read_parquet('{sections}')
        ), lg AS (
            SELECT uf, municipality, zone, section, i5, i5_biometric, i6, i7_failed_json
            FROM read_parquet('{logs}')
        ), i2 AS (
            SELECT uf, municipality, zone, section,
                   CASE WHEN bool_or(i2 <> 'equal') THEN string_agg(DISTINCT i2, '+' ORDER BY i2)
                        ELSE 'equal' END AS i2,
                   bool_or(counts_i2 = 'differs') AS i2_counts_differ
            FROM read_parquet('{contests}') WHERE cargo = 1 GROUP BY ALL
        ), co AS (
            SELECT uf, municipality, zone, section, expected_is_effective AS i9_expected_is_effective
            FROM read_parquet('{corr}')
        )
        SELECT * FROM bu FULL JOIN lg USING (uf, municipality, zone, section)
                         FULL JOIN i2 USING (uf, municipality, zone, section)
                         FULL JOIN co USING (uf, municipality, zone, section)
    """)
    return {
        name: sha(Path(root) / "release" / "manifest.json") for name, root in sorted(roots.items())
    }


# --------------------------------------------------------------------------- build


def _rows(db: Connection, sql: str, parameters: Sequence[Any] | None = None) -> list[Row]:
    cursor = db.execute(sql, parameters or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, r)) for r in cursor.fetchall()]


def _keyed(rows: Iterable[Row]) -> dict[tuple[Any, ...], Row]:
    return {tuple(r[k] for k in KEY): r for r in rows}


def _state(
    ready: object, reason: str | None = None, partial: bool = False
) -> tuple[str, str | None]:
    if ready:
        return ("partial" if partial else "ready"), None
    return "unavailable", reason


# Rows of one chunk are held in Python; a chunk is whole municipalities of one UF, about
# this many section keys (one municipality larger than this is a chunk of its own).
CHUNK_SECTIONS = 10000
CHUNK = "uf = ? AND list_contains(?, municipality)"


def _chunks(
    sizes: Iterable[tuple[Any, ...]], ufs: Collection[str] | None, limit: int
) -> Iterator[tuple[Any, list[Any]]]:
    """(uf, [municipality, ...]) groups of whole municipalities, in UF and municipality order."""
    current, municipalities, total = None, [], 0
    for uf, municipality, n in sizes:
        if ufs and uf not in ufs:
            continue
        if municipalities and (uf != current or total + n > limit):
            yield current, municipalities
            municipalities, total = [], 0
        current = uf
        municipalities.append(municipality)
        total += n
    if municipalities:
        yield current, municipalities


def build(
    year: int,
    bweb_root: str | Path,
    electorate_root: str | Path,
    semantic: Mapping[int, str | Path],
    output: str | Path,
    *,
    integrity: Mapping[int, Mapping[str, str | Path]] | None = None,
    exclusions_path: str | Path | None = None,
    ufs: Collection[str] | None = None,
    memory_limit: str = "1GB",
    chunk_sections: int = CHUNK_SECTIONS,
) -> JSON:
    import duckdb

    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    if year == 2026 and exclusions_path is None:
        raise ValueError("2026 needs the protection exclusions")
    if year == 2022 and integrity:
        raise ValueError("Phase 20 integrity releases exist for 2026 only")
    ufs = {u.lower() for u in ufs} if ufs else None
    output.mkdir(parents=True)
    work = output / ".work"
    (work / "parts").mkdir(parents=True)
    db = duckdb.connect(str(work / "build.duckdb"))
    db.execute(f"SET memory_limit = '{memory_limit}'")
    db.execute("SET threads = 2")
    db.execute("SET preserve_insertion_order = false")
    db.execute(f"SET temp_directory = '{work / 'spill'}'")

    protected = set()
    binding = {"version": VERSION, "year": year, "ufs": sorted(ufs) if ufs else None}
    am_list = files("election_audit").joinpath("resources/am-acre-time-municipalities.json")
    binding["am_acre_time_sha256"] = hashlib.sha256(am_list.read_bytes()).hexdigest()
    if exclusions_path:
        keys = json.loads(Path(exclusions_path).read_bytes())["section_keys"]
        protected = {tuple(k) for k in keys}
        binding["exclusions_sha256"] = sha(exclusions_path)
    inputs = {"bweb": {}, "semantic": {}, "integrity": {}}
    inputs["profile"] = load_profile(db, electorate_root, year, ufs)
    inputs["places"] = load_places(db, electorate_root, year, ufs)
    composition_errors = {}
    for round_number in (1, 2):
        inputs["bweb"][round_number] = load_bweb(db, bweb_root, year, round_number, ufs)
        db.execute(results_sql(round_number))
        composition_errors[round_number] = compositions(db, round_number)
        inputs["semantic"][round_number] = load_operations(db, semantic[round_number], round_number)
        if integrity:
            inputs["integrity"][round_number] = load_integrity(
                db, integrity[round_number], round_number
            )
    binding["inputs"] = inputs
    place_rounds = {
        r: (
            r
            if one(db.execute("SELECT count(*) FROM places WHERE round = ?", [r]).fetchone())[0]
            else 1
        )
        for r in (1, 2)
    }
    sources = ["places", "profile", "results1", "results2", "witnessed1", "witnessed2"]
    if integrity:
        sources += ["integrity1", "integrity2"]
    sizes = db.execute(
        "SELECT uf, municipality, count(*) FROM ("
        + " UNION ".join(f"SELECT uf, municipality, zone, section FROM {t}" for t in sources)
        + ") WHERE uf IS NOT NULL GROUP BY ALL ORDER BY ALL"
    ).fetchall()
    pa.default_memory_pool().release_unused()
    totals = Counter()
    for number, (uf, municipalities) in enumerate(_chunks(sizes, ufs, chunk_sections)):
        sections, restricted, units = uf_rows(
            db, uf, year, protected, place_rounds, bool(integrity), municipalities
        )
        for name, rows in (("sections", sections), ("restricted", restricted), ("units", units)):
            if rows:
                pq.write_table(_table(rows), work / "parts" / f"{name}-{number:05d}.parquet")
        totals["sections"] += len(sections)
        totals["units"] += len(units)
        del sections, restricted, units
    db.close()
    return _publish(output, work, binding, totals, composition_errors)


def uf_rows(
    db: Connection,
    uf: str,
    year: int,
    protected: Collection[tuple[str, ...]],
    place_rounds: Mapping[Any, Any],
    with_integrity: bool,
    municipalities: Sequence[str],
) -> tuple[list[Row], list[Row], list[Row]]:
    """Section rows of both rounds, their restricted measures and units, for some of one UF's
    municipalities. Close rules and harmonized units never cross a municipality."""
    chunk = [uf, municipalities]
    names = {
        (uf, m): n
        for m, n in db.execute(
            f"SELECT DISTINCT municipality, municipality_name FROM places WHERE {CHUNK}", chunk
        ).fetchall()
    }
    profile = _keyed(_rows(db, f"SELECT * FROM profile WHERE {CHUNK}", chunk))
    section_rows = []
    for round_number in (1, 2):
        witnessed, operations = uf_operations(db, round_number, uf, municipalities)
        election = election_for_round(round_number, year)
        results = _keyed(_rows(db, f"SELECT * FROM results{round_number} WHERE {CHUNK}", chunk))
        members, unknown_composition = defaultdict(list), set()
        for municipality, zone, section, member, unknown in db.execute(
            f"SELECT municipality, zone, section, member, composition_unknown "
            f"FROM members{round_number} WHERE {CHUNK}",
            chunk,
        ).fetchall():
            members[(uf, municipality, zone, section)].append(member)
            if unknown:
                unknown_composition.add((uf, municipality, zone, section))
        places, place_principals = {}, set()
        for r in _rows(
            db,
            f"SELECT * FROM places WHERE round = ? AND {CHUNK}",
            [place_rounds[round_number], *chunk],
        ):
            key = tuple(r[k] for k in KEY)
            places[key] = r
            if r["principal"] is None or r["principal"] == r["section"]:
                place_principals.add(key)
        checks = (
            _keyed(_rows(db, f"SELECT * FROM integrity{round_number} WHERE {CHUNK}", chunk))
            if with_integrity
            else {}
        )
        keys = set(results) | place_principals | set(witnessed) | set(checks)
        for key in sorted(keys):
            section_rows.append(
                _section_row(
                    key,
                    year,
                    round_number,
                    election.election_date,
                    results.get(key),
                    places.get(key),
                    place_rounds[round_number],
                    members.get(key),
                    key in unknown_composition,
                    profile,
                    witnessed.get(key),
                    operations.get(key),
                    key in protected,
                    checks.get(key, {}),
                )
            )
    rules = close_rules(section_rows, names)
    restricted_rows = []
    for row in section_rows:
        rule, expected = rules[(row["uf"], row["municipality"])]
        restricted_rows.append(_finish(row, rule, expected))
    units = harmonize(section_rows, restricted_rows, year)
    return section_rows, restricted_rows, units


def _section_row(
    key: tuple[str, ...],
    year: int,
    round_number: int,
    election_date: str,
    result: Row | None,
    place: Row | None,
    place_round: Any,
    member_list: Sequence[str] | None,
    unknown_composition: bool,
    profile: Mapping[Any, Row],
    witness: Any,
    ops: JSON | None,
    is_protected: bool,
    checks: Row,
) -> Row:
    row: Row = dict(zip(KEY, key))
    row.update(year=year, round=round_number)
    member_list = sorted(member_list or [key[3]])
    row["members_json"] = json.dumps(member_list)
    row["composition"] = "unknown" if unknown_composition or result is None else "bweb"
    row["in_bweb"] = result is not None
    row["in_places"] = place is not None
    row["location"] = (result or {}).get("location") or (place or {}).get("location")
    row["location_key"] = (
        digest(["polling-place-v1", year, key[0], key[1], key[2], row["location"]])
        if row["location"]
        else None
    )
    for name in ("location_type", "latitude", "longitude", "section_status", "accessibility"):
        row[name] = (place or {}).get(name)
    row["places_round"] = place_round
    for name in (
        "urn_kind",
        "urn_serial",
        "opened_at",
        "closed_at",
        "emitted_at",
        "received_at",
        "junta",
    ):
        row[name] = (result or {}).get(name)
    row["bweb_metadata_variants"] = (result or {}).get("metadata_variants")
    # Covariates: the members' voter profile summed into the principal, all or nothing.
    found = [profile.get((key[0], key[1], key[2], m)) for m in member_list]
    present = [p for p in found if p is not None]
    complete = len(present) == len(found)
    for name in PROFILE_COLUMNS:
        row[f"profile_{name}"] = sum(p[name] or 0 for p in present) if complete else None
    row["profile_members_missing"] = sum(1 for p in found if p is None)
    row["profile_state"], row["profile_reason"] = _state(complete, "missing_input")
    if is_protected:
        row["log_status"] = "protected_until_freeze"
    elif not witness:
        row["log_status"] = "no_log"
    elif "complete" not in witness:
        row["log_status"] = "log_error"
    elif ops is None:
        row["log_status"] = "no_official_session"
    else:
        row["log_status"] = "sessions"
    models = (ops or {}).get("log_models") or []
    versions = (ops or {}).get("log_software_versions") or []
    # The BU is emitted by the last urn: its model is the one compared with the BU.
    row["log_model"] = (ops or {}).get("last_model")
    row["log_models_json"] = json.dumps(models)
    row["log_software_version"] = (
        versions[0] if len(versions) == 1 else ("mixed" if versions else None)
    )
    for name in INTEGRITY_COLUMNS:
        row[name] = checks.get(name)
    row["model"] = row["bu_model"] or row["log_model"]
    row["model_source"] = (
        "bu_signature" if row["bu_model"] else ("log" if row["log_model"] else None)
    )
    row["model_agrees"] = (
        row["bu_model"] == row["log_model"] if row["bu_model"] and row["log_model"] else None
    )
    row["device_state"], row["device_reason"] = _state(row["model"], "missing_input")
    row["_ops"], row["_result"], row["_election_date"] = ops, result, election_date
    row["configured_close"] = (ops or {}).get("configured_close") or []
    return row


OPERATION_FIELDS = (
    "official_sessions_raw",
    "official_sessions",
    "copies_removed",
    "copy_conflicts",
    "unlinked_sessions",
    "devices",
    "clock_adh",
    "clock_adh_shift_s",
    "clock_tz_shifts",
    "clock_tz_shift_s",
    "clock_dst",
    "reading_backsteps",
    "reading_backstep_max_s",
    "overlapping_sessions",
)


def _finish(row: Row, rule: str, expected: str | None) -> Row:
    """Close rule, clock state and availability; returns the restricted measures."""
    ops, result = row.pop("_ops"), row.pop("_result")
    election_date = row.pop("_election_date")
    row["close_rule"], row["expected_close"] = rule, expected
    row["configured_close"] = json.dumps(row["configured_close"])
    row["clock_state"] = clock_state(ops, expected, election_date)
    row["results_state"], row["results_reason"] = _state(
        result is not None and result["eligible"] is not None and not result["unparsed_votes"],
        "missing_input" if result is None else "conflict",
    )
    if row["log_status"] == "protected_until_freeze":
        row["operations_state"], row["operations_reason"] = "unavailable", "outside_scope"
    elif ops is None:
        row["operations_state"], row["operations_reason"] = "unavailable", "missing_input"
    elif ops["copy_conflicts"]:
        row["operations_state"], row["operations_reason"] = "unavailable", "conflict"
    else:
        unresolved = sum(ops[f"unresolved_{m}"] for m in METHODS) + ops["orphan_completions"]
        row["operations_state"] = "partial" if unresolved else "ready"
        row["operations_reason"] = None
    usable = row["operations_state"] != "unavailable"
    timed = usable and row["clock_state"] in ("ok", "adjusted")
    row["timing_state"] = row["operations_state"] if timed else "unavailable"
    row["timing_reason"] = (
        None if timed else ("unresolved_clock" if usable else row["operations_reason"])
    )
    for name in OPERATION_FIELDS:
        row[name] = (ops or {}).get(name)
    return _restricted(row, result, ops, expected if timed else None)


def _restricted(row: Row, result: Row | None, ops: JSON | None, expected: str | None) -> Row:
    out = {k: row[k] for k in (*KEY, "year", "round")}
    for name in (
        "eligible",
        "attendance",
        "abstentions",
        "biometric_nh",
        "nominal",
        "blank",
        "null_votes",
        "other_votes",
    ):
        out[name] = (result or {}).get(name)
    for state in CYCLE_STATES:
        for method in METHODS:
            out[f"{state}_{method}"] = (ops or {}).get(f"{state}_{method}")
    for name in (
        "orphan_completions",
        "manual_requests",
        "authorization_failures",
        "completed_interrupted",
        "first_completion_reading",
        "last_completion_reading",
        "closing_reading",
        "active_seconds",
        "completion_gap_max_s",
    ):
        out[name] = (ops or {}).get(name)
    hours = (ops or {}).get("completions_by_hour")
    out["completions_by_hour"] = hours
    out["completed"] = sum(out[f"completed_{m}"] for m in METHODS) if ops else None
    out["completed_nonbiometric"] = (
        out["completed_manual"] + out["completed_unknown"] if ops else None
    )
    out["completed_after_close"] = (
        sum(hours[int(expected[:2]) :]) if ops and expected is not None and hours else None
    )
    return out


# --------------------------------------------------------------------------- crosswalk


def harmonize(section_rows: Sequence[Row], restricted_rows: Sequence[Row], year: int) -> list[Row]:
    """Connected components of (registered section) - (principal, round) links."""
    parent = {}

    def find(x: tuple[Any, ...]) -> tuple[Any, ...]:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple[Any, ...], b: tuple[Any, ...]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for row in section_rows:
        base = (row["uf"], row["municipality"], row["zone"])
        principal = ("p", row["round"], *base, row["section"])
        for member in json.loads(row["members_json"]):
            union(principal, ("s", *base, member))
    components = defaultdict(list)
    for node in list(parent):
        components[find(node)].append(node)
    restricted = {(r["round"], *(r[k] for k in KEY)): r for r in restricted_rows}
    sections = {(r["round"], *(r[k] for k in KEY)): r for r in section_rows}
    units = []
    for nodes in components.values():
        members = sorted(n[1:] for n in nodes if n[0] == "s")
        principals = {1: [], 2: []}
        for n in nodes:
            if n[0] == "p":
                principals[n[1]].append(n[2:])
        uf, municipality, zone = members[0][:3]
        unit_id = digest(["harmonized-unit-v1", year, [list(m) for m in members]])
        unit = {
            "unit_id": unit_id,
            "year": year,
            "uf": uf,
            "municipality": municipality,
            "zone": zone,
            "members_json": json.dumps([m[3] for m in members]),
            "members": len(members),
        }
        for r in (1, 2):
            keys = sorted(principals[r])
            unit[f"principals_r{r}_json"] = json.dumps([k[3] for k in keys])
            unit[f"principals_r{r}"] = len(keys)
        if not unit["principals_r1"] or not unit["principals_r2"]:
            kind = "one_round_only"
        elif len(principals[1]) == len(principals[2]) == 1 and principals[1] == principals[2]:
            kind = "same_principal"
        else:
            kind = "recombined"
        unit["kind"] = kind
        unit["comparable"] = kind != "one_round_only" and all(
            sections[(r, *k)]["results_state"] == "ready" for r in (1, 2) for k in principals[r]
        )
        units.append(unit)
        for r in (1, 2):
            for k in principals[r]:
                restricted[(r, *k)]["unit_id"] = unit_id
                sections[(r, *k)]["unit_id"] = unit_id
    return units


# --------------------------------------------------------------------------- publish


def _table(rows: Sequence[Row]) -> pa.Table:
    names = list(rows[0])
    return pa.Table.from_pylist([{k: r.get(k) for k in names} for r in rows])


LEDGER_FAMILIES = ("results", "profile", "device", "operations", "timing")


def ledger(db: Connection, sections: Path, units: Path) -> JSON:
    """Population counts by round and UF: availability, log status, clock state, model."""
    out = {}
    for name in (
        *[f"{f}_state" for f in LEDGER_FAMILIES],
        "log_status",
        "clock_state",
        "model",
        "model_agrees",
        "close_rule",
        "composition",
    ):
        rows = db.execute(
            f"SELECT round, uf, coalesce(CAST({name} AS VARCHAR), 'null') AS v, count(*) "
            f"FROM read_parquet('{sections}') GROUP BY ALL ORDER BY ALL"
        ).fetchall()
        family = defaultdict(dict)
        for round_number, uf, value, n in rows:
            family[value][f"r{round_number}:{uf}"] = n
        totals = defaultdict(Counter)
        for round_number, _, value, n in rows:
            totals[value][f"r{round_number}"] += n
        out[name] = {"by_round_uf": family, "by_round": {k: dict(v) for k, v in totals.items()}}
    out["units"] = {
        f"{kind}:{'comparable' if comparable else 'not_comparable'}": n
        for kind, comparable, n in db.execute(
            f"SELECT kind, comparable, count(*) FROM read_parquet('{units}') GROUP BY ALL ORDER BY ALL"
        ).fetchall()
    }
    return out


def _publish(
    output: Path,
    work: Path,
    binding: JSON,
    totals: Mapping[str, int],
    composition_errors: dict[int, int],
) -> JSON:
    import duckdb

    release = output / ".release.tmp"
    (release / "restricted").mkdir(parents=True)
    parts = work / "parts"
    targets = {
        "sections": release / "sections.parquet",
        "units": release / "units.parquet",
        "restricted": release / "restricted" / "sections.parquet",
    }
    with duckdb.connect(str(work / "build.duckdb")) as db:
        db.execute("SET threads = 2")
        db.execute(f"SET temp_directory = '{work / 'spill'}'")
        for name, target in targets.items():
            order = "unit_id" if name == "units" else "round, uf, municipality, zone, section"
            db.execute(
                f"COPY (SELECT * FROM read_parquet('{parts}/{name}-*.parquet', union_by_name = true) "
                f"ORDER BY {order}) TO '{target}' (FORMAT parquet, COMPRESSION zstd)"
            )
        restricted = targets["restricted"]
        for round_number in (1, 2):
            db.execute(
                f"COPY (SELECT v.* FROM votes{round_number} v SEMI JOIN "
                f"(SELECT * FROM read_parquet('{restricted}') WHERE round = {round_number}) s "
                f"USING (uf, municipality, zone, section) ORDER BY ALL) TO "
                f"'{release / 'restricted' / f'votes_r{round_number}.parquet'}' "
                "(FORMAT parquet, COMPRESSION zstd)"
            )
        db.execute(
            "COPY (SELECT m.unit_id, v.round, v.vote_type, v.number, "
            "CAST(sum(v.votes) AS BIGINT) AS votes "
            "FROM (SELECT *, 1 AS round FROM votes1 UNION ALL SELECT *, 2 FROM votes2) v "
            f"JOIN read_parquet('{restricted}') m USING (uf, municipality, zone, section, round) "
            f"GROUP BY ALL ORDER BY ALL) TO '{release / 'restricted' / 'unit_votes.parquet'}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        summary = ledger(db, targets["sections"], targets["units"])
    atomic(release / "ledger.json", summary)
    files = {
        str(p.relative_to(release)): {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in sorted(release.rglob("*"))
        if p.is_file()
    }
    manifest = {
        **binding,
        "sections": totals["sections"],
        "units": totals["units"],
        "composition_errors": composition_errors,
        "close_rules": CLOSE_RULES,
        "restricted": "restricted/ holds results and operational measures; before the Phase 23 "
        "freeze it is read by code only (development UFs excepted)",
        "copy_rule": "official sessions of one section with the same device, the same block start "
        "(first line hash of the official-round segment) and the same rank in the block are "
        "copies (internal and external memory of one urn); the copy with the longest block is "
        "kept; a shorter copy with more completions is a conflict. Prefix equality of the copies "
        "is not verified (Phase 20b).",
        "files": files,
    }
    atomic(release / "manifest.json", manifest)
    os.replace(release, output / "release")
    shutil.rmtree(work)
    return manifest


# --------------------------------------------------------------------------- CLI


def section_table_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit section-table", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("build", help="Build the section feature table of one year.")
    run.add_argument("--year", type=int, required=True, choices=(2026, 2022), help="Election year.")
    run.add_argument("--bweb-root", required=True, help="Verified BWEB input root.")
    run.add_argument("--electorate-root", required=True, help="Voter profile and polling places.")
    run.add_argument("--semantic-r1", required=True, help="Round-1 semantic pass (v4) root.")
    run.add_argument("--semantic-r2", required=True, help="Round-2 semantic pass (v4) root.")
    run.add_argument("--integrity-r1", help="Round-1 Phase 20 roots as JSON (2026).")
    run.add_argument("--integrity-r2", help="Round-2 Phase 20 roots as JSON (2026).")
    run.add_argument("--exclusions", help="Protected/stress exclusions JSON (2026).")
    run.add_argument("--output", required=True, help="New output directory.")
    run.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    run.add_argument("--memory-limit", default="1GB", help="DuckDB memory limit.")
    args = parser.parse_args(argv)
    integrity = None
    if args.integrity_r1 or args.integrity_r2:
        if not (args.integrity_r1 and args.integrity_r2):
            parser.error("Give both --integrity-r1 and --integrity-r2")
        integrity = {1: json.loads(args.integrity_r1), 2: json.loads(args.integrity_r2)}
    manifest = build(
        args.year,
        args.bweb_root,
        args.electorate_root,
        {1: args.semantic_r1, 2: args.semantic_r2},
        args.output,
        integrity=integrity,
        exclusions_path=args.exclusions,
        ufs=args.uf,
        memory_limit=args.memory_limit,
    )
    print(json.dumps({"sections": manifest["sections"], "units": manifest["units"]}))
    return 0
