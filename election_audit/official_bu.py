"""Pinned TSE BWEB CSV adapter; source extraction is distinct from final totalization.

The bundled dictionary is authoritative for encoding/header/category meanings.
Absent choices, exceptional categories, publisher status and clocks stay unknown.
No network access or writes occur while importing.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from importlib.resources import files
from urllib.parse import urlsplit

from election_audit.contracts import _valid_type, load_contract
from election_audit.electoral_imports import (
    checked_path,
    strict_json,
    table_schema,
    validate_import_row,
)
from election_audit.publication import SCHEMA, PublicationError
from election_audit.source_inventory import ALL_UFS, ELECTION, canonical, digest, identity

VERSION = "tse-bweb-2026-v1"
LAYOUT = strict_json(
    files("election_audit").joinpath("resources/bweb-2026-layout.json").read_text()
)
CONTRACT = load_contract()
SOURCE_FIELDS = {"path", "sha256", "official_url", "observed_at"}


def _row(name, **values):
    row = {key: values.get(key) for key in SCHEMA[name]["fields"]}
    states = {key: "unknown" for key, value in row.items() if value is None}
    if states:
        row["field_states"] = states
    return row


def _integer(token, *, width=None):
    if token in LAYOUT["missing_values"]:
        return None
    if not re.fullmatch(r"0|[1-9][0-9]*", token):
        raise PublicationError("Noncanonical or negative BWEB integer")
    if width is not None:
        if len(token) > width or int(token) == 0:
            raise PublicationError("BWEB geography outside supported code width")
        return token.zfill(width)
    return int(token)


def _required(token, *, width):
    value = _integer(token, width=width)
    if value is None:
        raise PublicationError("Missing BWEB geographic identifier")
    return value


def read_official_bu(bundle, document, bundle_bytes, *, max_rows, max_bytes):
    expected = {
        "adapter",
        "verification_status",
        "archive",
        "checksum",
        "resource_metadata",
        "catalog_metadata",
        "election",
        "uf",
    }
    if set(document) != expected or document["verification_status"] != "official_layout_verified":
        raise PublicationError("Invalid official BWEB bundle contract")
    if document["election"] != ELECTION or document["uf"] not in ALL_UFS:
        raise PublicationError("BWEB adapter requires exact 2026 presidential runoff and known UF")
    originals, objects, observations, sources = {}, {}, {}, {}
    byte_count = 0

    def source(data, spec, media, *, role):
        sha = hashlib.sha256(data).hexdigest()
        originals[sha] = data
        objects[sha] = {
            "object_sha256": sha,
            "byte_length": len(data),
            "media_type": media,
            "storage_locator": "originals/" + sha,
        }
        oid = identity("bweb-observation", [digest(document), spec, role, sha])
        observations[oid] = _row(
            "source_observation",
            observation_id=oid,
            run_id=digest(document),
            official_url=spec["official_url"],
            retrieval_url=spec["official_url"],
            object_sha256=sha,
            observed_at=spec["observed_at"],
            observation_status="historical_mapping_unknown",
        )
        return sha, oid

    for role in ("archive", "checksum", "resource_metadata", "catalog_metadata"):
        spec = document[role]
        if not isinstance(spec, dict) or set(spec) != SOURCE_FIELDS:
            raise PublicationError("Invalid official BWEB source specification")
        if not _valid_type(spec["observed_at"], "instant") or not _valid_type(
            spec["sha256"], "sha256"
        ):
            raise PublicationError("BWEB source hash and observation instant required")
        if not isinstance(spec["official_url"], str) or not spec["official_url"].startswith(
            "https://"
        ):
            raise PublicationError("BWEB source requires explicit HTTPS official URL")
        parsed_url = urlsplit(spec["official_url"])
        expected_host = (
            "cdn.tse.jus.br" if role in {"archive", "checksum"} else "dadosabertos.tse.jus.br"
        )
        if parsed_url.netloc != expected_host or parsed_url.fragment:
            raise PublicationError("BWEB source URL must name the official TSE host")
        path = checked_path(bundle.parent, spec["path"])
        byte_count += path.stat().st_size
        if byte_count > max_bytes:
            raise PublicationError("Bounded official BWEB byte limit exceeded")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise PublicationError("Official BWEB source hash mismatch")
        source(data, spec, "application/zip" if role == "archive" else "text/plain", role=role)
        sources[role] = data
    archive_spec = document["archive"]
    metadata = strict_json(sources["resource_metadata"].decode("utf-8"))
    catalog = strict_json(sources["catalog_metadata"].decode("utf-8"))
    if (
        metadata.get("success") is not True
        or catalog.get("success") is not True
        or metadata["result"]["url"] != archive_spec["official_url"]
        or metadata["result"]["package_id"] != catalog["result"]["id"]
    ):
        raise PublicationError("Official BWEB metadata/resource mismatch")
    url = archive_spec["official_url"]
    filename = url.rsplit("/", 1)[-1]
    if not re.fullmatch(r"bweb_2t_" + document["uf"].upper() + r"_[0-9]{12}\.zip", filename):
        raise PublicationError("Official BWEB URL election/UF mismatch")
    if document["checksum"]["official_url"] != url + ".sha512":
        raise PublicationError("Official BWEB checksum URL mismatch")
    # Pin both the hash and the named archive, rather than accepting any digest in a sidecar.
    checksum = sources["checksum"].decode("ascii").strip().split()
    if (
        len(checksum) != 2
        or checksum[1].lstrip("*") != filename
        or checksum[0].lower() != hashlib.sha512(sources["archive"]).hexdigest()
    ):
        raise PublicationError("Official BWEB SHA-512 checksum mismatch")
    member = filename[:-4] + ".csv"
    try:
        with zipfile.ZipFile(io.BytesIO(sources["archive"])) as z:
            info = z.infolist()
            if (
                len(info) != 2
                or {i.filename for i in info} != {member, LAYOUT["dictionary_member"]}
                or any(i.flag_bits & 1 for i in info)
            ):
                raise PublicationError("Unexpected official BWEB archive members")
            byte_count += sum(i.file_size for i in info)
            if byte_count > max_bytes:
                raise PublicationError("Bounded expanded BWEB byte limit exceeded")
            csv_bytes, dictionary = z.read(member), z.read(LAYOUT["dictionary_member"])
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise PublicationError("Invalid official BWEB ZIP/CRC") from exc
    if hashlib.sha256(dictionary).hexdigest() != LAYOUT["dictionary_sha256"]:
        raise PublicationError("Unreviewed official BWEB dictionary edition")
    csv_sha, csv_oid = source(csv_bytes, archive_spec, "text/csv", role=member)
    source(dictionary, archive_spec, "application/pdf", role=LAYOUT["dictionary_member"])
    text = csv_bytes.decode("latin-1")
    if "\x00" in text or text.startswith("ï»¿"):
        raise PublicationError("Unexpected BWEB BOM/NUL")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";", strict=True)
    if next(reader, None) != LAYOUT["header"]:
        raise PublicationError("Exact official BWEB CSV header mismatch")
    groups = defaultdict(list)
    input_rows, excluded_rows = 0, 0
    for record, tokens in enumerate(reader, 1):
        input_rows += 1
        if input_rows > max_rows:
            raise PublicationError("Bounded official BWEB input row limit exceeded")
        if len(tokens) != len(LAYOUT["header"]):
            raise PublicationError("Official BWEB CSV record width mismatch")
        r = dict(zip(LAYOUT["header"], tokens, strict=True))
        if (r["ANO_ELEICAO"], r["NR_TURNO"], r["CD_PLEITO"], r["DT_PLEITO"], r["SG_UF"]) != (
            "2026",
            "2",
            "3221",
            "2026-10-25 00:00:00",
            document["uf"].upper(),
        ):
            raise PublicationError("BWEB source election/round/UF mismatch")
        # The archive mixes offices. Exclude only the explicitly known governor contest.
        if (r["CD_ELEICAO"], r["CD_CARGO_PERGUNTA"]) != ("6258", "1"):
            if (r["CD_ELEICAO"], r["CD_CARGO_PERGUNTA"]) != ("6260", "3"):
                raise PublicationError("Unreviewed BWEB election/cargo pair")
            excluded_rows += 1
            continue
        if (r["CD_TIPO_ELEICAO"], r["NM_TIPO_ELEICAO"]) != ("0", "Eleição Ordinária"):
            raise PublicationError("Unreviewed BWEB election type")
        if r["DS_CARGO_PERGUNTA"] != "Presidente":
            raise PublicationError("BWEB cargo description mismatch")
        key = (
            document["uf"],
            _required(r["CD_MUNICIPIO"], width=5),
            _required(r["NR_ZONA"], width=4),
            _required(r["NR_SECAO"], width=4),
        )
        groups[key].append((r, record, reader.line_num))
    if not groups:
        raise PublicationError("BWEB archive contains no target presidential records")
    tables, witnesses = defaultdict(dict), defaultdict(set)

    def add(name, row, records) -> None:
        validate_import_row(name, row, schema=CONTRACT)
        key = canonical([row[k] for k in table_schema(name)["key"]]).decode()
        if key not in tables[name] and sum(map(len, tables.values())) >= max_rows:
            raise PublicationError("Bounded official BWEB generated row limit exceeded")
        previous = tables[name].get(key)
        if previous is not None and previous != row:
            raise PublicationError("Conflicting immutable BWEB key: " + name)
        tables[name][key] = row
        witnesses[(name, key)].update(records)

    eid = identity("election", ELECTION)
    cid = identity("contest", [eid, "0001", "br"])
    snap = identity("bweb-snapshot", [VERSION, digest(LAYOUT), digest(document), csv_sha])
    all_records = [number for group in groups.values() for _, number, _ in group]
    add("election", _row("election", election_id=eid, **ELECTION), all_records)
    add(
        "contest",
        _row("contest", contest_id=cid, election_id=eid, cargo_code="0001", jurisdiction_code="br"),
        all_records,
    )
    add(
        "snapshot",
        _row(
            "snapshot",
            snapshot_id=snap,
            created_at=archive_spec["observed_at"],
            contract_version="1.0.0",
            selection_policy=VERSION + ":published_presidential_rows",
            population_scope="2026 round 2 "
            + document["uf"]
            + "; published BWEB only; partial national",
            inventory_sha256=digest(document),
            manifest_locator="originals/" + hashlib.sha256(sources["archive"]).hexdigest(),
            manifest_captured_at=archive_spec["observed_at"],
        ),
        all_records,
    )
    candidate_numbers = sorted(
        {r["NR_VOTAVEL"] for g in groups.values() for r, _, _ in g if r["CD_TIPO_VOTAVEL"] == "1"}
    )
    arithmetic = []
    retransmissions = 0
    choice_fields = {
        "NR_PARTIDO",
        "SG_PARTIDO",
        "NM_PARTIDO",
        "CD_TIPO_VOTAVEL",
        "DS_TIPO_VOTAVEL",
        "NR_VOTAVEL",
        "NM_VOTAVEL",
        "QT_VOTOS",
    }
    for key, group in sorted(groups.items()):
        r = group[0][0]
        records = [n for _, n, _ in group]
        attributes = {k: v for k, v in r.items() if k not in choice_fields}
        if any(
            {k: v for k, v in other.items() if k not in choice_fields} != attributes
            for other, _, _ in group
        ):
            raise PublicationError("Conflicting repeated BWEB section metadata/totals")
        if (r["CD_TIPO_URNA"], r["DS_TIPO_URNA"]) != ("1", "Apurada"):
            raise PublicationError("Unreviewed BWEB urn category; original retained outside import")
        sid = identity("section", [eid, *key])
        location_code = _required(r["NR_LOCAL_VOTACAO"], width=4)
        lid = identity("location", [eid, *key[:3], location_code])
        add(
            "location",
            _row(
                "location",
                location_id=lid,
                election_id=eid,
                uf=key[0],
                municipality_tse=key[1],
                zone=key[2],
                location_code=location_code,
            ),
            records,
        )
        members = [key[3]]
        if r["DS_SECOES_AGREGADAS"] not in LAYOUT["missing_values"]:
            members += [_required(t.strip(), width=4) for t in r["DS_SECOES_AGREGADAS"].split("/")]
        if len(members) != len(set(members)):
            raise PublicationError("Duplicate/self aggregated BWEB section")
        for section in members:
            member_sid = identity("section", [eid, *key[:3], section])
            add(
                "section",
                _row(
                    "section",
                    section_id=member_sid,
                    election_id=eid,
                    uf=key[0],
                    municipality_tse=key[1],
                    zone=key[2],
                    section_code=section,
                ),
                records,
            )
            add(
                "section_composition",
                _row(
                    "section_composition",
                    snapshot_id=snap,
                    member_section_id=member_sid,
                    principal_section_id=sid,
                    location_id=lid,
                ),
                records,
            )
        vid = identity("bweb-result", [VERSION, snap, csv_sha, sid, cid])
        add(
            "result_version",
            _row(
                "result_version",
                result_version_id=vid,
                principal_section_id=sid,
                contest_id=cid,
                result_status="unknown",
            ),
            records,
        )
        sums = defaultdict(int)
        seen = {}
        for choice, number, _ in group:
            code, description = choice["CD_TIPO_VOTAVEL"], choice["DS_TIPO_VOTAVEL"]
            mapping = LAYOUT["vote_categories"].get(code)
            if mapping is None or mapping[0] != description:
                raise PublicationError("Unknown BWEB vote category/code description")
            kind = mapping[1]
            ballot = choice["NR_VOTAVEL"]
            if (
                _integer(ballot) is None
                or (kind == "blank" and ballot != "95")
                or (kind == "null" and ballot != "96")
                or (kind == "candidate" and not 1 <= int(ballot) <= 94)
            ):
                raise PublicationError("Invalid BWEB choice number/category")
            candidacy = identity("bweb-candidacy", [cid, ballot]) if kind == "candidate" else None
            if candidacy:
                add(
                    "candidacy",
                    _row(
                        "candidacy",
                        candidacy_id=candidacy,
                        contest_id=cid,
                        official_candidate_id="tse-ballot:"
                        + ELECTION["election_code"]
                        + ":1:br:"
                        + ballot,
                        ballot_number=ballot,
                    ),
                    [number],
                )
            choice_id = identity("bweb-choice", [cid, code, ballot])
            add(
                "vote_choice",
                _row(
                    "vote_choice",
                    vote_choice_id=choice_id,
                    contest_id=cid,
                    choice_code=code + ":" + ballot,
                    choice_kind=kind,
                    candidacy_id=candidacy,
                ),
                [number],
            )
            count = _integer(choice["QT_VOTOS"])
            if count is None:
                raise PublicationError("Missing BWEB choice count cannot be represented as zero")
            add(
                "vote_choice_count",
                _row(
                    "vote_choice_count",
                    result_version_id=vid,
                    vote_choice_id=choice_id,
                    vote_count=count,
                ),
                [number],
            )
            if choice_id not in seen:
                sums[kind] += count
            else:
                retransmissions += 1
            seen[choice_id] = count
        counts = {
            k: _integer(r[src])
            for k, src in (
                ("eligible_electors", "QT_APTOS"),
                ("attending_voters", "QT_COMPARECIMENTO"),
                ("abstaining_electors", "QT_ABSTENCOES"),
            )
        }
        present_candidates = {x[0]["NR_VOTAVEL"] for x in group if x[0]["CD_TIPO_VOTAVEL"] == "1"}
        total = _row(
            "section_contest_totals",
            result_version_id=vid,
            **counts,
            valid_candidate_votes=sums["candidate"]
            if present_candidates == set(candidate_numbers)
            else None,
            blank_votes=sums["blank"]
            if any(x[0]["CD_TIPO_VOTAVEL"] == "2" for x in group)
            else None,
            null_votes=sums["null"] if any(x[0]["CD_TIPO_VOTAVEL"] == "3" for x in group) else None,
        )
        for field, src in (
            ("eligible_electors", "QT_APTOS"),
            ("attending_voters", "QT_COMPARECIMENTO"),
            ("abstaining_electors", "QT_ABSTENCOES"),
        ):
            if counts[field] is None:
                total["field_states"][field] = LAYOUT["missing_values"][r[src]]
        add("section_contest_totals", total, records)
        add(
            "result_evidence",
            {
                "result_version_id": vid,
                "snapshot_id": snap,
                "official_target": True,
                "complete_choices": False,
                "expected_choice_ids": [],
                "status_evidence": {
                    "object_sha256": csv_sha,
                    "record_locator": canonical(
                        {
                            "member": member,
                            "records": records,
                            "interpretation": "Apurada; totalization status unknown",
                        }
                    ).decode(),
                },
                "supersedes": [],
                "supersession_evidence": {},
            },
            records,
        )
        for kind, field in (("generation", "DT_EMISSAO_BU"), ("receipt", "DT_BU_RECEBIDO")):
            raw = r[field]
            missing = raw in LAYOUT["missing_values"]
            add(
                "processing_event",
                _row(
                    "processing_event",
                    processing_event_id=identity("bweb-event", [vid, field]),
                    observation_id=csv_oid,
                    result_version_id=vid,
                    event_kind=kind,
                    event_time_raw=None if missing else raw,
                    availability_state=LAYOUT["missing_values"][raw] if missing else "unresolved",
                    confidence="unresolved",
                ),
                records,
            )
        attendance = counts["attending_voters"]
        electorate = counts["eligible_electors"]
        abstention = counts["abstaining_electors"]
        arithmetic.append(
            {
                "principal_section_id": sid,
                "published_vote_sum": sum(sums.values()),
                "attendance_difference": sum(sums.values()) - attendance
                if attendance is not None
                else None,
                "electorate_difference": attendance + abstention - electorate
                if None not in (attendance, abstention, electorate)
                else None,
            }
        )
    output = {name: [rows[k] for k in sorted(rows)] for name, rows in tables.items()}
    output["source_object"] = list(objects.values())
    output["source_observation"] = list(observations.values())
    output["record_lineage"] = [
        {
            "derived_table": name,
            "derived_key": key,
            "object_sha256": csv_sha,
            "record_locator": canonical(
                {"member": member, "records": sorted(records), "observation_id": csv_oid}
            ).decode(),
            "transformation_version": VERSION,
            "observation_id": csv_oid,
            "lineage_role": "input",
        }
        for (name, key), records in sorted(witnesses.items())
    ]
    if sum(map(len, output.values())) > max_rows:
        raise PublicationError("Bounded official BWEB generated row limit exceeded")
    summary = {
        "input_rows": input_rows,
        "excluded_governor_rows": excluded_rows,
        "presidential_source_rows": input_rows - excluded_rows,
        "principal_sections": len(groups),
        "snapshot_id": snap,
        "identical_retransmissions": retransmissions,
        "published_vote_sum": sum(a["published_vote_sum"] for a in arithmetic),
        "published_choice_arithmetic": dict(
            (
                name,
                {
                    "matched": sum(a[name] == 0 for a in arithmetic),
                    "mismatch": sum(a[name] not in (None, 0) for a in arithmetic),
                    "unknown": sum(a[name] is None for a in arithmetic),
                },
            )
            for name in ("attendance_difference", "electorate_difference")
        ),
        "arithmetic_findings": [
            a
            for a in arithmetic
            if a["attendance_difference"] != 0 or a["electorate_difference"] != 0
        ],
        "final_hierarchy": "unavailable_no_independent_final_reference",
        "canonical_totalization": "unavailable_no_official_status_linkage",
        "complete_choice_ledger": "unavailable_absent_rows_are_unknown",
        "signature_verification": "not_implemented",
    }
    return {
        "identity": document,
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "normalized_schema_sha256": digest({name: table_schema(name) for name in sorted(output)}),
        "source_discovery": {
            "layout": LAYOUT,
            "layout_sha256": digest(LAYOUT),
            "archive_sha256": hashlib.sha256(sources["archive"]).hexdigest(),
            "archive_sha512_verified": True,
            "dictionary_sha256": LAYOUT["dictionary_sha256"],
            "real_validation": summary,
        },
        "tables": output,
        "originals": originals,
        "verification_status": "official_layout_verified",
        "real_bu_validation": "official_bweb_layout_and_published_row_arithmetic_checked_not_final_reconciliation",
    }


def main(argv=None) -> int:
    """Inspect an explicit local official bundle without acquisition or publication."""
    import argparse
    from pathlib import Path

    from election_audit.electoral_imports import read_import
    from election_audit.electoral_results import derive_electoral

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024**2)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise PublicationError("Validation output must be a new file")
        if args.max_rows <= 0 or args.max_bytes <= 0:
            raise PublicationError("Positive BU validation bounds required")
        imported = read_import(args.bundle, max_rows=args.max_rows, max_bytes=args.max_bytes)
        if imported["verification_status"] != "official_layout_verified":
            raise PublicationError("Official BU inspection requires an official BWEB bundle")
        generated, _ = derive_electoral(imported["tables"])
        from collections import Counter

        report = {
            "adapter": VERSION,
            "bundle_sha256": imported["bundle_sha256"],
            "verification_status": imported["verification_status"],
            "real_bu_validation": imported["real_bu_validation"],
            "source_evidence": imported["source_discovery"],
            "table_rows": {n: len(rows) for n, rows in imported["tables"].items()},
            "canonical_selection": dict(
                Counter(r["selection_state"] for r in generated["canonical_result"])
            ),
            "reconciliation": dict(Counter(r["state"] for r in generated["result_reconciliation"])),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
