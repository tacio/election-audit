"""Round identities and cross-round contamination regression checks."""

import json
import sqlite3
import unittest
from pathlib import Path

from test_snapshots import SourceFixture

from election_audit.coverage import build_population
from election_audit.elections import ElectionDescriptor, coerce_election, election_for_round
from election_audit.snapshots import create_snapshot, inspect_snapshot
from election_audit.source_inventory import aux_url, index_url, inventory_sources, read_manifest
from scripts.download_tse_logs import presidential_election, validate_manifest_round


class ElectionTests(unittest.TestCase):
    def test_descriptor_rejects_relabeling_and_keeps_default_identity(self) -> None:
        self.assertEqual(election_for_round().pleito_code, "3221")
        self.assertEqual(election_for_round(1).election_code, "6257")
        self.assertEqual(coerce_election(election_for_round(1).as_dict()), election_for_round(1))
        with self.assertRaises(ValueError):
            ElectionDescriptor(2026, "3221", "6258", 1, "2026-10-04")
        with self.assertRaises(ValueError):
            election_for_round(True)

    def test_catalog_selection_checks_round_date_and_codes(self) -> None:
        config = {
            "pl": [
                {
                    "c": "ele2026",
                    "cd": "3220",
                    "dt": "04/10/2026",
                    "e": [{"cd": "6257", "t": "1", "tp": "8", "abr": [{"cp": [{"cd": "1"}]}]}],
                }
            ]
        }
        self.assertEqual(presidential_election(config, 1), ("3220", "6257"))
        with self.assertRaises(ValueError):
            presidential_election(config, 2)
        config["pl"][0]["e"][0]["cd"] = "6258"
        with self.assertRaises(ValueError):
            presidential_election(config, 1)

    def test_manifest_mismatch_prevents_cross_round_resume(self) -> None:
        c = sqlite3.connect(":memory:")
        self.addCleanup(c.close)
        c.execute("CREATE TABLE files(url TEXT PRIMARY KEY)")
        c.execute(
            "INSERT INTO files VALUES (?)",
            ("https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/ac/log.jez",),
        )
        validate_manifest_round(c, "3221")
        with self.assertRaisesRegex(ValueError, "different election round"):
            validate_manifest_round(c, "3220")


class FirstRoundSnapshotTests(SourceFixture):
    def test_first_round_inventory_snapshot_and_population_are_distinct(self) -> None:
        election = election_for_round(1)
        self.record_section()
        index = {
            "f": "o",
            "cdp": "3220",
            "abr": [
                {
                    "cd": "ac",
                    "mu": [
                        {
                            "cd": "01120",
                            "zon": [{"cd": "0001", "sec": [{"ns": "0001", "da": "date"}]}],
                        }
                    ],
                }
            ],
        }
        self.save(index_url("ac", election), index)
        directory = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/dados/ac/01120/0001/0001"
        self.save(
            aux_url(self.key, election),
            {
                "f": "o",
                "st": "Totalizada",
                "hashes": [
                    {"hash": "pkg", "st": "Totalizado", "arq": [{"tp": "log", "nm": "a-log.dat"}]}
                ],
            },
        )
        self.save(directory + "/pkg/a-log.dat", b"first-round bytes")
        inventory = inventory_sources(
            self.root, ["ac"], election=election, source_manifest=self.manifest
        )
        population = build_population(inventory)
        self.assertEqual(population["tables"]["election"][0]["round"], 1)
        self.assertEqual(
            population["tables"]["coverage_ledger"][0]["log_availability"], "available"
        )
        with self.assertRaisesRegex(ValueError, "different election round"):
            read_manifest(self.root, ["ac"])
        path = create_snapshot(
            self.root,
            Path(self.temporary.name) / "snapshots",
            ["ac"],
            election=election,
            source_manifest=self.manifest,
        )
        document = inspect_snapshot(path, verify_objects=True)
        self.assertEqual(document["payload"]["tables"]["election"][0]["election_code"], "6257")
        self.assertEqual(
            json.loads(document["snapshot"]["population_scope"])["election"]["round"], 1
        )
