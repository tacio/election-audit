"""Exact documented operational semantics with source-byte join and explicit readiness."""

import json
import tempfile
import unittest
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from election_audit.archive_parsing import inspect_artifact, parse_object
from election_audit.national import _compact_jsonl, _write_json
from election_audit.operational_review import classify, review_object
from election_audit.source_inventory import hash_file


class OperationalReviewTests(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        messages: Iterable[str],
        *,
        official: bool = True,
        date: str = "25/10/2026",
        round_number: int = 2,
    ) -> tuple[Path, Path]:
        original = root / "source.jez"
        prefix = [
            (
                "GAP",
                f"Iniciando aplicação - ELEIÇÃO OFICIAL {'SEGUNDO' if round_number == 2 else 'PRIMEIRO'} TURNO - {round_number}º turno",
            )
        ]
        if not official:
            prefix = [("GAP", "Iniciando aplicação - ELEIÇÃO SIMULADA SEGUNDO TURNO - 2º turno")]
        records = (
            prefix
            + [
                ("VOTA", f"Iniciando aplicação - {round_number}º turno"),
                ("VOTA", "Versão da aplicação: 10.23.0.0 - Praia da Barra do Cahy"),
            ]
            + [("VOTA", x) for x in messages]
        )
        body = "".join(
            f"{date} 10:00:{i:02d}\tINFO\t12345678\t{app}\t{message}\t0000000000000000\n"
            for i, (app, message) in enumerate(records)
        ).encode("latin-1")
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("logd.dat", body)
        parsed, _ = parse_object(original, root / "parse", expected_sha256=hash_file(original)[0])
        inspect_artifact(parsed)
        structural = root / "structural"
        structural.mkdir()
        for name in ("events", "issues"):
            _compact_jsonl(parsed / (name + ".jsonl"), structural / (name + ".parquet"), 2048)
        specs = {
            f: dict(zip(("sha256", "bytes"), hash_file(structural / f), strict=True))
            for f in ("events.parquet", "issues.parquet")
        }
        _write_json(
            structural / "artifact.json",
            {
                "object_sha256": hash_file(original)[0],
                "source_bytes": original.stat().st_size,
                "files": specs,
            },
        )
        return original, structural

    def rows(self, path: Path, name: str) -> list[Any]:
        return [
            json.loads(r) for r in pq.read_table(path / (name + ".parquet")).column(0).to_pylist()
        ]

    def test_official_biometric_manual_partial_and_full_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, structural = self.fixture(
                root,
                [
                    "Tipo de habilitação do eleitor [biométrica]",
                    "Eleitor foi habilitado",
                    "Voto confirmado para [Presidente]",
                    "O voto do eleitor foi computado",
                    "Solicitação de dado pessoal do eleitor para habilitação manual",
                    "Mesário 000000000001 habilitou o eleitor",
                    "Eleitor foi habilitado",
                    "Eleitor votou parcialmente e em seguida foi suspenso",
                    "O voto do eleitor foi computado",
                    "Eleitor foi habilitado",
                    "Eleitor foi suspenso e não confirmou nenhum voto",
                    "Procedimento de encerramento confirmado",
                ],
            )
            events = [
                json.loads(r)
                for r in pq.read_table(structural / "events.parquet").column(0).to_pylist()
            ]
            clock = {
                "timezone": "America/Rio_Branco",
                "adjustment_seconds": 0,
                "continuity": True,
                "evidence": {
                    "review_state": "reviewed",
                    "rule_id": "fixture-clock-v1",
                    "event_ids": [r["event_id"] for r in events],
                    "anchors": [
                        {
                            "event_id": events[0]["event_id"],
                            "source_line_sha256": events[0]["source_line_sha256"],
                        }
                    ],
                },
            }
            result = review_object(
                structural,
                source,
                root / "out",
                clock=clock,
            )
            cycles = self.rows(result, "cycles")
            self.assertEqual(
                [r["completion_state"] for r in cycles], ["completed", "completed", "suspended"]
            )
            self.assertEqual(
                [r["authorization_method"] for r in cycles], ["biometric", "manual", "unknown"]
            )
            self.assertEqual(cycles[0]["duration_seconds"], 2)
            self.assertIsNone(cycles[1]["duration_seconds"])
            self.assertEqual(self.rows(result, "sessions")[0]["session_kind"], "official_vota")
            self.assertEqual(
                result,
                review_object(
                    structural,
                    source,
                    root / "out",
                    clock=clock,
                ),
            )
            self.assertNotIn("000000000001", (result / "artifact.json").read_text())
            self.assertNotIn(
                "000000000001",
                "".join(pq.read_table(result / "events.parquet").column(0).to_pylist()),
            )

    def test_request_failure_not_manual_vote_unknown_clock_stays_null(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, structural = self.fixture(
                root,
                [
                    "Solicitação de dado pessoal do eleitor para habilitação manual",
                    "Identificador do eleitor digitado inválido",
                    "Eleitor foi habilitado",
                    "O voto do eleitor foi computado",
                ],
            )
            result = review_object(structural, source, root / "out")
            cycles = self.rows(result, "cycles")
            self.assertEqual(cycles[0]["completion_state"], "cancelled")
            self.assertEqual(cycles[1]["authorization_method"], "unknown")
            self.assertIsNone(cycles[1]["duration_seconds"])

    def test_simulated_or_other_round_never_official(self) -> None:
        for official, date, round_number in [(False, "25/10/2026", 2), (True, "04/10/2026", 1)]:
            with (
                self.subTest(official=official, round_number=round_number),
                tempfile.TemporaryDirectory() as d,
            ):
                root = Path(d)
                source, structural = self.fixture(
                    root,
                    ["Eleitor foi habilitado", "O voto do eleitor foi computado"],
                    official=official,
                    date=date,
                    round_number=round_number,
                )
                result = review_object(structural, source, root / "out", round_number=2)
                self.assertEqual(self.rows(result, "cycles"), [])

    def test_first_round_is_supported_with_its_own_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, structural = self.fixture(
                root,
                ["Eleitor foi habilitado", "O voto do eleitor foi computado"],
                date="04/10/2026",
                round_number=1,
            )
            result = review_object(structural, source, root / "out", round_number=1)
            self.assertEqual(len(self.rows(result, "cycles")), 1)

    def test_exact_rules_unknown_templates_and_corruption(self) -> None:
        self.assertEqual(classify("VOTA", "prefix Eleitor foi habilitado"), ("unknown", None))
        self.assertEqual(classify("OTHER", "Eleitor foi habilitado"), ("other_application", None))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, structural = self.fixture(
                root, ["Eleitor foi habilitado", "O voto do eleitor foi computado"]
            )
            source.write_bytes(source.read_bytes() + b"x")
            with self.assertRaisesRegex(ValueError, "hash/size"):
                review_object(structural, source, root / "out")
