"""Strict, pinned relocation of external original references; never falls back."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from election_audit.national_migration import file_stat, sha

type Roots = dict[str, tuple[Path, sqlite3.Connection]]

_CACHE: tuple[tuple[str, str | None], Roots] | None = None


def configure(path: str | Path, expected_sha: str) -> None:
    path = str(Path(path).absolute())
    if Path(path).is_symlink() or sha(path) != expected_sha:
        raise ValueError("Verified relocation registry checksum mismatch")
    os.environ["ELECTION_AUDIT_RELOCATION"] = path
    os.environ["ELECTION_AUDIT_RELOCATION_SHA256"] = expected_sha


def _load() -> Roots | None:
    global _CACHE
    path = os.environ.get("ELECTION_AUDIT_RELOCATION")
    if not path:
        return None
    expected = os.environ.get("ELECTION_AUDIT_RELOCATION_SHA256")
    key = (path, expected)
    if _CACHE and _CACHE[0] == key:
        return _CACHE[1]
    if not expected or Path(path).is_symlink() or sha(path) != expected:
        raise ValueError("Unpinned or modified relocation registry")
    doc = json.loads(Path(path).read_bytes())
    if doc["version"] != "verified-source-relocation-v1":
        raise ValueError("Unsupported relocation registry")
    roots = {}
    for certificate in doc["certificates"]:
        root = Path(certificate["root"])
        anchor = Path(certificate["mount"])
        if (
            not anchor.is_mount()
            or list((root.stat().st_dev, root.stat().st_ino)) != certificate["root_identity"]
            or root.stat().st_dev != anchor.stat().st_dev
        ):
            raise ValueError("Verified relocated source mount/root changed")
        ledger = Path(certificate["ledger"])
        if (
            ledger.is_symlink()
            or sha(ledger) != certificate["ledger_sha256"]
            or any(
                Path(str(ledger) + suffix).exists() and Path(str(ledger) + suffix).stat().st_size
                for suffix in ("-wal", "-journal")
            )
        ):
            raise ValueError("Verified relocation ledger changed")
        db = sqlite3.connect(ledger.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.execute("PRAGMA cache_size=-4096")
        binding = json.loads(db.execute("SELECT value FROM binding").fetchone()[0])
        for name in ("manifest_sha256", "identity", "root", "root_identity", "mount"):
            if binding[name] != certificate[name]:
                raise ValueError("Relocation certificate does not bind its verification ledger")
        if db.execute("SELECT count(*) FROM verified").fetchone()[0] != certificate["objects"]:
            raise ValueError("Relocation certificate object count mismatch")
        for alias in (certificate["old_root"], certificate["root"]):
            alias = os.path.abspath(alias)
            if alias in roots:
                raise ValueError("Ambiguous relocation alias")
            roots[alias] = (root, db)
    if _CACHE:
        for _, db in set(_CACHE[1].values()):
            db.close()
    _CACHE = (key, roots)
    return roots


def relocated_root(root: str | Path, relative: str | Path, object_sha: str, size: int) -> Path:
    """Resolve old or new roots before touching their filesystem, with no fallback."""
    roots = _load()
    if roots is None:
        return Path(root).resolve()
    alias = os.path.abspath(root)
    if alias not in roots:
        raise ValueError("Original root is not in the pinned relocation registry")
    new, db = roots[alias]
    row = db.execute(
        "SELECT sha,size,dev,ino,mtime,ctime FROM verified WHERE path=?", (str(relative),)
    ).fetchone()
    if row is None or row[:2] != (object_sha, size):
        raise ValueError("Original content is absent from verified relocated corpus")
    if file_stat(new, relative) != (row[2], row[3], size, row[4], row[5]):
        raise ValueError("Verified relocated original changed")
    return new
