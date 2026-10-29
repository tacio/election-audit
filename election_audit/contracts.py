"""Offline, declarative contract validation; no acquisition or transformation work."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any


def load_contract(name: str = "schema", root: Path | None = None) -> dict[str, Any]:
    """Load a repository contract; callers may supply another repository root."""
    if name not in {"schema", "features"}:
        raise ValueError(f"Unknown contract: {name}")
    resource = (
        files("election_audit").joinpath("resources", "contracts", f"{name}.json")
        if root is None
        else root / "election_audit" / "resources" / "contracts" / f"{name}.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_contracts(root: Path | None = None) -> list[str]:
    """Check registry structure and references, not real-world data readiness."""
    schema, features = load_contract(root=root), load_contract("features", root)
    errors: list[str] = []
    tables = schema["tables"]
    for name, table in tables.items():
        fields = table["fields"]
        if not table["grain"] or not table["primary_key"]:
            errors.append(f"{name}: grain and primary key required")
        for field, spec in fields.items():
            if spec["type"] not in schema["type_mapping"] or not spec["meaning"]:
                errors.append(f"{name}.{field}: undefined type/meaning")
        for key in [table["primary_key"], *table["unique_keys"]]:
            if not set(key) <= fields.keys():
                errors.append(f"{name}: unknown key field")
        for field in table["primary_key"]:
            if field in fields and fields[field]["nullable"]:
                errors.append(f"{name}.{field}: nullable primary key")
        for fk in table["foreign_keys"]:
            target = tables.get(fk["table"])
            if target is None:
                errors.append(f"{name}: unknown foreign table")
                continue
            if not set(fk["fields"]) <= fields.keys():
                errors.append(f"{name}: unknown foreign-key field")
            if fk["references"] not in [target["primary_key"], *target["unique_keys"]]:
                errors.append(f"{name}: foreign key is not many-to-one")
            if len(fk["fields"]) != len(fk["references"]):
                errors.append(f"{name}: foreign-key length mismatch")
            for local, remote in zip(fk["fields"], fk["references"], strict=False):
                if local in fields and remote in target["fields"]:
                    if fields[local]["type"] != target["fields"][remote]["type"]:
                        errors.append(f"{name}: foreign-key type mismatch")
    ids = [feature["id"] for feature in features["features"]]
    if len(ids) != len(set(ids)):
        errors.append("features: duplicate feature identity")
    for feature in features["features"]:
        if not set(feature["requires"]) <= features["inputs"].keys():
            errors.append(f"{feature['id']}: unknown required input")
        if not all(feature[k] for k in ("grain", "denominator", "unavailable_when")):
            errors.append(f"{feature['id']}: incomplete readiness contract")
    return errors


def _valid_type(value: Any, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "json":
        try:
            json.dumps(value, allow_nan=False)
            return True
        except TypeError, ValueError:
            return False
    if not isinstance(value, str):
        return False
    if kind == "sha256":
        return bool(re.fullmatch(r"[0-9a-f]{64}", value))
    if kind in {"date", "instant"}:
        try:
            if kind == "date":
                return date.fromisoformat(value).isoformat() == value
            instant = datetime.fromisoformat(value)
            return "T" in value and instant.utcoffset() is not None
        except ValueError:
            return False
    return kind == "text"


def validate_rows(
    table_name: str, rows: list[dict[str, Any]], *, schema: dict[str, Any] | None = None
) -> list[str]:
    """Validate row shape/types/keys/null reasons within a single table batch.

    Nullable fields must be present, with null reasons in ``field_states``.
    This does not validate cross-table evidence or semantic rules. Those require
    publication-time relational/accounting checks in later phases.
    """
    schema = load_contract() if schema is None else schema
    table = schema["tables"][table_name]
    fields = table["fields"]
    errors: list[str] = []
    seen: list[set[tuple[Any, ...]]] = [
        set() for _ in [table["primary_key"], *table["unique_keys"]]
    ]
    for index, row in enumerate(rows):
        prefix = f"{table_name}[{index}]"
        if set(row) - (fields.keys() | {"field_states"}):
            errors.append(f"{prefix}: unknown fields")
        states = row.get("field_states", {})
        if not isinstance(states, dict):
            errors.append(f"{prefix}: field_states must be an object")
            states = {}
        for name, spec in fields.items():
            if name not in row:
                errors.append(f"{prefix}.{name}: missing field")
            elif row[name] is None:
                if not spec["nullable"]:
                    errors.append(f"{prefix}.{name}: null not permitted")
                elif states.get(name) not in schema["null_states"]:
                    errors.append(f"{prefix}.{name}: explicit null reason required")
            elif not _valid_type(row[name], spec["type"]):
                errors.append(f"{prefix}.{name}: invalid {spec['type']}")
        for name in states:
            if name not in fields or row.get(name) is not None:
                errors.append(f"{prefix}.{name}: reason requires known null field")
        for key, known in zip([table["primary_key"], *table["unique_keys"]], seen, strict=True):
            values = tuple(row.get(name) for name in key)
            if any(value is None for value in values):
                continue
            try:
                if values in known:
                    errors.append(f"{prefix}: duplicate key {key}")
                known.add(values)
            except TypeError:
                errors.append(f"{prefix}: unhashable key {key}")
    return errors


def main() -> int:
    errors = validate_contracts()
    for error in errors:
        print(error)
    if not errors:
        print("Contract registries valid (metadata only; no data readiness claim).")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
