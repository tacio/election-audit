"""Phase 20b JWS check: signatures on the published results, against a pinned key."""

import base64
import contextlib
import datetime
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

URL = "https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json"
BODY = b'{ "ele" : "6258", "t" : "2", "dg" : "25/10/2026", "hg" : "23:27:02", "idg" : "1" }'


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@unittest.skipUnless(
    importlib.util.find_spec("cryptography"), "verification extra is not installed"
)
class SignedResultsTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import ed448, ed25519
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from cryptography.x509.oid import NameOID

        from election_audit import signed_results as sr

        self.sr = sr
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        root_key, middle_key = ed448.Ed448PrivateKey.generate(), ed448.Ed448PrivateKey.generate()
        self.key = ed25519.Ed25519PrivateKey.generate()
        public = self.key.public_key()

        def name(cn: str) -> x509.Name:
            return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

        def cert(subject: str, issuer: str, key: Any, signer: Any, ski: bool = False) -> Any:
            builder = (
                x509.CertificateBuilder()
                .subject_name(name(subject))
                .issuer_name(name(issuer))
                .public_key(key)
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime(2026, 1, 1))
                .not_valid_after(datetime.datetime(2027, 1, 1))
            )
            if ski:
                builder = builder.add_extension(
                    x509.SubjectKeyIdentifier.from_public_key(key), critical=False
                )
            return builder.sign(signer, None)

        root = cert("ROOT", "ROOT", root_key.public_key(), root_key)
        middle = cert("AC DIV", "ROOT", middle_key.public_key(), root_key)
        leaf = cert("LEAF", "AC DIV", public, middle_key, ski=True)
        ski = leaf.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
        self.kid = b64(ski)
        jwk = {
            "kty": "OKP",
            "crv": "Ed25519",
            "alg": "EdDSA",
            "kid": self.kid,
            "x": b64(public.public_bytes(Encoding.Raw, PublicFormat.Raw)),
        }
        pem = {
            n: c.public_bytes(Encoding.PEM).decode()
            for n, c in (("end_entity", leaf), ("intermediate", middle), ("root", root))
        }
        self.key_file = self.base / "key.json"
        self.key_file.write_text(json.dumps({"jwk": jwk, "certificates": pem, "source": "test"}))
        # A finished EA20 snapshot holding one unified file.
        self.ea20 = self.base / "ea20"
        (self.ea20 / "objects").mkdir(parents=True)
        (self.ea20 / "objects" / "br.json").write_bytes(BODY)
        with contextlib.closing(sqlite3.connect(self.ea20 / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(url, kind, scope_type, uf, municipality, path, sha256)")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?)",
                (
                    URL,
                    "unified",
                    "br",
                    "br",
                    None,
                    "objects/br.json",
                    hashlib.sha256(BODY).hexdigest(),
                ),
            )
            db.commit()
        (self.ea20 / "status.json").write_text(json.dumps({"stage": "finished", "round": 2}))

    def jws(self, payload: bytes, kid: str | None = None) -> bytes:
        head = b64(json.dumps({"kid": kid or self.kid, "typ": "JOSE", "alg": "EdDSA"}).encode())
        signed = f"{head}.{b64(payload)}".encode()
        return signed + b"." + b64(self.key.sign(signed)).encode()

    def fetch(self, signed: bytes, plain: bytes, name: str = "signed") -> Path:
        served = {URL[: -len("json")] + "jws": signed, URL: plain}
        output = self.base / name
        self.sr.fetch(self.ea20, output, delay=0, get=lambda url: (served[url], None, None))
        return output

    def test_a_signed_copy_of_the_snapshot_passes(self) -> None:
        root = self.fetch(self.jws(BODY), BODY)
        result = self.sr.run_verify(root, self.key_file, self.base / "out")
        self.assertEqual(result["summary"]["failed"], {"[]": 1})
        self.assertEqual(result["summary"]["signature"], {"verified": 1})
        self.assertEqual(result["summary"]["negative_control"], {"refused": 1})
        self.assertTrue(all(result["key"]["checks"].values()))

    def test_each_rule_fails_on_its_own_case(self) -> None:
        forged = self.jws(BODY)[:-4] + b"AAAA"
        rows = {
            "J1": self.sr.check_file(
                self.jws(BODY, kid="other"), self.public(), self.kid, BODY, BODY
            ),
            "J2": self.sr.check_file(forged, self.public(), self.kid, BODY, BODY),
            "J3": self.sr.check_file(self.jws(BODY), self.public(), self.kid, b"{}", BODY),
            "J4": self.sr.check_file(self.jws(BODY), self.public(), self.kid, BODY, BODY + b" "),
        }
        for rule, row in rows.items():
            self.assertEqual(json.loads(row["failed_json"]), [rule], rule)
        newer = BODY.replace(b'"idg" : "1"', b'"idg" : "2"')
        republished = self.sr.check_file(self.jws(newer), self.public(), self.kid, newer, BODY)
        self.assertEqual(json.loads(republished["failed_json"]), [])  # reported, not failed
        self.assertFalse(republished["payload_equals_ea20"])

    def test_a_key_that_does_not_match_its_certificate_is_refused(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        pinned = json.loads(self.key_file.read_text())
        other = ed25519.Ed25519PrivateKey.generate().public_key()
        pinned["jwk"]["x"] = b64(other.public_bytes(Encoding.Raw, PublicFormat.Raw))
        self.key_file.write_text(json.dumps(pinned))
        with self.assertRaises(ValueError):
            self.sr.check_key(self.key_file, "2026-10-25")

    def public(self) -> Any:
        return self.key.public_key()


if __name__ == "__main__":
    unittest.main()
