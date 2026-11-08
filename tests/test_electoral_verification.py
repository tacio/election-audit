"""Real BU/BWEB golden records and rejection paths, offline."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from election_audit.binary_bu import decode_bu
from election_audit.elections import election_for_round
from election_audit.electoral_verification import Evidence, verify_section

FIXTURE = Path(__file__).parent / "fixtures/binary-bu-2026"


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = json.loads((FIXTURE / "bweb-records.json").read_text())
        self.election = election_for_round(2)
        self.candidates = {"13": {"destination": "Válido"}, "22": {"destination": "Válido"}}

    def records(self, key):
        return [
            r
            for r in self.rows
            if (r["CD_MUNICIPIO"].zfill(5), r["NR_ZONA"].zfill(4), r["NR_SECAO"].zfill(4)) == key
        ]

    def test_three_independent_real_binary_csv_samples(self) -> None:
        for path in sorted(FIXTURE.glob("*.dat")):
            binary = decode_bu(path.read_bytes(), self.election)
            r = verify_section(self.records(binary["key"]), binary, self.candidates)
            self.assertTrue(r["complete_choices"])
            self.assertEqual(r["binary_link"], "exact_identity_and_counts_match")
            self.assertEqual(sum(x["count"] for x in r["choices"].values()), r["attending_voters"])
            self.assertEqual(r["signature_status"], "not_verified")
            self.assertIn("mirror", r["schema_provenance"])

    def test_omitted_blank_zero_is_derived_and_retained(self) -> None:
        path = FIXTURE / "01007-0009-0007.dat"
        b = decode_bu(path.read_bytes(), self.election)
        r = verify_section(self.records(b["key"]), b, self.candidates)
        self.assertEqual(r["choices"]["95"]["count"], 0)
        self.assertEqual(r["choices"]["95"]["origin"], "derived_zero_exhaustive_binary_accounting")

    def test_wrong_round_trailing_bytes_and_wrong_urn_rejected(self) -> None:
        raw = (FIXTURE / "01007-0009-0001.dat").read_bytes()
        with self.assertRaises(ValueError):
            decode_bu(raw, election_for_round(1))
        with self.assertRaises(ValueError):
            decode_bu(raw + b"extra", self.election)
        b = decode_bu(raw, self.election)
        rows = copy.deepcopy(self.records(b["key"]))
        for r in rows:
            r["NR_URNA_EFETIVADA"] = "1234567"
        with self.assertRaises(ValueError):
            verify_section(rows, b, self.candidates)

    def test_vote_mismatch_and_unknown_category_rejected(self) -> None:
        raw = (FIXTURE / "01007-0009-0001.dat").read_bytes()
        b = decode_bu(raw, self.election)
        for field, value in [("QT_VOTOS", "0"), ("CD_TIPO_VOTAVEL", "99")]:
            rows = copy.deepcopy(self.records(b["key"]))
            rows[0][field] = value
            with self.assertRaises(ValueError):
                verify_section(rows, b, self.candidates)

    def test_evidence_cache_hash_validation(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            e = Evidence(t)
            body, sha = e.keep(b"one", "https://resultados.tse.jus.br/example", "fixture")
            self.assertEqual(e.get("https://resultados.tse.jus.br/example", "fixture")[0], body)
            (Path(t) / "objects" / sha).write_bytes(b"two")
            with self.assertRaises(ValueError):
                e.get("https://resultados.tse.jus.br/example", "fixture")
            e.db.close()
