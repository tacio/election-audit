"""Check that wrappers preserve legacy options without touching acquisition."""

import sys
import unittest
from types import SimpleNamespace
from typing import Never
from unittest.mock import patch

from election_audit.cli import main


class CliTests(unittest.TestCase):
    def test_delegation_preserves_options_and_restores_process_arguments(self) -> None:
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

    def test_arguments_restored_when_delegate_exits(self) -> None:
        original = sys.argv

        def fail() -> Never:
            raise SystemExit(2)

        with patch("election_audit.cli.import_module", return_value=SimpleNamespace(main=fail)):
            with self.assertRaises(SystemExit):
                main(["inspect", "--invalid"])
        self.assertIs(sys.argv, original)


class PlatformTests(unittest.TestCase):
    def test_doctor_refuses_platforms_without_the_unix_modules(self) -> None:
        # xr1-20261109-P8-03: native Windows cannot import fcntl or resource.
        import contextlib
        import io

        from election_audit.cli import platform_support

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(platform_support("linux"))
            self.assertTrue(platform_support("darwin"))
            self.assertFalse(platform_support("win32"))
        self.assertIn("UNSUPPORTED", out.getvalue())
