"""The streaming session pass matches the event-level adapter and exports aggregates only."""

import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from election_audit import semantic_pass as sp

TOKEN = "ABCDEF0123456789"
VOTER = "000012345678"


def log_body(messages, *, round_number=2, date="25/10/2026", device="12345678", start=0):
    label = "SEGUNDO" if round_number == 2 else "PRIMEIRO"
    records = [
        ("GAP", f"Iniciando aplicação - ELEIÇÃO OFICIAL {label} TURNO - {round_number}º turno"),
        ("VOTA", f"Iniciando aplicação - {round_number}º turno"),
        ("VOTA", "Versão da aplicação: 10.23.0.0 - Praia da Barra do Cahy"),
        *[("VOTA", m) for m in messages],
    ]
    return "".join(
        f"{date} {8 + (start + i) // 3600:02d}:{(start + i) // 60 % 60:02d}:{(start + i) % 60:02d}"
        f"\tINFO\t{device}\t{app}\t{message}\t{TOKEN}\n"
        for i, (app, message) in enumerate(records)
    ).encode("latin-1")


def jez(*bodies, nested=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for index, body in enumerate(bodies):
            if nested:
                inner = io.BytesIO()
                with zipfile.ZipFile(inner, "w") as zi:
                    zi.writestr("logd.dat", body)
                z.writestr(f"inner{index}.jez", inner.getvalue())
            else:
                z.writestr("logd.dat", body)
    return stream.getvalue()


CYCLES = [
    # completed biometric
    "Tipo de habilitação do eleitor [biométrica]",
    "Eleitor foi habilitado",
    "Voto confirmado para [Presidente]",
    "O voto do eleitor foi computado",
    # completed manual, interrupted by a partial suspension
    "Solicitação de dado pessoal do eleitor para habilitação manual",
    f"Mesário {VOTER} habilitou o eleitor",
    "Eleitor foi habilitado",
    "Eleitor votou parcialmente e em seguida foi suspenso",
    "O voto do eleitor foi computado",
    # suspended, then an orphan completion and a failed authorization
    "Eleitor foi habilitado",
    "Eleitor foi suspenso e não confirmou nenhum voto",
    "O voto do eleitor foi computado",
    "Identificador do eleitor digitado inválido",
    # completed with an unknown message inside the cycle
    "Eleitor foi habilitado",
    "Mensagem desconhecida 42",
    "O voto do eleitor foi computado",
    "Procedimento de encerramento confirmado",
    "Finalização de aplicativo",
]


class SessionMachineTests(unittest.TestCase):
    def test_matches_the_event_level_adapter_on_edge_cases(self):
        cases = {
            "cycles": jez(log_body(CYCLES)),
            "two_members_nested": jez(log_body(CYCLES[:4]), log_body(CYCLES[4:]), nested=True),
            "wrong_day": jez(log_body(CYCLES, date="24/10/2026")),
            "wrong_round": jez(log_body(CYCLES, round_number=1)),
            "two_devices": jez(log_body(CYCLES[:6]) + log_body(CYCLES, device="87654321")),
        }
        with tempfile.TemporaryDirectory() as d:
            for name, body in cases.items():
                with self.subTest(case=name):
                    original = Path(d) / f"{name}.jez"
                    original.write_bytes(body)
                    expected, counts = sp.adapter_signatures(original, Path(d) / name, 2)
                    summary = sp.summarize_object(original, hashlib.sha256(body).hexdigest(), 2)
                    self.assertEqual(sp.pass_signatures(summary), expected)
                    self.assertEqual(
                        sum(s["manual_requests"] for s in summary.sessions),
                        counts.get("manual_requests", 0),
                    )
                    self.assertEqual(
                        sum(s["orphan_completions"] for s in summary.sessions),
                        counts.get("orphan_completions", 0),
                    )

    def test_session_aggregates_cadence_and_segments(self):
        body = jez(log_body(CYCLES))
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "x.jez"
            original.write_bytes(body)
            summary = sp.summarize_object(original, "x", 2)
        (session,) = [s for s in summary.sessions if s["session_kind"] == "official_vota"]
        self.assertEqual(session["cycles_completed_biometric"], 1)
        self.assertEqual(session["cycles_completed_manual"], 1)
        self.assertEqual(session["completed_interrupted"], 1)
        self.assertEqual(session["cycles_suspended_unknown"], 1)
        self.assertEqual(session["orphan_completions"], 1)
        self.assertEqual(session["authorization_failures"], 1)
        self.assertEqual(session["active_unknown_events"], 1)
        self.assertEqual(session["end_reason"], "application_exit")
        self.assertEqual(session["completions_by_reading_hour"][8], 3)
        self.assertEqual(session["completion_gaps"], 2)
        self.assertEqual(session["start_reading"], "2026-10-25T08:00:01")
        self.assertIsNotNone(session["closing_reading"])
        contexts = [s["context"] for s in summary.segments]
        self.assertEqual(contexts, ["initial", "official_round_2"])
        self.assertEqual(summary.segments[1]["lines"], len(CYCLES) + 3)
        templates = {t for _, t in summary.vocabulary}
        self.assertIn("Mesário # habilitou o eleitor", templates)
        self.assertFalse(any(VOTER in t or TOKEN in t for t in templates))

    def test_readings_are_validated_exactly(self):
        self.assertIsNone(sp.reading_seconds("31/02/2026 10:00:00"))
        self.assertIsNone(sp.reading_seconds("25/10/2026 24:00:00"))
        self.assertIsNone(sp.reading_seconds("25/10/2026 1:00:000"))
        value = sp.reading_seconds("25/10/2026 10:00:05")
        self.assertEqual(sp.iso_reading(value), "2026-10-25T10:00:05")


class PassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "turno-2"
        rows, logs = [], []
        bodies = {
            ("ac", "01015", "0002", "0101"): jez(log_body(CYCLES)),  # protected
            ("ac", "01023", "0001", "0001"): jez(log_body(CYCLES, start=10)),
            ("al", "27000", "0001", "0002"): jez(log_body(CYCLES[:5], start=20)),
            ("al", "27000", "0001", "0003"): b"not a zip",
        }
        for key, body in bodies.items():
            digest = hashlib.sha256(body).hexdigest()
            relative = f"objects/{digest[:2]}/{digest}.jez"
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.root / relative).write_bytes(body)
            url = (
                "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/"
                f"{'/'.join(key)}/hash/o03221-log.jez"
            )
            rows.append((url, relative, digest, len(body)))
            logs.append((url, "Totalizado"))
        manifest = self.root / "manifest.sqlite"
        with contextlib.closing(sqlite3.connect(manifest)) as db:
            db.execute("CREATE TABLE files(url,path,sha256,bytes)")
            db.execute("CREATE TABLE logs(url,package_status)")
            db.executemany("INSERT INTO files VALUES(?,?,?,?)", rows)
            db.executemany("INSERT INTO logs VALUES(?,?)", logs)
            db.commit()
        (self.root / "staging-certificate.json").write_text(
            json.dumps({"round": 2, "manifest_sha256": "m" * 64})
        )
        self.exclusions = base / "exclusions.json"
        self.exclusions.write_text(json.dumps({"section_keys": [["ac", "01015", "0002", "0101"]]}))
        self.output = base / "pass"

    def run_pass(self, **options):
        return sp.run_pass(
            self.root, 2, self.output, exclusions_path=self.exclusions, workers=1, **options
        )

    def test_pass_excludes_protected_records_errors_and_resumes(self):
        result = self.run_pass(shard_objects=2)
        self.assertEqual(result["objects"], 3)
        self.assertEqual(result["excluded_objects"], 1)
        self.assertEqual(result["errors"], 1)
        objects = pq.read_table(self.output / "release" / "objects.parquet").to_pylist()
        witnesses = [json.loads(o["witnesses_json"])[0] for o in objects]
        self.assertNotIn(["ac", "01015", "0002", "0101"], witnesses)
        self.assertEqual(sorted(o["status"] for o in objects), ["complete", "complete", "error"])
        sessions = pq.read_table(self.output / "release" / "sessions.parquet").to_pylist()
        self.assertEqual(sum(s["session_kind"] == "official_vota" for s in sessions), 2)
        exported = b"".join(p.read_bytes() for p in (self.output / "release").iterdir())
        self.assertNotIn(TOKEN.encode(), exported)
        self.assertNotIn(VOTER.encode(), exported)
        files = json.loads((self.output / "release" / "manifest.json").read_text())["files"]
        self.assertEqual(
            set(files), {f"{n}.parquet" for n in ("objects", "sessions", "segments", "vocabulary")}
        )
        with self.assertRaises(FileExistsError):
            self.run_pass(shard_objects=2)
        with self.assertRaisesRegex(ValueError, "binding"):
            self.run_pass(shard_objects=3, resume=True)
        again = self.run_pass(shard_objects=2, resume=True)
        self.assertEqual(again["files"], result["files"])

    def test_uf_filter_and_worker_cap(self):
        result = self.run_pass(ufs=["al"])
        self.assertEqual(result["objects"], 2)
        with self.assertRaisesRegex(ValueError, "half the CPUs"):
            sp.run_pass(
                self.root,
                2,
                Path(self.temp.name) / "x",
                exclusions_path=self.exclusions,
                workers=10_000,
            )


if __name__ == "__main__":
    unittest.main()
