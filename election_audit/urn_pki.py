"""Urn certificate checks against TSE's published certificate authorities.

Pinned inputs (``resources/pki/``, provenance in ``pki.json``): the CA certificates ``AC URNA``
(ECDSA P-521, issues UE2013/UE2015 urn certificates), ``AC UE2020`` and ``AC UE2022`` (Ed521)
from TSE's 2026 format package, and the five revocation lists. Every list is checked against its
digest, and the three whose issuer key is public are verified when loaded.

For one urn certificate the check gives its serial, its issuing CA, the CA's signature over the
certificate (ECDSA with SHA-512 over the TBSCertificate, or Ed521 over the raw TBSCertificate,
as in TSE's ``mr_util.valida_certificado``; Ed521 through ``ed521rs``), whether the serial is on that CA's revocation list,
and whether the CA certificate itself was valid on election day.

The next link (``AC URNA`` to ``AC RAIZ UE``; ``AC UE2020``/``AC UE2022`` to ``AC URNA v2``) is
not checked: those issuer certificates are not public. ``AC URNA``'s published certificate
expired on 2026-07-18, but its key signed the 2026-09-27 revocation list.
"""

import hashlib
import json
from datetime import UTC, datetime
from functools import lru_cache
from importlib.resources import files
from typing import TYPE_CHECKING, Any, cast

from election_audit import ed521
from election_audit.types import JSON, Row

if TYPE_CHECKING:
    import ed521rs
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec

VERSION = "urn-pki-v2"
CA_FILES = {"AC URNA": "acurna", "AC UE2020": "acue2020", "AC UE2022": "acue2022"}
ED521_SIGNATURE_OID = "1.3.6.1.4.1.44588.2.1"


def _resource(name: str) -> bytes:
    raw = files("election_audit").joinpath(f"resources/pki/{name}").read_bytes()
    return raw


@lru_cache(maxsize=1)
def provenance() -> JSON:
    return json.loads(_resource("pki.json"))


def _pinned(name: str) -> bytes:
    raw = _resource(name)
    section = "certificates" if name.endswith(".der") else "revocation_lists"
    if hashlib.sha256(raw).hexdigest() != provenance()[section][name]["sha256"]:
        raise ValueError(f"{name} digest mismatch")
    return raw


def _cn(name: x509.Name) -> str:
    from cryptography.x509.oid import NameOID

    values = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    # A common name is a string attribute; only some other attribute types hold bytes.
    return cast(str, values[0].value) if values else name.rfc4514_string()


def _signed_by(
    certificate_or_list: x509.Certificate | x509.CertificateRevocationList,
    key: ec.EllipticCurvePublicKey | ed521rs.VerifyingKey | Any,
    tbs: bytes,
) -> bool:
    """True when the CA ``key`` (an ECDSA key or an ``ed521rs.VerifyingKey``) signed ``tbs``."""
    import ed521rs
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    signature = certificate_or_list.signature
    if isinstance(key, ed521rs.VerifyingKey):
        algorithm = certificate_or_list.signature_algorithm_oid.dotted_string
        return algorithm == ED521_SIGNATURE_OID and key.verify(signature, tbs)
    try:
        key.verify(signature, tbs, ec.ECDSA(hashes.SHA512()))
    except InvalidSignature:
        return False
    return True


class Authority:
    def __init__(self, name: str) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        stem = CA_FILES[name]
        der = _pinned(f"{stem}.der")
        self.name, self.file = name, f"{stem}.der"
        self.certificate = x509.load_der_x509_certificate(der)
        if _cn(self.certificate.subject) != name:
            raise ValueError(f"{stem}.der is not {name}")
        import ed521rs

        self.key = ed521.certificate_public_key(self.certificate.public_bytes(Encoding.DER))
        if self.key is None:
            self.key = self.verifier = self.certificate.public_key()
        else:  # signs every UE2020/UE2022 urn certificate: precompute once
            self.verifier = ed521rs.VerifyingKey(self.key, precompute=True)
        crl = x509.load_der_x509_crl(_pinned(f"{stem}.crl"))
        if _cn(crl.issuer) != name or not _signed_by(crl, self.verifier, crl.tbs_certlist_bytes):
            raise ValueError(f"{stem}.crl is not signed by {name}")
        self.crl = crl
        self.revoked = {entry.serial_number for entry in crl}

    def valid_on(self, day: datetime) -> bool:
        c = self.certificate
        return c.not_valid_before_utc <= day <= c.not_valid_after_utc

    def summary(self) -> JSON:
        c, next_update = self.certificate, self.crl.next_update_utc
        return {
            "certificate": self.file,
            "serial": c.serial_number,
            "issuer": _cn(c.issuer),
            "not_before": c.not_valid_before_utc.isoformat(),
            "not_after": c.not_valid_after_utc.isoformat(),
            "crl_this_update": self.crl.last_update_utc.isoformat(),
            "crl_next_update": next_update.isoformat() if next_update else None,
            "revoked_serials": sorted(self.revoked),
        }


@lru_cache(maxsize=1)
def authorities() -> dict[str, Authority]:
    return {name: Authority(name) for name in CA_FILES}


def check_certificate(
    certificate: x509.Certificate | None, election_date: str | None = None
) -> Row:
    """PKI columns for a parsed urn certificate (``cryptography`` x509 object or None)."""
    row = {
        "cert_serial": None,
        "pki_issuer_signature": None,
        "pki_revoked": None,
        "pki_ca_valid_at_election": None,
    }
    if certificate is None:
        return row
    row["cert_serial"] = str(certificate.serial_number)
    authority = authorities().get(_cn(certificate.issuer))
    if authority is None or certificate.issuer != authority.certificate.subject:
        row["pki_issuer_signature"] = "unknown_issuer"
        return row
    signed = _signed_by(certificate, authority.verifier, certificate.tbs_certificate_bytes)
    if isinstance(authority.key, bytes):  # an Ed521 CA
        ed521.observe(
            "ca", authority.key, certificate.tbs_certificate_bytes, certificate.signature, signed
        )
    row["pki_issuer_signature"] = "verified" if signed else "failed"
    row["pki_revoked"] = certificate.serial_number in authority.revoked
    if election_date:
        day = datetime.fromisoformat(election_date).replace(tzinfo=UTC)
        row["pki_ca_valid_at_election"] = authority.valid_on(day)
    return row


def manifest() -> JSON:
    """What the run's manifest records about the trust anchors."""
    return {
        "version": VERSION,
        "package_sha256": provenance()["package_sha256"],
        "authorities": {name: a.summary() for name, a in authorities().items()},
        "files": {
            name: entry["sha256"]
            for section in ("certificates", "revocation_lists")
            for name, entry in provenance()[section].items()
        },
        "not_verified": "AC URNA to AC RAIZ UE and AC UE2020/AC UE2022 to AC URNA v2: "
        "issuer certificates not public (requested, LAI protocol 83529705172533)",
    }
