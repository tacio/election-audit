"""Check real pairs plus intentional failures without invoking document commands."""

import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import check_docs, fence_signature


class DocumentationTests(unittest.TestCase):
    def test_repository_pairs_and_links(self):
        self.assertEqual(check_docs(), [])

    def test_reject_revision_example_and_broken_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for language, revision, command in (
                ("en", 1, "safe-example"),
                ("pt-BR", 2, "different"),
            ):
                path = root / "docs" / language / "example.md"
                path.parent.mkdir(parents=True)
                path.write_text(
                    f"# Example\n\nDocument-ID: EA-EXAMPLE · Revision: {revision} · Language: {language}\n\n"
                    f"[missing](absent.md)\n\n```sh\n{command}\n```\n"
                )
            errors = check_docs(root)
            self.assertTrue(any("revision mismatch" in e for e in errors))
            self.assertTrue(any("fenced examples differ" in e for e in errors))
            self.assertEqual(sum("missing local link" in e for e in errors), 2)

    def test_translated_mermaid_labels_preserve_graph_structure(self):
        english = (
            "```mermaid\nflowchart LR\n"
            "    inputs[Explicit sources] --> ready[Feature readiness]\n```\n\n"
            "```mermaid\nerDiagram\n"
            "    snapshot ||--o{ observation : freezes\n```\n"
        )
        portuguese = (
            "```mermaid\nflowchart LR\n"
            "    inputs[Fontes explícitas] --> ready[Prontidão dos atributos]\n```\n\n"
            "```mermaid\nerDiagram\n"
            "    snapshot ||--o{ observation : congela\n```\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for language, diagrams in (("en", english), ("pt-BR", portuguese)):
                path = root / "docs" / language / "diagram.md"
                path.parent.mkdir(parents=True)
                paths[language] = path
                path.write_text(
                    f"# Diagram\n\nDocument-ID: EA-DIAGRAM · Revision: 1 · Language: {language}\n\n"
                    + diagrams
                )
            self.assertEqual(check_docs(root), [])
            original = paths["pt-BR"].read_text()
            for before, after in (
                ("inputs[", "other["),
                ("-->", "---"),
                ("flowchart LR", "flowchart RL"),
                ("||--o{", "||--||"),
                ("observation :", "other :"),
                ("    snapshot ||--o{ observation : congela\n", ""),
            ):
                with self.subTest(change=(before, after)):
                    paths["pt-BR"].write_text(original.replace(before, after))
                    self.assertTrue(any("fenced examples differ" in e for e in check_docs(root)))

    def test_unsupported_mermaid_constructs_are_compared_exactly(self):
        english = "```mermaid\nsequenceDiagram\n    A->>B: evidence\n```"
        portuguese = "```mermaid\nsequenceDiagram\n    A->>B: evidência\n```"
        self.assertNotEqual(fence_signature(english), fence_signature(portuguese))
