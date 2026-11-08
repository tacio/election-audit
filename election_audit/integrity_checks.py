"""Phase 20 Tier 1 integrity checks: the section pass over the bulk BU/RDV/signature archives.

One pass per round reads every member of the 28 verified bulk archives in physical
(header offset) order. The parent process hashes each log and BU image with SHA-512
as it reads it and never parses them, so the protected logs stay unread. Workers get
only the BU, RDV and signature file of each section and run:

- I1 (hash part): every published file's SHA-512 against the per-file hashes listed
  in both the software (CEPESC) and hardware (EdDSA) signature lists, each list's
  self-hash, and the BU hash chain over its vote totals (``ultimoHashVotosVotavel``).
  Signature arithmetic and the certificate chain are not verified here.
- I3: the RDV recount of every contest against the BU totals.
- I9 (section part): file presence, file-name identity against the BU and RDV
  contents, phase, pleito and extra archive members.

Release tables hold statuses and digests, never vote counts. Values appear only in
``discrepancies.jsonl`` for rows that disagree. Attendance needed by I5 goes to
``restricted/`` and is read by check code only, never reported before the Phase 23
freeze. The BWEB comparison (I2) reads the per-contest digests written here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import threading
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit import urn_pki
from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.section_table import distinct_sessions
from election_audit.semantic_pass import verified_bulk_archives
from election_audit.types import JSON, Argv, Row, one

if TYPE_CHECKING:
    import duckdb
    from asn1tools.compiler import Specification
    from cryptography import x509
type Verifier = Callable[[bytes, bytes], bool]
type Entries = Mapping[tuple[str, int], int]

VERSION = "integrity-sections-v4"  # v4: RDV contest blocks are summed
SHARD_SECTIONS = 250
MAX_SMALL = 8 * 1024**2  # BU, RDV and signature files are far smaller
# TSE's official 2026 specifications (resources/tse-format-2026-official.json).
BU_SHA = "ef64bf723f774403b423ed0b617f5a83a3f50c0023d0003e18cd29170404ab81"
RDV_SHA = "282dcde0c7ba1f1bb128fe27443ad8d18f7490416c9546d033910a7ec557a465"
SIGNATURE_SHA = "86a0edf579b91e0a6df9f0981521e0229f41cb6cab0ed8a66d8a56f68c1f396f"
SIGNATURE_TYPE = "EntidadeAssinaturaEcourna"
MEMBER = re.compile(
    r"o(\d{5})([a-z]{2})(\d{5})(\d{4})(\d{4})-(bu|busa|imgbu|imgbusa|log|logsa|rdv|vota|sa)"
    r"\.(dat|jez|vsc)"
)
KIND = {
    "bu": "bu",
    "busa": "bu",
    "imgbu": "imgbu",
    "imgbusa": "imgbu",
    "log": "log",
    "logsa": "log",
    "rdv": "rdv",
    "vota": "vsc",
    "sa": "vsc",
}
PARSED = ("bu", "rdv", "vsc")  # read by workers; logs and BU images are only hashed
CARGO = {
    "presidente": 1,
    "vicePresidente": 2,
    "governador": 3,
    "viceGovernador": 4,
    "senador": 5,
    "deputadoFederal": 6,
    "deputadoEstadual": 7,
    "deputadoDistrital": 8,
    "primeiroSuplenteSenador": 9,
    "segundoSuplenteSenador": 10,
    "prefeito": 11,
    "vicePrefeito": 12,
    "vereador": 13,
}
BU_VOTE = {"nominal": 1, "branco": 2, "nulo": 3, "legenda": 4, "cargoSemCandidato": 5}
# Canonical choice classes shared by the BU, the RDV and BWEB: N nominal, L party
# (legenda), B blank, X null, S no candidate for the office.
BU_CLASS = {"nominal": "N", "legenda": "L", "branco": "B", "nulo": "X", "cargoSemCandidato": "S"}
RDV_CLASS = {
    "nominal": "N",
    "legenda": "L",
    "branco": "B",
    "brancoAposSuspensao": "B",
    "nulo": "X",
    "nuloAposSuspensao": "X",
    "nuloPorRepeticao": "X",
    "nuloCargoSemCandidato": "S",
    "nuloAposSuspensaoCargoSemCandidato": "S",
}

SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("archive", pa.string()),
        ("package", pa.string()),  # urn | sa
        ("members_json", pa.string()),
        ("missing_json", pa.string()),
        ("vsc_status", pa.string()),
        ("vsc_error", pa.string()),
        ("equipment", pa.string()),
        ("sw_algorithm", pa.string()),
        ("hw_algorithm", pa.string()),
        ("hw_bits", pa.int32()),
        ("hw_key_name", pa.string()),
        ("key_set", pa.string()),
        ("certificate_sha256", pa.string()),
        ("i1_sw_self_hash", pa.bool_()),
        ("i1_hw_self_hash", pa.bool_()),
        ("i1_listed", pa.int32()),
        ("i1_listed_published", pa.int32()),
        ("i1_hash_mismatches", pa.int32()),
        ("i1_published_unlisted", pa.int32()),
        ("i1_lists_agree", pa.bool_()),
        ("i1_detail_json", pa.string()),
        ("i1_signature_math", pa.string()),  # verified | failed | not_verified
        ("i1_file_signatures_ok", pa.int32()),
        ("i1_file_signatures_failed", pa.int32()),
        # Ed521 signatures (self, files, BU chain) where ECPy's verdict, TSE's reference, differs
        ("ed521_ecpy_disagreements", pa.int32()),
        ("cert_subject", pa.string()),
        ("cert_issuer", pa.string()),
        ("cert_valid_at_election", pa.bool_()),
        ("cert_serial", pa.string()),
        ("pki_issuer_signature", pa.string()),  # verified | failed | unknown_issuer
        ("pki_revoked", pa.bool_()),
        ("pki_ca_valid_at_election", pa.bool_()),
        ("bu_status", pa.string()),
        ("bu_error", pa.string()),
        ("bu_identity", pa.string()),
        ("bu_phase", pa.string()),
        ("bu_pleito", pa.int32()),
        ("local", pa.string()),
        ("urn_type", pa.string()),
        ("urn_serial", pa.string()),
        ("software_version", pa.string()),
        ("load_code", pa.string()),
        ("flash_serial", pa.string()),
        ("loaded_at", pa.string()),
        ("opened_at", pa.string()),
        ("closed_at", pa.string()),
        ("emitted_at", pa.string()),
        ("chain_ok", pa.int32()),
        ("chain_failed", pa.int32()),
        ("chain_signature_ok", pa.int32()),
        ("chain_signature_failed", pa.int32()),
        ("rdv_status", pa.string()),
        ("rdv_error", pa.string()),
        ("rdv_identity", pa.string()),
        ("i3_equal", pa.int32()),
        ("i3_differ", pa.int32()),
        ("i3_unmatched", pa.int32()),
    ]
)
CONTEST_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("election", pa.int32()),
        ("cargo", pa.int32()),
        ("bu_digest", pa.string()),
        ("bu_choices", pa.int32()),
        ("bu_accounting", pa.string()),
        ("chain", pa.string()),
        ("rdv_digest", pa.string()),
        ("i3", pa.string()),
    ]
)
RESTRICTED_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("election", pa.int32()),
        ("cargo", pa.int32()),
        ("eligible", pa.int64()),
        ("attendance", pa.int64()),
        ("attended", pa.int64()),
        ("biometric", pa.int64()),
        ("biographic", pa.int64()),
        ("without_biometrics", pa.int64()),
        ("bu_votes", pa.int64()),
        ("rdv_ballots", pa.int64()),
        ("choices_per_ballot", pa.int32()),
    ]
)


# --------------------------------------------------------------------------- codecs


def _pinned(name: str, digest: str) -> Specification:
    import asn1tools

    raw = files("election_audit").joinpath(f"resources/{name}").read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{name} digest mismatch")
    return asn1tools.compile_string(raw.decode(), codec="der" if "assinatura" in name else "ber")


@lru_cache(maxsize=1)
def bu_codec() -> Specification:
    return _pinned("bu-2026-official.asn1", BU_SHA)


@lru_cache(maxsize=1)
def rdv_codec() -> Specification:
    return _pinned("rdv-2026-official.asn1", RDV_SHA)


@lru_cache(maxsize=1)
def signature_codec() -> Specification:
    return _pinned("assinatura-2026-official.asn1", SIGNATURE_SHA)


def _key_info(part: JSON) -> tuple[Any, Any]:
    """(tagChaves, certificadoDigital) of one EntidadeAssinatura; the other is None."""
    kind, value = part["informacaoChave"]
    return (value, None) if kind == "tagChaves" else (None, value)


def digest(entries: Entries) -> str:
    """SHA-256 of a contest's nonzero (class, number, count) entries in canonical order."""
    canonical = sorted([k, n, c] for (k, n), c in entries.items() if c)
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


def _cargo(code: tuple[str, Any]) -> str | int:
    kind, value = code
    return CARGO[value] if kind == "cargoConstitucional" else int(value)


def _hex(value: Any) -> str:
    return value.hex().upper() if isinstance(value, bytes | bytearray) else str(value)


# --------------------------------------------------------------------------- checks


def hardware_verifier(hardware: JSON) -> tuple[Verifier | None, x509.Certificate | None]:
    """Verifier for the urn hardware key, or None when it cannot be checked.

    Observed on 2026 urns, both over the 64-byte SHA-512 hash, hashed again with SHA-512:
    UE2013/UE2015 carry a DER certificate (sometimes followed by padding) and DER ECDSA P-521
    signatures; UE2020/UE2022 carry a PEM certificate with an Ed521 key and 132-byte Ed521
    signatures (``election_audit.ed521``).
    """
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = _key_info(hardware)[1]
    algorithm = hardware["autoAssinado"]["algoritmoAssinatura"]["algoritmo"]
    certificate = None
    try:
        if raw and raw[:5] == b"-----":  # UE2020/UE2022: PEM, Ed521 key with a TSE OID
            certificate = x509.load_pem_x509_certificate(raw)
        elif raw and raw[:2] == b"\x30\x82":
            certificate = x509.load_der_x509_certificate(raw[: 4 + int.from_bytes(raw[2:4], "big")])
    except ValueError:
        certificate = None
    if certificate is None:
        return None, certificate
    if algorithm == "eddsa":
        from cryptography.hazmat.primitives.serialization import Encoding

        from election_audit import ed521

        key = ed521.certificate_public_key(certificate.public_bytes(Encoding.DER))
        if key is None:
            return None, certificate
        return Ed521Verifier(key), certificate
    if algorithm != "ecdsa":
        return None, certificate
    key = certificate.public_key()
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp521r1":
        return None, certificate

    def verify(digest_: bytes, signature: bytes) -> bool:
        try:
            key.verify(signature, digest_, ec.ECDSA(hashes.SHA512()))
            return True
        except InvalidSignature, ValueError:
            return False

    return verify, certificate


class Ed521Verifier:
    """Verdicts of ``ed521rs`` (RFC 8032 decoding, as ``election_audit.ed521``) for one urn key.

    Each signature is also checked as ECPy, TSE's reference verifier, would; ``disagreements``
    counts the signatures where the two verdicts differ (expected 0)."""

    def __init__(self, key: bytes) -> None:
        import ed521rs

        self.key, self.keys = key, {}
        for mode in ("strict", "ecpy"):
            try:
                self.keys[mode] = ed521rs.VerifyingKey(key, mode=mode)
            except ValueError:
                self.keys[mode] = None  # the key does not decode: every signature fails
        self.disagreements = 0

    def _verify(self, mode: str, signature: bytes, message: bytes) -> bool:
        key = self.keys[mode]
        return key is not None and key.verify(signature, message)

    def __call__(self, digest_: bytes, signature: bytes) -> bool:
        message = hashlib.sha512(digest_).digest()
        verdict = self._verify("strict", signature, message)
        self.disagreements += verdict != self._verify("ecpy", signature, message)
        from election_audit import ed521

        ed521.observe("urn", self.key, message, signature, verdict)
        return verdict


def ed521_implementation() -> JSON:
    import ed521rs
    from ed521rs import _native

    return {
        "implementation": "ed521rs",
        "version": ed521rs.__version__,
        "native_sha256": sha(Path(_native.__file__)),
        "backend": ed521rs.backend(),
        "verdict": "mode=strict (RFC 8032 decoding; same verdicts as election_audit.ed521)",
        "cross_check": "mode=ecpy (ECPy 8143d9ac, TSE's reference verifier); "
        "disagreements in ed521_ecpy_disagreements",
    }


def check_signatures(
    raw: bytes, published: Mapping[str, bytes], election_date: str | None = None
) -> tuple[Row, Verifier | None]:
    """I1. ``published`` maps member name to its SHA-512 digest (bytes).

    Returns the row and a verifier for other values signed by the urn hardware key."""
    entity = signature_codec().decode(SIGNATURE_TYPE, raw)
    lists, row = {}, {}
    for side in ("assinaturaSW", "assinaturaHW"):
        part = entity[side]
        auto = part["autoAssinado"]
        content = part["conteudoAutoAssinado"]
        row[f"i1_{side[-2:].lower()}_self_hash"] = (
            auto["assinatura"]["hash"] == hashlib.sha512(content).digest()
        )
        listed = signature_codec().decode("Assinatura", content)["arquivosAssinados"]
        lists[side] = {f["nomeArquivo"]: f["assinatura"]["hash"] for f in listed}
        if side == "assinaturaHW":
            hardware_files = {f["nomeArquivo"]: f["assinatura"] for f in listed}
    software, hardware = entity["assinaturaSW"], entity["assinaturaHW"]
    names = set(lists["assinaturaSW"]) | set(lists["assinaturaHW"])
    mismatched = sorted(
        n
        for n in names & set(published)
        if any(lists[s].get(n) not in (None, published[n]) for s in lists)
        or any(n not in lists[s] for s in lists)
    )
    unlisted = sorted(n for n in published if n not in names)
    unpublished = sorted(n.rsplit("-", 1)[-1] for n in names - set(published))
    certificate = _key_info(hardware)[1]
    origin = entity["origemAssinaturaHW"]
    row.update(
        vsc_status="decoded",
        vsc_error=None,
        equipment=f"{origin['modeloEquipamento']}/{origin['algoritmoAssinatura']}",
        sw_algorithm=software["autoAssinado"]["algoritmoAssinatura"]["algoritmo"],
        hw_algorithm=hardware["autoAssinado"]["algoritmoAssinatura"]["algoritmo"],
        hw_bits=hardware["autoAssinado"]["algoritmoAssinatura"]["bits"],
        hw_key_name=hardware["autoAssinado"]["usuario"]["nomeUsuario"],
        key_set=_key_info(software)[0] or _key_info(hardware)[0],
        certificate_sha256=hashlib.sha256(certificate).hexdigest() if certificate else None,
        i1_listed=len(names),
        i1_listed_published=len(names & set(published)),
        i1_hash_mismatches=len(mismatched),
        i1_published_unlisted=len(unlisted),
        i1_lists_agree=set(lists["assinaturaSW"].items()) == set(lists["assinaturaHW"].items()),
        i1_detail_json=json.dumps(
            {"mismatched": mismatched, "unlisted": unlisted, "unpublished_kinds": unpublished},
            separators=(",", ":"),
        ),
    )
    verify, certificate_ = hardware_verifier(hardware)
    file_ok = file_failed = 0
    if verify is None:
        math = "not_verified"
    else:
        auto = hardware["autoAssinado"]["assinatura"]
        math = "verified" if verify(auto["hash"], auto["assinatura"]) else "failed"
        for name in sorted(set(published) & set(hardware_files)):
            entry = hardware_files[name]
            ok = entry["hash"] == published[name] and verify(entry["hash"], entry["assinatura"])
            file_ok, file_failed = file_ok + ok, file_failed + (not ok)
    valid = None
    if certificate_ is not None and election_date:
        from datetime import UTC, datetime

        day = datetime.fromisoformat(election_date).replace(tzinfo=UTC)
        valid = certificate_.not_valid_before_utc <= day <= certificate_.not_valid_after_utc
    row.update(
        i1_signature_math=math,
        i1_file_signatures_ok=file_ok if verify else None,
        i1_file_signatures_failed=file_failed if verify else None,
        ed521_ecpy_disagreements=(
            verify.disagreements if isinstance(verify, Ed521Verifier) else None
        ),
        cert_subject=_cn(certificate_.subject) if certificate_ is not None else None,
        cert_issuer=_cn(certificate_.issuer) if certificate_ is not None else None,
        cert_valid_at_election=valid,
        **urn_pki.check_certificate(certificate_, election_date),
    )
    return row, verify


def _cn(name: x509.Name) -> str:
    from cryptography.x509.oid import NameOID

    values = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    # A common name is a string attribute; only some other attribute types hold bytes.
    return cast(str, values[0].value) if values else name.rfc4514_string()


def chain(bu: JSON, election: JSON, pleito: Any) -> tuple[str, int]:
    """Recompute the BU hash chain of one election; returns (status, failing blocks)."""
    section = bu["identificacaoSecao"]
    load = bu["urna"]["correspondenciaResultado"]["carga"]["codigoCarga"]
    header = "|".join(
        [
            str(pleito).zfill(5),
            str(election["idEleicao"]).zfill(5),
            str(section["municipioZona"]["municipio"]).zfill(5),
            str(section["municipioZona"]["zona"]).zfill(4),
            str(section["secao"]).zfill(4),
            str(load).zfill(24),
        ]
    )
    blocks = sorted(
        (
            (cargo["ordemImpressao"], row["ordemGeracaoHash"], _cargo(cargo["codigoCargo"]), row)
            for result in election["resultadosVotacao"]
            for cargo in result["totaisVotosCargo"]
            for row in cargo["votosVotaveis"]
        ),
        key=lambda b: (b[0], b[1]),
    )
    value, failed = hashlib.sha512(header.encode()).digest(), 0
    for _, order, cargo, row in blocks:
        parts = [value.hex().upper(), str(order), str(cargo), str(BU_VOTE[row["tipoVoto"]])]
        parts.append(str(row["quantidadeVotos"]))
        if "identificacaoVotavel" in row:
            parts += [str(row["identificacaoVotavel"]["codigo"])]
            parts += [str(row["identificacaoVotavel"]["partido"])]
        value = hashlib.sha512("|".join(parts).encode()).digest()
        failed += value != row["hash"]
    final = value == election["ultimoHashVotosVotavel"]
    return ("ok" if final and not failed else "failed"), failed


def bu_contests(bu: JSON) -> dict[tuple[int, str | int], JSON]:
    """Per (election, cargo): canonical entries, attendance and votes, from a decoded BU."""
    contests = {}
    for election in bu["resultadosVotacaoPorEleicao"]:
        for result in election["resultadosVotacao"]:
            for cargo in result["totaisVotosCargo"]:
                entries = Counter()
                for row in cargo["votosVotaveis"]:
                    kind = BU_CLASS[row["tipoVoto"]]
                    ident = row.get("identificacaoVotavel")
                    number = (
                        ident["codigo"] if kind == "N" else ident["partido"] if kind == "L" else 0
                    )
                    entries[(kind, int(number))] += row["quantidadeVotos"]
                contests[(election["idEleicao"], _cargo(cargo["codigoCargo"]))] = {
                    "entries": entries,
                    "attendance": result["qtdComparecimento"],
                    "eligible": election["qtdEleitoresAptos"],
                }
    return contests


def rdv_contests(rdv: JSON) -> tuple[dict[tuple[int, str | int], JSON], str]:
    contests = {}
    kind, elections = rdv["eleicoes"]
    for election in elections:
        for cargo in election["votosCargos"]:
            entries = Counter()
            for vote in cargo["votos"]:
                cls = RDV_CLASS[vote["tipoVoto"]]
                typed = vote.get("digitacao") or ""
                # A party vote keeps what was typed (e.g. an incomplete or unknown
                # candidate number); the party is its first two digits.
                number = int(typed) if cls == "N" else int(typed[:2]) if cls == "L" else 0
                entries[(cls, number)] += 1
            key = (election["idEleicao"], _cargo(cargo["idCargo"]))
            # An RDV can hold several blocks for one contest, one per urn or medium
            # (seen in contingency counting); the section's record is their sum.
            found = contests.setdefault(
                key, {"entries": Counter(), "ballots": 0, "choices": cargo["quantidadeEscolhas"]}
            )
            if found["choices"] != cargo["quantidadeEscolhas"]:
                raise ValueError(f"RDV blocks of contest {key} differ in choices per ballot")
            found["entries"] += entries
            found["ballots"] += len(cargo["votos"])
    return contests, kind


def _key_of(identification: JSON) -> tuple[str, str, str]:
    zone = identification["municipioZona"]
    return (
        str(zone["municipio"]).zfill(5),
        str(zone["zona"]).zfill(4),
        str(identification["secao"]).zfill(4),
    )


def check_section(
    item: Row,
    blobs: Mapping[str, bytes],
    published: Mapping[str, bytes],
    pleito: int,
    election_date: str | None = None,
) -> tuple[Row, list[Row], list[Row], list[Row]]:
    """All per-section checks; returns (section row, contest rows, restricted rows, issues)."""
    uf, municipality, zone, section = item["key"]
    base = {"uf": uf, "municipality": municipality, "zone": zone, "section": section}
    row = {
        **base,
        "archive": item["archive"],
        "package": item["package"],
        "members_json": json.dumps(sorted(item["members"]), separators=(",", ":")),
        "missing_json": json.dumps(
            sorted(k for k in ("bu", "imgbu", "log", "rdv", "vsc") if k not in item["members"]),
            separators=(",", ":"),
        ),
    }
    issues, contests_out, restricted = [], [], []
    names = {
        item["members"][k]: published[k] for k in published if k != "vsc"
    }  # a list never holds itself
    verify = None
    if "vsc" in blobs:
        try:
            signed, verify = check_signatures(blobs["vsc"], names, election_date)
            row.update(signed)
        except Exception as exc:
            row.update(vsc_status="error", vsc_error=f"{type(exc).__name__}: {exc}"[:300])
    else:
        row["vsc_status"] = "missing"
    bu = rdv = None
    if "bu" in blobs:
        try:
            parser = bu_codec()
            envelope, used = parser.decode_with_length("EntidadeEnvelopeGenerico", blobs["bu"])
            if used != len(blobs["bu"]) or "seguranca" in envelope:
                raise ValueError("Trailing bytes or encrypted BU envelope")
            bu, used = parser.decode_with_length("EntidadeBoletimUrna", envelope["conteudo"])
            if used != len(envelope["conteudo"]):
                raise ValueError("Trailing bytes in BU content")
            identity = _key_of(bu["identificacaoSecao"]) == (municipality, zone, section)
            carga = bu["urna"]["correspondenciaResultado"]["carga"]
            kind, data = bu["dadosSecaoSA"]
            row.update(
                bu_status="decoded",
                bu_error=None,
                bu_identity="match" if identity else "mismatch",
                bu_phase=bu["fase"],
                bu_pleito=bu["cabecalho"]["idEleitoral"][1],
                local=str(bu["identificacaoSecao"]["local"]).zfill(4),
                urn_type=bu["urna"]["tipoUrna"],
                urn_serial=str(carga["numeroInternoUrna"]),
                software_version=bu["urna"]["versaoVotacao"],
                load_code=str(carga["codigoCarga"]),
                flash_serial=_hex(carga["numeroSerieFC"]),
                loaded_at=carga["dataHoraCarga"],
                opened_at=data.get("dataHoraAbertura") if kind == "dadosSecao" else None,
                closed_at=data.get("dataHoraEncerramento") if kind == "dadosSecao" else None,
                emitted_at=bu["dataHoraEmissao"],
            )
            if not identity:
                issues.append(
                    {
                        "check": "I9",
                        "kind": "bu_identity",
                        **base,
                        "bu": _key_of(bu["identificacaoSecao"]),
                    }
                )
            if row["bu_pleito"] != pleito or row["bu_phase"] != "oficial":
                issues.append(
                    {
                        "check": "I9",
                        "kind": "bu_round",
                        **base,
                        "pleito": row["bu_pleito"],
                        "phase": row["bu_phase"],
                    }
                )
        except Exception as exc:
            row.update(bu_status="error", bu_error=f"{type(exc).__name__}: {exc}"[:300])
            bu = None
    else:
        row["bu_status"] = "missing"
    if "rdv" in blobs:
        try:
            rdv = rdv_codec().decode("EntidadeResultadoRDV", blobs["rdv"])["rdv"]
            identity = _key_of(rdv["identificacao"]) == (municipality, zone, section)
            row.update(
                rdv_status="decoded",
                rdv_error=None,
                rdv_identity="match" if identity else "mismatch",
            )
            if not identity or rdv["pleito"] != pleito or rdv["fase"] != "oficial":
                issues.append(
                    {
                        "check": "I9",
                        "kind": "rdv_identity",
                        **base,
                        "rdv": _key_of(rdv["identificacao"]),
                        "pleito": rdv["pleito"],
                        "phase": rdv["fase"],
                    }
                )
        except Exception as exc:
            row.update(rdv_status="error", rdv_error=f"{type(exc).__name__}: {exc}"[:300])
            rdv = None
    else:
        row["rdv_status"] = "missing"
    if bu is None:
        return row, contests_out, restricted, issues
    statuses = {}
    for election in bu["resultadosVotacaoPorEleicao"]:
        statuses[election["idEleicao"]] = chain(bu, election, row["bu_pleito"])
    row["chain_ok"] = sum(s == "ok" for s, _ in statuses.values())
    row["chain_failed"] = sum(s != "ok" for s, _ in statuses.values())
    if verify is not None:
        signed = [
            verify(e["ultimoHashVotosVotavel"], e["assinaturaUltimoHashVotosVotavel"])
            for e in bu["resultadosVotacaoPorEleicao"]
        ]
        row["chain_signature_ok"], row["chain_signature_failed"] = (
            sum(signed),
            len(signed) - sum(signed),
        )
        if isinstance(verify, Ed521Verifier):
            row["ed521_ecpy_disagreements"] = verify.disagreements
        if not all(signed):
            issues.append(
                {
                    "check": "I1",
                    "kind": "bu_chain_signature",
                    **base,
                    "failed": len(signed) - sum(signed),
                }
            )
    for election_id, (status, failed) in statuses.items():
        if status != "ok":
            issues.append(
                {
                    "check": "I1",
                    "kind": "bu_chain",
                    **base,
                    "election": election_id,
                    "failed_blocks": failed,
                }
            )
    detail = bu.get("detalhamentoComparecimento") or {}
    ours = bu_contests(bu)
    theirs, _ = rdv_contests(rdv) if rdv is not None else ({}, None)
    equal = differ = 0
    for key, contest in sorted(ours.items()):
        votes = sum(contest["entries"].values())
        recount = theirs.get(key)
        choices = recount["choices"] if recount else 1
        accounting = "equal" if votes == contest["attendance"] * choices else "differs"
        if recount is None:
            i3 = "no_rdv" if rdv is None else "missing_in_rdv"
        elif recount["entries"] == +contest["entries"]:
            i3, equal = "equal", equal + 1
        else:
            i3, differ = "differs", differ + 1
            issues.append(
                {
                    "check": "I3",
                    "kind": "rdv_recount",
                    **base,
                    "election": key[0],
                    "cargo": key[1],
                    "bu": sorted([k, n, c] for (k, n), c in contest["entries"].items() if c),
                    "rdv": sorted([k, n, c] for (k, n), c in recount["entries"].items()),
                }
            )
        if accounting != "equal":
            issues.append(
                {
                    "check": "I9",
                    "kind": "bu_accounting",
                    **base,
                    "election": key[0],
                    "cargo": key[1],
                    "votes": votes,
                    "attendance": contest["attendance"],
                    "choices": choices,
                }
            )
        contests_out.append(
            {
                **base,
                "election": key[0],
                "cargo": key[1],
                "bu_digest": digest(contest["entries"]),
                "bu_choices": sum(1 for c in contest["entries"].values() if c),
                "bu_accounting": accounting,
                "chain": statuses[key[0]][0],
                "rdv_digest": digest(recount["entries"]) if recount else None,
                "i3": i3,
            }
        )
        restricted.append(
            {
                **base,
                "election": key[0],
                "cargo": key[1],
                "eligible": contest["eligible"],
                "attendance": contest["attendance"],
                "attended": bu["qtdEleitoresCompareceram"],
                "biometric": detail.get("qtdEleitoresHabilitadosPorBiometria"),
                "biographic": detail.get("qtdEleitoresHabilitadosPorBiografia"),
                "without_biometrics": detail.get("qtdEleitoresCompareceramSemBiometria"),
                "bu_votes": votes,
                "rdv_ballots": recount["ballots"] if recount else None,
                "choices_per_ballot": recount["choices"] if recount else None,
            }
        )
    unmatched = sorted(set(theirs) - set(ours))
    for key in unmatched:
        issues.append(
            {
                "check": "I3",
                "kind": "rdv_contest_not_in_bu",
                **base,
                "election": key[0],
                "cargo": key[1],
            }
        )
    row.update(i3_equal=equal, i3_differ=differ, i3_unmatched=len(unmatched))
    return row, contests_out, restricted, issues


# --------------------------------------------------------------------------- work list


def section_work_list(
    bulk_root: str | Path,
    archives: Sequence[Row],
    year: int,
    round_number: int,
    *,
    limit: int | None = None,
) -> tuple[list[Row], dict[str, Any]]:
    """Sections of the bulk archives in physical order, plus unexpected members per archive."""
    if year != 2026:
        raise ValueError("Only the 2026 member layout has been reviewed for integrity checks")
    pleito = int(election_for_round(round_number, year).pleito_code)
    items, extras = [], {}
    for archive in archives:
        sections, order, odd = {}, {}, []
        with zipfile.ZipFile(Path(bulk_root) / archive["path"]) as z:
            for info in sorted(z.infolist(), key=lambda i: i.header_offset):
                match = MEMBER.fullmatch(info.filename)
                if not match:
                    if info.filename != "leiame.pdf":
                        odd.append(
                            {"name": info.filename, "bytes": info.file_size, "crc": info.CRC}
                        )
                    continue
                if int(match[1]) != pleito or match[2] != archive["uf"]:
                    raise ValueError(f"Member {info.filename!r} outside {archive['path']}")
                key = (match[2], match[3], match[4], match[5])
                kind = KIND[match[6]]
                members = sections.setdefault(key, {})
                if kind in members:
                    raise ValueError(f"Duplicate {kind} for section {key} in {archive['path']}")
                members[kind] = info.filename
                order.setdefault(key, info.header_offset)
                if match[6] in ("busa", "imgbusa", "logsa", "sa"):
                    sections[key]["_sa"] = True
        extras[archive["path"]] = odd
        for key in sorted(sections, key=order.__getitem__):  # every section has an offset
            members = sections[key]
            sa = members.pop("_sa", False)
            items.append(
                {
                    "archive": archive["path"],
                    "key": list(key),
                    "members": members,
                    "package": "sa" if sa else "urn",
                }
            )
    return (items[:limit] if limit is not None else items), extras


def read_shard(
    bulk_root: str | Path, items: Sequence[Row]
) -> list[tuple[dict[str, bytes], dict[str, bytes]]]:
    """Read one shard's members in order: small files as bytes, others as SHA-512 only."""
    out, handle, current = [], None, None
    try:
        for item in items:
            if item["archive"] != current:
                if handle is not None:
                    handle.close()
                handle = zipfile.ZipFile(Path(bulk_root) / item["archive"])
                current = item["archive"]
            blobs, published = {}, {}
            assert handle is not None  # opened for the first item's archive
            for kind, name in sorted(
                item["members"].items(), key=lambda kv: handle.getinfo(kv[1]).header_offset
            ):
                h = hashlib.sha512()
                keep = kind in PARSED
                body = bytearray()
                with handle.open(name) as stream:  # zipfile checks the CRC at end of stream
                    for chunk in iter(lambda: stream.read(1024**2), b""):
                        h.update(chunk)
                        if keep:
                            body += chunk
                            if len(body) > MAX_SMALL:
                                raise ValueError(f"{name} exceeds the small-file bound")
                published[kind] = h.digest()
                if keep:
                    blobs[kind] = bytes(body)
            out.append((blobs, published))
    finally:
        if handle is not None:
            handle.close()
    return out


# --------------------------------------------------------------------------- pass


def _write(path: Path, rows: list[Row], schema: pa.Schema) -> None:
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")


def run_shard(
    task: tuple[str, int, list[Row], list[tuple[dict[str, bytes], dict[str, bytes]]], int, str],
) -> tuple[int, int, int]:
    shard_dir, index, items, bodies, pleito, election_date = task
    sections, contests, restricted, issues = [], [], [], []
    for item, (blobs, published) in zip(items, bodies, strict=True):
        try:
            row, c, r, i = check_section(item, blobs, published, pleito, election_date)
        except Exception as exc:  # recorded per section; the pass continues
            uf, mun, zone, sec = item["key"]
            row = {
                "uf": uf,
                "municipality": mun,
                "zone": zone,
                "section": sec,
                "archive": item["archive"],
                "package": item["package"],
                "bu_status": "error",
                "bu_error": f"check: {type(exc).__name__}: {exc}"[:300],
            }
            c, r, i = [], [], []
        sections.append(row)
        contests.extend(c)
        restricted.extend(r)
        issues.extend(i)
    temporary = Path(shard_dir) / f".{index:05d}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir()
    _write(temporary / "sections.parquet", sections, SECTION_SCHEMA)
    _write(temporary / "contests.parquet", contests, CONTEST_SCHEMA)
    _write(temporary / "restricted.parquet", restricted, RESTRICTED_SCHEMA)
    (temporary / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    os.replace(temporary, Path(shard_dir) / f"{index:05d}")
    return index, len(items), sum(1 for s in sections if s.get("bu_status") == "error")


def _init_worker() -> None:
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def run_sections(
    bulk_root: str | Path,
    round_number: int,
    output: str | Path,
    *,
    year: int = 2026,
    workers: int = 4,
    ufs: Collection[str] | None = None,
    limit: int | None = None,
    resume: bool = False,
    shard_sections: int = SHARD_SECTIONS,
) -> JSON:
    """Run the section pass of one round into a new (or resumed) output root."""
    bulk_root = Path(bulk_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    archives = verified_bulk_archives(bulk_root, year, round_number, set(ufs) if ufs else None)
    election = election_for_round(round_number, year)
    pleito = int(election.pleito_code)
    binding = {
        "version": VERSION,
        "year": year,
        "round": round_number,
        "pleito": pleito,
        "bulk_root": str(bulk_root),
        "archives": {a["path"]: {"sha256": a["sha256"], "bytes": a["bytes"]} for a in archives},
        "schemas": {
            "bu": BU_SHA,
            "rdv": RDV_SHA,
            "signature": SIGNATURE_SHA,
        },
        "pki": urn_pki.manifest()["files"],
        "ed521": {k: v for k, v in ed521_implementation().items() if k != "backend"},
        "ufs": sorted(ufs) if ufs else None,
        "limit": limit,
        "shard_sections": shard_sections,
        "logs": "hashed with SHA-512 only; never parsed (protected sections included)",
    }
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new (or pass --resume): {output}")
    if resume and json.loads((output / "binding.json").read_bytes()) != binding:
        raise ValueError("Resume binding differs from the original pass")
    output.mkdir(parents=True, exist_ok=resume)
    atomic(output / "binding.json", binding)
    shard_dir = output / "shards"
    shard_dir.mkdir(exist_ok=True)
    items, extras = section_work_list(bulk_root, archives, year, round_number, limit=limit)
    shards = [items[i : i + shard_sections] for i in range(0, len(items), shard_sections)]
    done = {int(p.name) for p in shard_dir.iterdir() if p.name.isdigit()}
    todo = [i for i in range(len(shards)) if i not in done]
    gate = threading.BoundedSemaphore(workers + 2)

    def tasks() -> Iterator[
        tuple[str, int, list[Row], list[tuple[dict[str, bytes], dict[str, bytes]]], int, str]
    ]:
        for i in todo:
            gate.acquire()
            yield (
                str(shard_dir),
                i,
                shards[i],
                read_shard(bulk_root, shards[i]),
                pleito,
                election.election_date,
            )

    started, finished, errors = time.monotonic(), sum(len(shards[i]) for i in done), 0

    def report(stage: str, **extra: Any) -> None:
        atomic(
            output / "status.json",
            {
                "stage": stage,
                "sections_total": len(items),
                "sections_done": finished,
                "shards_total": len(shards),
                "errors_this_session": errors,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "pid": os.getpid(),
                **extra,
            },
        )

    report("running")
    with multiprocessing.get_context("spawn").Pool(
        workers, initializer=_init_worker, maxtasksperchild=100
    ) as pool:
        for _, count, failed in pool.imap_unordered(run_shard, tasks()):
            gate.release()
            finished += count
            errors += failed
            report("running")
    report("merging")
    result = merge(output, len(shards), binding, extras)
    report("finished", **{k: result[k] for k in ("sections", "contests", "discrepancies")})
    return result


def merge(output: Path, shard_count: int, binding: JSON, extras: JSON) -> JSON:
    release = output / "release"
    shutil.rmtree(release, ignore_errors=True)
    temporary = output / ".release.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    (temporary / "restricted").mkdir(parents=True)
    counts = {}
    for name, schema, target in (
        ("sections", SECTION_SCHEMA, temporary / "sections.parquet"),
        ("contests", CONTEST_SCHEMA, temporary / "contests.parquet"),
        ("restricted", RESTRICTED_SCHEMA, temporary / "restricted" / "attendance.parquet"),
    ):
        rows = 0
        with pq.ParquetWriter(target, schema, compression="zstd") as writer:
            for index in range(shard_count):
                table = pq.read_table(output / "shards" / f"{index:05d}" / f"{name}.parquet")
                writer.write_table(table)
                rows += table.num_rows
        counts[name] = rows
    kinds = Counter()
    with (temporary / "discrepancies.jsonl").open("w") as out:
        for index in range(shard_count):
            with (output / "shards" / f"{index:05d}" / "discrepancies.jsonl").open() as shard:
                for line in shard:
                    issue = json.loads(line)
                    kinds[f"{issue['check']}:{issue['kind']}"] += 1
                    out.write(line)
    atomic(temporary / "archive_members.json", extras)
    summary = summarize(temporary)
    files_ = {
        str(p.relative_to(temporary)): {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in sorted(temporary.rglob("*"))
        if p.is_file()
    }
    manifest = {
        **binding,
        "sections": counts["sections"],
        "contests": counts["contests"],
        "discrepancies": sum(kinds.values()),
        "discrepancy_kinds": dict(sorted(kinds.items())),
        "unexpected_archive_members": {k: len(v) for k, v in extras.items() if v},
        "summary": summary,
        "files": files_,
        "restricted": "restricted/ holds attendance and vote totals for I5; read by check code only before the Phase 23 freeze",
        "signature_math": "hardware signatures verified against the urn certificate key: "
        "ECDSA P-521 (UE2013/UE2015) and Ed521 per DOC-ICP-01.01 (UE2020/UE2022), both over "
        "SHA-512 of the listed SHA-512 hash; CEPESC (software) is not public",
        "pki": urn_pki.manifest(),
        "ed521": ed521_implementation(),
    }
    atomic(temporary / "manifest.json", manifest)
    os.replace(temporary, release)
    return manifest


def summarize(release: Path) -> JSON:
    """Check-level counts, from statuses only."""
    sections = pq.read_table(release / "sections.parquet").to_pylist()
    contests = pq.read_table(
        release / "contests.parquet", columns=["i3", "chain", "bu_accounting"]
    ).to_pylist()
    counter = defaultdict(Counter)
    for s in sections:
        counter["package"][s["package"]] += 1
        counter["vsc_status"][s["vsc_status"]] += 1
        counter["bu_status"][s["bu_status"]] += 1
        counter["rdv_status"][s["rdv_status"]] += 1
        counter["bu_identity"][s["bu_identity"]] += 1
        counter["missing"][s["missing_json"]] += 1
        counter["equipment"][s["equipment"]] += 1
        counter["hw_algorithm"][f"{s['hw_algorithm']}/{s['hw_bits']}"] += 1
        counter["i1_files"][
            "all_match"
            if s["vsc_status"] == "decoded"
            and not s["i1_hash_mismatches"]
            and not s["i1_published_unlisted"]
            else "mismatch_or_unavailable"
        ] += 1
        counter["i1_self_hash"][f"sw={s['i1_sw_self_hash']},hw={s['i1_hw_self_hash']}"] += 1
        counter["i1_lists_agree"][str(s["i1_lists_agree"])] += 1
        counter["i1_signature_math"][str(s["i1_signature_math"])] += 1
        counter["i1_file_signatures"][
            f"ok={s['i1_file_signatures_ok']},failed={s['i1_file_signatures_failed']}"
        ] += 1
        counter["ed521_ecpy_disagreements"][str(s["ed521_ecpy_disagreements"])] += 1
        counter["cert_issuer"][str(s["cert_issuer"])] += 1
        counter["cert_valid_at_election"][str(s["cert_valid_at_election"])] += 1
        counter["pki"][
            f"{s.get('cert_issuer')}: issuer_signature={s.get('pki_issuer_signature')},"
            f"revoked={s.get('pki_revoked')},ca_valid={s.get('pki_ca_valid_at_election')}"
        ] += 1
        counter["chain_signature"][
            f"ok={s.get('chain_signature_ok')},failed={s.get('chain_signature_failed')}"
        ] += 1
    for c in contests:
        counter["i3"][c["i3"]] += 1
        counter["chain"][c["chain"]] += 1
        counter["bu_accounting"][c["bu_accounting"]] += 1
    return {
        k: dict(sorted(((str(a), b) for a, b in v.items()))) for k, v in sorted(counter.items())
    }


# --------------------------------------------------------------------------- CLI


# --------------------------------------------------------------------------- I2: BWEB


BWEB_VERSION = "integrity-bweb-v1"
BWEB_FILE = re.compile(r"files/bweb_([12])t_([A-Z]{2})_\d{12}\.zip")
BWEB_COLUMNS: Sequence[str] = (
    "SG_UF CD_MUNICIPIO NR_ZONA NR_SECAO CD_PLEITO NR_TURNO CD_ELEICAO CD_CARGO_PERGUNTA "
    "CD_TIPO_VOTAVEL NR_VOTAVEL QT_VOTOS QT_APTOS QT_COMPARECIMENTO QT_ABSTENCOES "
    "NR_LOCAL_VOTACAO NR_URNA_EFETIVADA CD_CARGA_1_URNA_EFETIVADA CD_CARGA_2_URNA_EFETIVADA "
    "CD_FLASHCARD_URNA_EFETIVADA DT_CARGA_URNA_EFETIVADA DT_ABERTURA DT_ENCERRAMENTO "
    "DT_EMISSAO_BU DS_SECOES_AGREGADAS CD_TIPO_URNA"
).split()
# BWEB section fields compared with the BU, as (BWEB expression, section-row column).
METADATA = {
    "local": "lpad(NR_LOCAL_VOTACAO, 4, '0')",
    "urn_serial": "NR_URNA_EFETIVADA",
    "load_code": "replace(CD_CARGA_1_URNA_EFETIVADA || CD_CARGA_2_URNA_EFETIVADA, '.', '')",
    "flash_serial": "upper(CD_FLASHCARD_URNA_EFETIVADA)",
    "loaded_at": "strftime(try_strptime(DT_CARGA_URNA_EFETIVADA, '%Y-%m-%d %H:%M:%S'), '%Y%m%dT%H%M%S')",
    "opened_at": "strftime(try_strptime(DT_ABERTURA, '%Y-%m-%d %H:%M:%S'), '%Y%m%dT%H%M%S')",
    "closed_at": "strftime(try_strptime(DT_ENCERRAMENTO, '%Y-%m-%d %H:%M:%S'), '%Y%m%dT%H%M%S')",
    "emitted_at": "strftime(try_strptime(DT_EMISSAO_BU, '%Y-%m-%d %H:%M:%S'), '%Y%m%dT%H%M%S')",
}
CONTEST_I2_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("election", pa.int32()),
        ("cargo", pa.int32()),
        ("i2", pa.string()),  # equal | differs | bweb_only | bu_only
        ("counts_i2", pa.string()),  # eligible/attendance: equal | differs | unavailable
        ("bweb_repeated_rows", pa.bool_()),
    ]
)
SECTION_I2_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("in_bu", pa.bool_()),
        ("in_bweb", pa.bool_()),
        ("bweb_urn_type", pa.string()),
        ("aggregated_sections", pa.int32()),
        ("metadata_variants", pa.int32()),
        ("metadata_differs_json", pa.string()),
    ]
)


def bweb_files(
    bweb_root: str | Path, round_number: int, ufs: Collection[str] | None = None
) -> list[Row]:
    """Complete BWEB archives of one round from the input manifest, size-checked."""
    import contextlib
    import sqlite3

    bweb_root = Path(bweb_root)
    uri = (bweb_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    found = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for path, digest_, size, status in db.execute(
            "SELECT path, sha256, bytes, status FROM files ORDER BY path"
        ):
            match = BWEB_FILE.fullmatch(path)
            if not match or int(match[1]) != round_number:
                continue
            uf = match[2].lower()
            if ufs and uf not in ufs:
                continue
            if status != "complete" or not digest_:
                raise ValueError(f"BWEB archive is not complete: {path}")
            if (bweb_root / path).stat().st_size != size:
                raise ValueError(f"BWEB archive size differs from its manifest: {path}")
            found.append({"uf": uf, "path": path, "sha256": digest_, "bytes": size})
    if not found or (not ufs and len(found) != 28):
        raise ValueError(f"Expected 28 BWEB archives for round {round_number}, found {len(found)}")
    return found


def load_bweb(db: duckdb.DuckDBPyConnection, archive_path: str | Path, table: str = "b") -> str:
    """Stream one BWEB CSV member into a DuckDB table of string columns."""
    import pyarrow.csv as pacsv

    db.execute(f"DROP TABLE IF EXISTS {table}")
    db.execute(f"CREATE TABLE {table} ({', '.join(f'{c} VARCHAR' for c in BWEB_COLUMNS)})")
    with zipfile.ZipFile(archive_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {archive_path}")
        with z.open(names[0]) as stream:
            reader = pacsv.open_csv(
                stream,
                read_options=pacsv.ReadOptions(encoding="latin-1", block_size=16 * 1024**2),
                parse_options=pacsv.ParseOptions(delimiter=";"),
                convert_options=pacsv.ConvertOptions(
                    include_columns=BWEB_COLUMNS,
                    column_types={c: pa.string() for c in BWEB_COLUMNS},
                ),
            )
            for batch in reader:
                db.register("batch", pa.Table.from_batches([batch]))
                db.execute(f"INSERT INTO {table} SELECT {', '.join(BWEB_COLUMNS)} FROM batch")
                db.unregister("batch")
    return names[0]


BWEB_ENTRIES_SQL = """
WITH e AS (
    SELECT lpad(CD_MUNICIPIO, 5, '0') AS municipality, lpad(NR_ZONA, 4, '0') AS zone,
           lpad(NR_SECAO, 4, '0') AS section, CAST(CD_ELEICAO AS INTEGER) AS election,
           CAST(CD_CARGO_PERGUNTA AS INTEGER) AS cargo,
           CASE CD_TIPO_VOTAVEL WHEN '1' THEN 'N' WHEN '2' THEN 'B' WHEN '3' THEN 'X'
                WHEN '4' THEN 'L' ELSE 'U' || CD_TIPO_VOTAVEL END AS k,
           CASE WHEN CD_TIPO_VOTAVEL IN ('1', '4') THEN CAST(NR_VOTAVEL AS BIGINT) ELSE 0 END AS n,
           CAST(QT_VOTOS AS BIGINT) AS c,
           CAST(QT_APTOS AS BIGINT) AS eligible, CAST(QT_COMPARECIMENTO AS BIGINT) AS attendance
    FROM b
)
SELECT municipality, zone, section, election, cargo, k, n, CAST(sum(c) AS BIGINT) AS c,
       count(*) AS rows_,
       min(eligible) AS eligible_min, max(eligible) AS eligible_max,
       min(attendance) AS attendance_min, max(attendance) AS attendance_max
FROM e GROUP BY ALL
ORDER BY municipality, zone, section, election, cargo, k, n
"""


def bweb_contests(
    db: duckdb.DuckDBPyConnection,
) -> dict[tuple[Any, ...], tuple[str, bool, Any, bool, Any, bool]]:
    """Contest digests and counts of one loaded BWEB table, streamed in key order.

    DuckDB groups and sorts (both spill to disk); the digest is built here with
    ``digest`` so it is the same canonical string as the BU side.
    """
    contests, key, entries, rows = {}, None, {}, []

    def flush() -> None:
        if key is None:
            return
        eligible = [r[0] for r in rows] + [r[1] for r in rows]
        attendance = [r[2] for r in rows] + [r[3] for r in rows]
        contests[key] = (
            digest(entries),
            max(r[4] for r in rows) > 1,
            min(eligible),
            max(eligible) != min(eligible),
            min(attendance),
            max(attendance) != min(attendance),
        )

    reader = db.execute(BWEB_ENTRIES_SQL).fetch_record_batch(65536)
    for batch in reader:
        for r in zip(*(column.to_pylist() for column in batch.columns), strict=True):
            current = r[:5]
            if current != key:
                flush()
                key, entries, rows = current, {}, []
            entries[(r[5], r[6])] = r[7]
            rows.append((r[9], r[10], r[11], r[12], r[8]))
    flush()
    return contests


def bweb_sections_sql() -> str:
    fields = ", ".join(f"{expr} AS {name}" for name, expr in METADATA.items())
    return f"""
WITH m AS (
    SELECT DISTINCT lpad(CD_MUNICIPIO, 5, '0') AS municipality, lpad(NR_ZONA, 4, '0') AS zone,
           lpad(NR_SECAO, 4, '0') AS section, {fields}, DS_SECOES_AGREGADAS AS aggregated,
           CD_TIPO_URNA AS urn_type
    FROM b
)
SELECT municipality, zone, section, count(*) AS variants,
       {", ".join(f"any_value({name}) AS {name}" for name in METADATA)},
       any_value(aggregated) AS aggregated, any_value(urn_type) AS urn_type
FROM m GROUP BY ALL
"""


def bweb_identity(
    db: duckdb.DuckDBPyConnection, uf: str, round_number: int, year: int
) -> list[str]:
    election = election_for_round(round_number, year)
    bad = one(
        db.execute(
            "SELECT count(*) FROM b WHERE lower(SG_UF) <> ? OR CD_PLEITO <> ? OR NR_TURNO <> ?",
            [uf, str(int(election.pleito_code)), str(round_number)],
        ).fetchone()
    )[0]
    return bad


def _bu_entries(
    bulk_root: str | Path, archive: str, key: tuple[str, ...], pleito: int, package: str
) -> dict[tuple[int, str | int], JSON]:
    """Re-read one BU from its bulk archive to report the values of a disagreeing contest."""
    uf, municipality, zone, section = key
    suffix = "busa" if package == "sa" else "bu"
    member = f"o{pleito:05d}{uf}{municipality}{zone}{section}-{suffix}.dat"
    with zipfile.ZipFile(Path(bulk_root) / archive) as z:
        raw = z.read(member)
    parser = bu_codec()
    envelope = parser.decode("EntidadeEnvelopeGenerico", raw)
    return bu_contests(parser.decode("EntidadeBoletimUrna", envelope["conteudo"]))


def _uf_db(temporary: Path, uf: str, memory_limit: str) -> duckdb.DuckDBPyConnection:
    """A fresh DuckDB database per BWEB archive, so no UF's memory carries over."""
    import duckdb

    db = duckdb.connect(str(temporary / f"bweb-{uf}.duckdb"))
    db.execute(f"SET memory_limit = '{memory_limit}'")
    db.execute("SET threads = 2")
    db.execute("SET preserve_insertion_order = false")
    db.execute(f"SET temp_directory = '{temporary / 'spill'}'")
    return db


def _drop_uf_db(db: duckdb.DuckDBPyConnection, temporary: Path, uf: str) -> None:
    db.close()
    for name in (f"bweb-{uf}.duckdb", f"bweb-{uf}.duckdb.wal"):
        (temporary / name).unlink(missing_ok=True)


def run_bweb(
    sections_root: str | Path,
    bweb_root: str | Path,
    output: str | Path,
    *,
    ufs: Collection[str] | None = None,
    memory_limit: str = "1GB",
) -> JSON:
    """I2: compare every BWEB contest and section field with the section-pass release."""
    import duckdb

    sections_root = Path(sections_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    release = sections_root / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    if manifest["version"] != VERSION:
        raise ValueError(f"Section release version {manifest['version']} is not {VERSION}")
    for name, entry in manifest["files"].items():
        if entry["sha256"] != sha(release / name):
            raise ValueError(f"Section release file changed: {name}")
    round_number, year, pleito = manifest["round"], manifest["year"], manifest["pleito"]
    archives = bweb_files(Path(bweb_root).expanduser(), round_number, set(ufs) if ufs else None)
    if not ufs and manifest["ufs"] is not None:
        raise ValueError("A national BWEB comparison needs a national section release")
    for a in archives:
        if sha(Path(bweb_root).expanduser() / a["path"]) != a["sha256"]:
            raise ValueError(f"BWEB archive hash differs from its manifest: {a['path']}")
    binding = {
        "version": BWEB_VERSION,
        "round": round_number,
        "year": year,
        "sections_release": str(release),
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "bweb": {a["path"]: a["sha256"] for a in archives},
        "ufs": sorted(ufs) if ufs else None,
    }
    output.mkdir(parents=True)
    temporary = output / ".work"
    temporary.mkdir()
    atomic(output / "binding.json", binding)
    started = time.monotonic()
    import pyarrow.dataset as ds

    sections_ds = ds.dataset(release / "sections.parquet")
    contests_ds = ds.dataset(release / "contests.parquet")
    restricted_ds = ds.dataset(release / "restricted" / "attendance.parquet")
    section_columns = [
        c
        for c in ["municipality", "zone", "section", "archive", "package", "bu_status", *METADATA]
        if c in sections_ds.schema.names
    ]
    key_columns = ["municipality", "zone", "section", "election", "cargo"]
    # Contest rows are written per UF so the national run stays inside the memory budget.
    contests_writer = pq.ParquetWriter(
        temporary / "contests.parquet", CONTEST_I2_SCHEMA, compression="zstd"
    )
    i2_tally, counts_tally, contest_total = Counter(), Counter(), 0
    section_rows, issues, per_uf = [], [], {}
    for archive in archives:
        uf = archive["uf"]
        contest_rows = []
        db = _uf_db(temporary, uf, memory_limit)
        member = load_bweb(db, Path(bweb_root).expanduser() / archive["path"])
        identity_errors = bweb_identity(db, uf, round_number, year)
        if identity_errors:
            issues.append(
                {"check": "I9", "kind": "bweb_identity", "uf": uf, "rows": identity_errors}
            )
        theirs = bweb_contests(db)
        meta_rows = db.execute(bweb_sections_sql()).fetchall()
        names = ["municipality", "zone", "section", "variants", *METADATA, "aggregated", "urn_type"]
        bweb_sections = {(r[0], r[1], r[2]): dict(zip(names, r, strict=True)) for r in meta_rows}
        del meta_rows
        # Release DuckDB's buffers before the Python lookups are built; the database
        # file stays until the UF is done and is reopened only for differing contests.
        db.close()
        flt = ds.field("uf") == uf
        ours_sections = {
            (r["municipality"], r["zone"], r["section"]): r
            for r in sections_ds.to_table(filter=flt, columns=section_columns).to_pylist()
        }
        columns = contests_ds.to_table(filter=flt, columns=[*key_columns, "bu_digest"])
        ours = dict(
            zip(
                zip(*(columns[c].to_pylist() for c in key_columns), strict=True),
                columns["bu_digest"].to_pylist(),
                strict=True,
            )
        )
        columns = restricted_ds.to_table(
            filter=flt, columns=[*key_columns, "eligible", "attendance"]
        )
        counts = dict(
            zip(
                zip(*(columns[c].to_pylist() for c in key_columns), strict=True),
                zip(
                    columns["eligible"].to_pylist(), columns["attendance"].to_pylist(), strict=True
                ),
                strict=True,
            )
        )
        del columns
        tally = Counter()
        for key in sorted(set(ours) | set(theirs)):
            base = {"uf": uf, "municipality": key[0], "zone": key[1], "section": key[2]}
            mine, other = ours.get(key), theirs.get(key)
            if mine is None:
                status = "bweb_only"
            elif other is None:
                status = "bu_only"
            else:
                status = "equal" if mine == other[0] else "differs"
            count_status, repeated = "unavailable", bool(other and other[1])
            if mine is not None and other is not None and key in counts:
                eligible, eligible_varies, attendance, attendance_varies = other[2:]
                restricted = counts[key]
                count_status = (
                    "equal"
                    if not eligible_varies
                    and not attendance_varies
                    and eligible == restricted[0]
                    and attendance == restricted[1]
                    else "differs"
                )
                if count_status == "differs":
                    issues.append(
                        {
                            "check": "I2",
                            "kind": "counts",
                            **base,
                            "election": key[3],
                            "cargo": key[4],
                            "bweb": {
                                "eligible": eligible,
                                "attendance": attendance,
                                "varies": [eligible_varies, attendance_varies],
                            },
                            "bu": {"eligible": restricted[0], "attendance": restricted[1]},
                        }
                    )
            if repeated:
                issues.append(
                    {
                        "check": "I2",
                        "kind": "bweb_repeated_rows",
                        **base,
                        "election": key[3],
                        "cargo": key[4],
                    }
                )
            if status == "differs":
                section = ours_sections[key[:3]]
                bu_side = _bu_entries(
                    manifest["bulk_root"],
                    section["archive"],
                    (uf, *key[:3]),
                    pleito,
                    section["package"],
                ).get(key[3:], {"entries": {}})["entries"]
                db = duckdb.connect(str(temporary / f"bweb-{uf}.duckdb"), read_only=True)
                rows = db.execute(
                    """SELECT CD_TIPO_VOTAVEL, NR_VOTAVEL, sum(CAST(QT_VOTOS AS BIGINT)) FROM b
                       WHERE lpad(CD_MUNICIPIO,5,'0')=? AND lpad(NR_ZONA,4,'0')=? AND lpad(NR_SECAO,4,'0')=?
                       AND CAST(CD_ELEICAO AS INTEGER)=? AND CAST(CD_CARGO_PERGUNTA AS INTEGER)=?
                       GROUP BY ALL ORDER BY ALL""",
                    list(key),
                ).fetchall()
                db.close()
                issues.append(
                    {
                        "check": "I2",
                        "kind": "contest",
                        **base,
                        "election": key[3],
                        "cargo": key[4],
                        "bu": sorted([k, n, c] for (k, n), c in bu_side.items() if c),
                        "bweb": [[t, v, int(c)] for t, v, c in rows],
                    }
                )
            elif status != "equal":
                issues.append(
                    {"check": "I2", "kind": status, **base, "election": key[3], "cargo": key[4]}
                )
            tally[status] += 1
            contest_rows.append(
                {
                    **base,
                    "election": key[3],
                    "cargo": key[4],
                    "i2": status,
                    "counts_i2": count_status,
                    "bweb_repeated_rows": repeated,
                }
            )
        for key in sorted(set(ours_sections) | set(bweb_sections)):
            base = {"uf": uf, "municipality": key[0], "zone": key[1], "section": key[2]}
            mine, other = ours_sections.get(key), bweb_sections.get(key)
            differs = {}
            if mine and other and mine.get("bu_status") == "decoded":
                differs = {
                    f: {"bu": mine.get(f), "bweb": other[f]}
                    for f in METADATA
                    if (mine.get(f) or None) != (other[f] or None)
                }
                if differs or other["variants"] != 1:
                    issues.append(
                        {
                            "check": "I2",
                            "kind": "section_fields",
                            **base,
                            "fields": differs,
                            "variants": other["variants"],
                        }
                    )
            aggregated = other["aggregated"] if other else None
            members = (
                0
                if aggregated in (None, "#NULO#", "#NULO", "-1")
                else len([x for x in aggregated.split("/") if x.strip()])
            )
            section_rows.append(
                {
                    **base,
                    "in_bu": mine is not None,
                    "in_bweb": other is not None,
                    "bweb_urn_type": other["urn_type"] if other else None,
                    "aggregated_sections": members,
                    "metadata_variants": other["variants"] if other else None,
                    "metadata_differs_json": json.dumps(sorted(differs), separators=(",", ":")),
                }
            )
        per_uf[uf] = {"csv": member, **dict(tally)}
        _drop_uf_db(db, temporary, uf)
        contests_writer.write_table(pa.Table.from_pylist(contest_rows, schema=CONTEST_I2_SCHEMA))
        i2_tally.update(r["i2"] for r in contest_rows)
        counts_tally.update(r["counts_i2"] for r in contest_rows)
        contest_total += len(contest_rows)
        del contest_rows, ours, counts, theirs
        atomic(
            output / "status.json",
            {
                "stage": "running",
                "done": sorted(per_uf),
                "elapsed_seconds": round(time.monotonic() - started, 1),
            },
        )
    contests_writer.close()
    final = output / ".release.tmp"
    final.mkdir()
    os.replace(temporary / "contests.parquet", final / "contests.parquet")
    _write(final / "sections.parquet", section_rows, SECTION_I2_SCHEMA)
    kinds = Counter(f"{i['check']}:{i['kind']}" for i in issues)
    (final / "discrepancies.jsonl").write_text(
        "".join(
            json.dumps(i, sort_keys=True, separators=(",", ":"), default=str) + "\n" for i in issues
        )
    )
    summary = {
        "i2": dict(i2_tally),
        "counts_i2": dict(counts_tally),
        "sections": dict(Counter(f"bu={r['in_bu']},bweb={r['in_bweb']}" for r in section_rows)),
        "section_fields_differ": sum(r["metadata_differs_json"] != "[]" for r in section_rows),
        "aggregated_principals": sum(r["aggregated_sections"] > 0 for r in section_rows),
        "aggregated_members": sum(r["aggregated_sections"] for r in section_rows),
        "per_uf": per_uf,
    }
    result = {
        **binding,
        "contests": contest_total,
        "sections": len(section_rows),
        "discrepancies": sum(kinds.values()),
        "discrepancy_kinds": dict(sorted(kinds.items())),
        "summary": summary,
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    atomic(final / "manifest.json", result)
    os.replace(final, output / "release")
    shutil.rmtree(temporary)
    atomic(
        output / "status.json", {"stage": "finished", "elapsed_seconds": result["elapsed_seconds"]}
    )
    return result


# --------------------------------------------------------------------------- I4: hierarchy


HIERARCHY_VERSION = "integrity-hierarchy-v1"
NODE_SCHEMA = pa.schema(
    [
        ("level", pa.string()),  # municipality | uf | br
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("comparison", pa.string()),  # sections_vs_ea20 | children_vs_ea20
        ("measures", pa.int32()),
        ("differing", pa.int32()),
        ("differing_json", pa.string()),
    ]
)
PRESIDENT_SQL = """
WITH s AS (
    SELECT lpad(CD_MUNICIPIO, 5, '0') AS municipality, lpad(NR_ZONA, 4, '0') AS zone,
           lpad(NR_SECAO, 4, '0') AS section,
           any_value(CAST(QT_APTOS AS BIGINT)) AS eligible,
           any_value(CAST(QT_COMPARECIMENTO AS BIGINT)) AS attendance,
           any_value(DS_SECOES_AGREGADAS) AS aggregated
    FROM b WHERE CD_CARGO_PERGUNTA = '1' GROUP BY ALL
), v AS (
    SELECT lpad(CD_MUNICIPIO, 5, '0') AS municipality,
           CASE CD_TIPO_VOTAVEL WHEN '1' THEN 'candidate:' || CAST(CAST(NR_VOTAVEL AS INTEGER) AS VARCHAR)
                WHEN '2' THEN 'blank' WHEN '3' THEN 'null' ELSE 'other:' || CD_TIPO_VOTAVEL END AS measure,
           sum(CAST(QT_VOTOS AS BIGINT)) AS value
    FROM b WHERE CD_CARGO_PERGUNTA = '1' GROUP BY ALL
)
SELECT municipality, measure, value FROM v
UNION ALL
SELECT municipality, 'electorate', sum(eligible) FROM s GROUP BY ALL
UNION ALL
SELECT municipality, 'attendance', sum(attendance) FROM s GROUP BY ALL
UNION ALL
SELECT municipality, 'principal_sections', count(*) FROM s GROUP BY ALL
UNION ALL
SELECT municipality, 'aggregated_sections',
       sum(CASE WHEN aggregated IN ('#NULO#', '#NULO', '-1') OR aggregated IS NULL THEN 0
                ELSE len(string_split(aggregated, '/')) END) FROM s GROUP BY ALL
"""


def ea20_measures(node: JSON) -> dict[str, int]:
    """Presidential measures of one EA20 unified file, as integers."""
    measures = {}
    for cargo in node["carg"]:
        if cargo["cd"] != "1":
            continue
        for group in cargo["agr"]:
            for party in group["par"]:
                for candidate in party["cand"]:
                    measures[f"candidate:{int(candidate['n'])}"] = int(candidate["vap"])
    votes, electorate, sections = node["v"], node["e"], node["s"]
    measures.update(
        blank=int(votes["vb"]),
        null=int(votes["vn"]),
        # Votes for a candidacy voided after the election: BWEB keeps them as nominal.
        null_technical=int(votes["vnt"]),
        electorate=int(electorate["te"]),
        attendance=int(electorate["c"]),
        sections_installed=int(sections["si"]),
    )
    return measures


# Section counts EA20 publishes but BWEB rows cannot reproduce (sections without a BU).
EA20_ONLY = ("sections_total", "sections_not_installed")


def ea20_extra(node: JSON) -> dict[str, int]:
    return {"sections_total": int(node["s"]["ts"]), "sections_not_installed": int(node["s"]["sni"])}


def ea20_nodes(
    ea20_root: str | Path, round_number: int
) -> tuple[dict[Any, JSON], dict[str, str], dict[Any, dict[str, int]]]:
    """Unified EA20 files of a finished hierarchy fetch, hash-checked, keyed by node."""
    import contextlib
    import sqlite3

    ea20_root = Path(ea20_root)
    status = json.loads((ea20_root / "status.json").read_text())
    if status.get("stage") != "finished" or status.get("round") != round_number:
        raise ValueError(f"EA20 root is not a finished round-{round_number} fetch")
    if status.get("unified_not_final"):
        raise ValueError("EA20 root has unified files that are not final")
    uri = (ea20_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    nodes, hashes, extras = {}, {}, {}
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for scope, uf, municipality, path, digest_ in db.execute(
            "SELECT scope_type, uf, municipality, path, sha256 FROM files WHERE kind = 'unified'"
        ):
            body = (ea20_root / path).read_bytes()
            if hashlib.sha256(body).hexdigest() != digest_:
                raise ValueError(f"EA20 object differs from its manifest: {path}")
            node = json.loads(body)
            key = (
                "br" if scope == "br" else "uf" if scope == "uf" else "municipality",
                uf if scope != "br" else None,
                str(node["cdabr"]).zfill(5) if scope == "mun" else None,
            )
            nodes[key] = ea20_measures(node)
            extras[key] = ea20_extra(node)
            hashes[path] = digest_
    return nodes, hashes, extras


def _compare(
    expected: Mapping[str, Any], observed: Mapping[str, Any], keys: Iterable[str]
) -> dict[str, JSON]:
    differing = {
        k: {"ea20": expected.get(k), "observed": observed.get(k)}
        for k in sorted(keys)
        if expected.get(k, 0) != observed.get(k, 0)
    }
    return differing


def run_hierarchy(
    bweb_root: str | Path,
    ea20_root: str | Path,
    round_number: int,
    output: str | Path,
    *,
    ufs: Collection[str] | None = None,
    memory_limit: str = "2GB",
) -> JSON:
    """I4: section sums (BWEB, tied to the BU by I2) against every EA20 node."""

    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    bweb_root, ea20_root = Path(bweb_root).expanduser(), Path(ea20_root).expanduser()
    archives = bweb_files(bweb_root, round_number, set(ufs) if ufs else None)
    for a in archives:
        if sha(bweb_root / a["path"]) != a["sha256"]:
            raise ValueError(f"BWEB archive hash differs from its manifest: {a['path']}")
    nodes, hashes, extras = ea20_nodes(ea20_root, round_number)
    listed = {k for k in nodes.get(("br", None, None), {}) if k.startswith("candidate:")}
    if not listed:
        raise ValueError("EA20 national file lists no presidential candidates")
    binding = {
        "version": HIERARCHY_VERSION,
        "round": round_number,
        "bweb": {a["path"]: a["sha256"] for a in archives},
        "ea20_root": str(ea20_root),
        "ea20_manifest_sha256": sha(ea20_root / "manifest.sqlite"),
        "ea20_unified_files": len(hashes),
        "ufs": sorted(ufs) if ufs else None,
        "source": "BWEB section rows (I2 ties each to its BU); presidential contest only",
    }
    output.mkdir(parents=True)
    temporary = output / ".work"
    temporary.mkdir()
    atomic(output / "binding.json", binding)
    started = time.monotonic()
    rows, issues = [], []
    uf_sums, aggregated = {}, Counter()

    def record(
        level: str,
        uf: str | None,
        municipality: str | None,
        comparison: str,
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> None:
        keys = set(expected) | set(observed)
        differing = _compare(expected, observed, keys)
        rows.append(
            {
                "level": level,
                "uf": uf,
                "municipality": municipality,
                "comparison": comparison,
                "measures": len(keys),
                "differing": len(differing),
                "differing_json": json.dumps(sorted(differing), separators=(",", ":")),
            }
        )
        if differing:
            issues.append(
                {
                    "check": "I4",
                    "kind": comparison,
                    "level": level,
                    "uf": uf,
                    "municipality": municipality,
                    "differing": differing,
                }
            )

    for archive in archives:
        uf = archive["uf"]
        db = _uf_db(temporary, uf, memory_limit)
        load_bweb(db, bweb_root / archive["path"])
        sums = defaultdict(dict)
        for municipality, measure, value in db.execute(PRESIDENT_SQL).fetchall():
            sums[municipality][measure] = int(value)
        children = Counter()
        municipalities = {k[2] for k in nodes if k[0] == "municipality" and k[1] == uf}
        for municipality in sorted(municipalities | set(sums)):
            observed = dict(sums.get(municipality, {}))
            observed["sections_installed"] = observed.pop("principal_sections", 0)
            aggregated[uf] += observed.pop("aggregated_sections", 0)
            for measure in [m for m in observed if m.startswith("candidate:") and m not in listed]:
                observed["null_technical"] = observed.get("null_technical", 0) + observed.pop(
                    measure
                )
            expected = dict(nodes.get(("municipality", uf, municipality), {}))
            record("municipality", uf, municipality, "sections_vs_ea20", expected, observed)
            children.update(nodes.get(("municipality", uf, municipality), {}))
        expected = nodes.get(("uf", uf, None), {})
        record("uf", uf, None, "children_vs_ea20", expected, dict(children))
        uf_sums[uf] = expected
        _drop_uf_db(db, temporary, uf)
        atomic(
            output / "status.json",
            {
                "stage": "running",
                "done": sorted(uf_sums),
                "elapsed_seconds": round(time.monotonic() - started, 1),
            },
        )
    if not ufs:
        total = Counter()
        for measures in uf_sums.values():
            total.update(measures)
        record("br", None, None, "children_vs_ea20", nodes.get(("br", None, None), {}), dict(total))
    final = output / ".release.tmp"
    final.mkdir()
    _write(final / "nodes.parquet", rows, NODE_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    summary = {
        f"{level}:{comparison}": dict(
            Counter(
                "equal" if r["differing"] == 0 else "differs"
                for r in rows
                if (r["level"], r["comparison"]) == (level, comparison)
            )
        )
        for level, comparison in sorted({(r["level"], r["comparison"]) for r in rows})
    }
    differing_measures = Counter(m for r in rows for m in json.loads(r["differing_json"]))
    result = {
        **binding,
        "nodes": len(rows),
        "discrepancies": len(issues),
        "summary": summary,
        "differing_measures": dict(differing_measures.most_common()),
        "aggregated_member_sections": dict(sorted(aggregated.items())),
        "ea20_section_counts": {
            f"{k[0]}:{k[1] or ''}": v
            for k, v in sorted(extras.items(), key=str)
            if k[0] != "municipality"
        },
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    atomic(final / "manifest.json", result)
    os.replace(final, output / "release")
    shutil.rmtree(temporary)
    atomic(
        output / "status.json", {"stage": "finished", "elapsed_seconds": result["elapsed_seconds"]}
    )
    return result


# --------------------------------------------------------------------------- I9: correspondences


CORRESPONDENCE_VERSION = "integrity-correspondence-v1"
CEFT_FILE = re.compile(r"files/CEFT_([12])t_([A-Z]{2})_\d{12}\.zip")
CORRESPONDENCE_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("ceft_rows", pa.int32()),
        ("origin", pa.string()),
        ("divergence", pa.string()),
        ("expected_is_effective", pa.bool_()),
        ("in_bu", pa.bool_()),
        ("effective_matches_bu_json", pa.string()),  # fields of the effective urn that differ
    ]
)


def _stamp(value: str | None) -> str | None:
    if not value or len(value) < 19:
        return None
    return value[:4] + value[5:7] + value[8:10] + "T" + value[11:13] + value[14:16] + value[17:19]


def run_correspondence(
    sections_root: str | Path,
    ceft_root: str | Path,
    output: str | Path,
    *,
    ufs: Collection[str] | None = None,
) -> JSON:
    """I9: each section's effective urn (CEFT) against the urn its BU says produced it."""
    import contextlib
    import csv
    import io
    import sqlite3

    sections_root = Path(sections_root).expanduser().absolute()
    ceft_root = Path(ceft_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    release = sections_root / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if entry["sha256"] != sha(release / name):
            raise ValueError(f"Section release file changed: {name}")
    round_number = manifest["round"]
    uri = (ceft_root / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    archives = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        for path, digest_, size, status in db.execute(
            "SELECT path, sha256, bytes, status FROM files ORDER BY path"
        ):
            match = CEFT_FILE.fullmatch(path)
            if not match or int(match[1]) != round_number:
                continue
            uf = match[2].lower()
            if ufs and uf not in ufs:
                continue
            if status != "complete" or sha(ceft_root / path) != digest_:
                raise ValueError(f"Correspondence archive incomplete or changed: {path}")
            archives.append({"uf": uf, "path": path, "sha256": digest_, "bytes": size})
    if not archives or (not ufs and len(archives) != 28):
        raise ValueError(f"Expected 28 correspondence archives, found {len(archives)}")
    binding = {
        "version": CORRESPONDENCE_VERSION,
        "round": round_number,
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "ceft": {a["path"]: a["sha256"] for a in archives},
        "ufs": sorted(ufs) if ufs else None,
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    import pyarrow.dataset as ds

    sections_ds = ds.dataset(release / "sections.parquet")
    fields = {
        "urn_serial": "NR_URNA_EFETIVADA",
        "load_code": "CD_CARGA_URNA_EFETIVADA",
        "flash_serial": "CD_FLASHCARD_URNA_EFETIVADA",
        "loaded_at": "DT_CARGA_URNA_EFETIVADA",
    }
    rows, issues = [], []
    for archive in archives:
        uf = archive["uf"]
        ours = {
            (r["municipality"], r["zone"], r["section"]): r
            for r in sections_ds.to_table(filter=ds.field("uf") == uf).to_pylist()
        }
        theirs = defaultdict(list)
        with zipfile.ZipFile(ceft_root / archive["path"]) as z:
            names = [n for n in z.namelist() if n.endswith(".csv")]
            if len(names) != 1:
                raise ValueError(f"Expected one CSV in {archive['path']}")
            with z.open(names[0]) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
                for r in reader:
                    if r["CD_PLEITO"] != str(manifest["pleito"]) or r["SG_UF"].lower() != uf:
                        issues.append(
                            {
                                "check": "I9",
                                "kind": "ceft_identity",
                                "uf": uf,
                                "row": {k: r[k] for k in ("CD_PLEITO", "SG_UF")},
                            }
                        )
                        continue
                    key = (
                        r["CD_MUNICIPIO"].zfill(5),
                        r["NR_ZONA"].zfill(4),
                        r["NR_SECAO"].zfill(4),
                    )
                    theirs[key].append(r)
        for key in sorted(set(ours) | set(theirs)):
            base = {"uf": uf, "municipality": key[0], "zone": key[1], "section": key[2]}
            entries, mine = theirs.get(key, []), ours.get(key)
            r = entries[-1] if entries else None
            differs = {}
            if r and mine and mine.get("bu_status") == "decoded":
                effective = {
                    "urn_serial": r["NR_URNA_EFETIVADA"],
                    # CEFT drops leading zeros of the 24-digit load code.
                    "load_code": r["CD_CARGA_URNA_EFETIVADA"].zfill(24),
                    "flash_serial": r["CD_FLASHCARD_URNA_EFETIVADA"].upper().zfill(8),
                    "loaded_at": _stamp(r["DT_CARGA_URNA_EFETIVADA"]),
                }
                differs = {
                    f: {"bu": mine.get(f), "ceft": effective[f]}
                    for f in fields
                    if (mine.get(f) or None) != (effective[f] or None)
                }
                if differs:
                    issues.append(
                        {"check": "I9", "kind": "effective_urn", **base, "fields": differs}
                    )
            if len(entries) > 1:
                issues.append(
                    {"check": "I9", "kind": "ceft_repeated", **base, "rows": len(entries)}
                )
            if not entries and mine:
                issues.append(
                    {"check": "I9", "kind": "no_correspondence", **base, "package": mine["package"]}
                )
            rows.append(
                {
                    **base,
                    "ceft_rows": len(entries),
                    "origin": r["CD_ORIGEM_VOTO"] if r else None,
                    "divergence": (r["TP_DIVERGENCIA"] or None) if r else None,
                    "expected_is_effective": (
                        r["SQ_CORRESPONDENCIA_ESPERADA"] == r["SQ_CORRESPONDENCIA_EFETIVADA"]
                        if r
                        else None
                    ),
                    "in_bu": mine is not None and mine.get("bu_status") == "decoded",
                    "effective_matches_bu_json": json.dumps(sorted(differs), separators=(",", ":")),
                }
            )
    final = output / ".release.tmp"
    final.mkdir()
    _write(final / "sections.parquet", rows, CORRESPONDENCE_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    summary = {
        "sections": len(rows),
        "origin": dict(Counter(str(r["origin"]) for r in rows)),
        "divergence": dict(Counter(str(r["divergence"]) for r in rows)),
        "expected_is_effective": dict(Counter(str(r["expected_is_effective"]) for r in rows)),
        "effective_matches_bu": dict(
            Counter(
                "n/a"
                if not r["in_bu"] or not r["ceft_rows"]
                else "match"
                if r["effective_matches_bu_json"] == "[]"
                else "differs"
                for r in rows
            )
        ),
        "kinds": dict(Counter(f"{i['check']}:{i['kind']}" for i in issues)),
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


# --------------------------------------------------------------------------- I5–I7: logs


LOGS_VERSION = "integrity-logs-v2"
CLOCK_RULES = {
    "R1": "at least one official voting session of the round",
    "R2": "the last official session has a closing reading",
    "R3": "no backward clock step inside official sessions",
    "R4": "no completion outside a vote cycle",
    "R5": "every official session starts on the election date",
    "R6": "official sessions do not overlap",
}
LOG_SECTION_SCHEMA = pa.schema(
    [
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("log", pa.string()),  # semantic | protected_or_unavailable | error
        ("official_sessions", pa.int32()),
        ("i5", pa.string()),  # equal | differs | unavailable
        ("i5_biometric", pa.string()),
        ("i6", pa.string()),
        ("i7_failed_json", pa.string()),
        ("unresolved_cycles", pa.int32()),
    ]
)


def _witness_map(release: Path) -> dict[tuple[str, ...], list[Row]]:
    objects = pq.read_table(
        release / "objects.parquet", columns=["object_sha256", "witnesses_json", "status"]
    ).to_pylist()
    mapping = defaultdict(list)
    for o in objects:
        slim = {"object_sha256": o["object_sha256"], "status": o["status"]}
        for w in json.loads(o["witnesses_json"]):
            mapping[tuple(w)].append(slim)
    return mapping


OFFICIAL_SQL = """
WITH s AS (
    SELECT {columns},
           row_number() OVER (PARTITION BY object_sha256, stream_ordinal, segment_ordinal
                              ORDER BY session_ordinal) AS rank_in_segment
    FROM read_parquet($sessions)
    WHERE session_kind = 'official_vota' AND session_round = $round
)
SELECT s.*, g.first_line_sha256 AS block_start, g.lines AS block_lines
FROM s LEFT JOIN (SELECT object_sha256, stream_ordinal, segment_ordinal, first_line_sha256, lines
                  FROM read_parquet($segments)) g
     USING (object_sha256, stream_ordinal, segment_ordinal)
"""
OFFICIAL_COLUMNS = (
    "object_sha256 stream_ordinal session_ordinal segment_ordinal device_id session_kind "
    "session_round start_reading end_reading closing_reading reading_backsteps "
    "orphan_completions cycles_completed_biometric cycles_completed_manual "
    "cycles_completed_unknown cycles_unresolved_biometric cycles_unresolved_manual "
    "cycles_unresolved_unknown"
).split()


def _official(
    release: Path, digests: Collection[str], round_number: int, memory_limit: str = "1GB"
) -> dict[str, list[Row]]:
    """Official sessions of the round per object, with the block each one starts in."""
    import duckdb

    with duckdb.connect() as db:
        db.execute(f"SET memory_limit = '{memory_limit}'")
        db.execute("SET threads = 2")
        cursor = db.execute(
            OFFICIAL_SQL.format(columns=", ".join(OFFICIAL_COLUMNS)),
            {
                "sessions": str(release / "sessions.parquet"),
                "segments": str(release / "segments.parquet"),
                "round": round_number,
            },
        )
        names = [d[0] for d in cursor.description]
        sessions = defaultdict(list)
        for values in cursor.fetchall():
            s = dict(zip(names, values, strict=True))
            if s["object_sha256"] in digests:
                sessions[s["object_sha256"]].append(s)
    return sessions


I6_SQL = """
WITH w1 AS (
    SELECT object_sha256, array_to_string(unnest(from_json(witnesses_json, '[["VARCHAR"]]')), '/') AS w
    FROM read_parquet($first_objects) WHERE status = 'complete'
), w2 AS (
    SELECT object_sha256, array_to_string(unnest(from_json(witnesses_json, '[["VARCHAR"]]')), '/') AS w
    FROM read_parquet($runoff_objects) WHERE status = 'complete'
), b1 AS (
    SELECT w, device_id, first_line_sha256, lines, fingerprint,
           row_number() OVER (PARTITION BY s.object_sha256, stream_ordinal
                              ORDER BY segment_ordinal DESC) = 1 AS is_last
    FROM read_parquet($first_segments) s JOIN w1 USING (object_sha256)
    WHERE context = 'official_round_1'
), b2 AS (
    SELECT w, device_id, first_line_sha256, lines, fingerprint
    FROM read_parquet($runoff_segments) s JOIN w2 USING (object_sha256)
    WHERE context = 'official_round_1'
), blocks AS (
    SELECT b1.w,
           CASE WHEN b2.w IS NULL THEN 'missing_in_runoff'
                WHEN b1.fingerprint = b2.fingerprint AND b1.lines = b2.lines THEN 'equal'
                WHEN b1.is_last AND b2.lines > b1.lines THEN 'open_prefix_unverified'
                ELSE 'differs' END AS status
    FROM b1 LEFT JOIN b2 ON b1.w = b2.w AND b1.device_id = b2.device_id
                         AND b1.first_line_sha256 = b2.first_line_sha256
    UNION ALL
    SELECT b2.w, 'extra_in_runoff' FROM b2
    WHERE NOT EXISTS (SELECT 1 FROM b1 WHERE b1.w = b2.w AND b1.device_id = b2.device_id
                                         AND b1.first_line_sha256 = b2.first_line_sha256)
), devices AS (
    SELECT coalesce(d1.w, d2.w) AS w, count(d1.w) > 0 AS has_first, count(d2.w) > 0 AS has_runoff,
           count(*) FILTER (WHERE d1.w IS NOT NULL AND d2.w IS NOT NULL) > 0 AS common_device
    FROM (SELECT DISTINCT w, device_id FROM b1) d1
    FULL JOIN (SELECT DISTINCT w, device_id FROM b2) d2 ON d1.w = d2.w AND d1.device_id = d2.device_id
    GROUP BY ALL
)
SELECT d.w, d.has_first, d.has_runoff, d.common_device,
       list(DISTINCT b.status ORDER BY b.status) AS statuses,
       count(*) FILTER (WHERE b.status = 'open_prefix_unverified') AS open_blocks
FROM devices d LEFT JOIN blocks b USING (w) GROUP BY ALL
"""


def round1_statuses(
    runoff: Path, first: Path, memory_limit: str = "1GB"
) -> dict[tuple[str, ...], str]:
    """I6 per section key: round-1 blocks of the runoff log against the round-1 log."""
    import duckdb

    with duckdb.connect() as db:
        db.execute(f"SET memory_limit = '{memory_limit}'")
        db.execute("SET threads = 2")
        rows = db.execute(
            I6_SQL,
            {
                "first_objects": str(first / "objects.parquet"),
                "runoff_objects": str(runoff / "objects.parquet"),
                "first_segments": str(first / "segments.parquet"),
                "runoff_segments": str(runoff / "segments.parquet"),
            },
        ).fetchall()
    out = {}
    for w, has_first, has_runoff, common, statuses, open_blocks in rows:
        if not has_runoff:
            status = "no_round1_block_in_runoff_log"
        elif not has_first:
            status = "no_round1_log_block"
        elif not common:
            status = "different_device"
        else:
            states = set(statuses or [])
            if states == {"equal"}:
                status = "equal"
            elif states == {"equal", "open_prefix_unverified"} and open_blocks == 1:
                status = "equal_closed_open_prefix_unverified"
            elif states == {"open_prefix_unverified"} and open_blocks == 1:
                status = "open_prefix_unverified"
            else:
                status = "+".join(sorted(states))
        out[tuple(w.split("/"))] = status
    return out


def clock_rules(sessions: Sequence[Row], election_date: str) -> list[str]:
    failed = []
    if not sessions:
        return ["R1"]
    ordered = sorted(sessions, key=lambda s: (s["stream_ordinal"], s["session_ordinal"]))
    if ordered[-1]["closing_reading"] is None:
        failed.append("R2")
    if any(s["reading_backsteps"] for s in ordered):
        failed.append("R3")
    if any(s["orphan_completions"] for s in ordered):
        failed.append("R4")
    if any((s["start_reading"] or "")[:10] != election_date for s in ordered):
        failed.append("R5")
    spans = sorted((s["start_reading"], s["end_reading"]) for s in ordered if s["start_reading"])
    if any(b[0] is not None and a[1] is not None and b[0] < a[1] for a, b in zip(spans, spans[1:])):
        failed.append("R6")
    return failed


def run_logs(
    sections_root: str | Path,
    semantic_root: str | Path,
    output: str | Path,
    *,
    semantic_round1: str | Path | None = None,
) -> JSON:
    """I5 (attendance), I6 (round-1 blocks) and I7 (clock and session rules) per section."""
    sections_root = Path(sections_root).expanduser().absolute()
    semantic = Path(semantic_root).expanduser().absolute() / "release"
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    release = sections_root / "release"
    manifest = json.loads((release / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if entry["sha256"] != sha(release / name):
            raise ValueError(f"Section release file changed: {name}")
    semantic_manifest = json.loads((semantic / "manifest.json").read_text())
    for name, entry in semantic_manifest["files"].items():
        if entry["sha256"] != sha(semantic / name):
            raise ValueError(f"Semantic release file changed: {name}")
    round_number, year = manifest["round"], manifest["year"]
    if semantic_manifest["round"] != round_number:
        raise ValueError("Semantic release and section release are different rounds")
    election = election_for_round(round_number, year)
    first = None
    if semantic_round1 is not None:
        first = Path(semantic_round1).expanduser().absolute() / "release"
        if round_number != 2 or json.loads((first / "manifest.json").read_text())["round"] != 1:
            raise ValueError("I6 compares a round-2 release with a round-1 release")
    binding = {
        "version": LOGS_VERSION,
        "round": round_number,
        "year": year,
        "sections_manifest_sha256": sha(release / "manifest.json"),
        "semantic_manifest_sha256": sha(semantic / "manifest.json"),
        "semantic_version": semantic_manifest["version"],
        "semantic_round1_manifest_sha256": sha(first / "manifest.json") if first else None,
        "rules": CLOCK_RULES,
        "copies": "official sessions copied across memories of one urn (same device, block "
        "start and rank in block) count once, as in the section table",
        "protected": "sections without a semantic-pass object (the 596 protected/stress logs, SA "
        "and unpublished logs) are reported as unavailable, never read",
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    sections = pq.read_table(
        release / "sections.parquet", columns=["uf", "municipality", "zone", "section", "package"]
    ).to_pylist()
    restricted = defaultdict(dict)
    president = pq.read_table(
        release / "restricted" / "attendance.parquet",
        columns=["uf", "municipality", "zone", "section", "cargo", "attended", "biometric"],
        filters=[("cargo", "=", 1)],
    )
    for r in president.to_pylist():
        if r["cargo"] == 1:  # president: present in every 2026 BU of both rounds
            restricted[(r["uf"], r["municipality"], r["zone"], r["section"])] = r
    witnesses = _witness_map(semantic)
    digests = {o["object_sha256"] for objs in witnesses.values() for o in objs}
    official = _official(semantic, digests, round_number)
    i6 = round1_statuses(semantic, first) if first is not None else None
    first_witnesses = _witness_map(first) if first is not None else None
    rows, issues = [], []
    for s in sections:
        key = (s["uf"], s["municipality"], s["zone"], s["section"])
        base = dict(zip(("uf", "municipality", "zone", "section"), key, strict=True))
        objects = [o for o in witnesses.get(key, []) if o["status"] == "complete"]
        row = {**base, "i6": None, "i7_failed_json": None, "unresolved_cycles": None}
        if not objects:
            state = "error" if witnesses.get(key) else "protected_or_unavailable"
            rows.append(
                {
                    **row,
                    "log": state,
                    "official_sessions": None,
                    "i5": "unavailable",
                    "i5_biometric": "unavailable",
                }
            )
            continue
        if len(objects) > 1:
            issues.append(
                {"check": "I9", "kind": "several_log_objects", **base, "objects": len(objects)}
            )
        raw = [x for o in objects for x in official.get(o["object_sha256"], [])]
        found, _ = distinct_sessions(raw)  # memory copies of one session count once
        completed = sum(
            x["cycles_completed_biometric"]
            + x["cycles_completed_manual"]
            + x["cycles_completed_unknown"]
            for x in found
        )
        biometric = sum(x["cycles_completed_biometric"] for x in found)
        unresolved = sum(
            x["cycles_unresolved_biometric"]
            + x["cycles_unresolved_manual"]
            + x["cycles_unresolved_unknown"]
            for x in found
        )
        bu = restricted.get(key)
        if bu is None or not found:
            i5 = i5b = "unavailable"
        else:
            i5 = "equal" if completed == bu["attended"] else "differs"
            i5b = (
                "equal"
                if bu["biometric"] is not None and biometric == bu["biometric"]
                else "differs"
                if bu["biometric"] is not None
                else "unavailable"
            )
            if i5 == "differs" or i5b == "differs":
                issues.append(
                    {
                        "check": "I5",
                        "kind": "attendance",
                        **base,
                        "log": {
                            "completed": completed,
                            "biometric": biometric,
                            "unresolved": unresolved,
                            "sessions": len(found),
                            "copies_removed": len(raw) - len(found),
                        },
                        "bu": {"attended": bu["attended"], "biometric": bu["biometric"]},
                    }
                )
        failed = clock_rules(found, election.election_date)
        if failed:
            issues.append(
                {"check": "I7", "kind": "rules", **base, "failed": failed, "sessions": len(found)}
            )
        status6 = None
        if first is not None and i6 is not None and first_witnesses is not None:  # all three
            if not [o for o in first_witnesses.get(key, []) if o["status"] == "complete"]:
                status6 = "round1_log_unavailable"
            else:
                status6 = i6.get(key, "no_round1_block_in_either_log")
            if status6 not in ("equal", "equal_closed_open_prefix_unverified"):
                issues.append({"check": "I6", "kind": status6, **base})
        rows.append(
            {
                **row,
                "log": "semantic",
                "official_sessions": len(found),
                "i5": i5,
                "i5_biometric": i5b,
                "i6": status6,
                "i7_failed_json": json.dumps(failed, separators=(",", ":")),
                "unresolved_cycles": unresolved,
            }
        )
    final = output / ".release.tmp"
    final.mkdir()
    _write(final / "sections.parquet", rows, LOG_SECTION_SCHEMA)
    (final / "discrepancies.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True, separators=(",", ":")) + "\n" for i in issues)
    )
    summary = {
        "sections": len(rows),
        "log": dict(Counter(r["log"] for r in rows)),
        "i5": dict(Counter(r["i5"] for r in rows)),
        "i5_biometric": dict(Counter(r["i5_biometric"] for r in rows)),
        "i6": dict(Counter(str(r["i6"]) for r in rows)),
        "i7": dict(Counter(r["i7_failed_json"] or "n/a" for r in rows)),
        "i7_rule_failures": dict(
            Counter(f for r in rows for f in json.loads(r["i7_failed_json"] or "[]"))
        ),
        "kinds": dict(Counter(f"{i['check']}:{i['kind']}" for i in issues)),
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


def integrity_check_main(argv: Argv = None) -> int:
    parser = argparse.ArgumentParser(
        prog="election-audit integrity-check", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser(
        "sections", help="Run the I1/I3/I9 section pass over one round's bulk archives."
    )
    run.add_argument(
        "--bulk-root", required=True, help="Verified bulk archive root (bulk-download)."
    )
    run.add_argument("--year", type=int, default=2026, choices=(2026,), help="Election year.")
    run.add_argument("--round", type=int, required=True, choices=(1, 2), help="Round.")
    run.add_argument("--output", required=True, help="New output directory.")
    run.add_argument("--workers", type=int, default=4, help="Worker processes.")
    run.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    run.add_argument("--limit", type=int, help="Process at most this many sections.")
    run.add_argument("--resume", action="store_true", help="Resume the same pass.")
    bweb = sub.add_parser("bweb", help="I2: compare BWEB with a finished section release.")
    bweb.add_argument("--sections", required=True, help="Section-pass output root.")
    bweb.add_argument("--bweb-root", required=True, help="Verified BWEB input root.")
    bweb.add_argument("--output", required=True, help="New output directory.")
    bweb.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    bweb.add_argument("--memory-limit", default="1GB", help="DuckDB memory limit per UF.")
    tree = sub.add_parser("hierarchy", help="I4: BWEB section sums against the EA20 hierarchy.")
    tree.add_argument("--bweb-root", required=True, help="Verified BWEB input root.")
    tree.add_argument("--ea20-root", required=True, help="Finished results-hierarchy root.")
    tree.add_argument("--round", type=int, required=True, choices=(1, 2), help="Round.")
    tree.add_argument("--output", required=True, help="New output directory.")
    tree.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    tree.add_argument("--memory-limit", default="2GB", help="DuckDB memory limit.")
    corr = sub.add_parser("correspondence", help="I9: effective urns (CEFT) against the BUs.")
    corr.add_argument("--sections", required=True, help="Section-pass output root.")
    corr.add_argument("--ceft-root", required=True, help="Verified correspondence input root.")
    corr.add_argument("--output", required=True, help="New output directory.")
    corr.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    logs = sub.add_parser("logs", help="I5-I7: semantic-pass sessions against the section release.")
    logs.add_argument("--sections", required=True, help="Section-pass output root (same round).")
    logs.add_argument("--semantic", required=True, help="Phase 21 semantic-pass root (same round).")
    logs.add_argument("--semantic-round1", help="Round-1 semantic-pass root, for I6 on round 2.")
    logs.add_argument("--output", required=True, help="New output directory.")
    prefix = sub.add_parser(
        "prefix", help="I6 re-read: verify round-1 block prefixes line by line (round 2)."
    )
    prefix.add_argument("--logs", required=True, help="Round-2 logs release root (I5-I7).")
    prefix.add_argument("--semantic", required=True, help="Round-2 semantic-pass root.")
    prefix.add_argument("--semantic-round1", required=True, help="Round-1 semantic-pass root.")
    prefix.add_argument("--output", required=True, help="New output directory.")
    prefix.add_argument("--workers", type=int, default=4, help="Worker processes.")
    prefix.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    prefix.add_argument("--resume", action="store_true", help="Resume the same pass.")
    printed = sub.add_parser("printed", help="I8: printed BU copies (QR codes) against the BUs.")
    printed.add_argument(
        "--bulk-root", required=True, help="Verified bulk archive root (bulk-download)."
    )
    printed.add_argument("--cmind", help="CMInd Totalização Paralela input root (raw/*.json).")
    printed.add_argument("--arvor", help="Arvor Totalização paralela input root.")
    printed.add_argument("--output", required=True, help="New output directory.")
    cross = sub.add_parser(
        "ed521-crosscheck", help="Our Ed521 verdicts against DataUrnas-BR's on the same signatures."
    )
    cross.add_argument(
        "--bulk-root", required=True, help="Verified bulk archive root (bulk-download)."
    )
    cross.add_argument("--round", type=int, required=True, choices=(1, 2), help="Round.")
    cross.add_argument("--reference", required=True, help="DataUrnas-BR's parsers/ed521.py.")
    cross.add_argument("--reference-label", required=True, help="Its source, e.g. repo@commit.")
    cross.add_argument("--vectors", required=True, help="ed521rs test-vector directory.")
    cross.add_argument("--output", required=True, help="New output directory.")
    cross.add_argument("--workers", type=int, default=4, help="Worker processes.")
    cross.add_argument("--uf", action="append", help="Restrict to UF (repeatable; lower case).")
    cross.add_argument("--limit", type=int, help="Process at most this many sections.")
    cross.add_argument("--resume", action="store_true", help="Resume the same pass.")
    zer = sub.add_parser("zeresima", help="Z1-Z5: the zerésima in every log against the votes.")
    zer.add_argument("--sections", required=True, help="Section-pass output root (same round).")
    zer.add_argument("--semantic", required=True, help="Semantic-pass v5 root (same round).")
    zer.add_argument("--output", required=True, help="New output directory.")
    zer.add_argument("--memory-limit", default="2GB", help="DuckDB memory limit.")
    args = parser.parse_args(argv)
    if args.command == "zeresima":
        from election_audit.zeresima import run_zeresima

        result = run_zeresima(
            args.sections, args.semantic, args.output, memory_limit=args.memory_limit
        )
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "ed521-crosscheck":
        from election_audit.ed521_crosscheck import run_crosscheck

        result = run_crosscheck(
            args.bulk_root,
            args.round,
            args.output,
            reference=args.reference,
            vectors=args.vectors,
            reference_label=args.reference_label,
            workers=args.workers,
            ufs=[u.lower() for u in args.uf] if args.uf else None,
            limit=args.limit,
            resume=args.resume,
        )
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "printed":
        from election_audit.printed_bu import run_printed

        result = run_printed(args.bulk_root, args.output, cmind=args.cmind, arvor=args.arvor)
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "prefix":
        from election_audit.round1_prefix import run_prefix

        result = run_prefix(
            args.logs,
            args.semantic,
            args.semantic_round1,
            args.output,
            workers=args.workers,
            ufs=[u.lower() for u in args.uf] if args.uf else None,
            resume=args.resume,
        )
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "logs":
        result = run_logs(
            args.sections, args.semantic, args.output, semantic_round1=args.semantic_round1
        )
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "correspondence":
        result = run_correspondence(
            args.sections,
            args.ceft_root,
            args.output,
            ufs=[u.lower() for u in args.uf] if args.uf else None,
        )
        print(json.dumps(result["summary"]))
        return 0
    if args.command == "hierarchy":
        result = run_hierarchy(
            args.bweb_root,
            args.ea20_root,
            args.round,
            args.output,
            ufs=[u.lower() for u in args.uf] if args.uf else None,
            memory_limit=args.memory_limit,
        )
        print(
            json.dumps(
                {k: result[k] for k in ("nodes", "discrepancies", "summary", "differing_measures")}
            )
        )
        return 0
    if args.command == "bweb":
        result = run_bweb(
            args.sections,
            args.bweb_root,
            args.output,
            ufs=[u.lower() for u in args.uf] if args.uf else None,
            memory_limit=args.memory_limit,
        )
        print(json.dumps({k: result[k] for k in ("contests", "sections", "discrepancy_kinds")}))
        return 0
    result = run_sections(
        args.bulk_root,
        args.round,
        args.output,
        year=args.year,
        workers=args.workers,
        ufs=[u.lower() for u in args.uf] if args.uf else None,
        limit=args.limit,
        resume=args.resume,
    )
    print(
        json.dumps(
            {k: result[k] for k in ("sections", "contests", "discrepancies", "discrepancy_kinds")}
        )
    )
    return 0
