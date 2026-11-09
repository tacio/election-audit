"""Phase 20b: TSE's JWS signatures on the published presidential results (an I4 extension).

TSE publishes every unified result file twice: ``-u.json`` and ``-u.jws``, a compact JWS
(RFC 7515) whose payload is the same bytes, signed with EdDSA over Ed25519 (RFC 8037). The
public key and its certificates (end entity, ``AC Divulgação``, root, Ed448) are given in
TSE's *Manual de verificação dos arquivos JWS*; they are pinned here from a key file, never
read from the JWS itself.

``fetch`` reads the unified files listed in a finished EA20 snapshot (``results_hierarchy``),
and fetches, for each, the ``.jws`` and the ``.json`` again, close together, into a new
content-addressed root. ``verify`` checks the pinned key, then each file:

- J1: the header names ``alg: EdDSA`` and the pinned ``kid``;
- J2: the signature verifies over ``header.payload`` (and a one-bit change is refused);
- J3: the payload is byte-identical to the ``.json`` fetched with it;
- J4: the payload is byte-identical to the EA20 snapshot's file used by I4 (a republication
  after the snapshot is reported with both generation stamps, not as a failure).
"""

import base64
import contextlib
import hashlib
import json
import os
import sqlite3
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa

from election_audit.national_migration import atomic, sha
from election_audit.sa_logs import _get
from election_audit.types import JSON, Row

FETCH_VERSION = "signed-results-fetch-v1"
VERSION = "integrity-jws-v2"
# Revocation lists named in the certificates: the end entity's issuer and the intermediate's.
CRLS = {"acdivulgacao.crl": ("end_entity", "intermediate"), "actot.crl": ("intermediate", "root")}
SCHEMA = """
CREATE TABLE binding(value TEXT NOT NULL);
CREATE TABLE files(
  url TEXT PRIMARY KEY, scope_type TEXT NOT NULL, uf TEXT, municipality TEXT,
  jws_path TEXT NOT NULL, jws_sha256 TEXT NOT NULL, json_path TEXT NOT NULL,
  json_sha256 TEXT NOT NULL, ea20_sha256 TEXT NOT NULL, fetched_at TEXT NOT NULL);
"""
FILE_SCHEMA = pa.schema(
    [
        ("url", pa.string()),
        ("scope_type", pa.string()),
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("header", pa.string()),  # ok | other_kid | other_alg | malformed
        ("signature", pa.string()),  # verified | failed | malformed
        ("negative_control", pa.string()),  # refused | accepted
        ("payload_equals_json", pa.bool_()),
        ("payload_equals_ea20", pa.bool_()),
        ("payload_generation", pa.string()),  # dg hg idg of the signed payload
        ("ea20_generation", pa.string()),
        ("failed_json", pa.string()),
    ]
)


def _b64(value: bytes | str) -> bytes:
    raw = value.encode() if isinstance(value, str) else value
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


def _store(output: Path, body: bytes, suffix: str) -> tuple[str, str]:
    digest = hashlib.sha256(body).hexdigest()
    relative = Path("objects") / digest[:2] / f"{digest}.{suffix}"
    target = output / relative
    if target.exists():
        if sha(target) != digest:
            raise ValueError(f"Stored object differs from its address: {relative}")
        return digest, str(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(body)
    os.chmod(temporary, 0o444)
    os.replace(temporary, target)
    return digest, str(relative)


def _ea20_rows(ea20_root: Path) -> list[Row]:
    uri = (ea20_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT url, scope_type, uf, municipality, path, sha256 FROM files "
                "WHERE kind='unified' ORDER BY url"
            )
        ]
    if not rows:
        raise ValueError(f"No unified files in {ea20_root}")
    return rows


def fetch(
    ea20_root: str | Path,
    output: str | Path,
    *,
    delay: float = 0.34,
    resume: bool = False,
    get: Callable[[str], tuple[bytes, str | None, str | None]] = _get,
) -> JSON:
    """The ``.jws`` and a fresh ``.json`` of every unified file of an EA20 snapshot."""
    ea20_root = Path(ea20_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    status = json.loads((ea20_root / "status.json").read_text())
    if status.get("stage") != "finished":
        raise ValueError("EA20 snapshot is not finished")
    binding = {
        "version": FETCH_VERSION,
        "round": status["round"],
        "ea20_root": str(ea20_root),
        "ea20_manifest_sha256": sha(ea20_root / "manifest.sqlite"),
    }
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new: {output}")
    output.mkdir(parents=True, exist_ok=resume)
    rows = _ea20_rows(ea20_root)
    with contextlib.closing(sqlite3.connect(output / "manifest.sqlite")) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='binding'").fetchone():
            db.executescript(SCHEMA)
            db.execute("INSERT INTO binding VALUES(?)", (json.dumps(binding, sort_keys=True),))
            db.commit()
        elif json.loads(db.execute("SELECT value FROM binding").fetchone()[0]) != binding:
            raise ValueError("Output belongs to another snapshot or version")
        done = {url for (url,) in db.execute("SELECT url FROM files")}
        todo = [r for r in rows if r["url"] not in done]
        for index, row in enumerate(todo):
            if not row["url"].endswith("-u.json"):
                raise ValueError(f"Not a unified result file: {row['url']}")
            if index:
                time.sleep(delay)
            signed, _, _ = get(row["url"][: -len("json")] + "jws")
            time.sleep(delay)
            plain, _, _ = get(row["url"])
            jws_sha, jws_path = _store(output, signed, "jws")
            json_sha, json_path = _store(output, plain, "json")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    row["url"],
                    row["scope_type"],
                    row["uf"],
                    row["municipality"],
                    jws_path,
                    jws_sha,
                    json_path,
                    json_sha,
                    row["sha256"],
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            db.commit()
            if index % 100 == 0:
                atomic(output / "status.json", {"stage": "running", "done": len(done) + index})
        fetched = db.execute("SELECT count(*) FROM files").fetchone()[0]
    if fetched != len(rows):
        raise ValueError("Fetched files do not match the snapshot")
    result = {**binding, "files": fetched}
    atomic(output / "status.json", {"stage": "finished", **result})
    return result


# --------------------------------------------------------------------------- verification


def check_key(key_file: Path, election_date: str) -> tuple[Any, JSON]:
    """The pinned Ed25519 key, after checking it against its certificates."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    pinned = json.loads(key_file.read_bytes())
    jwk = pinned["jwk"]
    if (jwk.get("kty"), jwk.get("crv"), jwk.get("alg")) != ("OKP", "Ed25519", "EdDSA"):
        raise ValueError("The pinned key is not an Ed25519 signing key")
    key = Ed25519PublicKey.from_public_bytes(_b64(jwk["x"]))
    certificates = {
        name: x509.load_pem_x509_certificate(pem.encode())
        for name, pem in pinned["certificates"].items()
    }
    leaf, middle, root = (certificates[n] for n in ("end_entity", "intermediate", "root"))
    raw = leaf.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ski = leaf.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    day = datetime.fromisoformat(election_date).replace(tzinfo=UTC)
    checks = {
        "certificate_key_is_jwk": raw == _b64(jwk["x"]),
        "kid_is_subject_key_identifier": base64.urlsafe_b64encode(ski).rstrip(b"=").decode()
        == jwk["kid"],
        "end_entity_signed_by_intermediate": _signed(leaf, middle),
        "intermediate_signed_by_root": _signed(middle, root),
        "root_self_signed": _signed(root, root),
        "valid_on_election_day": all(
            c.not_valid_before_utc <= day <= c.not_valid_after_utc for c in (leaf, middle, root)
        ),
    }
    summary = {
        "kid": jwk["kid"],
        "source": pinned.get("source"),
        "key_file_sha256": sha(key_file),
        "checks": checks,
        "subjects": {n: c.subject.rfc4514_string() for n, c in certificates.items()},
    }
    if not all(checks.values()):
        raise ValueError(f"Pinned key checks failed: {checks}")
    return key, summary


def check_crls(key_file: Path, crl_dir: Path, election_date: str) -> JSON:
    """Each certificate's revocation list: issuer, signature, currency and the serial."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
    from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PublicKey
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pinned = json.loads(key_file.read_bytes())
    certificates = {
        name: x509.load_pem_x509_certificate(pem.encode())
        for name, pem in pinned["certificates"].items()
    }
    day = datetime.fromisoformat(election_date).replace(tzinfo=UTC)
    lists = {}
    for name, (subject, issuer) in CRLS.items():
        path = crl_dir / name
        crl = x509.load_der_x509_crl(path.read_bytes())
        cert, authority = certificates[subject], certificates[issuer]
        next_update = crl.next_update_utc
        issuer_key = authority.public_key()
        signature = False
        if isinstance(issuer_key, (Ed448PublicKey, Ed25519PublicKey, EllipticCurvePublicKey)):
            try:
                signature = crl.is_signature_valid(issuer_key)
            except TypeError, ValueError:
                signature = False
        lists[name] = {
            "sha256": sha(path),
            "issuer_matches": crl.issuer == authority.subject,
            "signature_valid": signature,
            "this_update": crl.last_update_utc.isoformat(),
            "next_update": next_update.isoformat() if next_update else None,
            "current_on_election_day": crl.last_update_utc <= day
            and (next_update is None or day <= next_update),
            "certificate": subject,
            "certificate_serial": hex(cert.serial_number),
            "revoked": crl.get_revoked_certificate_by_serial_number(cert.serial_number) is not None,
            "entries": len(crl),
        }
    failed = [n for n, v in lists.items() if not (v["issuer_matches"] and v["signature_valid"])] + [
        n for n, v in lists.items() if v["revoked"]
    ]
    if failed:
        raise ValueError(f"Revocation check failed: {failed} {lists}")
    return lists


def _signed(child: Any, issuer: Any) -> bool:
    from cryptography.exceptions import InvalidSignature

    if child.issuer != issuer.subject:
        return False
    try:
        child.verify_directly_issued_by(issuer)
    except InvalidSignature, ValueError, TypeError:
        return False
    return True


def _generation(value: bytes) -> str | None:
    try:
        data = json.loads(value)
    except ValueError:
        return None
    return " ".join(str(data.get(k)) for k in ("dg", "hg", "idg"))


def check_file(body: bytes, key: Any, kid: str, plain: bytes, snapshot: bytes) -> Row:
    """J1-J4 for one compact JWS."""
    from cryptography.exceptions import InvalidSignature

    row: Row = {"failed_json": "[]"}
    parts = body.strip().split(b".")
    if len(parts) != 3:
        row.update(header="malformed", signature="malformed")
        row["failed_json"] = '["J1","J2"]'
        return row
    head, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64(head))
        signature, payload = _b64(signature_b64), _b64(payload_b64)
    except ValueError:
        row.update(header="malformed", signature="malformed")
        row["failed_json"] = '["J1","J2"]'
        return row
    row["header"] = (
        "other_alg"
        if header.get("alg") != "EdDSA"
        else "other_kid"
        if header.get("kid") != kid
        else "ok"
    )
    signed = head + b"." + payload_b64
    try:
        key.verify(signature, signed)
        row["signature"] = "verified"
    except InvalidSignature:
        row["signature"] = "failed"
    changed = bytearray(signed)
    changed[len(head) + 1 + len(payload_b64) // 2] ^= 0x01
    try:
        key.verify(signature, bytes(changed))
        row["negative_control"] = "accepted"
    except InvalidSignature:
        row["negative_control"] = "refused"
    row["payload_equals_json"] = payload == plain
    row["payload_equals_ea20"] = payload == snapshot
    row["payload_generation"] = _generation(payload)
    row["ea20_generation"] = _generation(snapshot)
    failed = []
    if row["header"] != "ok":
        failed.append("J1")
    if row["signature"] != "verified" or row["negative_control"] != "refused":
        failed.append("J2")
    if not row["payload_equals_json"]:
        failed.append("J3")
    if not row["payload_equals_ea20"] and row["payload_generation"] == row["ea20_generation"]:
        failed.append("J4")  # same publication, different bytes
    row["failed_json"] = json.dumps(failed, separators=(",", ":"))
    return row


def run_verify(
    signed_root: str | Path,
    key_file: str | Path,
    output: str | Path,
    *,
    crls: str | Path | None = None,
) -> JSON:
    """J1-J4 for every file of a finished signed-results fetch.

    With ``crls`` (a directory holding ``acdivulgacao.crl`` and ``actot.crl``), the pinned
    certificates are also checked against their revocation lists; a list not signed by its
    issuer, or one that revokes a certificate, stops the run. Without it the revocation
    status is recorded as not consulted.
    """
    import pyarrow.parquet as pq

    from election_audit.elections import election_for_round

    signed_root = Path(signed_root).expanduser().absolute()
    key_file = Path(key_file).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    status = json.loads((signed_root / "status.json").read_text())
    if status.get("stage") != "finished":
        raise ValueError("Signed-results fetch is not finished")
    election = election_for_round(status["round"])
    key, key_summary = check_key(key_file, election.election_date)
    key_summary["revocation"] = (
        check_crls(key_file, Path(crls).expanduser().absolute(), election.election_date)
        if crls is not None
        else "not consulted"
    )
    ea20_root = Path(status["ea20_root"])
    if sha(ea20_root / "manifest.sqlite") != status["ea20_manifest_sha256"]:
        raise ValueError("EA20 snapshot changed since the fetch")
    ea20 = {r["url"]: r for r in _ea20_rows(ea20_root)}
    binding = {
        "version": VERSION,
        "round": status["round"],
        "signed_root": str(signed_root),
        "signed_manifest_sha256": sha(signed_root / "manifest.sqlite"),
        "ea20_manifest_sha256": status["ea20_manifest_sha256"],
        "key": key_summary,
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    uri = (signed_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        files = [dict(r) for r in db.execute("SELECT * FROM files ORDER BY url")]
    rows = []
    for f in files:
        body = (signed_root / f["jws_path"]).read_bytes()
        plain = (signed_root / f["json_path"]).read_bytes()
        snapshot = (ea20_root / ea20[f["url"]]["path"]).read_bytes()
        if (hashlib.sha256(body).hexdigest(), hashlib.sha256(plain).hexdigest()) != (
            f["jws_sha256"],
            f["json_sha256"],
        ) or hashlib.sha256(snapshot).hexdigest() != f["ea20_sha256"]:
            raise ValueError(f"Stored object changed: {f['url']}")
        base = {k: f[k] for k in ("url", "scope_type", "uf", "municipality")}
        rows.append({**base, **check_file(body, key, key_summary["kid"], plain, snapshot)})
    final = output / ".release.tmp"
    final.mkdir()
    pq.write_table(
        pa.Table.from_pylist(rows, schema=FILE_SCHEMA), final / "files.parquet", compression="zstd"
    )
    summary = {
        "files": len(rows),
        "by_scope": dict(Counter(r["scope_type"] for r in rows)),
        "header": dict(Counter(r["header"] for r in rows)),
        "signature": dict(Counter(r["signature"] for r in rows)),
        "negative_control": dict(Counter(str(r.get("negative_control")) for r in rows)),
        "payload_equals_json": dict(Counter(str(r.get("payload_equals_json")) for r in rows)),
        "payload_equals_ea20": dict(Counter(str(r.get("payload_equals_ea20")) for r in rows)),
        "republished_since_ea20": sum(
            1
            for r in rows
            if r.get("payload_generation") and r["payload_generation"] != r["ea20_generation"]
        ),
        "failed": dict(Counter(r["failed_json"] for r in rows)),
    }
    result = {
        **binding,
        "summary": summary,
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
    }
    atomic(final / "manifest.json", result)
    os.replace(final, output / "release")
    return result
