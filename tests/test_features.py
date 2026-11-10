"""Evidence-qualified feature arithmetic and whole-principal round joins."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from election_audit.features import (
    FEATURES,
    _initialize,
    _sha,
    _store_unit,
    apply_links,
    derive_features,
    derive_rounds,
    ingest_verification,
    measures,
    publish_features,
    verified_member_sections,
)


def unit(turn: int = 2, section: str = "0001", snapshot: str = "source") -> dict[str, Any]:
    return {
        "round": turn,
        "uf": "ac",
        "municipality_tse": "01007",
        "zone": "0009",
        "section": section,
        "location_id": f"location-{turn}",
        "source_snapshot_id": snapshot,
        "source_ready": True,
        "lineage_keys": {"source": "test"},
    }


def counts() -> dict[str, Any]:
    return {
        "eligible_electors": 100,
        "attending_voters": 80,
        "abstaining_electors": 20,
        "total_presidential_ballots": 80,
        "valid_candidate_votes": 75,
        "blank_votes": 0,
        "null_votes": 5,
        "special_votes": 0,
        "unresolved_votes": 0,
        "complete_choices": True,
        "legal_final_counts_ready": True,
        "choices": {
            "13": {"count": 40, "origin": "observed"},
            "22": {"count": 35, "origin": "observed"},
        },
    }


def database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _initialize(db)
    return db


def links() -> dict[str, Any]:
    return {
        "version": "reviewed-feature-links-v1",
        "links": [
            {
                "location_id": f"location-{turn}",
                "stable_location_id": "stable",
                "verified": True,
                "composition_reviewed": True,
                "transfers_reviewed": True,
                "electorate_reviewed": True,
                "evidence": {
                    "object_sha256": "a" * 64,
                    "record_locator": f"official-register:{turn}",
                },
            }
            for turn in (1, 2)
        ],
    }


class FeatureTests(unittest.TestCase):
    def test_all_families_and_separate_zero_unknown(self) -> None:
        db = database()
        _store_unit(db, unit(), counts())
        derive_features(db, "13", "22")
        self.assertEqual(
            {r[0] for r in db.execute("SELECT feature_id FROM features")},
            {f["id"] for f in FEATURES},
        )
        self.assertAlmostEqual(
            db.execute("SELECT value FROM features WHERE feature_id='turnout_target'").fetchone()[
                0
            ],
            0.8,
        )
        self.assertEqual(
            db.execute("SELECT value FROM features WHERE component='blank_share'").fetchone()[0], 0
        )
        self.assertIsNone(
            db.execute(
                "SELECT value FROM features WHERE feature_id='conditional_unusualness'"
            ).fetchone()[0]
        )
        db.close()

    def test_unreconciled_and_zero_denominator_never_imputed(self) -> None:
        u = unit()
        u["source_ready"] = False
        values = measures(u, counts(), [], "13", "22")
        self.assertIsNone(values[("turnout_target", "turnout")][0])
        c = counts()
        c.update(eligible_electors=0, attending_voters=0, abstaining_electors=0)
        self.assertEqual(
            measures(unit(), c, [], "13", "22")[("turnout_target", "turnout")][3],
            "zero_denominator",
        )
        c = counts()
        c["special_votes"] = None
        self.assertIsNone(
            measures(unit(), c, [], "13", "22")[("unanimous_results", "strict_unanimity")][0]
        )

    def test_special_category_and_legal_destinations_are_separate(self) -> None:
        c = counts()
        c["choices"]["special:no_candidate"] = {"count": 0, "origin": "binary"}
        values = measures(unit(), c, [], "13", "22")
        self.assertAlmostEqual(values[("candidate_share_target", "candidate_a_share")][0], 40 / 75)
        c["legal_final_counts_ready"] = False
        self.assertIsNone(
            measures(unit(), c, [], "13", "22")[("blank_null_targets", "null_share")][0]
        )

    def test_a_unanimous_section_keeps_its_candidate_shares(self) -> None:
        # xr1-20261109-P7-05: BWEB omits a candidate with no votes
        c = counts()
        del c["choices"]["22"]
        c["choices"]["13"]["count"] = 75
        values = measures(unit(), c, [], "13", "22")
        self.assertEqual(values[("candidate_share_target", "candidate_a_share")][0], 1.0)
        self.assertEqual(values[("candidate_share_target", "candidate_b_share")][0], 0.0)
        c["complete_choices"] = False  # the absence is then unknown, not zero
        values = measures(unit(), c, [], "13", "22")
        self.assertIsNone(values[("candidate_share_target", "candidate_b_share")][0])

    def test_conflicting_duplicate_fails_without_multiplication(self) -> None:
        db = database()
        _store_unit(db, unit(), counts())
        _store_unit(db, unit(), counts())
        self.assertEqual(db.execute("SELECT count(*) FROM units").fetchone()[0], 1)
        c = counts()
        c["attending_voters"] = 81
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            _store_unit(db, unit(), c)
        db.close()

    def test_reviewed_whole_member_join_and_electorate_change(self) -> None:
        db = database()
        for turn in (1, 2):
            c = counts()
            c.update(eligible_electors=100 + turn, abstaining_electors=20 + turn)
            _store_unit(db, unit(turn), c, ["ac:01007:0009:0001", "ac:01007:0009:0002"])
        apply_links(db, links())
        derive_rounds(db)
        row = json.loads(db.execute("SELECT payload FROM comparisons").fetchone()[0])
        self.assertEqual(row["readiness_state"], "ready")
        self.assertEqual(row["electorate_change"], 1)
        self.assertEqual(row["candidate_transfer_inference"], "unavailable")
        self.assertEqual(row["candidate_vectors"]["1"]["13"], 40)
        db.close()

    def test_overlapping_principal_population_is_not_summed(self) -> None:
        db = database()
        for turn, section in [(1, "0001"), (2, "0001"), (2, "0002")]:
            _store_unit(db, unit(turn, section), counts(), ["ac:01007:0009:0001"])
        apply_links(db, links())
        derive_rounds(db)
        row = json.loads(db.execute("SELECT payload FROM comparisons").fetchone()[0])
        self.assertEqual(row["unavailable_reason"], "overlapping_principals")
        db.close()

    def test_legacy_aggregate_without_member_array_retains_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.sqlite"
            source = sqlite3.connect(path)
            source.execute(
                "CREATE TABLE section_result(uf,municipality,zone,section,round,state,payload)"
            )
            payload = {
                **counts(),
                "binary_link": "exact_identity_and_counts_match",
                "composition_raw": "2 / 003",
                "location_code": "1001",
            }
            source.execute(
                "INSERT INTO section_result VALUES(?,?,?,?,?,?,?)",
                ("ac", "01007", "0009", "0001", 2, "content_verified", json.dumps(payload)),
            )
            source.commit()
            source.close()
            pin = {"sha256": _sha(path), "bytes": path.stat().st_size}
            (Path(tmp) / "artifact.json").write_text(
                json.dumps({"files": {"evidence.sqlite": pin}})
            )
            db = database()
            ingest_verification(db, path)
            self.assertEqual(
                [r[0] for r in db.execute("SELECT member_key FROM members ORDER BY member_key")],
                ["ac:01007:0009:0001", "ac:01007:0009:0002", "ac:01007:0009:0003"],
            )
            self.assertEqual(_sha(path), pin["sha256"])
            db.close()

    def test_composition_missing_codes_consistency_and_duplicates(self) -> None:
        for token in ("#NULO#", "#NULO", "-1", ""):
            self.assertEqual(verified_member_sections("1", {"composition_raw": token}), ["0001"])
        for token in ("#NE#", "#NE", "-3", None):
            self.assertEqual(verified_member_sections("1", {"composition_raw": token}), [])
        self.assertEqual(
            verified_member_sections("1", {"composition_raw": "2", "member_sections": ["2", "1"]}),
            ["0001", "0002"],
        )
        for payload in (
            {"composition_raw": "2 / 2"},
            {"composition_raw": "1 / 2"},
            {"composition_raw": "invalid"},
            {"member_sections": ["2"]},
            {"composition_raw": "2", "member_sections": ["1", "3"]},
            {"composition_raw": "#NULO#", "member_sections": ["1", "2"]},
        ):
            with self.assertRaises(ValueError):
                verified_member_sections("1", payload)

    def test_unverified_link_and_new_directory_only(self) -> None:
        db = database()
        _store_unit(db, unit(), counts())
        doc = links()
        doc["links"] = doc["links"][1:]
        doc["links"][0]["verified"] = False
        with self.assertRaisesRegex(ValueError, "reviewed"):
            apply_links(db, doc)
        db.close()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                publish_features([], Path(tmp))
