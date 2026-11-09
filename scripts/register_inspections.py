"""Register the sections whose rows were inspected as development data (xr1 P7-11).

The study protocol counts as inspected the rows of integrity checks that disagree or fail.
Its partition generator reads append-only inspection registries keyed by stable location,
so every polling place holding such a section must be registered before Phase 23 draws its
partitions. Each entry anchors to the exact record seen: the file's SHA-256 and a
``path#line`` (JSON lines) or ``path#row`` (Parquet) locator.
"""

import argparse
import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

from election_audit.research_protocol import record_inspection
from election_audit.types import Argv

KEY = ("uf", "municipality", "zone", "section")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def section_rows(path: Path) -> Iterator[tuple[tuple[str, ...], str]]:
    """(section key, locator) for every row that names a section; others are skipped."""
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        for index, row in enumerate(pq.read_table(path, columns=list(KEY)).to_pylist()):
            if all(row.get(k) for k in KEY):
                yield tuple(str(row[k]) for k in KEY), f"{path}#row{index}"
        return
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if all(row.get(k) for k in KEY):
            yield tuple(str(row[k]) for k in KEY), f"{path}#line{number}"


def locations(tables: Sequence[Path]) -> dict[tuple[str, ...], set[str]]:
    """Polling-place keys of each section, from section tables of any round."""
    import pyarrow.parquet as pq

    found: dict[tuple[str, ...], set[str]] = {}
    for table in tables:
        for row in pq.read_table(table, columns=[*KEY, "location_key"]).to_pylist():
            if row["location_key"]:
                found.setdefault(tuple(str(row[k]) for k in KEY), set()).add(row["location_key"])
    return found


def register(
    registry: Path, sources: Sequence[Path], tables: Sequence[Path], reason: str
) -> dict[str, int]:
    places = locations(tables)
    sections, entries, unplaced = set(), set(), set()
    for source in sources:
        digest = sha256(source)
        first: dict[str, str] = {}  # one anchor per place and source
        for key, locator in section_rows(source):
            sections.add(key)
            if key not in places:
                unplaced.add(key)
                first.setdefault(f"section:{':'.join(key)}", locator)
            for place in places.get(key, ()):
                first.setdefault(f"location:{place}", locator)
        for stable_id, locator in first.items():
            evidence = {"object_sha256": digest, "record_locator": locator}
            entries.add(record_inspection(registry, stable_id, reason=reason, evidence=evidence))
    return {"sections": len(sections), "entries": len(entries), "unplaced": len(unplaced)}


def main(argv: Argv = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--section-table", type=Path, action="append", required=True)
    parser.add_argument("sources", type=Path, nargs="+")
    args = parser.parse_args(argv)
    print(json.dumps(register(args.registry, args.sources, args.section_table, args.reason)))


if __name__ == "__main__":
    main()
