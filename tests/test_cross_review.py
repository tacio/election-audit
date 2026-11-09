"""Cross-model review runner: prompt assembly, transcript audit and result extraction."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import cross_review


def write_events(folder: Path, events: list[object]) -> Path:
    path = folder / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\nnot json\n")
    return path


def codex_command(command: str, output: str = "") -> dict[str, object]:
    item = {"type": "command_execution", "command": command, "aggregated_output": output}
    return {"type": "item.completed", "item": item}


def gemini_tool(parameters: dict[str, str], state: str = "ACTIVE") -> dict[str, object]:
    info = {"name": "run_command", "parameters": parameters}
    return {"event": "step_update", "step_update": {"state": state, "tool_info": info}}


class CrossReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)

    def test_every_packet_and_round_prompt_exists(self) -> None:
        self.assertEqual(
            list(cross_review.packets()), ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
        )
        for name in cross_review.ROUNDS:
            self.assertTrue((cross_review.REVIEW / "prompts" / f"{name}.md").exists())
        schema = json.loads(cross_review.SCHEMA.read_text())
        self.assertEqual(schema["properties"]["round"]["enum"], list(cross_review.ROUNDS))

    def test_later_rounds_carry_only_the_packets_ledger_rows(self) -> None:
        campaign = self.folder / "campaigns" / "xr0"
        campaign.mkdir(parents=True)
        rows = [
            {"id": "xr0-P3-01", "packet": "P3", "disposition": "rejected"},
            {"id": "xr0-P3-02", "packet": "P3", "disposition": "confirmed"},
            {"id": "xr0-P7-01", "packet": "P7", "disposition": "confirmed"},
        ]
        (campaign / "ledger.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
        with mock.patch.object(cross_review, "campaign_dir", return_value=campaign):
            first = cross_review.build_prompt("xr0", "R1", "codex", "P3", "abc", None)
            challenge = cross_review.build_prompt("xr0", "R3", "gemini", "P3", "abc", None)
            verify = cross_review.build_prompt("xr0", "R5", "codex", "P3", "def", "abc..def")
            with self.assertRaises(SystemExit):
                cross_review.build_prompt("xr0", "R5", "codex", "P3", "def", None)
        self.assertNotIn("xr0-P3-01", first)
        self.assertIn('reviewer to "codex"', first)
        self.assertIn("xr0-P3-01", challenge)
        self.assertIn("xr0-P3-02", challenge)
        self.assertNotIn("xr0-P7-01", challenge)
        self.assertNotIn("xr0-P3-01", verify)
        self.assertIn("xr0-P3-02", verify)
        self.assertIn("git diff abc..def", verify)

    def test_the_audit_flags_commands_not_their_outputs(self) -> None:
        transcript = write_events(
            self.folder,
            [
                codex_command("cat election_audit/gedai.py", "see ~/data/election-audit-stage"),
                codex_command("ls ~/data/election-audit-stage/phase20b-gedai"),
                codex_command("curl https://example.org"),
                gemini_tool({"CommandLine": "cat /home/someone/data/x.log"}),
                gemini_tool({"CommandLine": "cat /home/someone/data/x.log"}, state="DONE"),
                gemini_tool({"CommandLine": f"ls {cross_review.ROOT}/data"}),
                gemini_tool({"CommandLine": f"ls {cross_review.ROOT}-review/clone"}),
                gemini_tool({"AbsolutePath": "docs/en/semantic-pass.md"}),
            ],
        )
        flagged = cross_review.audit(transcript)
        self.assertEqual(len(flagged), 4)
        self.assertIn("phase20b-gedai", flagged[0])
        self.assertIn("curl", flagged[1])

    def test_the_gemini_result_is_read_from_the_last_result_event(self) -> None:
        report = {"reviewer": "gemini", "findings": []}
        structured = write_events(
            self.folder, [{"event": "init"}, {"result": {"structured_output": report}}]
        )
        self.assertEqual(cross_review.gemini_result(structured), report)
        text = write_events(self.folder, [{"result": {"response": json.dumps(report)}}])
        self.assertEqual(cross_review.gemini_result(text), report)
        broken = write_events(self.folder, [{"result": {"response": "not json"}}])
        self.assertIsNone(cross_review.gemini_result(broken))

    def test_campaign_ids_are_plain(self) -> None:
        with self.assertRaises(SystemExit):
            cross_review.campaign_dir("../escape")


if __name__ == "__main__":
    unittest.main()
