"""Real-source CSV subset in generated fixture containers; full AC checked separately."""

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from election_audit.electoral_imports import read_import
from election_audit.electoral_results import derive_electoral
from election_audit.official_bu import LAYOUT, VERSION
from election_audit.publication import PublicationError
from election_audit.source_inventory import ELECTION

FIXTURES = Path(__file__).parent / "fixtures/bweb-2026"
FILENAME = "bweb_2t_AC_261020260742.zip"
URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/" + FILENAME


def sample_rows():
    with (FIXTURES / "ac-sample.csv").open(encoding="latin-1", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def official_bundle(root, *, rows=None, header=None, dictionary=None):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, header or LAYOUT["header"], delimiter=";", quoting=csv.QUOTE_ALL
    )
    writer.writeheader()
    writer.writerows(sample_rows() if rows is None else rows)
    with zipfile.ZipFile(root / FILENAME, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(FILENAME[:-4] + ".csv", buffer.getvalue().encode("latin-1"))
        archive.writestr(
            LAYOUT["dictionary_member"],
            dictionary
            if dictionary is not None
            else (FIXTURES / LAYOUT["dictionary_member"]).read_bytes(),
        )
    checksum = hashlib.sha512((root / FILENAME).read_bytes()).hexdigest()
    (root / (FILENAME + ".sha512")).write_text(checksum + "  " + FILENAME + "\n")
    (root / "resource.json").write_text(
        json.dumps({"success": True, "result": {"url": URL, "package_id": "fixture"}})
    )
    (root / "catalog.json").write_text(
        json.dumps({"success": True, "result": {"id": "fixture", "resources": []}})
    )
    document = {
        "adapter": VERSION,
        "verification_status": "official_layout_verified",
        "election": ELECTION,
        "uf": "ac",
    }
    for role, name, url in (
        ("archive", FILENAME, URL),
        ("checksum", FILENAME + ".sha512", URL + ".sha512"),
        (
            "resource_metadata",
            "resource.json",
            "https://dadosabertos.tse.jus.br/api/3/action/resource_show?id=fixture",
        ),
        (
            "catalog_metadata",
            "catalog.json",
            "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=fixture",
        ),
    ):
        document[role] = {
            "path": name,
            "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
            "official_url": url,
            "observed_at": "2026-10-30T00:54:14+00:00",
        }
    path = root / "bundle.json"
    path.write_text(json.dumps(document))
    return path


def repin(bundle, role):
    document = json.loads(bundle.read_text())
    spec = document[role]
    spec["sha256"] = hashlib.sha256((bundle.parent / spec["path"]).read_bytes()).hexdigest()
    bundle.write_text(json.dumps(document))


class OfficialBUTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_real_subset_office_filter_composition_originals_and_unknowns(self):
        imported = read_import(official_bundle(self.root))
        tables = imported["tables"]
        summary = imported["source_discovery"]["real_validation"]
        self.assertEqual(summary["principal_sections"], 3)
        self.assertEqual(summary["excluded_governor_rows"], 1)
        self.assertEqual(
            summary["published_choice_arithmetic"]["attendance_difference"]["matched"], 3
        )
        self.assertEqual(len(tables["section_composition"]), 4)
        self.assertEqual(len(tables["result_version"]), 3)
        self.assertTrue(all(r["result_status"] == "unknown" for r in tables["result_version"]))
        self.assertTrue(
            all(r["event_at"] is None and r["event_time_raw"] for r in tables["processing_event"])
        )
        self.assertTrue(any(t["blank_votes"] is None for t in tables["section_contest_totals"]))
        self.assertTrue(
            any(t["valid_candidate_votes"] is None for t in tables["section_contest_totals"])
        )
        self.assertTrue(
            all(
                t["special_votes"] is None and t["total_presidential_ballots"] is None
                for t in tables["section_contest_totals"]
            )
        )
        generated, _ = derive_electoral(tables)
        self.assertEqual(
            {r["selection_state"] for r in generated["canonical_result"]}, {"ineligible"}
        )
        self.assertTrue(all(r["turnout"] is None for r in generated["section_results"]))
        self.assertEqual(len(imported["originals"]), 6)
        self.assertTrue(
            all(json.loads(r["record_locator"])["records"] for r in tables["record_lineage"])
        )

    def test_retransmission_deduplication_preserves_all_witnesses(self):
        rows = sample_rows()
        rows.insert(1, copy.deepcopy(rows[0]))
        imported = read_import(official_bundle(self.root, rows=rows))
        self.assertEqual(
            imported["source_discovery"]["real_validation"]["identical_retransmissions"], 1
        )
        witnesses = [
            r
            for r in imported["tables"]["record_lineage"]
            if r["derived_table"] == "vote_choice_count"
        ]
        self.assertTrue(
            any(len(json.loads(r["record_locator"])["records"]) == 2 for r in witnesses)
        )
        self.assertEqual(
            imported["source_discovery"]["real_validation"]["published_choice_arithmetic"][
                "attendance_difference"
            ]["mismatch"],
            0,
        )

    def test_conflicting_counts_and_repeated_totals_fail(self):
        for field in ("QT_VOTOS", "QT_APTOS", "DT_EMISSAO_BU", "DS_SECOES_AGREGADAS"):
            rows = sample_rows()
            rows.insert(1, copy.deepcopy(rows[0]))
            rows[1][field] = "999"
            with self.subTest(field=field), self.assertRaisesRegex(PublicationError, "Conflicting"):
                read_import(official_bundle(self.root, rows=rows))

    def test_unknown_codes_missing_counts_election_and_geography_fail(self):
        for field, value in (
            ("CD_TIPO_VOTAVEL", "99"),
            ("NR_VOTAVEL", "96"),
            ("QT_VOTOS", "-1"),
            ("CD_TIPO_URNA", "4"),
            ("CD_ELEICAO", "9999"),
            ("NR_TURNO", "1"),
            ("SG_UF", "AL"),
            ("NR_ZONA", "-1"),
            ("QT_VOTOS", "01"),
        ):
            rows = sample_rows()
            rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(PublicationError):
                read_import(official_bundle(self.root, rows=rows))

    def test_missing_electorate_is_explicit_and_arithmetic_mismatch_is_retained(self):
        rows = sample_rows()
        first = rows[0]
        key = [first[k] for k in ("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")]
        for r in rows:
            if [r[k] for k in ("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")] == key:
                r["QT_APTOS"] = "-3"
        rows[0]["QT_VOTOS"] = str(int(rows[0]["QT_VOTOS"]) + 1)
        imported = read_import(official_bundle(self.root, rows=rows))
        totals = next(
            r
            for r in imported["tables"]["section_contest_totals"]
            if r["eligible_electors"] is None
        )
        self.assertEqual(totals["field_states"]["eligible_electors"], "not_published")
        summary = imported["source_discovery"]["real_validation"]
        self.assertEqual(
            summary["published_choice_arithmetic"]["attendance_difference"]["mismatch"], 1
        )
        self.assertEqual(
            summary["published_choice_arithmetic"]["electorate_difference"]["unknown"], 1
        )

    def test_hash_checksum_metadata_dictionary_header_and_resource_bounds(self):
        bundle = official_bundle(self.root)
        (self.root / FILENAME).write_bytes(b"tampered")
        with self.assertRaisesRegex(PublicationError, "hash"):
            read_import(bundle)
        bundle = official_bundle(self.root)
        sidecar = self.root / (FILENAME + ".sha512")
        sidecar.write_text("0" * 128 + "  " + FILENAME)
        repin(bundle, "checksum")
        with self.assertRaisesRegex(PublicationError, "SHA-512"):
            read_import(bundle)
        bundle = official_bundle(self.root)
        (self.root / "resource.json").write_text(
            json.dumps(
                {"success": True, "result": {"url": "https://invalid", "package_id": "fixture"}}
            )
        )
        repin(bundle, "resource_metadata")
        with self.assertRaisesRegex(PublicationError, "metadata"):
            read_import(bundle)
        with self.assertRaisesRegex(PublicationError, "dictionary"):
            read_import(official_bundle(self.root, dictionary=b"unreviewed edition"))
        rows = sample_rows()
        for r in rows:
            r["WRONG"] = r.pop("QT_VOTOS")
        header = ["WRONG" if h == "QT_VOTOS" else h for h in LAYOUT["header"]]
        with self.assertRaisesRegex(PublicationError, "header"):
            read_import(official_bundle(self.root, rows=rows, header=header))
        bundle = official_bundle(self.root)
        document = json.loads(bundle.read_text())
        document["archive"]["official_url"] = URL.replace("cdn.tse.jus.br", "unreviewed.example")
        bundle.write_text(json.dumps(document))
        with self.assertRaisesRegex(PublicationError, "official TSE host"):
            read_import(bundle)
        bundle = official_bundle(self.root)
        with self.assertRaisesRegex(PublicationError, "byte limit"):
            read_import(bundle, max_bytes=1)
        with self.assertRaisesRegex(PublicationError, "row limit"):
            read_import(bundle, max_rows=1)
        with self.assertRaisesRegex(PublicationError, "expanded"):
            read_import(
                bundle,
                max_bytes=sum(
                    (self.root / n).stat().st_size
                    for n in (FILENAME, FILENAME + ".sha512", "resource.json", "catalog.json")
                ),
            )


if __name__ == "__main__":
    unittest.main()
