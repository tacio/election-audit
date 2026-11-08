import importlib.util
import unittest
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parent / "fixtures/urn-pki"


@unittest.skipUnless(
    importlib.util.find_spec("cryptography"), "verification extra is not installed"
)
class UrnPkiTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography import x509

        from election_audit import urn_pki

        self.x509, self.pki = x509, urn_pki

    def leaf(self, stem: str) -> Any:
        return self.x509.load_pem_x509_certificate((FIXTURE / f"{stem}-leaf.pem").read_bytes())

    def test_authorities_and_revocation_lists_load_verified(self) -> None:
        authorities = self.pki.authorities()
        self.assertEqual(set(authorities), {"AC URNA", "AC UE2020", "AC UE2022"})
        self.assertEqual(authorities["AC URNA"].revoked, {2587697, 3042029, 3367061})
        self.assertEqual(authorities["AC UE2020"].revoked, set())
        self.assertIsInstance(authorities["AC UE2022"].key, bytes)
        manifest = self.pki.manifest()
        self.assertEqual(len(manifest["files"]), 8)
        self.assertEqual(manifest["authorities"]["AC URNA"]["not_after"][:10], "2026-07-18")

    def test_real_urn_certificates_verify_against_their_ca(self) -> None:
        for stem, ca_valid in (("acurna", False), ("acue2020", True), ("acue2022", True)):
            with self.subTest(stem=stem):
                row = self.pki.check_certificate(self.leaf(stem), "2026-10-25")
                self.assertEqual(row["pki_issuer_signature"], "verified")
                self.assertIs(row["pki_revoked"], False)
                # AC URNA's published certificate expired on 2026-07-18.
                self.assertIs(row["pki_ca_valid_at_election"], ca_valid)
                self.assertTrue(row["cert_serial"].isdigit())
        self.assertIsNone(
            self.pki.check_certificate(self.leaf("acue2022"))["pki_ca_valid_at_election"]
        )

    def test_a_changed_certificate_fails(self) -> None:
        for stem in ("acurna", "acue2022"):
            with self.subTest(stem=stem):
                der = bytearray(self.leaf(stem).public_bytes(_der()))
                index = der.index(b"ueao" if stem == "acurna" else b"UEAO")
                der[index + 4] ^= 1  # one digit of the urn name inside the TBSCertificate
                changed = self.x509.load_der_x509_certificate(bytes(der))
                row = self.pki.check_certificate(changed, "2026-10-25")
                self.assertEqual(row["pki_issuer_signature"], "failed")

    def test_a_forged_issuer_and_a_revoked_serial_are_reported(self) -> None:
        from datetime import UTC, datetime, timedelta

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        real = self.pki.authorities()["AC URNA"].certificate
        key = ec.generate_private_key(ec.SECP521R1())
        now = datetime(2026, 1, 1, tzinfo=UTC)

        def forged(issuer: Any, serial: int) -> Any:
            builder = (
                self.x509.CertificateBuilder()
                .subject_name(self.x509.Name.from_rfc4514_string("CN=ueao00000001,O=TSE,C=BR"))
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(serial)
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=3650))
            )
            return builder.sign(key, hashes.SHA512())

        row = self.pki.check_certificate(forged(real.subject, 3042029), "2026-10-25")
        self.assertEqual((row["pki_issuer_signature"], row["pki_revoked"]), ("failed", True))
        row = self.pki.check_certificate(
            forged(self.x509.Name.from_rfc4514_string("CN=AC URNA"), 5), "2026-10-25"
        )
        self.assertEqual(
            (row["pki_issuer_signature"], row["pki_revoked"]), ("unknown_issuer", None)
        )
        self.assertEqual(self.pki.check_certificate(None)["pki_issuer_signature"], None)


def _der() -> Any:
    from cryptography.hazmat.primitives.serialization import Encoding

    return Encoding.DER


if __name__ == "__main__":
    unittest.main()
