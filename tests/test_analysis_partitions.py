"""Exact seeded stable-location populations, independent of names/section codes."""

import copy
import unittest

from election_audit.analysis_partitions import VERSION, assign_partitions
from election_audit.publication import PublicationError


def specification():
    return {
        "version": VERSION,
        "seed": "frozen-2026",
        "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
        "links": [
            {
                "location_id": name,
                "stable_location_id": stable,
                "verified": True,
                "evidence": {
                    "object_sha256": "a" * 64,
                    "record_locator": "reviewed register row " + name,
                },
            }
            for name, stable in (
                ("round1-school", "stable-a"),
                ("round2-school", "stable-a"),
                ("other", "stable-b"),
            )
        ],
        "municipal_holdout": [],
    }


def population():
    return [
        {
            "snapshot_id": snap,
            "principal_section_id": section,
            "location_id": location,
            "election_id": snap,
            "uf": "AC",
            "municipality_tse": "00100",
        }
        for snap, section, location in (
            ("r1", "1", "round1-school"),
            ("r2", "9", "round2-school"),
            ("r2", "2", "other"),
            ("r2", "1", None),
        )
    ]


class PartitionTests(unittest.TestCase):
    def test_known_cross_round_identity_group_unknowns_and_no_overlap(self):
        plans, rows = assign_partitions(population(), specification())
        self.assertEqual(rows[0]["stable_location_id"], rows[-1]["stable_location_id"])
        self.assertEqual(rows[0]["partition_name"], rows[-1]["partition_name"])
        unknown = next(r for r in rows if r["location_id"] is None)
        self.assertFalse(unknown["eligible"])
        self.assertEqual(unknown["partition_name"], "unavailable")
        groups = {}
        for row in rows:
            if row["stable_location_id"]:
                groups.setdefault(row["stable_location_id"], set()).add(row["partition_name"])
        self.assertTrue(all(len(v) == 1 for v in groups.values()))
        self.assertEqual(plans[0]["population_rows"], 4)

    def test_reordering_resume_seed_version_population_and_stress(self):
        spec, pop = specification(), population()
        expected = assign_partitions(pop, spec)
        spec["links"].reverse()
        self.assertEqual(expected, assign_partitions(list(reversed(pop)), spec))
        spec["seed"] = "new-seed"
        self.assertNotEqual(
            expected[0][0]["partition_id"], assign_partitions(pop, spec)[0][0]["partition_id"]
        )
        spec["municipal_holdout"] = ["AC:00100"]
        self.assertTrue(
            all(
                r["partition_name"] == "municipal_stress"
                for r in assign_partitions(pop, spec)[1]
                if r["eligible"]
            )
        )
        self.assertNotEqual(
            expected[0][0]["partition_id"], assign_partitions(pop[:-1], spec)[0][0]["partition_id"]
        )
        spec["version"] = "future"
        with self.assertRaises(PublicationError):
            assign_partitions(pop, spec)

    def test_stale_conflicting_unverified_geographic_links_fail(self):
        for mutation in ("duplicate", "unverified", "stale", "geography", "fractions"):
            spec, pop = copy.deepcopy(specification()), population()
            if mutation == "duplicate":
                spec["links"].append(spec["links"][0])
            elif mutation == "unverified":
                spec["links"][0]["verified"] = False
            elif mutation == "stale":
                spec["links"][0]["location_id"] = "missing"
            elif mutation == "geography":
                pop[1]["municipality_tse"] = "wrong"
            else:
                spec["fractions"]["training"] = 0.9
            with self.subTest(mutation=mutation), self.assertRaises(PublicationError):
                assign_partitions(pop, spec)
