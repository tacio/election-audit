"""Frozen metadata coverage; no archive interpretation or electoral inference."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from election_audit.elections import coerce_election
from election_audit.source_inventory import (
    ALL_UFS,
    aux_url,
    canonical,
    identity,
    index_url,
    safe_source,
    section_directory,
    section_key,
)
from scripts.download_tse_logs import sections

SELECTION_VERSION = "frozen-index-current-assets-v1"
PACKAGE_STATUS_VERSION = "tse-package-status-exact-v1"
# Exact supplied acquisition-reference label only; no guessed numeric flags.
PACKAGE_STATUS_MAP = {"Totalizado": "totalized"}
PENDING_SNAPSHOT = "pending-snapshot"


def election_id(election=None):
    return identity("election", coerce_election(election).as_dict())


def section_id(key, election=None):
    return identity("section", [election_id(election), *key])


def verified_json(inventory, url, checks=None):
    check = (
        checks.get(url)
        if checks is not None
        else next((row for row in inventory["object_checks"] if row["url"] == url), None)
    )
    if check is None or check["state"] != "verified":
        raise ValueError("metadata_not_verified")
    body = safe_source(Path(inventory["source_root"]), check["storage_locator"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != check["expected_sha256"]:
        raise ValueError("metadata_changed_after_capture")
    return json.loads(body), check


def _lineage(table, key, check, pointer):
    return {
        "derived_table": table,
        "derived_key": canonical(key).decode(),
        "object_sha256": check["expected_sha256"],
        "record_locator": canonical(
            {
                "archive_segments": [],
                "json_pointer": pointer,
                "byte_range": None,
                "line_range": None,
            }
        ).decode(),
        "transformation_version": SELECTION_VERSION,
        "observation_id": check["observation_id"],
        "lineage_role": "input",
    }


def _index_records(config, uf, election=None):
    # Reuse the acquisition adapter's phase/pleito/UF checks, preserving raw records.
    validated = list(sections(config, uf, coerce_election(election).pleito_code))
    pointers = []
    for ai, area in enumerate(config["abr"]):
        for mi, municipality in enumerate(area["mu"]):
            for zi, zone in enumerate(municipality["zon"]):
                for si, _ in enumerate(zone["sec"]):
                    pointers.append(f"/abr/{ai}/mu/{mi}/zon/{zi}/sec/{si}")
    return list(zip(validated, pointers, strict=True))


def build_population(inventory: dict) -> dict:
    """Return contract rows plus explicit adapter evidence and unknown denominators.

    A whole-UF frozen index defines expected membership even for an explicitly
    sampled asset selection. Observed manifest-only sections are retained, but
    never silently counted as an authoritative expected population.
    """
    election = coerce_election(inventory["selection"]["election"])
    selected_election_id = election_id(election)

    def selected_section_id(key):
        return section_id(key, election)

    indexes, issues, candidates, index_checks = {}, [], defaultdict(list), {}
    checks = {row["url"]: row for row in inventory["object_checks"]}
    for uf in inventory["selection"]["ufs"]:
        try:
            config, check = verified_json(inventory, index_url(uf, election), checks)
            records = _index_records(config, uf, election)
            if not records:
                raise ValueError("empty_index")
            keys = [tuple(item[:4]) for item, _ in records]
            duplicate = len(keys) != len(set(keys))
            indexes[uf] = {
                "state": "duplicate_sections" if duplicate else "authoritative",
                "expected_members": None if duplicate else len(keys),
                "object_sha256": check["expected_sha256"],
            }
            for item, pointer in records:
                key = tuple(item[:4])
                candidates[key].append({"metadata": item[4], "json_pointer": pointer})
                index_checks[key] = check
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            indexes[uf] = {"state": str(exc), "expected_members": None, "object_sha256": None}
            issues.append({"kind": "index_unavailable", "uf": uf, "reason": str(exc)})

    histories, log_history = defaultdict(list), defaultdict(list)
    for row in inventory["manifest_rows"]["sections"]:
        histories[section_key(row)].append(row)
    for row in inventory["historical_advertisements"]:
        log_history[section_key(row)].append(row)
    selected = inventory["selection"]["section_keys"]
    requested = set() if selected is None else {tuple(key) for key in selected}
    file_keys, current_log_urls = set(), defaultdict(set)
    for row in inventory["manifest_rows"]["files"]:
        match = re.fullmatch(
            rf"https://resultados\.tse\.jus\.br/oficial/ele2026/arquivo-urna/{election.pleito_code}/dados/([a-z]{{2}})/(\d{{5}})/(\d{{4}})/(\d{{4}})/.+",
            row["url"],
        )
        if match:
            file_keys.add(match.groups())
            if row["url"].lower().endswith(("-log.jez", "-log.dat")):
                current_log_urls[match.groups()].add(row["url"])
    keys = sorted(set(candidates) | set(histories) | set(log_history) | requested | file_keys)
    metadata, composition_reasons, principals = {}, {}, {}
    for key in keys:
        variants = candidates.get(key, [])
        unique = {canonical(value["metadata"]) for value in variants}
        if len(unique) != 1:
            composition_reasons[key] = (
                "conflicting_index_records" if unique else "authoritative_index_missing"
            )
            continue
        value = variants[0]["metadata"]
        metadata[key] = value
        target = (*key[:3], str(value["nsp"]).zfill(4)) if value.get("nsp") else key
        principals[key] = target
    # Do not collapse chains/cycles or invent an absent terminal section.
    for key, target in list(principals.items()):
        if target not in principals or principals[target] != target:
            composition_reasons[key] = "missing_conflicting_or_nonterminal_principal"
    for key in composition_reasons:
        principals.pop(key, None)

    observations = list(inventory["source_observation"])
    by_url = {row["official_url"]: row for row in observations}
    packages, package_observations, assets, lineage = {}, [], [], []
    seen_assets = set()
    per_section_assets, aux_states = {}, {}
    capture_run = identity(
        "inventory-run", [inventory["manifest_rows_sha256"], inventory["manifest_captured_at"]]
    )

    def asset_observation(url):
        if url not in by_url:
            row = {
                "observation_id": identity(
                    "source-observation", [capture_run, url, "not_in_files"]
                ),
                "run_id": capture_run,
                "official_url": url,
                "retrieval_url": url,
                "object_sha256": None,
                "observed_at": inventory["manifest_captured_at"],
                "http_status": None,
                "etag": None,
                "last_modified_raw": None,
                "observation_status": "missing",
                "field_states": {
                    "object_sha256": "missing_source",
                    "http_status": "unknown",
                    "etag": "missing_source",
                    "last_modified_raw": "missing_source",
                },
            }
            by_url[url] = row
            observations.append(row)
        return by_url[url]

    for key in keys:
        if selected is not None and key not in requested:
            continue
        try:
            aux, check = verified_json(inventory, aux_url(key, election), checks)
            if str(aux.get("f", "")).lower() != "o":
                raise ValueError("nonofficial_auxiliary")
            entries, seen = [], set()
            for gi, group in enumerate(aux["hashes"]):
                for ai, asset in enumerate(group.get("arq", [])):
                    name, package = asset["nm"], group.get("hash")
                    if (
                        not isinstance(name, str)
                        or Path(name).name != name
                        or "\\" in name
                        or not package
                    ):
                        raise ValueError("invalid_package_asset")
                    url = f"{section_directory(key, election)}/{quote(str(package), safe='')}/{quote(name, safe='')}"
                    if str(asset.get("tp", "")).lower() == "log" or name.lower().endswith(
                        ("-log.jez", "-log.dat")
                    ):
                        entries.append(url)
                    pid = identity("package", [selected_section_id(key), package])
                    packages[pid] = {
                        "package_id": pid,
                        "section_id": selected_section_id(key),
                        "official_package_id": str(package),
                    }
                    mid = check["observation_id"]
                    if (pid, mid) not in seen:
                        # Raw null cannot be represented by the v1 non-null status
                        # contract. Keep its exact source and an explicit issue.
                        if not isinstance(group.get("st"), str):
                            issues.append(
                                {
                                    "kind": "unrepresentable_package_status",
                                    "section_key": list(key),
                                    "package": package,
                                    "raw": group.get("st"),
                                }
                            )
                            continue
                        po = {
                            "package_id": pid,
                            "metadata_observation_id": mid,
                            "package_status_raw": group["st"],
                            "package_status": PACKAGE_STATUS_MAP.get(group["st"], "unknown"),
                            "official_phase_raw": str(aux["f"]),
                            "received_at": None,
                            "processed_at": None,
                            "generated_at": None,
                            "published_at": None,
                            "field_states": {
                                field: "unknown"
                                for field in (
                                    "received_at",
                                    "processed_at",
                                    "generated_at",
                                    "published_at",
                                )
                            },
                        }
                        package_observations.append(po)
                        lineage.append(_lineage("source_package", [pid], check, f"/hashes/{gi}"))
                        lineage.append(
                            _lineage("package_observation", [pid, mid], check, f"/hashes/{gi}")
                        )
                        seen.add((pid, mid))
                    if (pid, mid, name) not in seen_assets:
                        seen_assets.add((pid, mid, name))
                        observation = asset_observation(url)
                        assets.append(
                            {
                                "package_id": pid,
                                "metadata_observation_id": mid,
                                "filename": name,
                                "asset_observation_id": observation["observation_id"],
                            }
                        )
                        lineage.append(
                            _lineage(
                                "package_asset", [pid, mid, name], check, f"/hashes/{gi}/arq/{ai}"
                            )
                        )
            per_section_assets[key] = sorted(set(entries))
            aux_states[key] = "verified"
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            aux_states[key] = str(exc)
            # These are current section URLs, with explicit *unknown* per-run
            # attribution. They establish local availability, never old run bytes.
            per_section_assets[key] = sorted(
                {row["url"] for row in log_history[key]} | current_log_urls[key]
            )

    section_rows, coverage, composition, evidence = [], [], [], []
    states = Counter()
    for key in keys:
        sid, principal = selected_section_id(key), principals.get(key)
        section_rows.append(
            {
                "section_id": sid,
                "election_id": selected_election_id,
                "uf": key[0],
                "municipality_tse": key[1],
                "zone": key[2],
                "section_code": key[3],
            }
        )
        urls = per_section_assets.get(key, [])
        successes = [url for url in urls if by_url.get(url, {}).get("object_sha256")]
        bad = [
            url
            for url in urls
            if checks.get(url, {}).get("state") not in (None, "verified", "missing_object")
        ]
        failed_attempts = [row for row in histories[key] if row["status"] == "error"]
        if selected is not None and key not in requested:
            state, availability = "not_selected", "unknown"
        elif principal is None:
            state, availability = "unresolved", "unknown"
        elif principal != key:
            state, availability = "aggregated", "not_applicable"
        elif urls and len(successes) == len(urls):
            state, availability = "acquired", "available"
        elif bad or failed_attempts:
            state, availability = "failed", "unknown"
        elif successes:
            state, availability = "unresolved", "unknown"
        elif not urls and (
            aux_states.get(key) == "verified" or (key in metadata and not metadata[key].get("da"))
        ):
            state, availability = "not_published", "not_published"
        else:
            state, availability = "missing", "missing"
        states[state] += 1
        row = {
            "snapshot_id": PENDING_SNAPSHOT,
            "section_id": sid,
            "principal_section_id": selected_section_id(principal) if principal else None,
            "installation_state": "unknown",
            "log_availability": availability,
            "bu_availability": "unknown",
            "parse_state": "not_attempted",
            "reconciliation_state": "not_attempted",
            "exclusion_reason": "outside_asset_selection" if state == "not_selected" else None,
            "field_states": {},
        }
        if principal is None:
            row["field_states"]["principal_section_id"] = "unresolved"
        if row["exclusion_reason"] is None:
            row["field_states"]["exclusion_reason"] = "not_applicable"
        coverage.append(row)
        if principal:
            composition.append(
                {
                    "snapshot_id": PENDING_SNAPSHOT,
                    "member_section_id": sid,
                    "principal_section_id": selected_section_id(principal),
                    "location_id": None,
                    "field_states": {"location_id": "unknown"},
                }
            )
        evidence.append(
            {
                "section_id": sid,
                "section_key": list(key),
                "membership": "expected_index"
                if key in candidates
                else "observed_or_requested_only",
                "acquisition_state": state,
                "composition_reason": composition_reasons.get(key),
                "index_records": candidates.get(key, []),
                "run_records": histories[key],
                "historical_advertisements": log_history[key],
                "current_log_urls": urls,
                "verified_current_logs": len(successes),
                "auxiliary_state": aux_states.get(key),
                "failed_attempts": len(failed_attempts),
            }
        )
        if key in index_checks:
            for item in candidates[key]:
                lineage.append(_lineage("section", [sid], index_checks[key], item["json_pointer"]))
                lineage.append(
                    _lineage(
                        "coverage_ledger",
                        [PENDING_SNAPSHOT, sid],
                        index_checks[key],
                        item["json_pointer"],
                    )
                )
                if principal:
                    lineage.append(
                        _lineage(
                            "section_composition",
                            [PENDING_SNAPSHOT, sid],
                            index_checks[key],
                            item["json_pointer"],
                        )
                    )

    authoritative = all(row["expected_members"] is not None for row in indexes.values())
    complete_composition = not composition_reasons
    expected_members = (
        sum(row["expected_members"] for row in indexes.values()) if authoritative else None
    )
    resolved = {selected_section_id(value) for value in principals.values()}
    expected_principals = len(resolved) if authoritative and complete_composition else None
    all_ufs = set(inventory["selection"]["ufs"]) == set(ALL_UFS)
    summary = {
        "national_status": "partial_national",
        "declared_ufs": inventory["selection"]["ufs"],
        "unavailable_ufs": sorted(set(ALL_UFS) - set(inventory["selection"]["ufs"])),
        "national_expected_members": expected_members if all_ufs else None,
        "expected_members": expected_members,
        "expected_unique_principals": expected_principals,
        "retained_sections": len(keys),
        "observed_only_sections": len(set(keys) - set(candidates)),
        "resolved_unique_principals": len(resolved),
        "member_accounting": dict(sorted(states.items())),
        "aggregated_member_sections": sum(bool(value.get("nsp")) for value in metadata.values()),
        "unresolved_composition_sections": len(composition_reasons),
        "acquired_unique_principals": sum(
            row["log_availability"] == "available"
            and row["principal_section_id"] == row["section_id"]
            for row in coverage
        ),
        "failed_attempt_sections": sum(bool(row["failed_attempts"]) for row in evidence),
        "unfinished_runs": [
            row["id"]
            for row in inventory["manifest_rows"]["runs"]
            if row["status"] == "running" or row["finished_at"] is None
        ],
        "run_status_is_coverage_proof": False,
        "indexes": indexes,
    }
    if (
        all_ufs
        and authoritative
        and expected_principals is not None
        and selected is None
        and states.get("acquired", 0) == expected_principals
        and not states.get("failed", 0)
        and not states.get("unresolved", 0)
    ):
        summary["national_status"] = "complete_indexed_local_assets"
    return {
        "tables": {
            "election": [{"election_id": selected_election_id, **election.as_dict()}],
            "source_object": inventory["source_object"],
            "source_observation": observations,
            "source_package": sorted(packages.values(), key=lambda row: row["package_id"]),
            "package_observation": package_observations,
            "package_asset": assets,
            "section": section_rows,
            "section_composition": composition,
            "coverage_ledger": coverage,
            "record_lineage": lineage,
        },
        "coverage_summary": summary,
        "section_evidence": evidence,
        "metadata_issues": issues,
    }
