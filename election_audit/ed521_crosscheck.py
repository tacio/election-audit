"""Phase 20b: our Ed521 verdicts against DataUrnas-BR's verifier on the same signatures.

The section pass (``integrity_checks.check_section``) runs unchanged over every section of one
round. Each Ed521 verdict it reaches (urn hardware signatures on the signature list, the files
and the BU vote-hash chain, and the ``AC UE2020``/``AC UE2022`` signatures on urn certificates)
is handed through ``election_audit.ed521.observer`` to this pass, which checks the same key,
message and signature again with DataUrnas-BR's ``verificar`` (``src/dataurnas/parsers/ed521.py``,
pure Python, loaded unmodified from a pinned file). Our verdict is ``ed521rs`` in strict mode.

Crafted edge cases (ed521rs's vectors: non-canonical encodings, S at and above L, small-order
points) are run through the same reference, recording which of ed521rs's two modes (strict, as
``election_audit.ed521``; ``ecpy``, as TSE's reference verifier) each of its verdicts matches.

Outputs hold counts and, for any signature where the verdicts differ, its section, key, message
and signature (public values). No vote counts are written.
"""

import importlib.util
import json
import multiprocessing
import os
import shutil
import threading
import time
from collections import Counter
from collections.abc import Callable, Collection, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

from election_audit import ed521
from election_audit import integrity_checks as ic
from election_audit.elections import election_for_round
from election_audit.national_migration import atomic, sha
from election_audit.semantic_pass import verified_bulk_archives
from election_audit.types import JSON, Row

VERSION = "ed521-crosscheck-v1"
VECTOR_FILES = ("edge-cases.json", "ecpy.json", "tse-2026.json")

type Reference = Callable[[bytes, bytes, bytes], bool]
type Task = tuple[str, int, list[Row], list[tuple[dict[str, bytes], dict[str, bytes]]], int, str]

_reference: Reference | None = None


def load_reference(path: Path, expected_sha256: str | None = None) -> Reference:
    """DataUrnas-BR's ``verificar(chave_publica, mensagem, assinatura)``, from a pinned file."""
    digest = sha(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"{path} changed: {digest} != {expected_sha256}")
    spec = importlib.util.spec_from_file_location("dataurnas_ed521_reference", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verificar


def run_vectors(reference: Reference, vectors: Path) -> JSON:
    """The reference's verdict on each vector, beside the verdicts the vector records."""
    rows, counts = [], Counter()
    for name in VECTOR_FILES:
        for v in json.loads((vectors / name).read_bytes())["vectors"]:
            key, message, signature = (bytes.fromhex(v[k]) for k in ("key", "message", "signature"))
            theirs = bool(reference(key, message, signature))
            expected = {m: v[m] for m in ("strict", "ecpy", "valid") if m in v}
            if "valid" in expected:  # real or published signatures: one verdict for every mode
                expected = {"strict": expected["valid"], "ecpy": expected["valid"]}
            matches = sorted(m for m, verdict in expected.items() if verdict == theirs)
            counts["+".join(matches) or "neither"] += 1
            rows.append(
                {
                    "file": name,
                    "id": v["id"],
                    "dataurnas": theirs,
                    "strict": expected["strict"],
                    "ecpy": expected["ecpy"],
                    "matches": matches,
                }
            )
    return {"vectors": rows, "matches": dict(sorted(counts.items()))}


def _init_worker(reference: str, expected_sha256: str) -> None:
    global _reference
    ic._init_worker()
    _reference = load_reference(Path(reference), expected_sha256)


def run_shard(task: Task) -> tuple[int, int, int]:
    shard_dir, index, items, bodies, pleito, election_date = task
    assert _reference is not None  # loaded by _init_worker
    seen: list[tuple[str, bytes, bytes, bytes, bool]] = []
    ed521.observer = lambda *verdict: seen.append(verdict)
    counts: Counter[str] = Counter()
    sections: Counter[str] = Counter()
    disagreements, errors = [], 0
    for item, (blobs, published) in zip(items, bodies, strict=True):
        seen.clear()
        try:
            ic.check_section(item, blobs, published, pleito, election_date)
        except Exception:  # the section pass records these; here they only lose coverage
            errors += 1
        kinds = set()
        for kind, key, message, signature, ours in seen:
            theirs = bool(_reference(key, message, signature))
            kinds.add(kind)
            verdict = "valid" if ours else "invalid"
            counts[f"{kind}:{verdict}:{'agree' if ours == theirs else 'differ'}"] += 1
            if ours != theirs:
                disagreements.append(
                    {
                        "section": "/".join(item["key"]),
                        "kind": kind,
                        "ours": ours,
                        "dataurnas": theirs,
                        "key": key.hex(),
                        "message": message.hex(),
                        "signature": signature.hex(),
                    }
                )
        sections["with_urn_ed521" if "urn" in kinds else "without_urn_ed521"] += 1
    ed521.observer = None
    body = {
        "sections": len(items),
        "section_errors": errors,
        "section_kinds": dict(sections),
        "signatures": dict(counts),
        "disagreements": disagreements,
    }
    temporary = Path(shard_dir) / f".{index:05d}.tmp"
    temporary.write_text(json.dumps(body, sort_keys=True))
    os.replace(temporary, Path(shard_dir) / f"{index:05d}.json")
    return index, len(items), errors


def run_crosscheck(
    bulk_root: str | Path,
    round_number: int,
    output: str | Path,
    *,
    reference: str | Path,
    vectors: str | Path,
    reference_label: str,
    workers: int = 4,
    ufs: Collection[str] | None = None,
    limit: int | None = None,
    resume: bool = False,
) -> JSON:
    """Run the cross-check of one round into a new (or resumed) output root."""
    bulk_root = Path(bulk_root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    reference = Path(reference).expanduser().absolute()
    vectors = Path(vectors).expanduser().absolute()
    archives = verified_bulk_archives(bulk_root, 2026, round_number, set(ufs) if ufs else None)
    election = election_for_round(round_number, 2026)
    pleito = int(election.pleito_code)
    binding = {
        "version": VERSION,
        "section_checks": ic.VERSION,
        "round": round_number,
        "pleito": pleito,
        "bulk_root": str(bulk_root),
        "archives": {a["path"]: {"sha256": a["sha256"], "bytes": a["bytes"]} for a in archives},
        "pki": ic.urn_pki.manifest()["files"],
        "ours": {k: v for k, v in ic.ed521_implementation().items() if k != "backend"},
        "reference": {"path": str(reference), "sha256": sha(reference), "label": reference_label},
        "vectors": {name: sha(vectors / name) for name in VECTOR_FILES},
        "vectors_root": str(vectors),
        "ufs": sorted(ufs) if ufs else None,
        "limit": limit,
        "shard_sections": ic.SHARD_SECTIONS,
        "logs": "hashed with SHA-512 only; never parsed (protected sections included)",
    }
    if output.exists() and not resume:
        raise FileExistsError(f"Output must be new (or pass --resume): {output}")
    if resume and json.loads((output / "binding.json").read_bytes()) != binding:
        raise ValueError("Resume binding differs from the original pass")
    output.mkdir(parents=True, exist_ok=resume)
    atomic(output / "binding.json", binding)
    atomic(
        output / "vectors.json",
        run_vectors(load_reference(reference, binding["reference"]["sha256"]), vectors),
    )
    shard_dir = output / "shards"
    shard_dir.mkdir(exist_ok=True)
    items, _ = ic.section_work_list(bulk_root, archives, 2026, round_number, limit=limit)
    size = ic.SHARD_SECTIONS
    shards = [items[i : i + size] for i in range(0, len(items), size)]
    done = {int(p.stem) for p in shard_dir.glob("[0-9]*.json")}
    todo = [i for i in range(len(shards)) if i not in done]
    gate = threading.BoundedSemaphore(workers + 2)

    def tasks() -> Iterator[Task]:
        for i in todo:
            gate.acquire()
            body = ic.read_shard(bulk_root, shards[i])
            yield str(shard_dir), i, shards[i], body, pleito, election.election_date

    started, finished = time.monotonic(), sum(len(shards[i]) for i in done)

    def report(stage: str, **extra: Any) -> None:
        atomic(
            output / "status.json",
            {
                "stage": stage,
                "sections_total": len(items),
                "sections_done": finished,
                "shards_total": len(shards),
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "pid": os.getpid(),
                **extra,
            },
        )

    report("running")
    with multiprocessing.get_context("spawn").Pool(
        workers,
        initializer=_init_worker,
        initargs=(str(reference), binding["reference"]["sha256"]),
        maxtasksperchild=100,
    ) as pool:
        for _, count, _ in pool.imap_unordered(run_shard, tasks()):
            gate.release()
            finished += count
            report("running")
    report("merging")
    result = merge(output, len(shards), binding)
    report("finished", **result["summary"])
    return result


def merge(output: Path, shard_count: int, binding: JSON) -> JSON:
    signatures: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    sections = errors = 0
    lines = []
    for i in range(shard_count):
        body = json.loads((output / "shards" / f"{i:05d}.json").read_bytes())
        sections += body["sections"]
        errors += body["section_errors"]
        signatures.update(body["signatures"])
        kinds.update(body["section_kinds"])
        lines += [json.dumps(d, sort_keys=True) + "\n" for d in body["disagreements"]]
    final = output / ".release.tmp"
    shutil.rmtree(final, ignore_errors=True)
    final.mkdir()
    (final / "disagreements.jsonl").write_text("".join(lines))
    shutil.copy2(output / "vectors.json", final / "vectors.json")
    summary = {
        "sections": sections,
        "section_errors": errors,
        "section_kinds": dict(sorted(kinds.items())),
        "signatures": dict(sorted(signatures.items())),
        "signatures_checked": sum(signatures.values()),
        "disagreements": len(lines),
        "vector_matches": json.loads((output / "vectors.json").read_bytes())["matches"],
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
