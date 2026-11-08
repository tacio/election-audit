"""Phase 20b: package names verified in the urn logs against TSE's published hash lists.

TSE publishes, per urn model, the SHA-512 (base64) of every file of the urn software
(``path1u13``, ``path1u15``, ``path1u20``, ``path1u22``: an HTML table with a block of base
files and one block per UF). The logs never carry a program hash: they record only that a
package's signature was verified, by name, with its result. So this check can compare names
and results, not bytes:

- H1: every package verified in a log is named in a list, and in which way: ``exact`` (in the
  list of the urn's own model), ``other_model`` (in another model's list: load media carry the
  packages of all four models), ``model_suffix`` (only once the model number is removed from
  the name, e.g. ``avmodue2020.vst`` against ``avmodue.vst``) or ``not_listed``;
- H2: every program package verification ended in ``SUCESSO`` (failures counted per path).

It reads the ``packages`` table of the semantic pass (``session-aggregates-v5``), national
counts of (model, application, stage, path, file, result) with the number of logs.
"""

import hashlib
import html
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.national_migration import atomic, sha
from election_audit.types import JSON

VERSION = "integrity-hash-lists-v1"
LISTS = {"UE2013": "path1u13", "UE2015": "path1u15", "UE2020": "path1u20", "UE2022": "path1u22"}
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
SUFFIX = re.compile(r"20(13|15|20|22)(?=\.vs[tuc]$)")
PATH_SCHEMA = pa.schema(
    [
        ("round", pa.int8()),
        ("model", pa.string()),
        ("application", pa.string()),
        ("stage", pa.string()),
        ("path", pa.string()),
        ("listed", pa.string()),  # exact | other_model | model_suffix | not_listed | data_file
        ("results_json", pa.string()),  # result -> events
        ("events", pa.int64()),
        ("objects", pa.int64()),
    ]
)


def read_list(path: Path) -> dict[str, dict[str, str]]:
    """{block: {file path: SHA-512 base64}} of one hash-list archive (one HTML table)."""
    with zipfile.ZipFile(path) as z:
        pages = [
            i for i in z.infolist() if i.filename.endswith(".html") and "__MACOSX" not in i.filename
        ]
        if len(pages) != 1:
            raise ValueError(f"Expected one HTML page in {path}")
        text = z.read(pages[0]).decode("utf-8")
    blocks: dict[str, dict[str, str]] = defaultdict(dict)
    block = None
    for row in ROW.findall(text):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in CELL.findall(row)]
        if len(cells) == 1:
            block = cells[0]
        elif len(cells) == 2 and block is not None:
            name, digest = cells
            if " - /" in name:  # UF blocks prefix the path with the UF
                name = name.split(" - ", 1)[1]
            blocks[block][name] = digest
    if not blocks:
        raise ValueError(f"No hash rows in {path}")
    return dict(blocks)


def listing(model: str | None, path: str, names: dict[str, set[str]]) -> str:
    if path.endswith(".vsc") or "#" in path:
        return "data_file"
    if model in names and path in names[model]:
        return "exact"
    if any(path in n for n in names.values()):
        return "other_model"
    stripped = SUFFIX.sub("", path)
    if any(stripped in {SUFFIX.sub("", p) for p in n} for n in names.values()):
        return "model_suffix"
    return "not_listed"


def run_hash_lists(
    semantic_roots: Sequence[str | Path], lists_root: str | Path, output: str | Path
) -> JSON:
    """H1-H2 over the package checks of the given semantic-pass releases."""
    lists_root = Path(lists_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    archives = {model: lists_root / f"{stem}.zip" for model, stem in LISTS.items()}
    lists = {model: read_list(path) for model, path in archives.items()}
    names = {model: {p for block in b.values() for p in block} for model, b in lists.items()}
    releases = []
    for root in semantic_roots:
        release = Path(root).expanduser().absolute() / "release"
        manifest = json.loads((release / "manifest.json").read_text())
        if manifest["version"] != "session-aggregates-v5":
            raise ValueError(f"Expected a session-aggregates-v5 release: {release}")
        if manifest["files"]["packages.parquet"]["sha256"] != sha(release / "packages.parquet"):
            raise ValueError(f"Packages table changed: {release}")
        releases.append((manifest["round"], release))
    binding = {
        "version": VERSION,
        "lists": {
            model: {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for model, path in archives.items()
        },
        "list_sizes": {m: {b: len(v) for b, v in blocks.items()} for m, blocks in lists.items()},
        "semantic": {str(r): sha(rel / "manifest.json") for r, rel in releases},
        "compared": "names and verification results only: the logs carry no program hash",
    }
    output.mkdir(parents=True)
    atomic(output / "binding.json", binding)
    grouped: dict[tuple, dict] = {}
    for number, release in releases:
        for r in pq.read_table(release / "packages.parquet").to_pylist():
            key = (number, r["model"], r["application"], r["stage"], r["path"])
            entry = grouped.setdefault(key, {"results": Counter(), "events": 0, "objects": 0})
            entry["results"][r["result"]] += r["events"]
            entry["events"] += r["events"]
            entry["objects"] = max(entry["objects"], r["objects"])  # logs, not per file
    rows = []
    for (number, model, application, stage, path), entry in sorted(
        grouped.items(), key=lambda kv: tuple("" if v is None else str(v) for v in kv[0])
    ):
        rows.append(
            {
                "round": number,
                "model": model,
                "application": application,
                "stage": stage,
                "path": path,
                "listed": listing(model, path, names),
                "results_json": json.dumps(dict(sorted(entry["results"].items()))),
                "events": entry["events"],
                "objects": entry["objects"],
            }
        )
    final = output / ".release.tmp"
    final.mkdir()
    pq.write_table(
        pa.Table.from_pylist(rows, schema=PATH_SCHEMA), final / "paths.parquet", compression="zstd"
    )
    programs = [r for r in rows if r["listed"] != "data_file"]
    failures = Counter()
    for r in programs:
        for result, count in json.loads(r["results_json"]).items():
            if result != "SUCESSO":
                failures[f"{r['path']}:{result}"] += count
    summary = {
        "paths": len(rows),
        "listed": dict(Counter(r["listed"] for r in rows)),
        "not_listed_programs": sorted({r["path"] for r in rows if r["listed"] == "not_listed"}),
        "model_suffix_programs": sorted({r["path"] for r in rows if r["listed"] == "model_suffix"}),
        "program_verification_failures": dict(sorted(failures.items())),
        "models": dict(Counter(str(r["model"]) for r in programs)),
    }
    result = {
        **binding,
        "summary": summary,
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(final.iterdir())
        },
    }
    atomic(final / "manifest.json", result)
    os.replace(final, output / "release")
    return result
