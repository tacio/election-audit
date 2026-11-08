"""Portable, bounded, checksummed exploration datasets; no live acquisition reads."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Self
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import urlopen

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from election_audit.types import JSON, Row, one

VERSION = "audit-dashboard-data-v1"
MAX_MANIFEST = 4 * 1024**2
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
DIMENSIONS = (
    "uf",
    "municipality_tse",
    "zone",
    "round",
    "readiness",
    "location_id",
    "partition_name",
    "record_kind",
    "feature_id",
    "component",
)
TABLES = {
    "coverage": "operational_coverage",
    "electoral": "section_results",
    "unanimity": "unanimous_results",
    "rounds": "round_comparison",
    "operations": "session_summaries",
    "late": "late_voting",
    "timing": "result_timing",
    "reconciliation": "result_reconciliation",
    "hierarchy": "hierarchy_reconciliation",
    "features": "audit_features",
    "models": "analysis_ledger",
    "impact": "impact_scenario",
}


def _json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Dataset paths must be relative")
    decoded = unquote(value)
    parsed = urlsplit(decoded)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or decoded.startswith("/")
        or ".." in Path(decoded).parts
    ):
        raise ValueError("Dataset path escapes its manifest")
    return decoded


class AuditDataset:
    """Read only manifest-declared Parquet files with bounded verified caching."""

    @classmethod
    def open(
        cls,
        uri: str | Path,
        *,
        cache: str | Path | None = None,
        cache_bytes: int = 256 * 1024**2,
        allow_http: bool = False,
    ) -> Self:
        return cls(uri, cache=cache, cache_bytes=cache_bytes, allow_http=allow_http)

    def __init__(
        self,
        uri: str | Path,
        *,
        cache: str | Path | None = None,
        cache_bytes: int = 256 * 1024**2,
        allow_http: bool = False,
    ) -> None:
        self.uri = str(uri)
        parsed = urlsplit(self.uri)
        self.remote = parsed.scheme in {"https", "http"}
        if parsed.scheme == "http" and not (
            allow_http and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Only HTTPS dataset URLs are accepted outside loopback tests")
        if parsed.scheme and not self.remote:
            raise ValueError("Dataset must be a local manifest or HTTPS URL")
        if self.remote:
            body = self._download(self.uri, MAX_MANIFEST)
        else:
            path = Path(self.uri).expanduser().resolve()
            if path.is_dir():
                path /= "dataset.json"
            self.uri = str(path)
            if path.stat().st_size > MAX_MANIFEST:
                raise ValueError("Dataset manifest exceeds limit")
            body = path.read_bytes()
        self.manifest = json.loads(body)
        if self.manifest.get("version") != VERSION:
            raise ValueError("Unsupported dashboard dataset")
        if self.manifest.get("access_state") not in {
            "development_only",
            "final_evaluated",
            "exploratory_unpartitioned",
        }:
            raise ValueError("Dataset must explicitly declare outcome access state")
        self.manifest_sha256 = hashlib.sha256(body).hexdigest()
        self.cache = Path(cache or Path.home() / ".cache" / "election-audit" / "dashboard")
        if type(cache_bytes) is not int or cache_bytes < 1:
            raise ValueError("Positive cache bound required")
        self.cache_bytes = cache_bytes
        for name, spec in self.manifest["tables"].items():
            if (
                not NAME.fullmatch(name)
                or not isinstance(spec.get("rows"), int)
                or spec["rows"] < 0
            ):
                raise ValueError("Invalid dataset table")
            _relative(spec["path"])
            if (
                not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", ""))
                or type(spec.get("bytes")) is not int
                or spec["bytes"] < 1
            ):
                raise ValueError("Invalid dataset checksum/size")

    def _download(self, url: str, maximum: int) -> bytes:
        with urlopen(url, timeout=20) as response:
            final = urlsplit(response.url)
            origin = urlsplit(self.uri)
            if (final.scheme, final.netloc) != (origin.scheme, origin.netloc):
                raise ValueError("Cross-origin dataset redirect rejected")
            body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValueError("Dataset download exceeds byte limit")
        return body

    @property
    def tables(self) -> tuple[str, ...]:
        return tuple(sorted(self.manifest["tables"]))

    def file(self, table: str) -> Path:
        spec = self.manifest["tables"][table]
        relative = _relative(spec["path"])
        if not self.remote:
            root = Path(self.uri).parent
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Dataset path escapes its manifest")
        else:
            if spec["bytes"] > self.cache_bytes:
                raise ValueError("Partition exceeds dashboard cache budget")
            self.cache.mkdir(parents=True, exist_ok=True)
            path = self.cache / (spec["sha256"] + ".parquet")
            if not path.exists():
                for old in sorted(self.cache.glob("*.parquet"), key=lambda p: p.stat().st_mtime):
                    if (
                        sum(p.stat().st_size for p in self.cache.glob("*.parquet")) + spec["bytes"]
                        <= self.cache_bytes
                    ):
                        break
                    old.unlink()
                body = self._download(urljoin(self.uri, relative), spec["bytes"])
                if hashlib.sha256(body).hexdigest() != spec["sha256"]:
                    raise ValueError("Dataset checksum mismatch")
                with tempfile.NamedTemporaryFile(dir=self.cache, delete=False) as f:
                    f.write(body)
                    temporary = Path(f.name)
                temporary.replace(path)
        if path.stat().st_size != spec["bytes"] or _hash(path) != spec["sha256"]:
            raise ValueError("Dataset checksum/size mismatch")
        return path

    def _view(self, db: duckdb.DuckDBPyConnection, table: str) -> None:
        relation = db.read_parquet(str(self.file(table)))
        columns = set(relation.columns)
        relation.create_view("source_records")
        additions = [
            "json_extract_string(payload, '$." + name + "') AS \"" + name + '"'
            for name in DIMENSIONS
            if name not in columns
        ]
        sql = "SELECT *" + ("," + ",".join(additions) if additions else "") + " FROM source_records"
        db.execute("CREATE VIEW records AS " + sql)

    def page(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        limit: int = 250,
        offset: int = 0,
    ) -> JSON:
        if (
            type(limit) is not int
            or not 1 <= limit <= 10000
            or type(offset) is not int
            or offset < 0
        ):
            raise ValueError("Invalid bounded page")
        filters = filters or {}
        if set(filters) - set(DIMENSIONS):
            raise ValueError("Unknown dashboard filter")
        where, values = [], []
        for key, value in filters.items():
            if value not in (None, "", "all"):
                where.append('"' + key + '" = ?')
                values.append(str(value))
        with duckdb.connect() as db:
            db.execute("SET threads=2")
            db.execute("SET memory_limit='256MB'")
            self._view(db, table)
            clause = " WHERE " + " AND ".join(where) if where else ""
            count = one(db.execute("SELECT count(*) FROM records" + clause, values).fetchone())[0]
            rows = db.execute(
                "SELECT payload FROM records" + clause + " LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return {
            "rows": [json.loads(r[0]) for r in rows],
            "total": count,
            "offset": offset,
            "limit": limit,
            "release_id": self.manifest["release_id"],
            "filters": filters,
            "table": table,
            "manifest_sha256": self.manifest_sha256,
        }

    def options(self, table: str, dimension: str) -> list[Any]:
        if dimension not in DIMENSIONS:
            raise ValueError("Unknown dimension")
        with duckdb.connect() as db:
            self._view(db, table)
            return [
                r[0]
                for r in db.execute(
                    'SELECT DISTINCT "'
                    + dimension
                    + '" FROM records WHERE "'
                    + dimension
                    + '" IS NOT NULL ORDER BY 1 LIMIT 1000'
                ).fetchall()
            ]

    def csv(self, table: str, **kwargs: Any) -> tuple[str, JSON]:
        import csv
        import io

        result = self.page(table, **kwargs)
        rows = result["rows"]
        stream = io.StringIO()
        columns = sorted({k for r in rows for k in r})
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(
            {k: _json(v) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows
        )
        return stream.getvalue(), {k: v for k, v in result.items() if k != "rows"}


def publish_dataset(
    tables: Mapping[str, Iterable[Row]],
    output: str | Path,
    *,
    release_id: str,
    access_state: str,
    notes: Sequence[str] = (),
) -> Path:
    """Write a new immutable dataset from explicit, already access-filtered row streams."""
    if access_state not in {"development_only", "final_evaluated", "exploratory_unpartitioned"}:
        raise ValueError("Explicit access state required")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".dashboard-", dir=output.parent))
    try:
        schema = pa.schema([(d, pa.string()) for d in DIMENSIONS] + [("payload", pa.string())])
        specs = {}
        for name, rows in tables.items():
            if not NAME.fullmatch(name):
                raise ValueError("Invalid table name")
            path = staging / (name + ".parquet")
            count, batch = 0, []
            with pq.ParquetWriter(path, schema, compression="zstd") as writer:
                for row in rows:
                    record = {
                        d: str(row[d]) if row.get(d) is not None else None for d in DIMENSIONS
                    }
                    record["payload"] = _json(row)
                    batch.append(record)
                    count += 1
                    if len(batch) == 2048:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        batch = []
                if batch:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            specs[name] = {
                "path": path.name,
                "bytes": path.stat().st_size,
                "rows": count,
                "sha256": _hash(path),
            }
        manifest = {
            "version": VERSION,
            "release_id": release_id,
            "access_state": access_state,
            "tables": specs,
            "notes": list(notes),
        }
        (staging / "dataset.json").write_text(_json(manifest) + "\n")
        staging.rename(output)
        return output / "dataset.json"
    except BaseException:
        shutil.rmtree(staging)
        raise


def export_release(release: str | Path, output: str | Path) -> Path:
    """Export curated marts; untouched test outcomes never enter the output directory."""
    from election_audit.publication import inspect_release, open_release
    from election_audit.release_tools import resolve_release

    path = resolve_release(release)
    document = inspect_release(path)
    with open_release(path, _verified_document=document) as db:
        names = set(document.get("combined_tables", document["tables"]))
        partitioned = "test_partition_status" in names
        final_evaluated = False
        if partitioned:
            # Only the research producer's validator can certify the full immutable
            # evaluation record and its protocol/model/population references.
            try:
                from election_audit.research_evaluation import final_evaluation_complete
            except ImportError:
                final_evaluation_complete = None
            if final_evaluation_complete is not None:
                final_evaluated = final_evaluation_complete(db, document)
        protected = partitioned and not final_evaluated
        if protected:
            selected = {"features": "training_features"} if "training_features" in names else {}
            # Coverage is metadata only. No per-unit outcome or unfiltered ledger is exported.
            if "operational_coverage" in names:
                selected["coverage"] = "operational_coverage"
            state = "development_only"
        else:
            selected = {k: v for k, v in TABLES.items() if v in names}
            state = "final_evaluated" if final_evaluated else "exploratory_unpartitioned"

        def stream(table: str) -> Iterator[Row]:
            cursor = db
            cursor.execute('SELECT payload FROM "' + table + '"')
            while batch := cursor.fetchmany(2048):
                for (payload,) in batch:
                    row = json.loads(payload)
                    if protected and table == "operational_coverage":
                        row = {
                            k: row.get(k)
                            for k in (
                                "snapshot_id",
                                "section_id",
                                "uf",
                                "log_availability",
                                "bu_availability",
                                "source_parse_state",
                                "operational_parse_state",
                                "exclusion_reason",
                            )
                        }
                    row.setdefault(
                        "readiness",
                        row.get(
                            "availability",
                            row.get(
                                "computational_state", row.get("reconciliation_state", "unknown")
                            ),
                        ),
                    )
                    yield row

        return publish_dataset(
            {k: stream(v) for k, v in selected.items()},
            output,
            release_id=path.name,
            access_state=state,
            notes=[
                "Read-only exploration export; unknown values remain unknown.",
                "Protected outcomes excluded; only training/calibration features exposed."
                if protected
                else "Unpartitioned data are exploratory, not an untouched test evaluation.",
            ],
        )
