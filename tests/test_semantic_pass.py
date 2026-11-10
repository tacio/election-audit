"""The streaming session pass matches the event-level adapter and exports aggregates only."""

import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from test_sevenzip import make_7z

from election_audit import semantic_pass as sp
from election_audit.elections import election_for_round

TOKEN = "ABCDEF0123456789"
VOTER = "000012345678"


def log_body(
    messages: Iterable[str],
    *,
    round_number: int = 2,
    date: str = "25/10/2026",
    device: str = "12345678",
    start: int = 0,
) -> bytes:
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


def jez(*bodies: bytes, nested: bool = False) -> bytes:
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


def timed_body(records: Iterable[tuple[str, int, str, str]], device: str = "12345678") -> bytes:
    """Log lines from (date, seconds after 08:00, application, message) records."""
    return "".join(
        f"{date} {8 + t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d}"
        f"\tINFO\t{device}\t{app}\t{message}\t{TOKEN}\n"
        for date, t, app, message in records
    ).encode("latin-1")


OFFICIAL_2 = "Iniciando aplicação - ELEIÇÃO OFICIAL SEGUNDO TURNO - 2º turno"
SOFTWARE = "Versão da aplicação: 10.23.0.0 - Praia da Barra do Cahy"
# An urn switched on the day before and left running into election day.
DAY_BEFORE = timed_body(
    [
        ("24/10/2026", 3600, "GAP", "Iniciando aplicação - 2º turno"),
        ("24/10/2026", 3601, "GAP", OFFICIAL_2),
        ("24/10/2026", 3602, "VOTA", "Iniciando aplicação - 2º turno"),
        ("24/10/2026", 3603, "VOTA", SOFTWARE),
        ("24/10/2026", 3604, "VOTA", "Urna ligada conectada na rede CA"),
        *[("25/10/2026", 10 + i, "VOTA", m) for i, m in enumerate(CYCLES)],
    ]
)
# A mid-day restart: the GAP restart line is not followed by the official marker.
RESTART = timed_body(
    [
        ("25/10/2026", 0, "GAP", OFFICIAL_2),
        ("25/10/2026", 1, "VOTA", "Iniciando aplicação - 2º turno"),
        ("25/10/2026", 2, "VOTA", SOFTWARE),
        *[("25/10/2026", 10 + i, "VOTA", m) for i, m in enumerate(CYCLES[:4])],
        ("25/10/2026", 3600, "GAP", "Iniciando aplicação - 2º turno"),
        ("25/10/2026", 3601, "VOTA", "Iniciando aplicação - 2º turno"),
        ("25/10/2026", 3602, "VOTA", SOFTWARE),
        *[("25/10/2026", 3610 + i, "VOTA", m) for i, m in enumerate(CYCLES[4:])],
    ]
)


class SessionMachineTests(unittest.TestCase):
    def test_matches_the_event_level_adapter_on_edge_cases(self) -> None:
        cases = {
            "cycles": jez(log_body(CYCLES)),
            "two_members_nested": jez(log_body(CYCLES[:4]), log_body(CYCLES[4:]), nested=True),
            "wrong_day": jez(log_body(CYCLES, date="24/10/2026")),
            "wrong_round": jez(log_body(CYCLES, round_number=1)),
            "two_devices": jez(log_body(CYCLES[:6]) + log_body(CYCLES, device="87654321")),
            "day_before": jez(DAY_BEFORE),
            "midday_restart": jez(RESTART),
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

    def test_session_aggregates_cadence_and_segments(self) -> None:
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

    def test_sessions_started_the_day_before_and_restarts_keep_their_votes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "x.jez"
            original.write_bytes(jez(DAY_BEFORE))
            early = sp.summarize_object(original, "x", 2)
            original.write_bytes(jez(RESTART))
            restart = sp.summarize_object(original, "x", 2)
        (session,) = early.sessions
        self.assertEqual(session["session_kind"], "official_vota")
        self.assertTrue(session["started_before_election_day"])
        self.assertEqual(session["start_reading"], "2026-10-24T09:00:02")
        completed = sum(session[f"cycles_completed_{m}"] for m in sp.METHODS)
        self.assertEqual(completed, 3)
        sessions = restart.sessions
        self.assertEqual([s["session_kind"] for s in sessions], ["official_vota"] * 2)
        self.assertFalse(any(s["started_before_election_day"] for s in sessions))
        self.assertEqual(sum(s[f"cycles_completed_{m}"] for s in sessions for m in sp.METHODS), 3)
        # The restart line stays in the official block.
        self.assertEqual([g["context"] for g in restart.segments], ["initial", "official_round_2"])

    def test_a_clock_excursion_or_orphan_completion_ends_the_pending_cycle(self) -> None:
        # xr1-20261109-P2-04: an authorization whose next events are off election day does
        # not take a completion read after the clock returns.
        start = [
            ("25/10/2026", 0, "GAP", OFFICIAL_2),
            ("25/10/2026", 1, "VOTA", "Iniciando aplicação - 2º turno"),
            ("25/10/2026", 2, "VOTA", SOFTWARE),
        ]
        excursion = timed_body(
            [
                *start,
                ("25/10/2026", 10, "VOTA", "Eleitor foi habilitado"),
                ("01/01/2000", 11, "VOTA", "Eleitor foi suspenso e não confirmou nenhum voto"),
                ("25/10/2026", 12, "VOTA", "O voto do eleitor foi computado"),
            ]
        )
        # xr1-20261109-P2-05: an orphan completion clears a pending manual request.
        orphan = timed_body(
            [
                *start,
                (
                    "25/10/2026",
                    10,
                    "VOTA",
                    "Solicitação de dado pessoal do eleitor para habilitação manual",
                ),
                ("25/10/2026", 10, "VOTA", f"Mesário {VOTER} habilitou o eleitor"),
                ("25/10/2026", 11, "VOTA", "O voto do eleitor foi computado"),
                ("25/10/2026", 12, "VOTA", "Eleitor foi habilitado"),
                ("25/10/2026", 13, "VOTA", "O voto do eleitor foi computado"),
            ]
        )
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "x.jez"
            original.write_bytes(jez(excursion))
            (moved,) = sp.summarize_object(original, "x", 2).sessions
            original.write_bytes(jez(orphan))
            (cleared,) = sp.summarize_object(original, "x", 2).sessions
        self.assertEqual(sum(moved[f"cycles_completed_{m}"] for m in sp.METHODS), 0)
        self.assertEqual(sum(moved[f"cycles_unresolved_{m}"] for m in sp.METHODS), 1)
        self.assertEqual(cleared["orphan_completions"], 1)
        self.assertEqual(cleared["cycles_completed_manual"], 0)
        self.assertEqual(cleared["cycles_completed_unknown"], 1)

    def test_zeresima_markers_keep_their_place_among_the_votes(self) -> None:
        zeresima = [
            "Aguardando data e hora para emissão da zerésima",
            "Gerando relatório [ZERÉSIMA] [INÍCIO]",
            "Gerando relatório [ZERÉSIMA] [TÉRMINO]",
            "Imprimindo relatório [ZERÉSIMA] via nº [1]",
            "Urna pronta para receber votos",
        ]
        late = "Imprimindo relatório [ZERÉSIMA] via nº [2]"
        body = log_body([*zeresima, *CYCLES[:4], late, "Zerésima nova 7"])
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "x.jez"
            original.write_bytes(jez(body))
            summary = sp.summarize_object(original, "x", 2)
        rows = [(m["kind"], m["completions_before"], m["session_ordinal"]) for m in summary.markers]
        self.assertEqual(
            rows,
            [
                ("await_datetime", 0, 0),
                ("zeresima_start", 0, 0),
                ("zeresima_end", 0, 0),
                ("zeresima_print", 0, 0),
                ("ready", 0, 0),
                ("zeresima_print", 1, 0),
                ("other", 1, 0),
            ],
        )
        self.assertEqual(summary.markers[-1]["template"], "Zerésima nova #")
        self.assertEqual(summary.markers[0]["reading"], "2026-10-25T08:00:03")
        self.assertEqual({m["segment_ordinal"] for m in summary.markers}, {1})

    def test_package_checks_are_counted_and_failures_located(self) -> None:
        load = "Verificação de assinatura de aplicação por etapa [1] - [Pacote: /bin/avbin.vst]"
        body = timed_body(
            [
                ("25/10/2026", 0, "SCUE", f"{load} - [Arquivo: avbin] - [SUCESSO]"),
                ("25/10/2026", 1, "SCUE", "Identificação do Modelo de Urna: UE2020"),
                (
                    "25/10/2026",
                    2,
                    "GAP",
                    "Verificação de assinatura - Etapa [3] - [/lib/avlib.vst] - [ERRO]",
                ),
                (
                    "25/10/2026",
                    3,
                    "GAP",
                    "Verificação de assinatura - Etapa [4] - [/dsk/fi/estatico/o00407ac-ce.vsc] - [SUCESSO]",
                ),
                (
                    "25/10/2026",
                    4,
                    "GAP",
                    "Verificação de assinatura - Etapa [4] - [/dsk/fi/estatico/o00407ac-ce.vsc] - [SUCESSO]",
                ),
                ("25/10/2026", 5, "GAP", "Erro na verificação de assinatura do arquivo - vota.vsu"),
            ]
        )
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / "x.jez"
            original.write_bytes(jez(body))
            summary = sp.summarize_object(original, "x", 2)
        self.assertEqual(
            summary.packages,
            {
                ("UE2020", "SCUE", "aplicação", "/bin/avbin.vst", "avbin", "SUCESSO"): 1,
                ("UE2020", "GAP", "startup", "/lib/avlib.vst", None, "ERRO"): 1,
                ("UE2020", "GAP", "startup", "/dsk/fi/estatico/o#ac-ce.vsc", None, "SUCESSO"): 2,
            },
        )
        self.assertEqual(
            [(m["kind"], m["line"]) for m in summary.markers],
            [("signature_error", 3), ("signature_error", 6)],
        )

    def test_readings_are_validated_exactly(self) -> None:
        self.assertIsNone(sp.reading_seconds("31/02/2026 10:00:00"))
        self.assertIsNone(sp.reading_seconds("25/10/2026 24:00:00"))
        self.assertIsNone(sp.reading_seconds("25/10/2026 1:00:000"))
        value = sp.reading_seconds("25/10/2026 10:00:05")
        self.assertEqual(sp.iso_reading(value), "2026-10-25T10:00:05")


class PassTests(unittest.TestCase):
    def setUp(self) -> None:
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

    def run_pass(self, **options: Any) -> dict[str, Any]:
        return sp.run_pass(
            self.root, 2, self.output, exclusions_path=self.exclusions, workers=1, **options
        )

    def test_pass_excludes_protected_records_errors_and_resumes(self) -> None:
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
            set(files),
            {
                f"{n}.parquet"
                for n in ("objects", "sessions", "segments", "markers", "packages", "vocabulary")
            },
        )
        with self.assertRaises(FileExistsError):
            self.run_pass(shard_objects=2)
        with self.assertRaisesRegex(ValueError, "binding"):
            self.run_pass(shard_objects=3, resume=True)
        again = self.run_pass(shard_objects=2, resume=True)
        self.assertEqual(again["files"], result["files"])

    def test_uf_filter_and_worker_cap(self) -> None:
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


def log_body_2022(
    messages: Iterable[str],
    *,
    round_number: int = 2,
    date: str = "30/10/2022",
    device: str = "12345678",
    start: int = 0,
) -> bytes:
    """A 2022 (8.26.0.0) log: same machine, different round and software markers."""
    label = "SEGUNDO" if round_number == 2 else "PRIMEIRO"
    records = [
        ("GAP", f"Iniciando aplicação - Oficial - {round_number}º turno"),
        (
            "GAP",
            f"Iniciando aplicação - ELEIÇÃO OFICIAL {label} TURNO - Oficial - {round_number}º turno",
        ),
        ("VOTA", f"Iniciando aplicação - Oficial - {round_number}º turno"),
        ("VOTA", "Versão da aplicação: 8.26.0.0 - Onça-pintada"),
        *[("VOTA", m) for m in messages],
    ]
    return "".join(
        f"{date} {8 + (start + i) // 3600:02d}:{(start + i) // 60 % 60:02d}:{(start + i) % 60:02d}"
        f"\tINFO\t{device}\t{app}\t{message}\t{TOKEN}\n"
        for i, (app, message) in enumerate(records)
    ).encode("latin-1")


CYCLES_2022 = [
    "Tipo de habilitação do eleitor [biométrica]",
    "Eleitor foi habilitado",
    "Voto confirmado para [Presidente]",
    "O voto do eleitor foi computado",
    # 2022 manual flow: poll-worker fingerprint, no "habilitou o eleitor" marker
    "Solicitação de dado pessoal do eleitor para habilitação manual",
    "Solicita digital do mesário",
    "Capturada a digital do mesário",
    "Eleitor foi habilitado",
    "O voto do eleitor foi computado",
    "Título inválido",
    "O eleitor identificado já votou",
    "Eleitor foi habilitado",
    "Eleitor foi suspenso e não confirmou nenhum voto",
    "Procedimento de encerramento confirmado",
    "Finalização de aplicativo",
]


class Year2022Tests(unittest.TestCase):
    def test_2022_descriptors(self) -> None:
        first, second = election_for_round(1, 2022), election_for_round(2, 2022)
        self.assertEqual((first.pleito_code, first.election_date), ("406", "2022-10-02"))
        self.assertEqual((second.pleito_code, second.election_date), ("407", "2022-10-30"))
        self.assertEqual(election_for_round(2).year, 2026)
        with self.assertRaises(ValueError):
            election_for_round(2, 2018)

    def test_7z_logs_match_the_adapter_and_keep_unreviewed_methods_unknown(self) -> None:
        cases = {
            "cycles": make_7z([("logd.dat", log_body_2022(CYCLES_2022))]),
            "nested": make_7z(
                [
                    ("670.jez", make_7z([("logd.dat", log_body_2022(CYCLES_2022[:4]))])),
                    ("logd.dat", log_body_2022(CYCLES_2022[4:], start=50)),
                ]
            ),
            "wrong_day": make_7z([("logd.dat", log_body_2022(CYCLES_2022, date="29/10/2022"))]),
        }
        with tempfile.TemporaryDirectory() as d:
            for name, body in cases.items():
                with self.subTest(case=name):
                    original = Path(d) / f"{name}.logjez"
                    original.write_bytes(body)
                    expected, counts = sp.adapter_signatures(original, Path(d) / name, 2, 2022)
                    summary = sp.summarize_object(body, "x", 2, 2022)
                    self.assertEqual(sp.pass_signatures(summary), expected)
                    self.assertEqual(
                        sum(s["manual_requests"] for s in summary.sessions),
                        counts.get("manual_requests", 0),
                    )
        summary = sp.summarize_object(cases["cycles"], "x", 2, 2022)
        (session,) = [s for s in summary.sessions if s["session_kind"] == "official_vota"]
        self.assertTrue(session["software_supported"])
        self.assertEqual(session["cycles_completed_biometric"], 1)
        self.assertEqual(session["cycles_completed_unknown"], 1)  # manual is not inferred
        self.assertEqual(session["cycles_completed_manual"], 0)
        self.assertEqual(session["authorization_failures"], 1)
        self.assertEqual(session["cycles_suspended_unknown"], 1)

    def test_decades_long_clock_steps_are_kept_not_overflowed(self) -> None:
        body = (
            log_body_2022(CYCLES_2022[:4])
            + log_body_2022(CYCLES_2022[:4], date="01/01/1933", start=10).split(b"\n", 4)[4]
        )
        summary = sp.summarize_object(make_7z([("logd.dat", body)]), "x", 2, 2022)
        (session,) = [s for s in summary.sessions if s["session_kind"] == "official_vota"]
        self.assertGreater(session["reading_backstep_max_s"], 2**31)
        with tempfile.TemporaryDirectory() as d:
            sp._write(Path(d) / "s.parquet", summary.sessions, sp.SESSION_SCHEMA)
            rows = pq.read_table(Path(d) / "s.parquet").to_pylist()
        self.assertEqual(rows[-1]["reading_backstep_max_s"], session["reading_backstep_max_s"])

    def test_rules_do_not_cross_years(self) -> None:
        log_2026 = jez(log_body(CYCLES, date="30/10/2022"))
        summary = sp.summarize_object(log_2026, "x", 2, 2022)
        self.assertFalse(any(s["session_kind"] == "official_vota" for s in summary.sessions))
        log_2022 = make_7z([("logd.dat", log_body_2022(CYCLES_2022, date="25/10/2026"))])
        summary = sp.summarize_object(log_2022, "x", 2, 2026)
        self.assertFalse(any(s["session_kind"] == "official_vota" for s in summary.sessions))


class BulkPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bulk = Path(self.temp.name) / "bulk"
        (self.bulk / "files").mkdir(parents=True)
        rows = []
        for year, turn, uf, members in (
            (2022, 2, "AC", {"o00407-0101500020088.logjez": log_body_2022(CYCLES_2022)}),
            (2022, 2, "AL", {"o00407-2700000010002.logjez": b"broken", "leiame.pdf": b"%PDF"}),
            (2022, 1, "AC", {"o00406-0101500020088.logjez": log_body_2022(CYCLES_2022)}),
        ):
            path = f"files/bu_imgbu_logjez_rdv_vscmr_{year}_{turn}t_{uf}.zip"
            with zipfile.ZipFile(self.bulk / path, "w") as z:
                z.writestr(next(iter(members)).replace(".logjez", ".bu"), b"bu")
                for name, body in members.items():
                    z.writestr(name, make_7z([("logd.dat", body)]) if body[:2] == b"30" else body)
            data = (self.bulk / path).read_bytes()
            rows.append((path, hashlib.sha256(data).hexdigest(), len(data), "complete"))
        with contextlib.closing(sqlite3.connect(self.bulk / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE files(path,sha256,bytes,status)")
            db.executemany("INSERT INTO files VALUES(?,?,?,?)", rows)
            db.commit()
        self.output = Path(self.temp.name) / "pass"

    def run_bulk(self, **options: Any) -> dict[str, Any]:
        return sp.run_pass(
            None, 2, self.output, bulk_root=self.bulk, year=2022, workers=1, **options
        )

    def test_bulk_pass_reads_members_in_order_with_witnesses(self) -> None:
        result = self.run_bulk(ufs=["ac", "al"], shard_objects=1)
        self.assertEqual((result["objects"], result["errors"]), (2, 1))
        self.assertEqual(result["year"], 2022)
        self.assertEqual(len(result["archives"]), 2)
        objects = pq.read_table(self.output / "release" / "objects.parquet").to_pylist()
        self.assertEqual(
            [json.loads(o["witnesses_json"]) for o in objects],
            [[["ac", "01015", "0002", "0088"]], [["al", "27000", "0001", "0002"]]],
        )
        with zipfile.ZipFile(self.bulk / "files/bu_imgbu_logjez_rdv_vscmr_2022_2t_AC.zip") as z:
            body = z.read("o00407-0101500020088.logjez")
        self.assertEqual(objects[0]["object_sha256"], hashlib.sha256(body).hexdigest())
        sessions = pq.read_table(self.output / "release" / "sessions.parquet").to_pylist()
        self.assertEqual(sum(s["session_kind"] == "official_vota" for s in sessions), 1)
        exported = b"".join(p.read_bytes() for p in (self.output / "release").iterdir())
        self.assertNotIn(TOKEN.encode(), exported)
        again = self.run_bulk(ufs=["ac", "al"], shard_objects=1, resume=True)
        self.assertEqual(again["files"], result["files"])

    def test_bulk_mode_never_reads_2026_and_takes_no_exclusions(self) -> None:
        with self.assertRaisesRegex(ValueError, "certified staging"):
            sp.bulk_archives(self.bulk, 2026, 2)
        with self.assertRaisesRegex(ValueError, "protected"):
            self.run_bulk(exclusions_path="x.json")
        with self.assertRaisesRegex(ValueError, "28 bulk archives"):
            self.run_bulk()
        with self.assertRaisesRegex(ValueError, "exclusions"):
            sp.run_pass(Path(self.temp.name), 2, self.output, year=2022, workers=1)


if __name__ == "__main__":
    unittest.main()


class StagedHashTests(unittest.TestCase):
    def test_a_staged_object_that_changed_is_an_error_not_a_summary(self) -> None:
        # xr1-20261109-P2-01: the parsed bytes are hashed, not trusted by their manifest entry.
        import hashlib
        import tempfile

        from election_audit.semantic_pass import run_shard

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = jez(log_body(["O voto do eleitor foi computado"]))
            (root / "a.jez").write_bytes(body)
            (root / "b.jez").write_bytes(body + b"changed")
            item = {"witnesses": [["ac", "01015", "0002", "0001"]], "package": "Totalizado"}
            digest = hashlib.sha256(body).hexdigest()
            items = [
                {**item, "path": "a.jez", "sha256": digest},
                {**item, "path": "b.jez", "sha256": digest},  # same pin, different bytes
            ]
            (root / "shards").mkdir()
            run_shard((str(root), 2, str(root / "shards"), 0, items, None, 2026))
            objects = pq.read_table(root / "shards" / "00000" / "objects.parquet").to_pylist()
            self.assertEqual([o["status"] for o in objects], ["complete", "error"])
            self.assertIn("certified hash", objects[1]["error"])
