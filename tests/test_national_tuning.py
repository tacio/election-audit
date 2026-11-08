"""Tuner resource decisions, noise, finite resume and fresh applied configurations."""

import copy
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from election_audit.national import LIMITS, _read_json
from election_audit.national_storage import iter_compact, process_compact_original
from election_audit.national_tuning import (
    code_pins,
    limits,
    load_state,
    recommendation,
    resource_reason,
    rss_bytes,
    run,
    save_state,
    tuning_guard,
    validate_state,
    winner,
)
from election_audit.source_inventory import digest


def best(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """The recommended trial, which these cases always have."""
    found = winner(trials)
    assert found is not None
    return found


class TuningTests(unittest.TestCase):
    def test_resource_headroom_host_pressure_and_small_hardware(self) -> None:
        policy = limits(1024**3, 8 * 1024**2, 30, 1024, 1024, 1024**3)
        pressure = {"memory_available_bytes": 4 * 1024**3, "memory_pressure_full_avg10": 0}
        self.assertIsNone(resource_reason(policy, pressure, 200 * 1024**2, 100 * 1024**2))
        self.assertEqual(
            resource_reason(policy, pressure, 1024**3, 100 * 1024**2), "aggregate_memory_headroom"
        )
        self.assertEqual(
            resource_reason(policy, {**pressure, "memory_available_bytes": 1}, 1, 1),
            "host_memory_available",
        )
        self.assertEqual(
            resource_reason(policy, {**pressure, "memory_pressure_full_avg10": 10}, 1, 1),
            "host_memory_pressure",
        )
        with self.assertRaisesRegex(ValueError, "at least 1 GiB"):
            limits(512 * 1024**2)

    def test_repeat_noise_plateau_and_rejected_trials_not_winners(self) -> None:
        def trials(batch: int, values: list[float]) -> list[dict[str, Any]]:
            return [
                {"state": "accepted", "batch_rows": batch, "events_per_second": v} for v in values
            ]

        values = trials(2048, [100, 102]) + trials(8192, [101, 103])
        self.assertEqual(best(values)["batch_rows"], 2048)
        values += trials(32768, [125, 124])
        values += [{"state": "rejected", "batch_rows": 65536, "events_per_second": 9999}]
        self.assertEqual(best(values)["batch_rows"], 32768)
        self.assertIsNone(winner(trials(2048, [100])))

    def test_resume_identity_and_completed_run_do_not_reprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from election_audit.national import _write_json

            root = Path(tmp)
            spec: dict[str, Any] = {"code": code_pins(), "policy": limits()}
            spec["spec_id"] = digest(spec)
            state = {"spec_id": spec["spec_id"], "state": "complete"}
            validate_state(spec, state)
            _write_json(root / "spec.json", spec)
            save_state(root / "state.json", state)
            with patch("election_audit.national_tuning.subprocess.Popen") as spawn:
                self.assertEqual(run(root), state)
                spawn.assert_not_called()
            bad = copy.deepcopy(spec)
            bad["code"]["national.py"] = "bad"
            with self.assertRaisesRegex(ValueError, "identity changed"):
                validate_state(bad, state)

    def test_guard_honors_custom_disk_reserves(self) -> None:
        spec = {"policy": limits(), "store": "/tmp", "scratch": "/tmp"}
        with patch("election_audit.national_tuning.shutil.disk_usage") as usage:
            usage.return_value.free = 19 * 1024**3
            with self.assertRaisesRegex(OSError, "reserve"):
                tuning_guard(spec, 1)
            usage.return_value.free = 25 * 1024**3
            with self.assertRaisesRegex(OSError, "reserve"):
                tuning_guard(spec, 1)

    def test_exit_race_zombie_has_zero_resident_memory(self) -> None:
        with patch("pathlib.Path.read_text", return_value="Name:\tpython\nState:\tZ (zombie)\n"):
            self.assertEqual(rss_bytes(1234), 0)
        with patch("pathlib.Path.read_text", return_value="Name:\tpython\nState:\tR (running)\n"):
            with self.assertRaisesRegex(OSError, "observe"):
                rss_bytes(1234)

    def test_pressure_backoff_is_persisted_without_starting_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from election_audit.national import _write_json

            root = Path(tmp)
            policy = limits()
            policy["cooldown_seconds"] = 0
            spec = {
                "code": code_pins(),
                "policy": policy,
                "candidates": [2],
                "store": str(root / "store"),
            }
            spec["spec_id"] = digest(spec)
            _write_json(root / "spec.json", spec)
            save_state(
                root / "state.json",
                {
                    "spec_id": spec["spec_id"],
                    "state": "prepared",
                    "trials": [],
                    "active": None,
                    "elapsed_seconds": 0,
                },
            )
            with (
                patch(
                    "election_audit.national_tuning.host_pressure",
                    return_value={"memory_available_bytes": 1, "memory_pressure_full_avg10": 0},
                ),
                patch("election_audit.national_tuning.subprocess.Popen") as spawn,
            ):
                result = run(root)
            self.assertEqual(result["state"], "backoff")
            self.assertEqual(
                load_state(root / "state.json")["stop_reason"], "host_memory_available"
            )
            spawn.assert_not_called()

    def test_interrupted_output_is_charged_and_not_a_timing_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from election_audit.national import _write_json

            root = Path(tmp)
            policy = limits(output_bytes=1024**2)
            spec = {
                "code": code_pins(),
                "policy": policy,
                "candidates": [2],
                "repeats": 2,
                "store": str(root / "store"),
                "scratch": str(root / "scratch"),
            }
            spec["spec_id"] = digest(spec)
            retained = root / "store/tuning" / spec["spec_id"] / "trial-000"
            retained.mkdir(parents=True)
            (retained / "partial.parquet").write_bytes(b"x" * (2 * 1024**2))
            _write_json(root / "spec.json", spec)
            save_state(
                root / "state.json",
                {
                    "spec_id": spec["spec_id"],
                    "state": "running",
                    "trials": [],
                    "active": {
                        "trial_id": "trial-000",
                        "batch_rows": 2,
                        "monotonic_started": time.monotonic(),
                    },
                    "elapsed_seconds": 0,
                },
            )
            with patch("election_audit.national_tuning.subprocess.Popen") as spawn:
                result = run(root)
            self.assertEqual(result["state"], "bounded_stop")
            self.assertEqual(result["trials"][0]["output_bytes"], 2 * 1024**2)
            self.assertEqual(result["trials"][0]["state"], "rejected")
            self.assertIsNone(result["winner"])
            spawn.assert_not_called()

    def test_completed_state_recovers_missing_recommendation_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from election_audit.national import _write_json

            root = Path(tmp)
            spec: dict[str, Any] = {"code": code_pins(), "policy": limits()}
            spec["spec_id"] = digest(spec)
            state = {
                "spec_id": spec["spec_id"],
                "state": "complete",
                "winner": {"batch_rows": 8192},
            }
            _write_json(root / "spec.json", spec)
            save_state(root / "state.json", state)
            with patch("election_audit.national_tuning.subprocess.Popen") as spawn:
                self.assertEqual(run(root), state)
                first = (root / "recommended.json").read_bytes()
                self.assertEqual(run(root), state)
                self.assertEqual(first, (root / "recommended.json").read_bytes())
                spawn.assert_not_called()
            self.assertEqual(recommendation(root / "recommended.json")["event_batch_rows"], 8192)

    def test_real_batch_knob_changes_row_groups_preserves_full_events(self) -> None:
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(
                    "logd.dat",
                    b"25/10/2026 08:00:00\tINFO\t123\tVOTA\tUnknown message\ttoken\n" * 19,
                )
            body = archive.getvalue()
            sha = hashlib.sha256(body).hexdigest()
            source = root / "raw/objects" / sha[:2] / (sha + ".jez")
            source.parent.mkdir(parents=True)
            source.write_bytes(body)
            row = {
                "source_root": str(root / "raw"),
                "path": str(source.relative_to(root / "raw")),
                "sha256": sha,
                "bytes": len(body),
                "url": "https://official.example/log.jez",
            }
            old_limits = dict(LIMITS)
            try:
                with patch("election_audit.national.guard"):
                    a = process_compact_original(
                        row,
                        root / "trial-a",
                        root / "scratch",
                        output_budget_bytes=8 * 1024**2,
                        batch_rows=2,
                    )
                    b = process_compact_original(
                        row,
                        root / "trial-b",
                        root / "scratch",
                        output_budget_bytes=8 * 1024**2,
                        batch_rows=16,
                    )
                self.assertEqual(list(iter_compact(a / "events")), list(iter_compact(b / "events")))
                self.assertGreater(
                    pq.ParquetFile(a / "events/events.parquet").metadata.num_row_groups,
                    pq.ParquetFile(b / "events/events.parquet").metadata.num_row_groups,
                )
                self.assertEqual(
                    _read_json(b / "checkpoint.json")["resources"]["event_batch_rows"], 16
                )
            finally:
                LIMITS.clear()
                LIMITS.update(old_limits)
