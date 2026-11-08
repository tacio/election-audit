"""Phase 20b Ed521 cross-check: every verdict is observed and re-checked by a reference."""

import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tests.test_integrity_checks import FIXTURE, ITEM

AGREEING = """
from election_audit import ed521


def verificar(chave_publica, mensagem, assinatura, contexto=b""):
    return ed521.verify(chave_publica, assinatura, mensagem)
"""
REJECTING = """
def verificar(chave_publica, mensagem, assinatura, contexto=b""):
    return False
"""


@unittest.skipUnless(importlib.util.find_spec("ed521rs"), "verification extra is not installed")
class CrossCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        from election_audit import ed521
        from election_audit import ed521_crosscheck as cc

        self.ed521, self.cc = ed521, cc
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        provenance = json.loads((FIXTURE / "provenance.json").read_text())
        self.blobs = {k: (FIXTURE / ITEM["members"][k]).read_bytes() for k in ("bu", "rdv", "vsc")}
        self.published = {
            k: bytes.fromhex(provenance["members"][ITEM["members"][k]]["sha512"])
            for k in ITEM["members"]
        }

    def reference(self, name: str, source: str) -> Path:
        path = self.base / f"{name}.py"
        path.write_text(source)
        return path

    def test_every_ed521_verdict_of_a_section_is_observed(self) -> None:
        from election_audit import integrity_checks as ic

        seen = []
        self.ed521.observer = lambda *verdict: seen.append(verdict)
        try:
            ic.check_section(ITEM, self.blobs, self.published, 3221)
        finally:
            self.ed521.observer = None
        self.assertEqual(Counter(kind for kind, *_ in seen), {"urn": 7, "ca": 1})
        self.assertTrue(all(verdict for *_, verdict in seen))
        self.assertTrue(all(len(key) == 66 and len(sig) == 132 for _, key, _, sig, _ in seen))

    def run_shard(self, reference: Path) -> dict:
        self.cc._reference = self.cc.load_reference(reference)
        shard = self.base / reference.stem
        shard.mkdir()
        task = (str(shard), 0, [ITEM], [(self.blobs, self.published)], 3221, "2026-10-25")
        self.assertEqual(self.cc.run_shard(task), (0, 1, 0))
        self.assertIsNone(self.ed521.observer)
        return json.loads((shard / "00000.json").read_text())

    def test_agreeing_reference_has_no_disagreements(self) -> None:
        body = self.run_shard(self.reference("agree", AGREEING))
        self.assertEqual(body["signatures"], {"urn:valid:agree": 7, "ca:valid:agree": 1})
        self.assertEqual(body["disagreements"], [])
        self.assertEqual(body["section_kinds"], {"with_urn_ed521": 1})

    def test_each_disagreement_is_listed_with_its_values(self) -> None:
        body = self.run_shard(self.reference("reject", REJECTING))
        self.assertEqual(body["signatures"], {"urn:valid:differ": 7, "ca:valid:differ": 1})
        first = body["disagreements"][0]
        self.assertEqual(
            (first["section"], first["ours"], first["dataurnas"]),
            ("ac/01015/0002/0088", True, False),
        )
        self.assertEqual(len(bytes.fromhex(first["signature"])), 132)

    def test_vectors_record_the_mode_each_verdict_matches(self) -> None:
        seed = bytes(66)
        key = self.ed521.public_key(seed)
        signature = self.ed521.sign(seed, b"m")
        s = int.from_bytes(signature[66:], "little") + self.ed521.L  # S above L
        high = signature[:66] + s.to_bytes(66, "little")
        vector = {"key": key.hex(), "message": b"m".hex()}
        vectors = self.base / "vectors"
        vectors.mkdir()
        files = {
            "edge-cases.json": [
                {**vector, "id": "ok", "signature": signature.hex(), "strict": True, "ecpy": True},
                {**vector, "id": "s+l", "signature": high.hex(), "strict": False, "ecpy": True},
            ],
            "ecpy.json": [],
            "tse-2026.json": [
                {**vector, "id": "real", "signature": signature.hex(), "valid": True}
            ],
        }
        for name, rows in files.items():
            (vectors / name).write_text(json.dumps({"vectors": rows}))
        result = self.cc.run_vectors(
            self.cc.load_reference(self.reference("agree", AGREEING)), vectors
        )
        self.assertEqual(result["matches"], {"ecpy+strict": 2, "strict": 1})
        self.assertEqual([v["matches"] for v in result["vectors"]][1], ["strict"])

    def test_the_reference_file_is_pinned(self) -> None:
        path = self.reference("agree", AGREEING)
        with self.assertRaises(ValueError):
            self.cc.load_reference(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
