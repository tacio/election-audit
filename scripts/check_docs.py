"""Offline documentation pairing/link checks; never run documented commands."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
META = re.compile(r"^Document-ID: ([A-Z0-9.-]+) · Revision: ([0-9]+) · Language: (en|pt-BR)$", re.M)
FENCES = re.compile(r"^```[^\n]*\n.*?^```[ \t]*$", re.M | re.S)
LINKS = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def document_paths(root: Path) -> list[Path]:
    return sorted(
        [
            *root.glob("README*.md"),
            *root.joinpath("docs").rglob("*.md"),
            *root.joinpath("research").glob("*.md"),
        ]
    )


def fence_signature(block: str) -> tuple[str, ...]:
    """Keep code exact; compare supported Mermaid syntax with labels removed.

    Only labels in recognized flowchart edges and ER relationships may differ.
    Unknown diagram syntax remains exact, so unsupported constructs are never
    silently discarded. Direction, IDs, arrows, cardinality, order and node shape
    declarations remain part of the signature.
    """
    lines = block.splitlines()
    if lines[0] != "```mermaid" or len(lines) < 3:
        return (block,)
    kind = lines[1].strip()
    signature = [lines[0], kind]
    for line in lines[2:-1]:
        stripped = line.strip()
        if kind == "erDiagram":
            edge = re.fullmatch(
                r"([A-Za-z_]\w*)\s+([|o{}]+(?:--|\.\.)[|o{}]+)\s+"
                r"([A-Za-z_]\w*)\s*:\s*.+",
                stripped,
            )
            if edge:
                signature.append(" ".join(edge.groups()))
                continue
        elif re.fullmatch(r"flowchart (?:TB|TD|BT|RL|LR)", kind):
            edge = re.fullmatch(
                r"([A-Za-z_]\w*)(\[[^\[\]\n]*\])?\s*"
                r"(-->|---|-\.->|==>)\s*"
                r"([A-Za-z_]\w*)(\[[^\[\]\n]*\])?",
                stripped,
            )
            if edge:
                source, source_label, arrow, target, target_label = edge.groups()
                signature.append(
                    f"{source}{'[]' if source_label is not None else ''} "
                    f"{arrow} {target}{'[]' if target_label is not None else ''}"
                )
                continue
        signature.append(line)
    signature.append(lines[-1])
    return tuple(signature)


def check_docs(root: Path = ROOT) -> list[str]:
    """Check paired metadata, code examples, Mermaid structure and local links.

    This cannot establish translation quality or execute recipes. Phase 9 can
    extend these checks without running acquisition examples in this checker.
    """
    errors: list[str] = []
    pairs: dict[str, dict[str, tuple[Path, str, str]]] = defaultdict(dict)
    for path in document_paths(root):
        content = path.read_text(encoding="utf-8")
        label = path.relative_to(root)
        metadata = META.search(content)
        if metadata is None:
            errors.append(f"{label}: missing document metadata")
            continue
        identity, revision, language = metadata.groups()
        if language in pairs[identity]:
            errors.append(f"{label}: duplicate {identity}/{language}")
        pairs[identity][language] = path, revision, content
        expected = "pt-BR" if "pt-BR" in path.parts or ".pt-BR." in path.name else "en"
        if language != expected:
            errors.append(f"{label}: language/path mismatch")
        for target in LINKS.findall(FENCES.sub("", content)):
            # Markdown optional link titles are not used in current references.
            target = target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("mailto:"):
                continue
            local = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not local.exists():
                errors.append(f"{label}: missing local link {target}")
                continue
            if parsed.fragment and local.suffix == ".md":
                headings = re.findall(r"^#{1,6} (.+)$", local.read_text(), re.M)
                anchors = set()
                for heading in headings:
                    heading = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                    anchors.add(heading)
                if unquote(parsed.fragment) not in anchors:
                    errors.append(f"{label}: missing local anchor {target}")
    for identity, languages in pairs.items():
        if set(languages) != {"en", "pt-BR"}:
            errors.append(f"{identity}: missing language counterpart")
            continue
        en_path, en_revision, en = languages["en"]
        pt_path, pt_revision, pt = languages["pt-BR"]
        if en_revision != pt_revision:
            errors.append(f"{identity}: revision mismatch")
        if [fence_signature(block) for block in FENCES.findall(en)] != [
            fence_signature(block) for block in FENCES.findall(pt)
        ]:
            errors.append(f"{identity}: fenced examples differ")
        if en_path.parent.name == "en" and pt_path != root / "docs" / "pt-BR" / en_path.relative_to(
            root / "docs" / "en"
        ):
            errors.append(f"{identity}: parallel paths differ")
    return errors


def main() -> int:
    errors = check_docs()
    for error in errors:
        print(error)
    if not errors:
        print(
            "Documentation pairs, revisions, local links, code examples and Mermaid structure valid."
        )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
