"""xr1 triage: run this project's strict Ed521 verifier on the frozen ed521rs vectors."""

import json
import sys
from pathlib import Path

from election_audit import ed521
from election_audit.ed521_crosscheck import VECTOR_FILES

root = Path(sys.argv[1])
disagree = []
total = 0
for name in VECTOR_FILES:
    for v in json.loads((root / name).read_bytes())["vectors"]:
        key, message, signature = (bytes.fromhex(v[k]) for k in ("key", "message", "signature"))
        ours = ed521.verify(key, signature, message)
        expected = v.get("strict", v.get("valid"))
        total += 1
        if ours != expected:
            disagree.append((name, v["id"], ours, expected))
print(f"{total} vectors, {len(disagree)} where ed521.verify differs from the strict label")
for row in disagree:
    print(row)
