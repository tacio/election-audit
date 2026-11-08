"""Outcome protection at the physical dataset boundary."""

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import duckdb

from election_audit.dashboard_data import AuditDataset, export_release


class DashboardReleaseTests(unittest.TestCase):
    def test_partitioned_export_excludes_raw_outcomes_and_redacts_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as db:
            names = [
                "test_partition_status",
                "training_features",
                "section_results",
                "operational_coverage",
            ]
            db.execute("CREATE TABLE test_partition_status(access_state VARCHAR)")
            # Inspection is not completion of the final evaluation.
            db.execute("INSERT INTO test_partition_status VALUES ('development_inspected')")
            for table, value in [
                ("training_features", {"value": 0.5, "unit_key": "development"}),
                ("section_results", {"secret_test_outcome": 666}),
                (
                    "operational_coverage",
                    {"uf": "ac", "section_id": "test", "secret_test_outcome": 666},
                ),
            ]:
                db.execute(f"CREATE TABLE {table}(payload VARCHAR)")
                db.execute(f"INSERT INTO {table} VALUES (?)", [json.dumps(value)])
            document = {"tables": dict.fromkeys(names, {})}
            with (
                patch(
                    "election_audit.release_tools.resolve_release",
                    return_value=Path(directory) / "release",
                ),
                patch("election_audit.publication.inspect_release", return_value=document),
                patch("election_audit.publication.open_release", return_value=nullcontext(db)),
            ):
                manifest = export_release("unused", Path(directory) / "export")
            d = AuditDataset.open(manifest)
            self.assertEqual(d.manifest["access_state"], "development_only")
            self.assertEqual(d.tables, ("coverage", "features"))
            self.assertNotIn("secret_test_outcome", d.page("coverage")["rows"][0])
            for path in manifest.parent.rglob("*.parquet"):
                self.assertNotIn(b"secret_test_outcome", path.read_bytes())
