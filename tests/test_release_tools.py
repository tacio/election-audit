"""Offline CLI, integrity accounting, strict read-only SQL and paired report tests."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout

import test_reconstruction
import test_snapshots

from election_audit.cli import main
from election_audit.publication import (
    PublicationError,
    build_from_parse,
    inspect_release,
    open_release,
)
from election_audit.release_tools import COUNT_SQL, query_release, report_release, validate_release
from election_audit.types import one


class ReleaseInterfaceTests(test_snapshots.SourceFixture):
    frozen_parse = test_reconstruction.PublicationTests.frozen_parse

    def build(self):
        base, _, parsed = self.frozen_parse()
        return base, build_from_parse(parsed, base / "warehouse")

    def test_frozen_pipeline_validate_and_bounded_select(self) -> None:
        base, path = self.build()
        result = validate_release(path)
        self.assertEqual(result["logical_digests"], "passed")
        self.assertEqual(result["metadata_lineage_state"], "preserved")
        self.assertEqual(result["electoral_validation"], "unavailable")
        self.assertEqual(query_release(path, COUNT_SQL)["rows"], [("completed", 1)])
        query = query_release(path, "SELECT event_id FROM selected_event", max_rows=1)
        self.assertEqual(len(query["rows"]), 1)
        self.assertTrue(query["truncated"])
        with open_release(path) as db:
            self.assertGreater(
                one(db.execute(
                    "SELECT count(*) FROM record_lineage WHERE derived_table='section'"
                ).fetchone())[0],
                0,
            )
        self.assertEqual(inspect_release(path)["tables"]["operational_coverage"]["rows"], 1)

    def test_sql_cannot_copy_write_multistatement_or_read_external_files(self) -> None:
        base, path = self.build()
        before = inspect_release(path)
        destination = base / "forbidden.csv"
        attempts = [
            "CREATE TABLE bad(x INT)",
            "DELETE FROM voting_session",
            "SELECT 1; SELECT 2",
            f"COPY voting_session TO '{destination}'",
            "INSTALL httpfs",
            "ATTACH ':memory:' AS other",
            "PRAGMA threads=1",
            "SELECT * FROM read_csv('/etc/passwd')",
        ]
        for sql in attempts:
            with self.subTest(sql=sql):
                with self.assertRaises(Exception):
                    query_release(path, sql)
        self.assertFalse(destination.exists())
        self.assertEqual(before, inspect_release(path))
        with self.assertRaises(PublicationError):
            query_release(path, "SELECT 1", max_rows=0)

    def test_reports_default_both_same_findings_sql_and_languages(self) -> None:
        base, path = self.build()
        output = base / "reports"
        products = report_release(path, output)
        self.assertEqual(
            {p.name for p in products},
            {"report.en.md", "report.pt-BR.md", "findings.json", "lifecycle.sql", "late.sql"},
        )
        english = (output / "report.en.md").read_text()
        portuguese = (output / "report.pt-BR.md").read_text()
        self.assertIn("Initial operational report", english)
        self.assertIn("Relatório operacional inicial", portuguese)
        for sql in (COUNT_SQL, "completion_at > target_date 17:00:00 America/Sao_Paulo"):
            self.assertIn(sql, english)
            self.assertIn(sql, portuguese)
        findings = json.loads((output / "findings.json").read_text())
        self.assertIsNone(findings["global_eligible_cycle_total"])
        self.assertEqual(findings["national_status"], "partial_national")
        only = report_release(path, base / "only", language="pt-BR")
        self.assertEqual(len(only), 4)
        with self.assertRaises(PublicationError):
            report_release(path, path / "reports")

    def test_cli_build_validate_query_report_and_bad_options(self) -> None:
        base, _, parsed = self.frozen_parse()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "build",
                        str(parsed),
                        "--input-kind",
                        "parse",
                        "--store",
                        str(base / "warehouse"),
                    ]
                ),
                0,
            )
        path = output.getvalue().strip()
        for arguments in (
            ["validate", path],
            ["query", path, "--sql", COUNT_SQL],
            ["report", path, "--output", str(base / "reports")],
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(arguments), 0)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["query", path, "--sql", "COPY voting_session TO '/tmp/forbidden.csv'"])

    def test_logical_digest_and_lineage_accounting_failures_are_detected(self) -> None:
        from election_audit.archive_parsing import _read_checked, _write_checked
        from election_audit.publication import _validate_accounting

        base, path = self.build()
        manifest = _read_checked(path, "release.json")
        manifest["tables"]["selected_event"]["logical_sha256"] = "0" * 64
        (path / "release.json").unlink()
        (path / "release.json.sha256").unlink()
        _write_checked(path, "release.json", manifest)
        with self.assertRaisesRegex(PublicationError, "Logical"):
            validate_release(path)
        # Explicit relational failure independent of byte-integrity checks.
        with open_release(path) as db:
            literals = ",".join(
                "'" + str(path / f).replace("'", "''") + "'"
                for f in manifest["tables"]["record_lineage"]["files"]
            )
            db.execute(
                f"CREATE OR REPLACE TEMP VIEW record_lineage AS SELECT * FROM read_parquet([{literals}], hive_partitioning=false) WHERE false"
            )
            with self.assertRaisesRegex(PublicationError, "lineage"):
                _validate_accounting(
                    db, _read_checked(path, "context.json"), set(manifest["selected_objects"])
                )

    def test_evidenced_partitions_include_events_cycles_and_their_lineage(self) -> None:
        from election_audit.archive_parsing import FrozenParseReader, iter_event_witnesses
        from election_audit.publication import publish_release
        from election_audit.reconstruction import reconstruct_parse

        base, _, parsed = self.frozen_parse()
        reader = FrozenParseReader(parsed)
        events = list(iter_event_witnesses(parsed))
        section = reader.document["context_tables"]["section"][0]
        claim = test_reconstruction.claim(
            events,
            event_ids=[e["event_id"] for e in events],
            session_kind="official_vota",
            principal_section_id=section["section_id"],
            election_id=section["election_id"],
        )
        evidence = test_reconstruction.evidence(segments=[claim])
        shard = reconstruct_parse(parsed, base / "operations", evidence=evidence)
        path = publish_release([shard], base / "warehouse")
        manifest = inspect_release(path)
        for name in ("selected_event", "anonymous_cycle", "event_evidence"):
            self.assertTrue(
                all("year=2026/round=2/uf=ac" in file for file in manifest["tables"][name]["files"])
            )
        operational_lineage = [
            file
            for file in manifest["tables"]["record_lineage"]["files"]
            if "/context-" not in file
        ]
        self.assertTrue(all("year=2026/round=2/uf=ac" in file for file in operational_lineage))

    def test_snapshot_to_release_uses_worker_setting_and_is_standalone(self) -> None:
        import shutil

        from election_audit.publication import ResourceConfig, build_from_snapshot

        base, snapshot, parsed = self.frozen_parse()
        path = build_from_snapshot(
            snapshot, base / "warehouse", config=ResourceConfig(parser_workers=2)
        )
        shutil.rmtree(snapshot)
        shutil.rmtree(parsed.parent.parent)
        shutil.rmtree(base / "warehouse" / "parsed")
        shutil.rmtree(base / "warehouse" / "operations")
        self.assertEqual(validate_release(path)["integrity"], "passed")
        self.assertEqual(inspect_release(path)["settings_applied"]["parser_workers"], 2)

    def test_report_reuses_one_verified_manifest(self) -> None:
        from unittest.mock import patch

        from election_audit import release_tools

        base, path = self.build()
        with patch.object(
            release_tools, "inspect_release", wraps=release_tools.inspect_release
        ) as inspect:
            report_release(path, base / "reports")
        self.assertEqual(inspect.call_count, 1)

    def test_disjoint_bounded_objects_preserve_global_overlap_uncertainty(self) -> None:
        from test_archive_parsing import archive_bytes, log_line

        from election_audit.archive_parsing import parse_snapshot
        from election_audit.publication import ResourceConfig
        from election_audit.reconstruction import ReconstructionError
        from election_audit.snapshots import create_snapshot

        self.record_section()
        self.record_section(code="0002")
        other = self.log_url.replace("/0001/pkg/", "/0002/pkg/")
        self.advertise()
        self.advertise(url=other, code="0002")
        self.save_index([{"ns": "0001"}, {"ns": "0002"}])
        self.save(
            self.log_url,
            archive_bytes([("logd.dat", log_line("Eleitor foi habilitado") + log_line())]),
        )
        self.save(
            other,
            archive_bytes(
                [
                    (
                        "logd.dat",
                        log_line("Eleitor foi habilitado")
                        + log_line(timestamp="25/10/2026 08:02:00"),
                    )
                ]
            ),
        )
        from pathlib import Path

        base = Path(self.temporary.name)
        snapshot = create_snapshot(self.root, base / "snapshots", ["ac"])
        parsed = parse_snapshot(snapshot, base / "parsed", workers=2)
        with self.assertRaises(ReconstructionError):
            build_from_parse(parsed, base / "bounded", config=ResourceConfig(max_events=1))
        path = build_from_parse(parsed, base / "warehouse")
        manifest = inspect_release(path)
        self.assertEqual(len(manifest["selected_objects"]), 2)
        self.assertEqual(manifest["cross_shard_overlap"], "unresolved")
        self.assertIsNone(manifest["global_eligible_cycle_total"])
        self.assertEqual(validate_release(path)["selected_objects"], 2)
