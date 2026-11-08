"""Explicit normalized electoral imports. This is NOT a verified official BU decoder.

The contract is versioned independently of TSE's CSV/ASN.1/JSON formats. No source
category codes, signatures, clocks or official status are inferred by this module.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterator, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

from election_audit.contracts import _valid_type, validate_rows
from election_audit.publication import SCHEMA, PublicationError
from election_audit.source_inventory import canonical, digest
from election_audit.types import JSON, Row

VERSION = "electoral-normalized-v1"
CONTRACT_TABLES = (
    "election",
    "contest",
    "section",
    "location",
    "section_composition",
    "snapshot",
    "candidacy",
    "vote_choice",
    "result_version",
    "section_contest_totals",
    "vote_choice_count",
    "processing_event",
    "harmonized_population",
    "harmonized_member",
)
# Extension fields are deliberately normalized concepts, never claimed TSE headers.
EXTENSIONS = {
    "result_evidence": {
        "key": ["result_version_id"],
        "columns": {
            "result_version_id": "text",
            "snapshot_id": "text",
            "official_target": "boolean",
            "complete_choices": "boolean",
            "expected_choice_ids": "json",
            "status_evidence": "json",
            "supersedes": "json",
            "supersession_evidence": "json",
        },
    },
    "electorate_reference": {
        "key": ["snapshot_id", "principal_section_id"],
        "columns": {
            "snapshot_id": "text",
            "principal_section_id": "text",
            "eligible_electors": "integer",
        },
    },
    "final_result_reference": {
        "key": ["reference_id"],
        "columns": {
            "reference_id": "text",
            "snapshot_id": "text",
            "contest_id": "text",
            "level": "text",
            "uf": "text",
            "municipality_tse": "text",
            "zone": "text",
            "expected_principals": "json",
            "metrics": "json",
            "final": "boolean",
        },
    },
    "harmonization_evidence": {
        "key": ["population_id"],
        "columns": {
            "population_id": "text",
            "composition_reviewed": "boolean",
            "transfers_reviewed": "boolean",
            "electorate_reviewed": "boolean",
            "evidence": "json",
        },
    },
}


def table_schema(name: str) -> JSON:
    if name in SCHEMA:
        spec = SCHEMA[name]
        return {
            "columns": {k: v["type"] for k, v in spec["fields"].items()},
            "key": spec["primary_key"],
        }
    if name not in EXTENSIONS:
        raise PublicationError(f"Unknown normalized import table: {name}")
    return EXTENSIONS[name]


def checked_path(root: Path, locator: str) -> Path:
    """No absolute paths, traversal, symlinks, or platform-specific separators."""
    if not isinstance(locator, str) or "\\" in locator or ":" in locator:
        raise PublicationError("Unsafe import locator")
    relative = Path(locator)
    path = root / relative
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise PublicationError("Unsafe import locator")
    if any(
        (root / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)
    ):
        raise PublicationError("Symlink in import locator")
    if not path.resolve().is_relative_to(root.resolve()):
        raise PublicationError("Import locator escapes root")
    return path


def _pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(text: str | bytes) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            PublicationError(f"Invalid JSON constant: {value}")
        ),
    )


def _csv_value(token: str, kind: str) -> Any:
    if token == "\\N":
        return None
    if kind == "integer":
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", token):
            raise PublicationError("Noncanonical integer token")
        return int(token)
    if kind == "boolean":
        if token not in ("true", "false"):
            raise PublicationError("Boolean token must be true or false")
        return token == "true"
    if kind == "json":
        return strict_json(token)
    return token


def _rows(data: bytes, spec: JSON, name: str) -> Iterator[tuple[Row, JSON]]:
    if spec["encoding"] != "utf-8":
        raise PublicationError("Normalized v1 encoding must be strict UTF-8")
    text = data.decode("utf-8", errors="strict")
    if text.startswith("\ufeff") or "\x00" in text:
        raise PublicationError("BOM/NUL not permitted by normalized v1")
    columns = table_schema(name)["columns"]
    if spec["format"] == "jsonl":
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                raise PublicationError("Blank normalized JSONL record")
            yield strict_json(line), {"line": number}
    elif spec["format"] == "csv":
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=";", strict=True)
        expected = [*columns, "field_states"] if name in SCHEMA else list(columns)
        if next(reader, None) != expected:
            raise PublicationError(f"Exact normalized CSV header mismatch: {name}")
        for record, tokens in enumerate(reader, 1):
            if len(tokens) != len(expected):
                raise PublicationError("CSV record width mismatch")
            yield (
                {
                    key: _csv_value(value, columns.get(key, "json"))
                    for key, value in zip(expected, tokens, strict=True)
                },
                {"record": record, "ending_line": reader.line_num},
            )
    else:
        raise PublicationError("Normalized format must be csv or jsonl")


def validate_import_row(name: str, row: Row, *, schema: JSON | None = None) -> None:
    if name in SCHEMA:
        errors = validate_rows(name, [row], schema=schema)
        if errors:
            raise PublicationError("; ".join(errors))
    else:
        columns = table_schema(name)["columns"]
        if not isinstance(row, dict) or set(row) != set(columns):
            raise PublicationError(f"Exact normalized row fields required: {name}")
        if any(not _valid_type(row[key], kind) for key, kind in columns.items()):
            raise PublicationError(f"Invalid normalized extension type: {name}")
    if name == "vote_choice" and row["choice_kind"] not in {
        "candidate",
        "blank",
        "null",
        "special",
        "unresolved",
    }:
        raise PublicationError("Unknown normalized vote category")
    if name == "result_version" and row["result_status"] not in {
        "totalized",
        "received",
        "rejected",
        "excluded",
        "unknown",
        "conflict",
    }:
        raise PublicationError("Unknown normalized result status")
    enums = {
        "processing_event": {
            "event_kind": {"receipt", "processing", "generation", "publication", "observation"},
            "availability_state": {
                "observed",
                "missing_source",
                "not_published",
                "unresolved",
                "conflict",
            },
            "confidence": {"verified", "bounded", "unresolved"},
        },
        "harmonized_population": {
            "comparability_state": {"comparable", "incomparable", "unresolved"}
        },
    }
    for field, allowed in enums.get(name, {}).items():
        if row[field] not in allowed:
            raise PublicationError(f"Unknown normalized category: {name}.{field}")
    if name in ("vote_choice_count", "section_contest_totals", "electorate_reference"):
        if any(type(v) is int and v < 0 for v in row.values()):
            raise PublicationError("Negative electoral count")


def read_import(
    bundle: str | Path, *, max_rows: int = 100_000, max_bytes: int = 64 * 1024**2
) -> JSON:
    """Read only explicitly listed files, preserve exact bytes and every row witness.

    A caller supplies the byte hash, source locator and observation time. Successful
    parsing proves the normalized contract only, never compatibility with a real BU.
    """
    bundle = Path(bundle).resolve()
    bundle_bytes = bundle.read_bytes()
    document = strict_json(bundle_bytes.decode("utf-8"))
    if isinstance(document, dict) and document.get("adapter") == "tse-bweb-2026-v1":
        from election_audit.official_bu import read_official_bu

        return read_official_bu(
            bundle, document, bundle_bytes, max_rows=max_rows, max_bytes=max_bytes
        )
    if set(document) != {"adapter", "verification_status", "sources"}:
        raise PublicationError("Invalid normalized bundle fields")
    if document["adapter"] != VERSION or document["verification_status"] != "normalized_only":
        raise PublicationError("Only normalized_only adapter verification is implemented")
    tables, originals, lineage, objects, observations = {}, {}, [], {}, {}
    input_bytes, input_rows = 0, 0
    for spec in document["sources"]:
        if set(spec) != {
            "path",
            "sha256",
            "table",
            "format",
            "encoding",
            "official_url",
            "observed_at",
            "schema_evidence",
        }:
            raise PublicationError("Invalid normalized source specification")
        name = spec["table"]
        if name not in (*CONTRACT_TABLES, *EXTENSIONS):
            raise PublicationError("Table is outside electoral import contract")
        if not _valid_type(spec["observed_at"], "instant") or not spec["schema_evidence"]:
            raise PublicationError("Source observation time and schema evidence required")
        path = checked_path(bundle.parent, spec["path"])
        input_bytes += path.stat().st_size
        if input_bytes > max_bytes:
            raise PublicationError("Bounded normalized import byte limit exceeded")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != spec["sha256"]:
            raise PublicationError("Electoral source hash mismatch")
        originals[sha] = data
        objects[sha] = {
            "object_sha256": sha,
            "byte_length": len(data),
            "media_type": "text/" + spec["format"],
            "storage_locator": f"originals/{sha}",
        }
        oid = digest({"source": spec, "adapter": VERSION})
        observations[oid] = {
            "observation_id": oid,
            "run_id": digest(document),
            "official_url": spec["official_url"],
            "retrieval_url": spec["official_url"],
            "object_sha256": sha,
            "observed_at": spec["observed_at"],
            "http_status": None,
            "etag": None,
            "last_modified_raw": None,
            "observation_status": "historical_mapping_unknown",
            "field_states": dict.fromkeys(("http_status", "etag", "last_modified_raw"), "unknown"),
        }
        for row, locator in _rows(data, spec, name):
            input_rows += 1
            if input_rows > max_rows:
                raise PublicationError("Bounded normalized import row limit exceeded")
            validate_import_row(name, row)
            tables.setdefault(name, []).append(row)
            lineage.append(
                {
                    "derived_table": name,
                    "derived_key": canonical([row[k] for k in table_schema(name)["key"]]).decode(),
                    "object_sha256": sha,
                    "record_locator": canonical(locator).decode(),
                    "transformation_version": VERSION,
                    "observation_id": oid,
                    "lineage_role": "input",
                }
            )
    # Identical retransmissions retain multiple lineage witnesses, never additive rows.
    for name, rows in tables.items():
        unique = {}
        for row in rows:
            key = canonical([row[k] for k in table_schema(name)["key"]])
            if key in unique and unique[key] != row:
                raise PublicationError(f"Conflicting immutable normalized key: {name}")
            unique[key] = row
        tables[name] = list(unique.values())
    tables["source_object"] = list(objects.values())
    tables["source_observation"] = list(observations.values())
    tables["record_lineage"] = list({canonical(r): r for r in lineage}.values())
    return {
        "identity": document,
        "normalized_schema_sha256": digest({name: table_schema(name) for name in sorted(tables)}),
        "source_discovery": strict_json(
            files("election_audit")
            .joinpath("resources", "electoral-source-evidence.json")
            .read_text()
        ),
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "tables": tables,
        "originals": originals,
        "verification_status": "normalized_only",
        "real_bu_validation": "unavailable_no_verified_official_adapter_or_real_BU",
    }
