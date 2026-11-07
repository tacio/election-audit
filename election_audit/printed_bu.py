"""I8: printed BU copies (QR codes read at the polling station) against the published BUs.

A printed BU carries its content in QR codes (TSE, "QR Code no Boletim de Urna", 2026 manual,
format VRQR 6.0): each ``QRBU:i:n VRQR:v`` code holds a slice of the content followed by
``HASH:h``, the SHA-512 of all content and hashes before it; the last code adds ``ASSI:s``, the
urn's signature over ``SHA-512(h_n)`` (Ed521 on UE2020/UE2022, ECDSA P-521 on UE2013/UE2015),
and two ``QRCE`` codes carry the urn certificate. A copy read from paper by a third party did
not pass through TSE's transmission or totalization.

For every collected copy this module recomputes the hash chain, verifies the urn signature and
the certificate's issuing TSE authority (``urn_pki``), then compares the content field by field
with the binary BU that TSE published for the same section, and the QR certificate with the
hardware certificate of that section's signature file. Collections are third-party and not a
random sample: agreement corroborates the sections covered and nothing else.

Two collections are read: CMInd's Totalização Paralela (public API records with the raw QR
text) and Arvor's Totalização paralela (published CSV with the reassembled content, final
hash, signature and certificate, but not the per-code slices, which are recovered by search).
"""

from __future__ import annotations

import binascii
import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.national_migration import atomic, sha

VERSION = "printed-bu-v1"
PLEITO_ROUND = {3220: 1, 3221: 2}
ELECTION_DATE = {1: "2026-10-04", 2: "2026-10-25"}
QR_LIMIT = 1100  # characters per printed code, header and security fields included
MAX_SPLIT = 3  # codes searched when only the reassembled content is known
ORIGIN = {
    "votacaoUE": "VOTA",
    "votacaoRED": "RED",
    "saMistaMRParcialCedula": "SA",
    "saMistaBUImpressoCedula": "SA",
    "saManual": "SA",
    "saEletronica": "SA",
}
SUMMARY_KEYS = ("APTA", "APTS", "APTT", "CSEC", "NOMI", "LEGC", "BRAN", "NULO", "TOTC")
NOT_IN_BU = ("AGRE", "ORLC", "PROC", "DTPL", "VERC", "MAJO", "PROP")  # printed, no BU field

RECORD_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("source_id", pa.string()),
        ("submitted_at", pa.string()),
        ("uf", pa.string()),
        ("municipality", pa.string()),
        ("zone", pa.string()),
        ("section", pa.string()),
        ("round", pa.int8()),
        ("origin", pa.string()),
        ("qr_codes", pa.int16()),
        ("chain", pa.string()),
        ("signature", pa.string()),
        ("algorithm", pa.string()),
        ("urn_model", pa.string()),
        ("cert_sha256", pa.string()),
        ("cert_issuer", pa.string()),
        ("pki_issuer_signature", pa.string()),
        ("pki_revoked", pa.bool_()),
        ("published_bu", pa.string()),
        ("certificate_matches_bu", pa.bool_()),
        ("contests", pa.int16()),
        ("header_differences", pa.int32()),
        ("contest_differences", pa.int32()),
        ("internal_inconsistencies", pa.int32()),
        ("status", pa.string()),
        ("final_hash", pa.string()),
        ("detail_json", pa.string()),
    ]
)


# --------------------------------------------------------------------------- QR text


def chain(chunks):
    """Cumulative hashes of content slices, as the urn computes them (manual 1.6.1)."""
    accumulated, hashes = "", []
    for data in chunks:
        message = f"{accumulated} {data}" if accumulated else data
        value = hashlib.sha512(message.encode()).hexdigest().upper()
        hashes.append(value)
        accumulated = f"{message} HASH:{value}"
    return hashes


def split_search(content, final, max_parts=MAX_SPLIT):
    """Content slices (cut at spaces) whose chain ends in ``final``, or None."""
    if chain([content])[-1] == final:
        return [content]
    spaces = [m.start() for m in re.finditer(" ", content)]

    def search(start, parts_left, chunks):
        if parts_left == 1:
            candidate = [*chunks, content[start:]]
            return candidate if chain(candidate)[-1] == final else None
        for cut in spaces:
            if cut <= start or cut - start > QR_LIMIT:
                continue
            found = search(cut + 1, parts_left - 1, [*chunks, content[start:cut]])
            if found:
                return found
        return None

    for parts in range(2, max_parts + 1):
        found = search(0, parts, [])
        if found:
            return found
    return None


def parse_codes(text):
    """Printed codes of one BU from raw QR text: content slices, hashes, signature, cert."""
    text = " ".join(text.split())
    pieces = re.split(r"(?=\bQR(?:BU|CE):\d+:\d+\b)", text)
    data, certificate, errors = {}, {}, []
    totals = {"QRBU": set(), "QRCE": set()}
    for piece in pieces:
        match = re.match(r"(QRBU|QRCE):(\d+):(\d+) ?(.*)$", piece.strip())
        if not match:
            if piece.strip():
                errors.append("text_outside_codes")
            continue
        kind, index, total, body = match[1], int(match[2]), int(match[3]), match[4]
        totals[kind].add(total)
        target = data if kind == "QRBU" else certificate
        if index in target:
            if target[index] != body:
                errors.append(f"{kind.lower()}_{index}_read_twice_differently")
            continue
        target[index] = body
    for kind, target in (("QRBU", data), ("QRCE", certificate)):
        if len(totals[kind]) > 1:
            errors.append(f"{kind.lower()}_totals_disagree")
        expected = max(totals[kind]) if totals[kind] else 0
        missing = sorted(set(range(1, expected + 1)) - set(target))
        if missing:
            errors.append(f"{kind.lower()}_missing_{'.'.join(map(str, missing))}")
    chunks, printed, signature = [], [], None
    for index in sorted(data):
        body = data[index]
        match = re.match(r"VRQR:(\S+) (.*?) HASH:([0-9A-F]+)(?: ASSI:([0-9A-F]+))?$", body)
        if not match:
            errors.append(f"qrbu_{index}_malformed")
            continue
        chunks.append(match[2])
        printed.append(match[3])
        signature = match[4] or signature
    cert_hex, ids = "", set()
    for index in sorted(certificate):
        fields = dict(f.split(":", 1) for f in certificate[index].split(" ") if ":" in f)
        cert_hex += fields.get("CERT", "")
        ids.add((fields.get("IDUE"), fields.get("MDUE")))
    if len(ids) > 1:
        errors.append("qrce_urn_disagrees")
    urn, model = next(iter(ids)) if len(ids) == 1 else (None, None)
    return {
        "chunks": chunks,
        "printed_hashes": printed,
        "final_hash": printed[-1] if printed else None,
        "signature": signature,
        "cert": binascii.unhexlify(cert_hex) if cert_hex else None,
        "cert_urn": urn,
        "cert_model": model,
        "qr_codes": len(data),
        "errors": errors,
    }


def load_certificate(raw):
    """Urn certificate from QRCE bytes: DER on UE2013/UE2015 (maybe padded), PEM otherwise."""
    from cryptography import x509

    if not raw:
        return None
    try:
        if raw[:2] == b"\x30\x82":
            return x509.load_der_x509_certificate(raw[: 4 + int.from_bytes(raw[2:4], "big")])
        match = re.search(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", raw, re.S)
        return x509.load_pem_x509_certificate(match[0]) if match else None
    except ValueError:
        return None


def verify_signature(certificate, final_hash, signature):
    """(algorithm, verdict) for the urn's signature over SHA-512 of the final hash."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding

    from election_audit import ed521
    from election_audit.integrity_checks import Ed521Verifier

    if certificate is None or not final_hash or not signature:
        return None, "unverifiable"
    digest, value = bytes.fromhex(final_hash), bytes.fromhex(signature)
    key = ed521.certificate_public_key(certificate.public_bytes(Encoding.DER))
    if key is not None:
        return "ed521", "verified" if Ed521Verifier(key)(digest, value) else "failed"
    public = certificate.public_key()
    if not isinstance(public, ec.EllipticCurvePublicKey) or public.curve.name != "secp521r1":
        return "unsupported", "unverifiable"
    try:
        public.verify(value, digest, ec.ECDSA(hashes.SHA512()))
        return "ecdsa-p521", "verified"
    except InvalidSignature, ValueError:
        return "ecdsa-p521", "failed"


# --------------------------------------------------------------------------- content


def parse_content(content):
    """Printed content as header fields and per (election, office) contests."""
    header, elections, unknown = {}, {}, []
    election = contest = party = number = None
    for token in content.split(" "):
        if ":" not in token:
            unknown.append(token)
            continue
        key, value = token.split(":", 1)
        if key == "IDEL":
            election = elections.setdefault(int(value), {"fields": {}, "contests": {}})
            contest = party = None
        elif election is None:
            if key == "HICA":
                header.setdefault("HICA", []).append(value)
            else:
                header.setdefault(key, value)
        elif key == "CARG":
            contest = {"fields": {}, "entries": Counter(), "parties": {}}
            election["contests"][int(value)] = contest
            party = None
        elif contest is None:
            election["fields"][key] = value
        elif key == "PART":
            number = int(value)
            party = contest["parties"].setdefault(number, {"nominal": 0})
        elif key.isdigit():
            contest["entries"][("N", int(key))] += int(value)
            if party is not None:
                party["nominal"] += int(value)
        elif key in ("LEGP", "TOTP") and party is not None:
            party[key] = int(value)
            if key == "LEGP" and int(value):
                contest["entries"][("L", number)] += int(value)
        elif key in ("TIPO", "VERC"):
            contest["fields"][key] = value
        elif key in SUMMARY_KEYS:
            party = None
            contest["fields"][key] = int(value)
            if key in ("BRAN", "NULO", "CSEC") and int(value):
                cls = {"BRAN": "B", "NULO": "X", "CSEC": "S"}[key]
                contest["entries"][(cls, 0)] += int(value)
        else:
            unknown.append(token)
    return {"header": header, "elections": elections, "unknown": unknown}


def internal_inconsistencies(parsed):
    """Printed totals that disagree with the printed counts they summarize."""
    issues = []
    for idel, election in parsed["elections"].items():
        for cargo, contest in election["contests"].items():
            f, e = contest["fields"], contest["entries"]
            nominal = sum(v for (k, _), v in e.items() if k == "N")
            party = sum(v for (k, _), v in e.items() if k == "L")
            sums = {
                "NOMI": nominal,
                "LEGC": party,
                "TOTC": nominal + party + f.get("BRAN", 0) + f.get("NULO", 0) + f.get("CSEC", 0),
            }
            for key, value in sums.items():
                if key in f and f[key] != value:
                    issues.append({"election": idel, "office": cargo, key: [f[key], value]})
            for number, p in contest["parties"].items():
                if "TOTP" in p and p["TOTP"] != p["nominal"] + p.get("LEGP", 0):
                    issues.append({"election": idel, "office": cargo, "party": number})
    return issues


def bu_header(bu, uf):
    """Header fields of a decoded binary BU, in the printed representation."""
    section = bu["identificacaoSecao"]
    load = bu["urna"]["correspondenciaResultado"]["carga"]
    first = bu["resultadosVotacaoPorEleicao"][0]
    kind, data = bu["dadosSecaoSA"]
    detail = bu.get("detalhamentoComparecimento") or {}
    fields = {
        "ORIG": ORIGIN.get(bu["urna"]["tipoArquivo"]),
        "PLEI": str(bu["cabecalho"]["idEleitoral"][1]),
        "TURN": str(PLEITO_ROUND.get(bu["cabecalho"]["idEleitoral"][1])),
        "FASE": {"oficial": "O", "simulado": "S", "treinamento": "T"}.get(bu["fase"]),
        "UNFE": uf.upper(),
        "MUNI": str(section["municipioZona"]["municipio"]),
        "ZONA": str(section["municipioZona"]["zona"]),
        "SECA": str(section["secao"]),
        "IDUE": str(load["numeroInternoUrna"]),
        "IDCA": load["codigoCarga"],
        "HIQT": str(len(bu["historicoCodigosCarga"])),
        "HICA": [f"{i}:{c}" for i, c in enumerate(bu["historicoCodigosCarga"], 1)],
        "VERS": bu["urna"]["versaoVotacao"].split(" ")[0],
        "LOCA": str(section["local"]),
        "APTO": str(first["qtdEleitoresAptos"]),
        "APTS": str(first.get("qtdEleitoresAptosSecao")),
        "APTT": str(first.get("qtdEleitoresAptosTTE")),
        "COMP": str(bu["qtdEleitoresCompareceram"]),
        "FALT": str(first["qtdEleitoresAptos"] - bu["qtdEleitoresCompareceram"]),
        "HBBM": str(detail.get("qtdEleitoresHabilitadosPorBiometria")),
        "HBBG": str(detail.get("qtdEleitoresHabilitadosPorBiografia")),
        "HBSB": str(detail.get("qtdEleitoresCompareceramSemBiometria")),
    }
    if kind == "dadosSecao":
        for prefix, stamp in (("AB", "dataHoraAbertura"), ("FC", "dataHoraEncerramento")):
            day, time_ = data[stamp].split("T")
            fields[f"DT{prefix}"], fields[f"HR{prefix}"] = day, time_
    else:
        fields["JUNT"], fields["TURM"] = str(data["juntaApuradora"]), str(data["turmaApuradora"])
    if kind == "dadosSA" or fields["ORIG"] == "RED":
        day, time_ = bu["dataHoraEmissao"].split("T")
        fields["DTEM"], fields["HREM"] = day, time_
    return fields


def _number(value):
    """Printed numbers drop leading zeros; codes such as IDCA keep them (compare as text)."""
    return str(int(value)) if isinstance(value, str) and value.isdigit() else value


def compare(parsed, bu, uf):
    """Header and contest differences between printed content and the binary BU."""
    from election_audit.integrity_checks import bu_contests

    expected = bu_header(bu, uf)
    header = []
    for key, printed in parsed["header"].items():
        if key in NOT_IN_BU:
            continue
        if key not in expected:
            header.append({"field": key, "printed": printed, "bu": "no_field"})
        elif key in ("IDCA", "HICA"):
            if printed != expected[key]:
                header.append({"field": key, "printed": printed, "bu": expected[key]})
        elif _number(printed) != _number(expected[key]):
            header.append({"field": key, "printed": printed, "bu": expected[key]})
    for key in ("COMP", "IDUE", "IDCA", "MUNI", "ZONA", "SECA"):
        if key not in parsed["header"]:
            header.append({"field": key, "printed": None, "bu": expected.get(key)})
    contests = []
    published = bu_contests(bu)
    eligible = {e["idEleicao"]: e["qtdEleitoresAptos"] for e in bu["resultadosVotacaoPorEleicao"]}
    printed_keys = set()
    for idel, election in parsed["elections"].items():
        for cargo, contest in election["contests"].items():
            key = (idel, cargo)
            printed_keys.add(key)
            other = published.get(key)
            if other is None:
                contests.append({"election": idel, "office": cargo, "bu": "no_contest"})
                continue
            printed_entries = {k: v for k, v in contest["entries"].items() if v}
            bu_entries = {k: v for k, v in other["entries"].items() if v}
            if printed_entries != bu_entries:
                keys = sorted(set(printed_entries) | set(bu_entries))
                contests.append(
                    {
                        "election": idel,
                        "office": cargo,
                        "entries": [
                            [k[0], k[1], printed_entries.get(k, 0), bu_entries.get(k, 0)]
                            for k in keys
                            if printed_entries.get(k, 0) != bu_entries.get(k, 0)
                        ],
                    }
                )
            apta = contest["fields"].get("APTA")
            if apta is not None and apta != eligible.get(idel):
                contests.append(
                    {"election": idel, "office": cargo, "APTA": [apta, eligible.get(idel)]}
                )
    for key in sorted(set(published) - printed_keys):
        if any(published[key]["entries"].values()):
            contests.append({"election": key[0], "office": key[1], "printed": "no_contest"})
    return header, contests


# --------------------------------------------------------------------------- sources


def read_cmind(root):
    """CMInd records (``raw/bu_*.json`` from the public API) and the files read."""
    root = Path(root)
    records, files = [], {}
    for path in sorted((root / "raw").glob("bu_*.json")):
        files[f"raw/{path.name}"] = sha(path)
        data = json.loads(path.read_text())["data"]
        codes = parse_codes(data["qr_raw"])
        records.append(
            {
                "source": "cmind",
                "source_id": str(data["id"]),
                "submitted_at": data.get("submitted_em") or data.get("submetido_em"),
                "simulated": str(data.get("is_simulated")) not in ("0", "False", "None"),
                **codes,
            }
        )
    return records, files


def read_arvor(root):
    """Arvor records (``totalizacao_dados/bus.csv``, checked against its manifest)."""
    root = Path(root) / "totalizacao_dados"
    manifest = json.loads((root / "manifest.json").read_text())
    path = root / "bus.csv"
    digest = sha(path)
    if manifest["arquivos"]["bus.csv"]["sha256"] != digest:
        raise ValueError("Arvor bus.csv does not match its manifest")
    csv.field_size_limit(10**8)
    records = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            chunks = split_search(row["conteudo"], row["hash_final"])
            records.append(
                {
                    "source": "arvor",
                    "source_id": row["id"],
                    "submitted_at": row["recebido_em"],
                    "simulated": row["fase"] != "O",
                    "chunks": chunks or [row["conteudo"]],
                    "chunks_recovered": chunks is not None,
                    "printed_hashes": None,
                    "final_hash": row["hash_final"],
                    "signature": row["assi"],
                    "cert": binascii.unhexlify(row["cert_hex"]) if row["cert_hex"] else None,
                    "cert_urn": row["idue"],
                    "cert_model": row["mdue"],
                    "qr_codes": len(chunks) if chunks else None,
                    "errors": [],
                }
            )
    return records, {
        "totalizacao_dados/bus.csv": digest,
        "totalizacao_dados/manifest.json": sha(root / "manifest.json"),
    }


# --------------------------------------------------------------------------- published BUs


class Published:
    """Binary BUs and signature files of the bulk archives, opened per (round, UF)."""

    def __init__(self, bulk_root):
        self.root = Path(bulk_root)
        self.archives, self.handles = {}, {}

    def archive(self, round_number, uf):
        from election_audit.semantic_pass import verified_bulk_archives

        key = (round_number, uf)
        if key not in self.handles:
            self.close()  # one central directory in memory at a time (São Paulo's is ~0.4 GB)
            found = verified_bulk_archives(self.root, 2026, round_number, {uf})
            self.archives[key] = found[0]
            self.handles = {key: zipfile.ZipFile(self.root / found[0]["path"])}
        return self.handles[key]

    def section(self, round_number, uf, municipality, zone, section):
        """(BU bytes, signature-file bytes, package) or None when not published."""
        pleito = 3220 if round_number == 1 else 3221
        prefix = f"o{pleito:05d}{uf}{municipality}{zone}{section}-"
        handle = self.archive(round_number, uf)
        names = handle.NameToInfo
        for bu, vsc, package in (("bu.dat", "vota.vsc", "urn"), ("busa.dat", "sa.vsc", "sa")):
            if prefix + bu in names:
                signature = handle.read(prefix + vsc) if prefix + vsc in names else None
                return handle.read(prefix + bu), signature, package
        return None

    def close(self):
        for handle in self.handles.values():
            handle.close()
        self.handles = {}

    def bindings(self):
        return {
            f"{r}:{uf}": {"path": a["path"], "sha256": a["sha256"], "bytes": a["bytes"]}
            for (r, uf), a in sorted(self.archives.items())
        }


def hardware_certificate(raw):
    """DER SHA-256 of the urn hardware certificate in a signature file, or None."""
    from cryptography.hazmat.primitives.serialization import Encoding

    from election_audit.integrity_checks import SIGNATURE_TYPE, _key_info, signature_codec

    if raw is None:
        return None
    entity = signature_codec().decode(SIGNATURE_TYPE, raw)
    certificate = load_certificate(_key_info(entity["assinaturaHW"])[1])
    return (
        hashlib.sha256(certificate.public_bytes(Encoding.DER)).hexdigest() if certificate else None
    )


# --------------------------------------------------------------------------- pass


def check_record(record, published):
    """One output row for a collected printed BU."""
    from cryptography.hazmat.primitives.serialization import Encoding

    from election_audit import urn_pki
    from election_audit.integrity_checks import bu_codec

    content = " ".join(record["chunks"])
    parsed = parse_content(content)
    h = parsed["header"]
    detail = {"errors": list(record["errors"])}
    pleito = int(h["PLEI"]) if h.get("PLEI", "").isdigit() else None
    round_number = PLEITO_ROUND.get(pleito)
    key = {
        "uf": (h.get("UNFE") or "").lower() or None,
        "municipality": h.get("MUNI", "").zfill(5) or None,
        "zone": h.get("ZONA", "").zfill(4) or None,
        "section": h.get("SECA", "").zfill(4) or None,
    }
    computed = chain(record["chunks"]) if record["chunks"] else []
    if not computed or (record.get("chunks_recovered") is False):
        chain_status = "slices_not_recovered" if record["chunks"] else "no_content"
    elif record["printed_hashes"] is not None and computed != record["printed_hashes"]:
        chain_status = "failed"
        detail["chain_failed_codes"] = [
            i + 1 for i, (a, b) in enumerate(zip(computed, record["printed_hashes"])) if a != b
        ]
    else:
        chain_status = "ok" if computed[-1] == record["final_hash"] else "failed"
    certificate = load_certificate(record["cert"])
    algorithm, signature = verify_signature(certificate, record["final_hash"], record["signature"])
    pki = urn_pki.check_certificate(certificate, ELECTION_DATE.get(round_number))
    cert_sha = (
        hashlib.sha256(certificate.public_bytes(Encoding.DER)).hexdigest() if certificate else None
    )
    if record["cert_urn"] and h.get("IDUE") and _number(record["cert_urn"]) != _number(h["IDUE"]):
        detail["errors"].append("qrce_urn_differs_from_content")
    detail["unknown_tokens"] = parsed["unknown"][:20]
    issues = internal_inconsistencies(parsed)
    if issues:
        detail["internal"] = issues
    row = {
        "source": record["source"],
        "source_id": record["source_id"],
        "submitted_at": record["submitted_at"],
        **key,
        "round": round_number,
        "origin": h.get("ORIG"),
        "qr_codes": record["qr_codes"],
        "chain": chain_status,
        "signature": signature,
        "algorithm": algorithm,
        "urn_model": record["cert_model"],
        "cert_sha256": cert_sha,
        "cert_issuer": urn_pki._cn(certificate.issuer) if certificate else None,
        "pki_issuer_signature": pki["pki_issuer_signature"],
        "pki_revoked": pki["pki_revoked"],
        "published_bu": None,
        "certificate_matches_bu": None,
        "contests": sum(len(e["contests"]) for e in parsed["elections"].values()),
        "header_differences": None,
        "contest_differences": None,
        "internal_inconsistencies": len(issues),
        "final_hash": record["final_hash"],
    }
    authentic = chain_status == "ok" and signature == "verified" and not detail["errors"]
    if record["simulated"] or h.get("FASE") != "O" or round_number is None:
        row["status"] = "out_of_scope"
    elif not all(key.values()):
        row["status"] = "unreadable"
    else:
        found = published.section(round_number, key["uf"], *list(key.values())[1:])
        if found is None:
            row["published_bu"] = "absent"
            row["status"] = "no_published_bu" if authentic else "not_authentic"
        else:
            raw, vsc, package = found
            row["published_bu"] = package
            parser = bu_codec()
            envelope = parser.decode("EntidadeEnvelopeGenerico", raw)
            bu = parser.decode("EntidadeBoletimUrna", envelope["conteudo"])
            header, contests = compare(parsed, bu, key["uf"])
            bu_cert = hardware_certificate(vsc)
            row["certificate_matches_bu"] = None if bu_cert is None else bu_cert == cert_sha
            row["header_differences"], row["contest_differences"] = len(header), len(contests)
            if header or contests:
                detail["header"], detail["contests"] = header, contests
            if not authentic:
                row["status"] = "not_authentic"
            elif header or contests:
                row["status"] = "differs"
            elif row["certificate_matches_bu"] is False:
                row["status"] = "equal_content_other_certificate"
            else:
                row["status"] = "equal"
    row["detail_json"] = json.dumps(detail, separators=(",", ":"), sort_keys=True)
    return row


def run_printed(bulk_root, output, *, cmind=None, arvor=None):
    """I8 over the given collections; writes ``release/printed.parquet`` and its manifest."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if not cmind and not arvor:
        raise ValueError("Give at least one collection (--cmind or --arvor)")
    records, inputs = [], {}
    for name, root, reader in (("cmind", cmind, read_cmind), ("arvor", arvor, read_arvor)):
        if root:
            found, files = reader(root)
            records += found
            inputs[name] = {"root": str(Path(root).resolve()), "files": files}

    def archive_order(record):
        head = record["chunks"][0] if record["chunks"] else ""
        found = [re.search(rf"\b{k}:(\S+)", head) for k in ("PLEI", "UNFE")]
        return tuple(m[1] if m else "" for m in found)

    published = Published(bulk_root)
    try:
        rows = [check_record(r, published) for r in sorted(records, key=archive_order)]
    finally:
        published.close()
    rows.sort(key=lambda r: (r["source"], int(r["source_id"]) if r["source_id"].isdigit() else 0))
    staging = output / "release.partial"
    staging.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=RECORD_SCHEMA), staging / "printed.parquet")
    summary = summarize(rows)
    result = {
        "version": VERSION,
        "inputs": inputs,
        "bulk_archives": published.bindings(),
        "summary": summary,
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(staging.iterdir())
        },
    }
    atomic(staging / "manifest.json", result)
    shutil.move(staging, output / "release")
    return result


def summarize(rows):
    in_scope = [r for r in rows if r["status"] not in ("out_of_scope",)]
    sections = {}
    for r in in_scope:
        key = (r["round"], r["uf"], r["municipality"], r["zone"], r["section"])
        sections.setdefault(key, []).append(r)
    agreeing = sum(1 for copies in sections.values() if len({c["final_hash"] for c in copies}) == 1)
    return {
        "records": len(rows),
        "status": dict(Counter(r["status"] for r in rows)),
        "by_source_round_status": {
            f"{s}:{r}:{st}": n
            for (s, r, st), n in sorted(
                Counter((r["source"], r["round"], r["status"]) for r in rows).items(),
                key=str,
            )
        },
        "sections": len(sections),
        "sections_per_round": dict(Counter(k[0] for k in sections)),
        "sections_with_several_copies": sum(1 for c in sections.values() if len(c) > 1),
        "sections_whose_copies_share_one_final_hash": agreeing,
        "chain": dict(Counter(r["chain"] for r in rows)),
        "signature": dict(Counter(r["signature"] for r in rows)),
        "pki_issuer_signature": dict(Counter(str(r["pki_issuer_signature"]) for r in rows)),
        "certificate_matches_bu": dict(Counter(str(r["certificate_matches_bu"]) for r in rows)),
        "internal_inconsistencies": sum(r["internal_inconsistencies"] for r in rows),
        "contests_compared": sum(r["contests"] for r in rows if r["status"] == "equal"),
    }
