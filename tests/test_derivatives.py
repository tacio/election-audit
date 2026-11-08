"""Synthetic frozen operational parent → normalized immutable electoral child."""

import copy
import json
import shutil
from unittest.mock import patch

import test_reconstruction
import test_snapshots
from test_electoral_imports import bundle_at
from test_electoral_results import electoral_data

from election_audit.derivatives import publish_derivative
from election_audit.publication import (
    PublicationError,
    ResourceConfig,
    build_from_parse,
    inspect_release,
    open_release,
)
from election_audit.release_tools import query_release, report_release, validate_release
from election_audit.source_inventory import hash_file
from election_audit.types import one


class DerivativeTests(test_snapshots.SourceFixture):
    frozen_parse = test_reconstruction.PublicationTests.frozen_parse

    def parent_and_bundle(self):
        base, _, parsed = self.frozen_parse()
        parent = build_from_parse(parsed, base / "warehouse")
        with open_release(parent) as db:
            section = json.loads(
                one(db.execute("SELECT payload FROM section LIMIT 1").fetchone())[0]
            )
            snapshot = json.loads(
                one(db.execute("SELECT payload FROM snapshot LIMIT 1").fetchone())[0]
            )
        data = electoral_data()
        data.pop("election")
        data.pop("snapshot")
        data.pop("section")
        data.pop("section_composition")
        data["contest"][0]["election_id"] = section["election_id"]
        data["result_version"][0]["principal_section_id"] = section["section_id"]
        data["result_evidence"][0]["snapshot_id"] = snapshot["snapshot_id"]
        directory = base / "imports"
        directory.mkdir()
        bundle = bundle_at(directory, data)
        doc = json.loads(bundle.read_text())
        sha = next(s["sha256"] for s in doc["sources"] if s["table"] == "result_version")
        data["result_evidence"][0]["status_evidence"]["object_sha256"] = sha
        bundle_at(directory, data)
        return base, parent, bundle, data

    def test_end_to_end_query_validate_report_relocation_and_one_physical_hash_pass(self) -> None:
        base, parent, bundle, _ = self.parent_and_bundle()
        before = inspect_release(parent)
        child = publish_derivative(parent, bundle, base / "warehouse")
        self.assertEqual(child, publish_derivative(parent, bundle, base / "warehouse"))
        self.assertEqual(before, inspect_release(parent))
        self.assertEqual(validate_release(child)["integrity"], "passed")
        result = query_release(
            child,
            "SELECT json_extract(payload, '$.strict_unanimity')::BOOLEAN FROM unanimous_results",
        )
        self.assertEqual(result["rows"], [(True,)])
        self.assertEqual(
            query_release(child, "SELECT count(*) FROM anonymous_cycle")["rows"], [(1,)]
        )
        self.assertEqual(
            query_release(child, "SELECT sum(attending_voters) FROM section_contest_totals")[
                "rows"
            ],
            [(10,)],
        )
        self.assertFalse(any((child / "facts" / "anonymous_cycle").glob("**/*")))
        from election_audit import derivatives, publication, release_tools

        reads = []

        def counted(path):
            reads.append(str(path))
            return hash_file(path)

        with (
            patch.object(publication, "hash_file", side_effect=counted),
            patch.object(derivatives, "hash_file", side_effect=counted),
            patch.object(
                release_tools, "inspect_release", wraps=release_tools.inspect_release
            ) as inspect,
        ):
            report_release(child, base / "reports")
        self.assertEqual(inspect.call_count, 1)
        fact_reads = [p for p in reads if p.endswith(".parquet")]
        self.assertEqual(len(fact_reads), len(set(fact_reads)))
        self.assertTrue((base / "reports" / "report.en.md").is_file())
        self.assertTrue((base / "reports" / "report.pt-BR.md").is_file())
        findings = json.loads((base / "reports" / "findings.json").read_text())
        self.assertEqual(len(findings["parent_chain"]), 2)
        self.assertIn("unavailable", findings["electoral_validation"])
        moved = base / "moved"
        shutil.move(base / "warehouse", moved)
        moved_child = moved / "releases" / child.name
        self.assertEqual(validate_release(moved_child)["integrity"], "passed")
        self.assertEqual(
            query_release(moved_child, "SELECT count(*) FROM canonical_result")["rows"], [(1,)]
        )

    def test_official_bu_child_preserves_verification_originals_unknowns_and_relocation(
        self,
    ) -> None:
        from test_official_bu import official_bundle

        base, parent, _, _ = self.parent_and_bundle()
        root = base / "official"
        root.mkdir()
        bundle = official_bundle(root)
        child = publish_derivative(parent, bundle, base / "warehouse")
        doc = inspect_release(child)
        self.assertEqual(doc["verification_status"], "official_layout_verified")
        validation = validate_release(child)
        self.assertEqual(validation["verification_status"], "official_layout_verified")
        self.assertEqual(validation["integrity"], "passed")
        self.assertEqual(
            query_release(child, "SELECT count(*) FROM result_version")["rows"], [(3,)]
        )
        self.assertEqual(
            query_release(child, "SELECT DISTINCT result_status FROM result_version")["rows"],
            [("unknown",)],
        )
        report_release(child, base / "official-report")
        findings = json.loads((base / "official-report/findings.json").read_text())
        self.assertEqual(findings["verification_status"], "official_layout_verified")
        self.assertIn(
            "Official BWEB layout verified", (base / "official-report/report.en.md").read_text()
        )
        self.assertEqual(len(doc["originals"]), 6)
        from election_audit.analysis import feature_rows

        features = list(
            feature_rows(child, doc, {"cutoff_at": "2026-10-30T00:00:00+00:00"}, ResourceConfig())
        )
        official = [r for r in features if "official_layout_verified" in r["quality_indicators"]]
        self.assertTrue(official)
        self.assertTrue(all(not r["scientific_eligible"] for r in official))
        self.assertTrue(
            all(
                "source_schema_not_officially_verified" not in r["scientific_blockers"]
                for r in official
            )
        )
        self.assertTrue(any("normalized_only" in r["quality_indicators"] for r in features))
        moved = base / "official-moved"
        shutil.move(base / "warehouse", moved)
        self.assertEqual(validate_release(moved / "releases" / child.name)["integrity"], "passed")

    def test_official_reobservation_appends_without_reusing_another_snapshot_identity(self) -> None:
        from test_official_bu import official_bundle

        base, parent, _, _ = self.parent_and_bundle()
        root = base / "official"
        root.mkdir()
        bundle = official_bundle(root)
        first = publish_derivative(parent, bundle, base / "warehouse")
        document = json.loads(bundle.read_text())
        # Same exact original files; a new archive observation with reused catalog evidence.
        document["archive"]["observed_at"] = "2026-10-31T00:00:00+00:00"
        bundle.write_text(json.dumps(document))
        second = publish_derivative(first, bundle, base / "warehouse")
        self.assertEqual(
            query_release(second, "SELECT count(*) FROM result_version")["rows"], [(6,)]
        )
        self.assertEqual(
            query_release(first, "SELECT count(*) FROM result_version")["rows"], [(3,)]
        )
        self.assertEqual(validate_release(second)["integrity"], "passed")
        self.assertEqual(
            query_release(second, "SELECT count(DISTINCT snapshot_id) FROM result_evidence")[
                "rows"
            ],
            [(2,)],
        )
        self.assertEqual(
            query_release(second, "SELECT DISTINCT result_status FROM result_version")["rows"],
            [("unknown",)],
        )

    def test_append_derivative_retains_versions_and_recalculates_conflict(self) -> None:
        base, parent, bundle, data = self.parent_and_bundle()
        child = publish_derivative(parent, bundle, base / "warehouse")
        second_data = {}
        for name in (
            "result_version",
            "result_evidence",
            "section_contest_totals",
            "vote_choice_count",
        ):
            second_data[name] = copy.deepcopy(data[name])
            for r in second_data[name]:
                r["result_version_id"] = "new"
        directory = base / "second"
        directory.mkdir()
        bundle = bundle_at(directory, second_data)
        sha = hash_file(directory / "result_version.jsonl")[0]
        second_data["result_evidence"][0]["status_evidence"]["object_sha256"] = sha
        bundle_at(directory, second_data)
        latest = publish_derivative(child, bundle, base / "warehouse")
        self.assertEqual(
            query_release(latest, "SELECT selection_state FROM canonical_result")["rows"],
            [("conflict",)],
        )
        self.assertEqual(
            query_release(latest, "SELECT count(*) FROM result_version")["rows"], [(2,)]
        )
        self.assertEqual(
            query_release(child, "SELECT selection_state FROM canonical_result")["rows"],
            [("selected",)],
        )
        self.assertEqual(validate_release(latest)["integrity"], "passed")

    def test_tamper_parent_pin_and_external_query_guards(self) -> None:
        base, parent, bundle, _ = self.parent_and_bundle()
        child = publish_derivative(parent, bundle, base / "warehouse")
        for sql in (
            "DELETE FROM result_version",
            "SELECT 1; SELECT 2",
            "SELECT * FROM read_csv('/etc/passwd')",
            "COPY section_results TO '/tmp/forbidden.csv'",
        ):
            with self.assertRaises(Exception):
                query_release(child, sql)
        with self.assertRaisesRegex(PublicationError, "immutable"):
            report_release(child, parent / "reports")
        (parent / "release.json").write_bytes(b"changed")
        with self.assertRaisesRegex(PublicationError, "parent manifest"):
            inspect_release(child)

    def test_row_resource_bound_and_missing_parent(self) -> None:
        base, parent, bundle, _ = self.parent_and_bundle()
        with self.assertRaisesRegex(PublicationError, "row limit"):
            publish_derivative(
                parent, bundle, base / "warehouse", config=ResourceConfig(max_events=1)
            )
        child = publish_derivative(parent, bundle, base / "warehouse")
        shutil.rmtree(parent)
        with self.assertRaises(OSError):
            inspect_release(child)
