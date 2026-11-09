"""Phase 20 section pass: real AC files pass, tampering is caught, logs are only hashed."""

import contextlib
import copy
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parent / "fixtures/integrity-2026"
PREFIX = "o03221ac0101500020088"
ITEM: dict[str, Any] = {
    "archive": "files/bu_imgbu_logjez_rdv_vscmr_2026_2t_AC.zip",
    "key": ["ac", "01015", "0002", "0088"],
    "members": {
        k: f"{PREFIX}-{s}"
        for k, s in (
            ("bu", "bu.dat"),
            ("rdv", "rdv.dat"),
            ("imgbu", "imgbu.dat"),
            ("vsc", "vota.vsc"),
            ("log", "log.jez"),
        )
    },
    "package": "urn",
}


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class SectionCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        from election_audit import integrity_checks as ic

        self.ic = ic
        self.provenance = json.loads((FIXTURE / "provenance.json").read_text())
        self.blobs = {k: (FIXTURE / ITEM["members"][k]).read_bytes() for k in ("bu", "rdv", "vsc")}
        self.published = {
            k: bytes.fromhex(self.provenance["members"][ITEM["members"][k]]["sha512"])
            for k in ITEM["members"]
        }

    def check(
        self, blobs: dict[str, bytes] | None = None, published: dict[str, bytes] | None = None
    ) -> tuple[Any, ...]:
        return self.ic.check_section(ITEM, blobs or self.blobs, published or self.published, 3221)

    def test_real_section_passes_every_check(self) -> None:
        row, contests, restricted, issues = self.check()
        self.assertEqual(issues, [])
        self.assertEqual((row["vsc_status"], row["bu_status"], row["rdv_status"]), ("decoded",) * 3)
        self.assertEqual((row["i1_hash_mismatches"], row["i1_published_unlisted"]), (0, 0))
        self.assertEqual((row["i1_listed"], row["i1_listed_published"]), (11, 4))
        self.assertTrue(row["i1_sw_self_hash"] and row["i1_hw_self_hash"] and row["i1_lists_agree"])
        self.assertEqual((row["hw_algorithm"], row["hw_bits"]), ("eddsa", 521))
        self.assertEqual(row["i1_signature_math"], "verified")
        self.assertEqual((row["i1_file_signatures_ok"], row["i1_file_signatures_failed"]), (4, 0))
        self.assertEqual((row["chain_signature_ok"], row["chain_signature_failed"]), (2, 0))
        self.assertEqual((row["cert_issuer"], row["cert_valid_at_election"]), ("AC UE2022", None))
        self.assertEqual((row["pki_issuer_signature"], row["pki_revoked"]), ("verified", False))
        self.assertEqual(row["equipment"], "ue2022/eddsa")
        self.assertTrue(row["key_set"].isdigit())
        self.assertEqual((row["chain_ok"], row["chain_failed"], row["i3_equal"]), (2, 0, 2))
        self.assertEqual(
            [(c["election"], c["cargo"], c["i3"]) for c in contests],
            [(6258, 1, "equal"), (6260, 3, "equal")],
        )
        self.assertTrue(all(c["bu_digest"] == c["rdv_digest"] for c in contests))
        # Release rows carry no counts; attendance stays in the restricted rows.
        self.assertFalse({"attendance", "bu_votes", "eligible"} & (set(row) | set(contests[0])))
        self.assertEqual({r["attendance"] for r in restricted}, {r["bu_votes"] for r in restricted})

    def test_a_changed_file_hash_is_named(self) -> None:
        published = dict(self.published, log=hashlib.sha512(b"other bytes").digest())
        row, _, _, _ = self.check(published=published)
        self.assertEqual(row["i1_hash_mismatches"], 1)
        self.assertEqual(json.loads(row["i1_detail_json"])["mismatched"], [ITEM["members"]["log"]])

    def test_a_changed_vote_count_breaks_the_chain_and_the_recount(self) -> None:
        from election_audit.binary_bu import codec

        parser = codec()
        envelope = parser.decode("EntidadeEnvelopeGenerico", self.blobs["bu"])
        bu = parser.decode("EntidadeBoletimUrna", envelope["conteudo"])
        changed = copy.deepcopy(bu)
        rows = changed["resultadosVotacaoPorEleicao"][0]["resultadosVotacao"][0][
            "totaisVotosCargo"
        ][0]["votosVotaveis"]
        rows[0]["quantidadeVotos"] += 1
        rows[1]["quantidadeVotos"] -= 1  # totals still add up
        envelope["conteudo"] = parser.encode("EntidadeBoletimUrna", changed)
        blobs = dict(self.blobs, bu=parser.encode("EntidadeEnvelopeGenerico", envelope))
        row, contests, _, issues = self.check(blobs=blobs)
        kinds = sorted(i["kind"] for i in issues)
        self.assertEqual(kinds, ["bu_chain", "rdv_recount"])
        self.assertEqual((row["chain_failed"], row["i3_differ"]), (1, 1))
        self.assertEqual(contests[0]["bu_accounting"], "equal")
        # The file no longer matches its signed hash either.
        published = dict(self.published, bu=hashlib.sha512(blobs["bu"]).digest())
        row, _, _, _ = self.check(blobs=blobs, published=published)
        self.assertEqual(row["i1_hash_mismatches"], 1)

    def test_corrupt_files_are_recorded_not_raised(self) -> None:
        row, contests, _, _ = self.check(blobs={"bu": b"\x30\x03xyz", "rdv": b"", "vsc": b"junk"})
        self.assertEqual((row["bu_status"], row["rdv_status"], row["vsc_status"]), ("error",) * 3)
        self.assertEqual(contests, [])

    def ecdsa_vsc(self, files: Mapping[str, bytes], tamper: bool = False) -> bytes:
        """A signature file in the observed 2026 layout, signed with a fresh P-521 key."""
        import datetime

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP521R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AC URNA")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ueao00000001")]))
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2030, 1, 1))
            .sign(key, hashes.SHA512())
        )

        def signed(digest: bytes) -> dict[str, Any]:
            return {
                "tamanho": 1,
                "hash": digest,
                "assinatura": key.sign(digest, ec.ECDSA(hashes.SHA512())),
            }

        codec = self.ic.signature_codec()
        content = codec.encode(
            "Assinatura",
            {
                "arquivosAssinados": [
                    {"nomeArquivo": n, "assinatura": signed(hashlib.sha512(b).digest())}
                    for n, b in files.items()
                ]
            },
        )
        auto = signed(hashlib.sha512(content).digest())
        if tamper:
            auto["assinatura"] = key.sign(b"other", ec.ECDSA(hashes.SHA512()))

        def side(algorithm: str, certificate: Any = None) -> dict[str, Any]:
            part = {
                "dataHoraCriacao": "20261025T150320",
                "versao": 2,
                "autoAssinado": {
                    "usuario": {"nomeUsuario": "ueao00000001", "serial": 1},
                    "algoritmoHash": {"algoritmo": "sha512"},
                    "algoritmoAssinatura": {"algoritmo": algorithm, "bits": 521},
                    "assinatura": auto,
                },
                "conteudoAutoAssinado": content,
            }
            part["informacaoChave"] = (
                ("certificadoDigital", certificate)
                if certificate
                else ("tagChaves", "202609110000")
            )
            return part

        return codec.encode(
            self.ic.SIGNATURE_TYPE,
            {
                "assinaturaSW": side("cepesc"),
                "assinaturaHW": side(
                    "ecdsa", cert.public_bytes(serialization.Encoding.DER) + b"\x00"
                ),
                "origemAssinaturaHW": {
                    "modeloEquipamento": "ue2015",
                    "algoritmoAssinatura": "ecdsa",
                },
            },
        )

    def test_ecdsa_urn_signatures_are_verified(self) -> None:
        files = {"o1-bu.dat": b"bu bytes", "o1-log.jez": b"log bytes"}
        published = {n: hashlib.sha512(b).digest() for n, b in files.items()}
        row, verify = self.ic.check_signatures(self.ecdsa_vsc(files), published, "2026-10-25")
        assert verify is not None
        self.assertEqual((row["i1_signature_math"], row["i1_file_signatures_ok"]), ("verified", 2))
        self.assertEqual((row["cert_issuer"], row["cert_valid_at_election"]), ("AC URNA", True))
        self.assertTrue(verify(published["o1-bu.dat"], b"\x30\x00") is False)
        row, _ = self.ic.check_signatures(
            self.ecdsa_vsc(files, tamper=True), published, "2026-10-25"
        )
        self.assertEqual(row["i1_signature_math"], "failed")
        changed = dict(published, **{"o1-log.jez": hashlib.sha512(b"other").digest()})
        row, _ = self.ic.check_signatures(self.ecdsa_vsc(files), changed, "2026-10-25")
        self.assertEqual((row["i1_file_signatures_ok"], row["i1_file_signatures_failed"]), (1, 1))


class Ed521Tests(unittest.TestCase):
    """DOC-ICP-01.01 E-521 arithmetic and signatures, with no optional dependency."""

    def test_base_point_has_order_l_and_lies_on_the_curve(self) -> None:
        from election_audit import ed521

        x, y = ed521.BASE_X, ed521.BASE_Y
        self.assertEqual((x * x + y * y - 1 - ed521.D * x * x * y * y) % ed521.P, 0)
        identity = ed521._multiply(ed521.L, ed521.BASE)
        self.assertTrue(ed521._equal(identity, ed521._IDENTITY))
        self.assertFalse(ed521._equal(ed521._multiply(ed521.L - 1, ed521.BASE), ed521._IDENTITY))
        self.assertEqual(ed521.decode(ed521.encode(ed521.BASE)), ed521.BASE)

    def test_fast_multiplication_agrees_with_double_and_add(self) -> None:
        import random

        from election_audit import ed521

        point = ed521._multiply(123456789, ed521.BASE)
        self.assertTrue(ed521._equal(ed521._double(point), ed521._add(point, point)))
        rng = random.Random(20261106)
        scalars = [0, 1, 15, 16, ed521.L - 1] + [rng.randrange(ed521.L) for _ in range(6)]
        for scalar in scalars:
            with self.subTest(scalar=scalar):
                expected = ed521._multiply(scalar, ed521.BASE)
                self.assertTrue(ed521._equal(ed521._base_multiply(scalar), expected))
                self.assertTrue(ed521._equal(ed521._fast_multiply(scalar, ed521.BASE), expected))
                other = ed521._multiply(scalar, point)
                self.assertTrue(ed521._equal(ed521._fast_multiply(scalar, point), other))

    def test_sign_verify_round_trip(self) -> None:
        from election_audit import ed521

        seed = bytes(range(66))
        key, message = ed521.public_key(seed), b"boletim de urna"
        signature = ed521.sign(seed, message)
        self.assertEqual(len(signature), 132)
        self.assertTrue(ed521.verify(key, signature, message))
        self.assertFalse(ed521.verify(key, signature, message + b"!"))
        self.assertFalse(ed521.verify(ed521.public_key(bytes(66)), signature, message))
        changed = bytearray(signature)
        changed[70] ^= 1
        self.assertFalse(ed521.verify(key, bytes(changed), message))
        too_large = signature[:66] + (int.from_bytes(signature[66:], "little") + ed521.L).to_bytes(
            66, "little"
        )
        self.assertFalse(ed521.verify(key, too_large, message))  # S must be below L
        self.assertFalse(ed521.verify(key, signature[:131], message))


@unittest.skipUnless(importlib.util.find_spec("ed521rs"), "verification extra is not installed")
class Ed521rsParityTests(unittest.TestCase):
    """``ed521rs`` (used by the section pass) gives ``election_audit.ed521``'s verdicts."""

    def cases(self) -> Iterator[tuple[bytes, bytes, bytes]]:
        import random

        from election_audit import ed521

        rng = random.Random(20261106)
        for index in range(12):
            seed, message = rng.randbytes(66), rng.randbytes(64)
            key, signature = ed521.public_key(seed), ed521.sign(seed, message)
            yield key, signature, message
            yield key, signature, message[:-1] + bytes([message[-1] ^ 1])
            changed = bytearray(signature)
            changed[rng.randrange(132)] ^= 1 << rng.randrange(8)
            yield key, bytes(changed), message
            if index < 3:
                s = int.from_bytes(signature[66:], "little") + ed521.L  # non-canonical S
                yield key, signature[:66] + s.to_bytes(66, "little"), message
                yield key, signature[:131], message
                yield bytes(66), signature, message

    def test_strict_verdicts_match_the_python_reference(self) -> None:
        import ed521rs

        from election_audit import ed521

        verdicts = []
        for key, signature, message in self.cases():
            expected = ed521.verify(key, signature, message)
            verdicts.append(expected)
            try:
                got = ed521rs.verify(key, signature, message)
            except ValueError:
                got = False
            self.assertEqual(got, expected)
        self.assertEqual(verdicts.count(True), 12)

    def test_the_verifier_counts_ecpy_disagreements(self) -> None:
        from election_audit import ed521
        from election_audit import integrity_checks as ic

        seed, digest = bytes(range(66)), hashlib.sha512(b"bu").digest()
        key = ed521.public_key(seed)
        signature = ed521.sign(seed, hashlib.sha512(digest).digest())
        verify = ic.Ed521Verifier(key)
        self.assertTrue(verify(digest, signature))
        self.assertFalse(verify(digest[::-1], signature))
        self.assertEqual(verify.disagreements, 0)
        s = int.from_bytes(signature[66:], "little") + ed521.L
        self.assertFalse(verify(digest, signature[:66] + s.to_bytes(66, "little")))
        self.assertEqual(verify.disagreements, 1)  # ECPy accepts S >= L
        self.assertEqual(ic.ed521_implementation()["implementation"], "ed521rs")


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class UrnEd521Tests(unittest.TestCase):
    """The real UE2022 fixture: every hardware signature verifies, changes are caught."""

    def setUp(self) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        from election_audit import ed521
        from election_audit import integrity_checks as ic

        self.ed521, self.ic = ed521, ic
        self.raw = (FIXTURE / f"{PREFIX}-vota.vsc").read_bytes()
        self.hardware = ic.signature_codec().decode(self.ic.SIGNATURE_TYPE, self.raw)[
            "assinaturaHW"
        ]
        certificate = x509.load_pem_x509_certificate(self.hardware["informacaoChave"][1])
        key = ed521.certificate_public_key(certificate.public_bytes(Encoding.DER))
        assert key is not None
        self.key = key

    def signed(self, digest: bytes, signature: bytes) -> bool:
        return self.ed521.verify(self.key, signature, hashlib.sha512(digest).digest())

    def test_self_and_file_signatures_verify(self) -> None:
        auto = self.hardware["autoAssinado"]["assinatura"]
        self.assertEqual(len(self.key), 66)
        self.assertTrue(self.signed(auto["hash"], auto["assinatura"]))
        listed = self.ic.signature_codec().decode(
            "Assinatura", self.hardware["conteudoAutoAssinado"]
        )["arquivosAssinados"]
        self.assertEqual(len(listed), 11)
        for entry in listed:
            self.assertTrue(
                self.signed(entry["assinatura"]["hash"], entry["assinatura"]["assinatura"])
            )
            path = FIXTURE / entry["nomeArquivo"]
            if path.exists():
                self.assertEqual(
                    hashlib.sha512(path.read_bytes()).digest(), entry["assinatura"]["hash"]
                )

    def test_a_flipped_hash_or_the_unhashed_digest_fails(self) -> None:
        auto = self.hardware["autoAssinado"]["assinatura"]
        flipped = bytes([auto["hash"][0] ^ 1]) + auto["hash"][1:]
        self.assertFalse(self.signed(flipped, auto["assinatura"]))
        self.assertFalse(self.ed521.verify(self.key, auto["assinatura"], auto["hash"]))

    def test_a_changed_signature_is_reported_as_failed(self) -> None:
        codec = self.ic.signature_codec()
        entity = codec.decode(self.ic.SIGNATURE_TYPE, self.raw)
        signature = bytearray(entity["assinaturaHW"]["autoAssinado"]["assinatura"]["assinatura"])
        signature[100] ^= 0x10
        entity["assinaturaHW"]["autoAssinado"]["assinatura"]["assinatura"] = bytes(signature)
        row, _ = self.ic.check_signatures(codec.encode(self.ic.SIGNATURE_TYPE, entity), {})
        self.assertEqual(row["i1_signature_math"], "failed")
        row, verify = self.ic.check_signatures(self.raw, {})
        assert verify is not None
        self.assertEqual(row["i1_signature_math"], "verified")
        self.assertEqual(row["ed521_ecpy_disagreements"], 0)
        self.assertFalse(verify(b"\x00" * 64, bytes(signature)))

    def test_other_key_types_have_no_ed521_key(self) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        self.assertIsNone(self.ed521.certificate_public_key(b"\x30\x00"))
        # An ECDSA certificate from the ECDSA test helper carries no Ed521 key.
        helper = SectionCheckTests("test_ecdsa_urn_signatures_are_verified")
        helper.setUp()
        entity = self.ic.signature_codec().decode(
            self.ic.SIGNATURE_TYPE, helper.ecdsa_vsc({"o1-bu.dat": b"x"})
        )
        raw = entity["assinaturaHW"]["informacaoChave"][1]
        der = x509.load_der_x509_certificate(raw[: 4 + int.from_bytes(raw[2:4], "big")])
        self.assertIsNone(self.ed521.certificate_public_key(der.public_bytes(Encoding.DER)))


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class SectionPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bulk = Path(self.temp.name) / "bulk"
        (self.bulk / "files").mkdir(parents=True)
        path = ITEM["archive"]
        with zipfile.ZipFile(self.bulk / path, "w") as z:
            z.writestr("leiame.pdf", b"%PDF")
            for kind in ("vsc", "bu", "rdv", "imgbu"):
                z.writestr(ITEM["members"][kind], (FIXTURE / ITEM["members"][kind]).read_bytes())
            z.writestr(ITEM["members"]["log"], b"stand-in log bytes, never parsed")
            z.writestr("o03221ac0101500020089-rdv.dat", b"rdv only")
            z.writestr("abc-bu=.id", b"abc-bu=")
        data = (self.bulk / path).read_bytes()
        with contextlib.closing(sqlite3.connect(self.bulk / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path,sha256,bytes,status)")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?)",
                (path, hashlib.sha256(data).hexdigest(), len(data), "complete"),
            )
            db.commit()
        self.output = Path(self.temp.name) / "out"

    def run_pass(self, **options: Any) -> dict[str, Any]:
        from election_audit.integrity_checks import run_sections

        return run_sections(
            self.bulk, 2, self.output, ufs=["ac"], workers=1, shard_sections=1, **options
        )

    def test_pass_hashes_logs_groups_sections_and_resumes(self) -> None:
        import pyarrow.parquet as pq

        result = self.run_pass()
        self.assertEqual((result["sections"], result["contests"]), (2, 2))
        self.assertEqual(result["unexpected_archive_members"], {ITEM["archive"]: 1})
        sections = pq.read_table(self.output / "release/sections.parquet").to_pylist()
        self.assertEqual([s["section"] for s in sections], ["0088", "0089"])
        first, second = sections
        detail = json.loads(first["i1_detail_json"])
        self.assertEqual(detail["mismatched"], [ITEM["members"]["log"]])  # stand-in log bytes
        self.assertEqual(json.loads(second["missing_json"]), ["bu", "imgbu", "log", "vsc"])
        self.assertEqual((second["bu_status"], second["rdv_status"]), ("missing", "error"))
        self.assertEqual(result["logs"][:24], "hashed with SHA-512 only")
        released = b"".join(
            p.read_bytes() for p in (self.output / "release").rglob("*") if p.is_file()
        )
        self.assertNotIn(b"stand-in log bytes", released)
        again = self.run_pass(resume=True)
        self.assertEqual(again["files"], result["files"])
        with self.assertRaises(FileExistsError):
            self.run_pass()

    def test_only_reviewed_years_and_complete_archives(self) -> None:
        from election_audit.integrity_checks import section_work_list

        with self.assertRaisesRegex(ValueError, "2026 member layout"):
            section_work_list(self.bulk, [], 2022, 2)
        with zipfile.ZipFile(self.bulk / ITEM["archive"], "a") as z:
            z.writestr(ITEM["members"]["bu"].replace("-bu.dat", "-busa.dat"), b"x")
        archive = {"path": ITEM["archive"], "uf": "ac"}
        with self.assertRaisesRegex(ValueError, "Duplicate bu"):
            section_work_list(self.bulk, [archive], 2026, 2)

    def write_bweb(
        self, root: Path, change: Callable[[list[dict[str, Any]]], None] | None = None
    ) -> Path:
        """A BWEB archive built from the fixture BU, optionally with one value changed."""
        import csv
        import io

        import pyarrow.parquet as pq

        from election_audit.binary_bu import codec
        from election_audit.integrity_checks import BWEB_COLUMNS, bu_contests

        section = pq.read_table(self.output / "release/sections.parquet").to_pylist()[0]
        raw = (FIXTURE / ITEM["members"]["bu"]).read_bytes()
        envelope = codec().decode("EntidadeEnvelopeGenerico", raw)
        contests = bu_contests(codec().decode("EntidadeBoletimUrna", envelope["conteudo"]))

        def stamp(v: str) -> str:
            return f"{v[:4]}-{v[4:6]}-{v[6:8]} {v[9:11]}:{v[11:13]}:{v[13:15]}"

        rows: list[dict[str, Any]] = []
        for (election, cargo), contest in contests.items():
            for (cls, number), count in sorted(contest["entries"].items()):
                rows.append(
                    {
                        "SG_UF": "AC",
                        "CD_MUNICIPIO": "1015",
                        "NR_ZONA": "2",
                        "NR_SECAO": "88",
                        "CD_PLEITO": "3221",
                        "NR_TURNO": "2",
                        "CD_ELEICAO": str(election),
                        "CD_CARGO_PERGUNTA": str(cargo),
                        "CD_TIPO_VOTAVEL": {"N": "1", "B": "2", "X": "3", "L": "4"}[cls],
                        "NR_VOTAVEL": str(number or {"B": 95, "X": 96}[cls]),
                        "QT_VOTOS": str(count),
                        "QT_APTOS": str(contest["eligible"]),
                        "QT_COMPARECIMENTO": str(contest["attendance"]),
                        "QT_ABSTENCOES": str(contest["eligible"] - contest["attendance"]),
                        "NR_LOCAL_VOTACAO": section["local"].lstrip("0"),
                        "NR_URNA_EFETIVADA": section["urn_serial"],
                        "CD_CARGA_1_URNA_EFETIVADA": section["load_code"][:18],
                        "CD_CARGA_2_URNA_EFETIVADA": section["load_code"][18:],
                        "CD_FLASHCARD_URNA_EFETIVADA": section["flash_serial"],
                        "DT_CARGA_URNA_EFETIVADA": stamp(section["loaded_at"]),
                        "DT_ABERTURA": stamp(section["opened_at"]),
                        "DT_ENCERRAMENTO": stamp(section["closed_at"]),
                        "DT_EMISSAO_BU": stamp(section["emitted_at"]),
                        "DS_SECOES_AGREGADAS": "#NULO#",
                        "CD_TIPO_URNA": "1",
                    }
                )
        if change:
            change(rows)
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=BWEB_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
        (root / "files").mkdir(parents=True)
        path = "files/bweb_2t_AC_261020260742.zip"
        with zipfile.ZipFile(root / path, "w") as z:
            z.writestr("bweb_2t_AC_261020260742.csv", text.getvalue().encode("latin-1"))
        data = (root / path).read_bytes()
        with contextlib.closing(sqlite3.connect(root / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path,sha256,bytes,status)")
            db.execute(
                "INSERT INTO files VALUES(?,?,?,?)",
                (path, hashlib.sha256(data).hexdigest(), len(data), "complete"),
            )
            db.commit()
        return root

    def test_bweb_comparison_names_changed_counts_and_fields(self) -> None:
        from election_audit.integrity_checks import run_bweb

        self.run_pass()
        same = run_bweb(
            self.output,
            self.write_bweb(Path(self.temp.name) / "bweb"),
            Path(self.temp.name) / "i2",
            ufs=["ac"],
        )
        self.assertEqual(same["summary"]["i2"], {"equal": 2})
        self.assertEqual(same["discrepancy_kinds"], {})

        def change(rows: list[dict[str, Any]]) -> None:
            rows[0]["QT_VOTOS"] = str(int(rows[0]["QT_VOTOS"]) + 1)
            for row in rows:
                row["CD_FLASHCARD_URNA_EFETIVADA"] = "00000000"

        other = run_bweb(
            self.output,
            self.write_bweb(Path(self.temp.name) / "bweb2", change),
            Path(self.temp.name) / "i2b",
            ufs=["ac"],
        )
        self.assertEqual(other["summary"]["i2"], {"equal": 1, "differs": 1})
        self.assertEqual(other["discrepancy_kinds"], {"I2:contest": 1, "I2:section_fields": 1})
        text = (Path(self.temp.name) / "i2b/release/discrepancies.jsonl").read_text()
        issues = [json.loads(line) for line in text.splitlines()]
        fields = next(i for i in issues if i["kind"] == "section_fields")["fields"]
        self.assertEqual(sorted(fields), ["flash_serial"])
        contest = next(i for i in issues if i["kind"] == "contest")
        self.assertNotEqual(contest["bu"], contest["bweb"])
        with self.assertRaises(FileExistsError):
            run_bweb(
                self.output, Path(self.temp.name) / "bweb", Path(self.temp.name) / "i2", ufs=["ac"]
            )

    def write_ea20(self, root: Path, bump: int = 0, voided: int | None = None) -> Path:
        """A one-municipality EA20 tree whose totals come from the fixture BU."""
        from election_audit.binary_bu import codec
        from election_audit.integrity_checks import bu_contests

        raw = (FIXTURE / ITEM["members"]["bu"]).read_bytes()
        envelope = codec().decode("EntidadeEnvelopeGenerico", raw)
        contest = bu_contests(codec().decode("EntidadeBoletimUrna", envelope["conteudo"]))[
            (6258, 1)
        ]
        entries = contest["entries"]
        candidates = [
            {"n": str(n), "vap": str(c + (bump if i == 0 else 0))}
            for i, ((k, n), c) in enumerate(sorted(entries.items()))
            if k == "N" and n != voided
        ]
        node = {
            "carg": [{"cd": "1", "agr": [{"par": [{"cand": candidates}]}]}],
            "v": {
                "vb": str(entries.get(("B", 0), 0)),
                "vn": str(entries.get(("X", 0), 0)),
                "vnt": str(entries.get(("N", voided), 0)),
            },
            "e": {"te": str(contest["eligible"]), "c": str(contest["attendance"])},
            "s": {"ts": "1", "si": "1", "sni": "0"},
        }
        root.mkdir(parents=True)
        (root / "objects").mkdir()
        rows = []
        for scope, uf, code in (("mun", "ac", "01015"), ("uf", "ac", None), ("br", "br", None)):
            body = json.dumps(dict(node, cdabr=code or uf)).encode()
            digest = hashlib.sha256(body).hexdigest()
            (root / "objects" / f"{digest}.json").write_bytes(body)
            rows.append(("unified", scope, uf, code, f"objects/{digest}.json", digest))
        with contextlib.closing(sqlite3.connect(root / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(kind, scope_type, uf, municipality, path, sha256)")
            db.executemany("INSERT INTO files VALUES(?,?,?,?,?,?)", rows)
            db.commit()
        (root / "status.json").write_text(
            json.dumps({"stage": "finished", "round": 2, "unified_not_final": 0})
        )
        return root

    def test_hierarchy_matches_and_maps_voided_candidacies(self) -> None:
        from election_audit.integrity_checks import run_hierarchy

        self.run_pass()
        bweb = self.write_bweb(Path(self.temp.name) / "bweb")
        tmp = Path(self.temp.name)
        same = run_hierarchy(bweb, self.write_ea20(tmp / "ea20"), 2, tmp / "i4", ufs=["ac"])
        self.assertEqual(same["discrepancies"], 0)
        self.assertEqual(same["summary"]["municipality:sections_vs_ea20"], {"equal": 1})
        # EA20 reports votes for a voided candidacy as technical nulls; BWEB keeps them nominal.
        voided = run_hierarchy(
            bweb, self.write_ea20(tmp / "ea20v", voided=22), 2, tmp / "i4v", ufs=["ac"]
        )
        self.assertEqual(voided["discrepancies"], 0)
        changed = run_hierarchy(
            bweb, self.write_ea20(tmp / "ea20c", bump=1), 2, tmp / "i4c", ufs=["ac"]
        )
        # Only the municipality differs from its sections; the UF still sums its children.
        self.assertEqual(changed["differing_measures"], {"candidate:13": 1})
        self.assertEqual(changed["summary"]["uf:children_vs_ea20"], {"equal": 1})

    def test_effective_urn_matches_its_bu(self) -> None:
        import csv
        import io

        import pyarrow.parquet as pq

        from election_audit.integrity_checks import run_correspondence

        self.run_pass()
        section = pq.read_table(self.output / "release/sections.parquet").to_pylist()[0]

        def write(root: Path, serial: str) -> Path:
            row = {
                "CD_PLEITO": "3221",
                "SG_UF": "AC",
                "CD_MUNICIPIO": "01015",
                "NR_ZONA": "2",
                "NR_SECAO": "88",
                "SQ_CORRESPONDENCIA_ESPERADA": "1",
                "SQ_CORRESPONDENCIA_EFETIVADA": "1",
                "NR_URNA_EFETIVADA": serial,
                "CD_CARGA_URNA_EFETIVADA": section["load_code"].lstrip("0"),
                "CD_FLASHCARD_URNA_EFETIVADA": section["flash_serial"],
                "DT_CARGA_URNA_EFETIVADA": "{}-{}-{} {}:{}:{}".format(
                    *(
                        section["loaded_at"][i:j]
                        for i, j in ((0, 4), (4, 6), (6, 8), (9, 11), (11, 13), (13, 15))
                    )
                ),
                "CD_ORIGEM_VOTO": "U",
                "TP_DIVERGENCIA": "",
            }
            text = io.StringIO()
            writer = csv.DictWriter(text, fieldnames=list(row), delimiter=";")
            writer.writeheader()
            writer.writerow(row)
            (root / "files").mkdir(parents=True)
            path = "files/CEFT_2t_AC_261020261201.zip"
            with zipfile.ZipFile(root / path, "w") as z:
                z.writestr("ceft_2t_AC_261020261201.csv", text.getvalue().encode("latin-1"))
            data = (root / path).read_bytes()
            with contextlib.closing(sqlite3.connect(root / "manifest.sqlite")) as db:
                db.execute("CREATE TABLE files(path,sha256,bytes,status)")
                db.execute(
                    "INSERT INTO files VALUES(?,?,?,?)",
                    (path, hashlib.sha256(data).hexdigest(), len(data), "complete"),
                )
                db.commit()
            return root

        tmp = Path(self.temp.name)
        same = run_correspondence(
            self.output, write(tmp / "c1", section["urn_serial"]), tmp / "o1", ufs=["ac"]
        )
        self.assertEqual(same["summary"]["effective_matches_bu"], {"match": 1, "n/a": 1})
        other = run_correspondence(self.output, write(tmp / "c2", "1"), tmp / "o2", ufs=["ac"])
        # Section 0089 (an RDV and nothing else) has no correspondence row.
        self.assertEqual(same["summary"]["kinds"], {"I9:no_correspondence": 1})
        self.assertEqual(
            other["summary"]["kinds"], {"I9:effective_urn": 1, "I9:no_correspondence": 1}
        )


class RdvBlockTests(unittest.TestCase):
    def test_repeated_contest_blocks_are_summed(self) -> None:
        from election_audit.integrity_checks import rdv_contests

        def block(votes: list[Any], choices: int = 1) -> dict[str, Any]:
            return {
                "idCargo": ("cargoConstitucional", "presidente"),
                "quantidadeEscolhas": choices,
                "votos": [{"tipoVoto": t, "digitacao": d} for t, d in votes],
            }

        rdv = {
            "eleicoes": (
                "eleicaoVota",
                [
                    {
                        "idEleicao": 6257,
                        "votosCargos": [
                            block([("nominal", "13"), ("branco", None)]),
                            block([("nominal", "13"), ("nominal", "22"), ("nulo", None)]),
                        ],
                    }
                ],
            )
        }
        contests, _ = rdv_contests(rdv)
        (contest,) = contests.values()
        self.assertEqual(contest["ballots"], 5)
        self.assertEqual(
            dict(contest["entries"]), {("N", 13): 2, ("N", 22): 1, ("B", 0): 1, ("X", 0): 1}
        )
        rdv["eleicoes"][1][0]["votosCargos"][1]["quantidadeEscolhas"] = 2
        with self.assertRaisesRegex(ValueError, "choices"):
            rdv_contests(rdv)


class LogRuleTests(unittest.TestCase):
    def session(self, **values: Any) -> dict[str, Any]:
        base = {
            "stream_ordinal": 0,
            "session_ordinal": 0,
            "start_reading": "2026-10-25T08:00:00",
            "end_reading": "2026-10-25T17:00:00",
            "closing_reading": "2026-10-25T17:00:00",
            "reading_backsteps": 0,
            "orphan_completions": 0,
        }
        return base | values

    def test_clock_and_session_rules(self) -> None:
        from election_audit.integrity_checks import clock_rules

        self.assertEqual(clock_rules([self.session()], "2026-10-25"), [])
        self.assertEqual(clock_rules([], "2026-10-25"), ["R1"])
        broken = [
            self.session(
                end_reading="2026-10-25T12:00:00", closing_reading=None, reading_backsteps=1
            ),
            self.session(
                session_ordinal=1,
                start_reading="2026-10-25T11:00:00",
                closing_reading=None,
                orphan_completions=2,
            ),
            self.session(
                session_ordinal=2,
                start_reading="2026-10-24T09:00:00",
                end_reading="2026-10-24T09:10:00",
            ),
        ]
        self.assertEqual(clock_rules(broken, "2026-10-25"), ["R3", "R4", "R5", "R6"])
        last_open = [
            self.session(),
            self.session(
                session_ordinal=1,
                start_reading="2026-10-25T17:01:00",
                end_reading="2026-10-25T17:30:00",
                closing_reading=None,
            ),
        ]
        self.assertEqual(clock_rules(last_open, "2026-10-25"), ["R2"])

    def test_memory_copies_of_a_session_count_once(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        from election_audit.integrity_checks import OFFICIAL_COLUMNS, _official
        from election_audit.section_table import distinct_sessions

        def session(
            stream: int, ordinal: int, device: str, start: str, done: int
        ) -> dict[str, Any]:
            values = dict.fromkeys(OFFICIAL_COLUMNS, 0) | {
                "object_sha256": "obj",
                "stream_ordinal": stream,
                "session_ordinal": ordinal,
                "segment_ordinal": 1,
                "device_id": device,
                "session_kind": "official_vota",
                "session_round": 2,
                "start_reading": start,
                "end_reading": None,
                "closing_reading": None,
                "cycles_completed_manual": done,
            }
            return values

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Internal (MI) and external (ME) memories of one urn, the ME copy longer, then
            # the replacement urn: the first urn's session counts once.
            rows = [
                session(0, 0, "u1", "2026-10-25T07:00:00", 64),
                session(1, 1, "u1", "2026-10-25T07:00:00", 69),
                session(2, 2, "u2", "2026-10-25T10:00:00", 155),
            ]
            pq.write_table(pa.Table.from_pylist(rows), root / "sessions.parquet")
            segments = [
                {"object_sha256": "obj", "stream_ordinal": s, "segment_ordinal": 1,
                 "first_line_sha256": "b2" if s == 2 else "b1", "lines": 900 + s}
                for s in range(3)
            ]  # fmt: skip
            pq.write_table(pa.Table.from_pylist(segments), root / "segments.parquet")
            official = _official(root, {"obj"}, 2)
            kept, conflicts = distinct_sessions(official["obj"])
            self.assertEqual(len(official["obj"]), 3)
            self.assertEqual([s["cycles_completed_manual"] for s in kept], [69, 155])
            self.assertEqual(conflicts, 0)  # the kept, longer copy also has the most cycles
            self.assertEqual(_official(root, {"other"}, 2), {})

    def test_round1_blocks_are_compared_block_by_block(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        from election_audit.integrity_checks import round1_statuses
        from election_audit.semantic_pass import OBJECT_SCHEMA, SEGMENT_SCHEMA

        def release(root: Path, objects: list[Any], segments: list[Any]) -> Path:
            root.mkdir(parents=True)
            pq.write_table(
                pa.Table.from_pylist(
                    [
                        {
                            "object_sha256": o,
                            "status": "complete",
                            "witnesses_json": json.dumps([w]),
                        }
                        for o, w in objects
                    ],
                    schema=OBJECT_SCHEMA,
                ),
                root / "objects.parquet",
            )
            pq.write_table(
                pa.Table.from_pylist(
                    [
                        {
                            "object_sha256": o,
                            "stream_ordinal": 0,
                            "segment_ordinal": i,
                            "device_id": d,
                            "context": c,
                            "lines": n,
                            "fingerprint": f,
                            "first_line_sha256": s,
                        }
                        for o, i, d, c, n, f, s in segments
                    ],
                    schema=SEGMENT_SCHEMA,
                ),
                root / "segments.parquet",
            )
            return root

        a, b, c, d = (["ac", "01015", "0002", f"000{i}"] for i in range(1, 5))
        with tempfile.TemporaryDirectory() as tmp:
            r1 = "official_round_1"
            first = release(
                Path(tmp) / "r1",
                [("1a", a), ("1b", b), ("1c", c), ("1d", d)],
                [
                    ("1a", 0, "u1", r1, 10, "f1", "s1"),
                    ("1a", 1, "u1", r1, 50, "f2", "s2"),
                    ("1b", 0, "u2", r1, 10, "f1", "s1"),
                    ("1c", 0, "u3", r1, 10, "f1", "s1"),
                    ("1d", 0, "u4", r1, 10, "f1", "s1"),
                ],
            )
            runoff = release(
                Path(tmp) / "r2",
                [("2a", a), ("2b", b), ("2c", c), ("2d", d)],
                [
                    ("2a", 0, "u1", r1, 10, "f1", "s1"),
                    ("2a", 1, "u1", r1, 70, "g2", "s2"),  # open last block
                    ("2b", 0, "u2", r1, 10, "zz", "s1"),  # same start, changed
                    ("2c", 0, "u9", r1, 10, "f1", "s1"),  # another urn
                    ("2d", 0, "u4", "official_round_2", 10, "f1", "s1"),  # no round-1 block
                ],
            )
            statuses = round1_statuses(runoff, first)
        self.assertEqual(statuses[tuple(a)], "equal_closed_open_prefix_unverified")
        self.assertEqual(statuses[tuple(b)], "differs")
        self.assertEqual(statuses[tuple(c)], "different_device")
        self.assertEqual(statuses[tuple(d)], "no_round1_block_in_runoff_log")


if __name__ == "__main__":
    unittest.main()


class SmallOrderKeyTests(unittest.TestCase):
    """xr1-20261109-P3-04: a small-order key verifies a fixed signature for every message."""

    def setUp(self) -> None:
        from election_audit import ed521

        self.ed521 = ed521
        self.identity = ed521.encode((0, 1, 1, 0))
        self.forged = ed521.encode(ed521.BASE) + (1).to_bytes(ed521.SIZE, "little")

    def test_points_of_order_one_two_and_four_are_small(self) -> None:
        order_two = self.ed521.encode((0, self.ed521.P - 1, 1, 0))
        self.assertTrue(self.ed521.small_order(self.identity))
        self.assertTrue(self.ed521.small_order(order_two))
        self.assertFalse(self.ed521.small_order(self.ed521.encode(self.ed521.BASE)))
        self.assertIsNone(self.ed521.small_order(b"\xff" * self.ed521.SIZE))
        # The equation alone accepts the forgery, which is why the key must be checked.
        self.assertTrue(self.ed521.verify(self.identity, self.forged, b"any message"))

    @unittest.skipUnless(importlib.util.find_spec("ed521rs"), "verification extra is not installed")
    def test_the_urn_verifier_trusts_no_signature_under_a_small_order_key(self) -> None:
        import hashlib

        from election_audit.integrity_checks import Ed521Verifier

        verifier = Ed521Verifier(self.identity)
        self.assertTrue(verifier.small_order)
        for digest in (b"\x00" * 64, b"\x01" * 64):
            # The verifier hashes the digest again; the forgery holds for any message.
            self.assertTrue(
                self.ed521.verify(self.identity, self.forged, hashlib.sha512(digest).digest())
            )
            self.assertFalse(verifier(digest, self.forged))


@unittest.skipUnless(importlib.util.find_spec("asn1tools"), "verification extra is not installed")
class SignatureIssueTests(unittest.TestCase):
    """xr1-20261109-P0-05: I1 and certificate failures become issue rows."""

    def test_each_failure_is_one_issue_and_a_clean_row_has_none(self) -> None:
        from election_audit.integrity_checks import signature_issues

        base = {"uf": "ac", "municipality": "01007", "zone": "0001", "section": "0010"}
        clean = {
            "vsc_status": "decoded",
            "i1_hash_mismatches": 0,
            "i1_published_unlisted": 0,
            "i1_file_signatures_failed": 0,
            "i1_signature_math": "verified",
            "hw_key_small_order": False,
            "cert_valid_at_election": True,
            "pki_issuer_signature": "verified",
            "pki_revoked": False,
            "pki_ca_valid_at_election": False,  # an expired CA is not a per-section issue
        }
        self.assertEqual(signature_issues(clean, base), [])
        bad = clean | {
            "i1_hash_mismatches": 1,
            "i1_file_signatures_failed": 2,
            "i1_signature_math": "failed",
            "hw_key_small_order": True,
            "pki_issuer_signature": "unknown_issuer",
            "pki_revoked": True,
        }
        kinds = [i["kind"] for i in signature_issues(bad, base)]
        self.assertEqual(
            kinds,
            [
                "file_hash_mismatch",
                "file_signature",
                "self_signature",
                "key_small_order",
                "certificate_issuer",
                "certificate_revoked",
            ],
        )
        missing = signature_issues({"vsc_status": "missing"}, base)
        self.assertEqual(
            [(i["check"], i["kind"], i["value"]) for i in missing], [("I1", "vsc", "missing")]
        )
