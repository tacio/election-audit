"""I8: printed BU copies read from QR codes against the published binary BUs."""

import contextlib
import datetime
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

import pyarrow.parquet as pq

from election_audit import printed_bu as pb

FIXTURE = Path(__file__).parent / "fixtures/integrity-2026"
PREFIX = "o03221ac0101500020088"
ARCHIVE = "files/bu_imgbu_logjez_rdv_vscmr_2026_2t_AC.zip"
HEADER = (
    "ORIG ORLC PROC DTPL PLEI TURN FASE UNFE MUNI ZONA SECA IDUE IDCA HIQT HICA VERS LOCA "
    "APTO APTS APTT COMP FALT HBBM HBBG HBSB DTAB HRAB DTFC HRFC"
).split()


class ChainTests(unittest.TestCase):
    def test_slices_are_recovered_from_the_final_hash(self) -> None:
        content = " ".join(f"{90000 + i}:{i}" for i in range(250))  # over one code's limit
        cut = content.rfind(" ", 0, 1000)
        chunks = [content[:cut], content[cut + 1 :]]
        final = pb.chain(chunks)[-1]
        self.assertEqual(pb.split_search(content, final), chunks)
        self.assertIsNone(pb.split_search(content, "0" * 128))

    def test_codes_are_reassembled_in_order_and_gaps_named(self) -> None:
        chunks = ["ORIG:VOTA PLEI:3221", "IDEL:6258 CARG:1 13:1"]
        hashes = pb.chain(chunks)
        codes = [
            f"QRBU:{i}:2 VRQR:6.0 {c} HASH:{h}" for i, (c, h) in enumerate(zip(chunks, hashes), 1)
        ]
        codes[-1] += " ASSI:ABCD"
        parsed = pb.parse_codes("\n".join(reversed(codes)) + " QRCE:1:2 IDUE:1 MDUE:2020 CERT:30")
        self.assertEqual(parsed["chunks"], chunks)
        self.assertEqual((parsed["final_hash"], parsed["signature"]), (hashes[-1], "ABCD"))
        self.assertEqual(parsed["errors"], ["qrce_missing_2"])
        self.assertEqual(pb.parse_codes(codes[1])["errors"], ["qrbu_missing_1"])


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class PrintedPassTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        from election_audit.integrity_checks import bu_codec, bu_contests

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        raw = (FIXTURE / f"{PREFIX}-bu.dat").read_bytes()
        codec = bu_codec()
        bu = codec.decode(
            "EntidadeBoletimUrna", codec.decode("EntidadeEnvelopeGenerico", raw)["conteudo"]
        )
        # A bulk root holding the section's BU and signature file.
        self.bulk = base / "bulk"
        (self.bulk / "files").mkdir(parents=True)
        with zipfile.ZipFile(self.bulk / ARCHIVE, "w") as z:
            for suffix in ("bu.dat", "vota.vsc"):
                z.writestr(f"{PREFIX}-{suffix}", (FIXTURE / f"{PREFIX}-{suffix}").read_bytes())
        body = (self.bulk / ARCHIVE).read_bytes()
        with contextlib.closing(sqlite3.connect(self.bulk / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path, sha256, bytes, status)")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?)",
                (ARCHIVE, hashlib.sha256(body).hexdigest(), len(body), "complete"),
            )
            db.commit()
        # Printed content rendered from the BU, as the urn prints it.
        fields = pb.bu_header(bu, "ac") | {"ORLC": "LEG", "PROC": "1219", "DTPL": "20261025"}
        tokens = []
        for key in HEADER:
            values = fields[key] if isinstance(fields[key], list) else [fields[key]]
            tokens += [f"{key}:{v}" for v in values]
        eligible = {
            e["idEleicao"]: e["qtdEleitoresAptos"] for e in bu["resultadosVotacaoPorEleicao"]
        }
        for (idel, cargo), contest in bu_contests(bu).items():
            entries = contest["entries"]
            nominal = {n: v for (k, n), v in entries.items() if k == "N"}
            tokens += [f"IDEL:{idel}", f"CARG:{cargo}", "TIPO:0", "VERC:202610091513"]
            tokens += [f"{n}:{v}" for n, v in sorted(nominal.items()) if v]
            tokens += [f"APTA:{eligible[idel]}", f"NOMI:{sum(nominal.values())}"]
            tokens += [f"BRAN:{entries[('B', 0)]}", f"NULO:{entries[('X', 0)]}"]
            tokens += [f"TOTC:{sum(entries.values())}"]
        self.content = " ".join(tokens)
        self.urn = fields["IDUE"]
        self.key = ec.generate_private_key(ec.SECP521R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TEST CA")])
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(1)
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2030, 1, 1))
            .sign(self.key, hashes.SHA512())
        )
        self.cmind = base / "cmind"
        (self.cmind / "raw").mkdir(parents=True)

    def qr(self, content: str, *, sign: bool = True, final: str | None = None) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding

        cut = content.rfind(" ", 0, 600)
        chunks = [content[:cut], content[cut + 1 :]]
        hashes_ = pb.chain(chunks)
        signed = final or hashes_[-1]
        signature = self.key.sign(bytes.fromhex(signed), ec.ECDSA(hashes.SHA512())).hex().upper()
        codes = [
            f"QRBU:{i}:2 VRQR:6.0 {c} HASH:{h}" for i, (c, h) in enumerate(zip(chunks, hashes_), 1)
        ]
        codes[-1] += f" ASSI:{signature if sign else 'AB' * 66}"
        cert = self.cert.public_bytes(Encoding.DER).hex().upper()
        half = len(cert) // 2
        codes += [f"QRCE:1:2 IDUE:{self.urn} MDUE:2015 CERT:{cert[:half]}"]
        codes += [f"QRCE:2:2 IDUE:{self.urn} MDUE:2015 CERT:{cert[half:]}"]
        return "\n".join(codes)

    def write(self, number: int, qr: str) -> None:
        record = {"data": {"id": str(number), "is_simulated": "0", "qr_raw": qr}}
        (self.cmind / "raw" / f"bu_{number:06d}.json").write_text(json.dumps(record))

    def run_pass(self, name: str = "out") -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        result = pb.run_printed(self.bulk, Path(self.temp.name) / name, cmind=self.cmind)
        table = pq.read_table(Path(self.temp.name) / name / "release" / "printed.parquet")
        return result, {r["source_id"]: r for r in table.to_pylist()}

    def trusted(self) -> Any:
        """The test key is self-signed; treat it as CA-issued to reach the comparison paths."""
        from election_audit import urn_pki

        real = urn_pki.check_certificate

        def check(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return real(*args, **kwargs) | {
                "pki_issuer_signature": "verified",
                "pki_revoked": False,
            }

        return mock.patch.object(urn_pki, "check_certificate", side_effect=check)

    def test_a_copy_signed_by_an_untrusted_key_is_not_authentic(self) -> None:
        # xr1-20261109-P4-01: a self-signed key can sign copied content.
        self.write(1, self.qr(self.content))
        _, rows = self.run_pass()
        self.assertEqual(rows["1"]["pki_issuer_signature"], "unknown_issuer")
        self.assertEqual(
            (rows["1"]["signature"], rows["1"]["status"]), ("verified", "not_authentic")
        )

    def test_copies_are_verified_and_compared(self) -> None:
        changed = self.content.replace(" 13:", " 13:1", 1)
        self.assertNotEqual(changed, self.content)
        self.write(1, self.qr(self.content))
        self.write(2, self.qr(changed))  # re-signed by the same key: authentic, different
        self.write(3, self.qr(self.content, sign=False))
        self.write(4, self.qr(self.content.replace("FASE:O", "FASE:S")))
        with self.trusted():
            result, rows = self.run_pass()
        equal = rows["1"]
        self.assertEqual(
            (equal["chain"], equal["signature"], equal["qr_codes"]), ("ok", "verified", 2)
        )
        self.assertEqual(equal["pki_issuer_signature"], "verified")
        self.assertFalse(equal["certificate_matches_bu"])  # not the urn's key
        self.assertEqual(equal["status"], "equal_content_other_certificate")
        self.assertEqual((equal["header_differences"], equal["contest_differences"]), (0, 0))
        self.assertEqual(
            (equal["uf"], equal["municipality"], equal["zone"], equal["section"], equal["round"]),
            ("ac", "01015", "0002", "0088", 2),
        )
        self.assertEqual(rows["2"]["status"], "differs")
        detail = json.loads(rows["2"]["detail_json"])
        self.assertEqual(detail["contests"][0]["entries"][0][:2], ["N", 13])
        self.assertTrue(detail["internal"])  # the printed totals no longer add up
        self.assertEqual((rows["3"]["signature"], rows["3"]["status"]), ("failed", "not_authentic"))
        self.assertEqual(rows["4"]["status"], "out_of_scope")
        self.assertEqual(result["summary"]["sections"], 1)
        self.assertEqual(result["summary"]["sections_with_several_copies"], 1)
        self.assertEqual(result["summary"]["sections_whose_copies_share_one_final_hash"], 0)
        self.assertIn("2:ac", result["bulk_archives"])
        with self.assertRaises(FileExistsError), self.trusted():
            self.run_pass()

    def test_arvor_input_must_match_its_manifest(self) -> None:
        root = Path(self.temp.name) / "arvor" / "totalizacao_dados"
        root.mkdir(parents=True)
        (root / "bus.csv").write_text("id\n")
        (root / "manifest.json").write_text(json.dumps({"arquivos": {"bus.csv": {"sha256": "0"}}}))
        with self.assertRaises(ValueError):
            pb.run_printed(self.bulk, Path(self.temp.name) / "o", arvor=root.parent)


if __name__ == "__main__":
    unittest.main()
