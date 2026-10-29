"""Check that wrappers preserve legacy options without touching acquisition."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from election_audit.cli import main


class CliTests(unittest.TestCase):
    def test_delegation_preserves_options_and_restores_process_arguments(self):
        original = sys.argv
        for command, module, options, expected in (
            (
                "download",
                "download_tse_logs",
                ["--ufs", "ac", "--limit", "5"],
                ["--ufs", "ac", "--limit", "5"],
            ),
            (
                "resume",
                "download_tse_logs",
                ["--output", "/tmp/corpus"],
                ["--missing-only", "--output", "/tmp/corpus"],
            ),
            ("inspect", "inspect_tse_logs", ["--per-uf", "2"], ["--per-uf", "2"]),
        ):
            with self.subTest(command=command):
                seen = []
                delegate = SimpleNamespace(main=lambda: seen.append(sys.argv[:]))
                with patch("election_audit.cli.import_module", return_value=delegate) as imported:
                    main([command, *options])
                imported.assert_called_once_with(f"scripts.{module}")
                self.assertEqual(seen, [[f"election-audit {command}", *expected]])
                self.assertIs(sys.argv, original)

    def test_arguments_restored_when_delegate_exits(self):
        original = sys.argv

        def fail():
            raise SystemExit(2)

        with patch("election_audit.cli.import_module", return_value=SimpleNamespace(main=fail)):
            with self.assertRaises(SystemExit):
                main(["inspect", "--invalid"])
        self.assertIs(sys.argv, original)
