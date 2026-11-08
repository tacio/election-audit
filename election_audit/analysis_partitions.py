"""Frozen seeded polling-location populations, including unknown identities."""

from __future__ import annotations

import math

import duckdb

from election_audit.electoral_results import _anchor
from election_audit.publication import PublicationError
from election_audit.source_inventory import digest
from election_audit.types import JSON, Row

VERSION = "location-partition-v1"
SCHEMAS = {
    "partition_plan": {"key": ["partition_id"], "columns": {"partition_id": "text"}},
    "location_partition": {
        "key": ["partition_id", "snapshot_id", "principal_section_id"],
        "columns": {
            "partition_id": "text",
            "snapshot_id": "text",
            "principal_section_id": "text",
            "stable_location_id": "text",
            "partition_name": "text",
        },
    },
}


def assign_partitions(population: list[Row], specification: JSON) -> tuple[list[Row], list[Row]]:
    """Only reviewed stable identity links group observations across elections/rounds."""
    if not isinstance(specification, dict) or set(specification) != {
        "version",
        "seed",
        "fractions",
        "links",
        "municipal_holdout",
    }:
        raise PublicationError(
            "Partition requires exact version/seed/fractions/links/municipal_holdout fields"
        )
    if (
        specification["version"] != VERSION
        or not isinstance(specification["seed"], str)
        or not specification["seed"]
    ):
        raise PublicationError("Partition requires a version and nonempty string seed")
    fractions = specification["fractions"]
    if (
        not isinstance(fractions, dict)
        or set(fractions) != {"training", "calibration", "test"}
        or any(
            type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 1
            for value in fractions.values()
        )
        or not math.isclose(sum(fractions.values()), 1, abs_tol=1e-12)
    ):
        raise PublicationError("Positive training/calibration/test fractions must sum to one")
    links = {}
    if not isinstance(specification["links"], list) or not isinstance(
        specification["municipal_holdout"], list
    ):
        raise PublicationError("Partition links/municipal holdout must be lists")
    for link in specification["links"]:
        if (
            not isinstance(link, dict)
            or set(link) != {"location_id", "stable_location_id", "verified", "evidence"}
            or link["verified"] is not True
            or not _anchor(link["evidence"])
        ):
            raise PublicationError(
                "Stable location link requires verified identity and original-record anchor"
            )
        if not all(
            isinstance(link[k], str) and link[k] for k in ("location_id", "stable_location_id")
        ):
            raise PublicationError("Stable location identity must be explicit")
        if link["location_id"] in links:
            raise PublicationError("Duplicate/conflicting stable location link")
        links[link["location_id"]] = link
    if any(not isinstance(m, str) or not m for m in specification["municipal_holdout"]) or len(
        set(specification["municipal_holdout"])
    ) != len(specification["municipal_holdout"]):
        raise PublicationError(
            "Municipal holdout identifiers must be unique UF:municipality strings"
        )
    population = sorted(population, key=lambda r: (r["snapshot_id"], r["principal_section_id"]))
    keys = [(r["snapshot_id"], r["principal_section_id"]) for r in population]
    if len(keys) != len(set(keys)):
        raise PublicationError("Duplicate partition observation")
    observed_locations = {r["location_id"] for r in population if r["location_id"]}
    if set(links) - observed_locations:
        raise PublicationError("Stale location link outside exact unit population")
    normalized_spec = {
        **specification,
        "links": sorted(links.values(), key=lambda r: r["location_id"]),
        "municipal_holdout": sorted(specification["municipal_holdout"]),
    }
    population_hash = digest(population)
    partition_id = digest({"population": population_hash, "specification": normalized_spec})
    strata = {}
    for row in population:
        link = links.get(row["location_id"])
        if not link:
            continue
        stable = link["stable_location_id"]
        stratum = (row["uf"], row["municipality_tse"])
        if not all(stratum):
            raise PublicationError("Verified location requires known geographic stratum")
        if stable in strata and strata[stable] != stratum:
            raise PublicationError("Stable location conflicts across geographic strata")
        strata[stable] = stratum
    assignments = {}
    for stable, stratum in sorted(strata.items()):
        number = int(
            digest(
                {
                    "version": VERSION,
                    "seed": specification["seed"],
                    "stratum": stratum,
                    "stable_location_id": stable,
                }
            ),
            16,
        ) / (1 << 256)
        municipal_key = ":".join(stratum)
        assignments[stable] = (
            "municipal_stress"
            if municipal_key in specification["municipal_holdout"]
            else (
                "training"
                if number < fractions["training"]
                else "calibration"
                if number < fractions["training"] + fractions["calibration"]
                else "test"
            )
        )
    rows = []
    for row in population:
        link = links.get(row["location_id"])
        stable = link["stable_location_id"] if link else None
        rows.append(
            {
                **row,
                "partition_id": partition_id,
                "stable_location_id": stable,
                "partition_name": assignments[stable] if stable else "unavailable",
                "eligible": bool(stable),
                "unavailable_reason": None if stable else "unverified_stable_location_identity",
                "identity_evidence": link["evidence"] if link else None,
                "stratum": {"uf": row["uf"], "municipality_tse": row["municipality_tse"]},
            }
        )
    plan = {
        "partition_id": partition_id,
        "version": VERSION,
        "population_sha256": population_hash,
        "population_rows": len(population),
        "verified_locations": len(assignments),
        "specification": normalized_spec,
        "strata_fields": ["uf", "municipality_tse"],
        "assignment_rule": "sha256(canonical(version,seed,stratum,stable_location_id))/2**256; cumulative fractions; municipal stress first",
        "fraction_interpretation": "seeded_probability_thresholds_not_forced_small_stratum_counts",
        "test_access_rule": "untouched_until_logged_inspection; inspected_partition_is_development_for_future_analyses",
    }
    return [plan], rows


def partition_tables(
    db: duckdb.DuckDBPyConnection, specification: JSON, limit: int
) -> tuple[list[Row], list[Row]]:
    sql = """SELECT c.snapshot_id,c.principal_section_id,c.location_id,s.election_id,s.uf,s.municipality_tse
        FROM section_composition c JOIN section s ON s.section_id=c.principal_section_id
        WHERE c.member_section_id=c.principal_section_id
        UNION
        SELECT o.snapshot_id,o.section_id,NULL,s.election_id,s.uf,s.municipality_tse
        FROM operational_coverage o JOIN section s ON s.section_id=o.section_id
        WHERE json_extract_string(o.payload,'$.principal_section_id') IS NULL ORDER BY 1,2"""
    rows = db.execute(sql).fetchmany(limit + 1)
    if len(rows) > limit:
        raise PublicationError("Bounded partition unit population limit exceeded")
    fields = [
        "snapshot_id",
        "principal_section_id",
        "location_id",
        "election_id",
        "uf",
        "municipality_tse",
    ]
    return assign_partitions([dict(zip(fields, row, strict=True)) for row in rows], specification)
