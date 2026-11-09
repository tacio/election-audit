"""xr1 R4: rehash the recorded inputs that two stages trusted by their manifest entry.

- Staged log objects (codex-P2-01): every object of a semantic release, against the digest the
  release recorded for it.
- BWEB archives (codex-P0-01): every complete file of the BWEB input root, against its manifest.

Usage: rehash_inputs.py OUTPUT.json SEMANTIC_RELEASE [SEMANTIC_RELEASE ...] --bweb ROOT
Writes counts and every mismatch; never writes next to the inputs.
"""

import hashlib
import json
import sqlite3
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pyarrow.parquet as pq


def digest(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def check(pairs: list[tuple[str, str]], workers: int = 4) -> dict:
    with Pool(workers) as pool:
        found = pool.map(digest, [p for p, _ in pairs], chunksize=256)
    bad = [p for (p, want), got in zip(pairs, found, strict=True) if got != want]
    return {"checked": len(pairs), "mismatched_or_missing": len(bad), "examples": bad[:20]}


def main() -> None:
    output, args = Path(sys.argv[1]), sys.argv[2:]
    if output.exists():
        raise SystemExit(f"Output must be new: {output}")
    bweb = args[args.index("--bweb") + 1]
    releases = args[: args.index("--bweb")]
    result, start = {}, time.monotonic()
    for release in releases:
        root = Path(release)
        staged = Path(json.loads((root.parent / "binding.json").read_text())["staged_root"])
        rows = pq.read_table(root / "objects.parquet", columns=["object_sha256", "path"])
        pairs = [(str(staged / r["path"]), r["object_sha256"]) for r in rows.to_pylist()]
        result[release] = check(pairs)
    uri = (Path(bweb) / "manifest.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as db:
        pairs = [
            (str(Path(bweb) / p), d)
            for p, d in db.execute("SELECT path, sha256 FROM files WHERE status='complete'")
        ]
    result[bweb] = check(pairs)
    result["seconds"] = round(time.monotonic() - start, 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
