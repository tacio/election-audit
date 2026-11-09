"""Phase 20b signature-error rules (O19) over semantic-pass markers and sessions."""

import json
import unittest
from typing import Any

from election_audit.signature_errors import error_class, section_rules

VERIFY = "Inicialização do aplicativo | Validando assinaturas (#) | Erro na verificação"
SIGN = "Erro na assinatura |  (#) | Ocorreu um erro durante a assinatura do arquivo: RDV MI"


def marker(template: str, line: int, *, before: int = 0, **extra: Any) -> dict[str, Any]:
    row = {
        "object_sha256": "o",
        "stream_ordinal": 0,
        "segment_ordinal": 1,
        "session_ordinal": None,
        "device_id": "d1",
        "template": template,
        "line": line,
        "reading": "2026-10-25T09:00:00",
        "completions_before": before,
        "context": "official_round_2",
        "block_start": "b1",
        "rank": 1,
    }
    return row | extra


def session(ordinal: int, done: int, **extra: Any) -> dict[str, Any]:
    row = {
        "object_sha256": "o",
        "stream_ordinal": 0,
        "segment_ordinal": 1,
        "session_ordinal": ordinal,
        "session_kind": "official_vota",
        "session_round": 2,
        "done": done,
    }
    return row | extra


class SignatureErrorRuleTests(unittest.TestCase):
    def rules(self, markers: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> Any:
        result = section_rules(markers, sessions, 2)
        return result["row"], json.loads(result["row"]["failed_json"]), result["errors"]

    def test_templates_are_classed_by_what_failed(self) -> None:
        self.assertEqual(error_class(VERIFY), "verification")
        self.assertEqual(error_class("Falha ao validar assinatura UE pacote"), "verification")
        self.assertEqual(error_class(SIGN), "signing")
        self.assertEqual(
            error_class("MSD com problema ao assinar.: Erro ao inicializar"), "signing"
        )

    def test_a_startup_error_followed_by_a_restart_passes_and_counts_the_votes(self) -> None:
        # Error before the first session; the urn restarts and records 40 votes.
        row, failed, errors = self.rules([marker(VERIFY, 10)], [session(1, 40)])
        self.assertEqual(failed, [])
        self.assertEqual((row["verification_errors"], row["votes_later"]), (1, 40))
        self.assertIsNone(row["votes_same_session_after_verification"])
        self.assertFalse(errors[0]["in_session"])

    def test_e1_fails_votes_in_the_session_of_a_verification_error(self) -> None:
        sessions = [session(1, 10), session(2, 5)]
        restarted = marker(VERIFY, 50, before=10, session_ordinal=1)
        row, failed, _ = self.rules([restarted], sessions)
        self.assertEqual((failed, row["votes_later"]), ([], 5))
        continued = marker(VERIFY, 50, before=7, session_ordinal=1)
        row, failed, _ = self.rules([continued], sessions)
        self.assertEqual((failed, row["votes_same_session_after_verification"]), (["E1"], 3))

    def test_e2_allows_only_the_cycle_in_flight_after_a_signing_error(self) -> None:
        sessions = [session(1, 14), session(2, 239, segment_ordinal=2)]
        row, failed, _ = self.rules([marker(SIGN, 70, before=13, session_ordinal=1)], sessions)
        self.assertEqual(failed, [])
        self.assertEqual((row["votes_same_session_after_signing"], row["votes_later"]), (1, 239))
        _, failed, _ = self.rules([marker(SIGN, 70, before=12, session_ordinal=1)], sessions)
        self.assertEqual(failed, ["E2"])

    def test_memory_copies_count_once_and_other_contexts_are_ignored(self) -> None:
        copy = marker(VERIFY, 10, object_sha256="o2")
        other = marker(VERIFY, 3, context="other_context", block_start="b0")
        sessions = [session(1, 40), session(1, 38, object_sha256="o2")]
        row, failed, errors = self.rules([marker(VERIFY, 10), copy, other], sessions)
        self.assertEqual((len(errors), row["verification_errors"]), (1, 1))
        self.assertEqual(row["votes_later"], 40)  # the longer copy
        self.assertEqual(failed, [])

    def test_later_blocks_of_another_round_or_kind_are_not_counted(self) -> None:
        sessions = [
            session(1, 0),
            session(2, 9, segment_ordinal=2),
            session(3, 4, segment_ordinal=3, session_round=1),
            session(4, 6, segment_ordinal=4, session_kind="unresolved"),
        ]
        row, _, _ = self.rules([marker(VERIFY, 10, session_ordinal=1)], sessions)
        self.assertEqual(row["votes_later"], 9)

    def test_e3_fails_votes_before_the_next_restart(self) -> None:
        # xr1-20261109-P4-03: votes later in the block are not proof of a restart.
        restarted = marker(VERIFY, 10, votes_without_restart=0, restart_line=20)
        row, failed, _ = self.rules([restarted], [session(1, 40)])
        self.assertEqual((failed, row["votes_without_restart_after_verification"]), ([], 0))
        continued = marker(VERIFY, 10, votes_without_restart=40, restart_line=None)
        row, failed, _ = self.rules([continued], [session(1, 40)])
        self.assertEqual(failed, ["E3"])
        in_flight = marker(SIGN, 70, before=13, session_ordinal=1, votes_without_restart=1)
        _, failed, _ = self.rules([in_flight], [session(1, 14)])
        self.assertEqual(failed, [])
        unknown = marker(VERIFY, 10)  # no reread: unavailable, never a pass by default
        row, failed, _ = self.rules([unknown], [session(1, 40)])
        self.assertEqual((failed, row["restart_unavailable"]), ([], 1))

    def test_restart_evidence_reads_the_streams_next_gap_start(self) -> None:
        from test_semantic_pass import jez, log_body

        from election_audit.signature_errors import restart_evidence

        vote = "O voto do eleitor foi computado"
        body = log_body([vote]) + log_body([vote], start=10)  # lines 1-4, then GAP at 5
        found = restart_evidence(
            jez(body), [{"stream_ordinal": 0, "line": 3}, {"stream_ordinal": 0, "line": 6}]
        )
        self.assertEqual(found[(0, 3)], {"votes_without_restart": 1, "restart_line": 5})
        self.assertEqual(found[(0, 6)], {"votes_without_restart": 1, "restart_line": None})

    def test_counts_that_do_not_add_up_are_reported(self) -> None:
        row, _, errors = self.rules([marker(VERIFY, 10, before=5)], [session(1, 2)])
        self.assertEqual(row["inconsistent_counts"], 1)
        self.assertTrue(errors[0]["inconsistent"])


if __name__ == "__main__":
    unittest.main()
