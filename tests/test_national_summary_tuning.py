"""Finite safe tuning decisions and resumable-state integrity."""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from election_audit.national_summary_tuning import choose, read_state, save_state


class SummaryTuningTests(unittest.TestCase):
    def trials(self, workers: int, values: list[float], batch: int = 32) -> list[dict[str, Any]]:
        return [
            {
                "state": "accepted",
                "workers": workers,
                "batch_objects": batch,
                "objects_per_second": v,
            }
            for v in values
        ]

    def test_noise_plateau_prefers_fewer_workers(self) -> None:
        result = choose(self.trials(1, [10, 10.2]) + self.trials(2, [10.3, 10.1]))
        self.assertEqual(result["selected"]["workers"], 1)

    def test_sustained_improvement_justifies_real_parallelism(self) -> None:
        result = choose(
            self.trials(1, [5, 5.1]) + self.trials(2, [8, 8.1]) + self.trials(3, [9, 9.2])
        )
        self.assertEqual(result["selected"]["workers"], 3)

    def test_rejected_or_single_observation_cannot_win(self) -> None:
        trials = self.trials(1, [5, 5]) + self.trials(3, [500])
        trials.append(
            {"state": "rejected", "workers": 3, "batch_objects": 32, "objects_per_second": 900}
        )
        self.assertEqual(choose(trials)["selected"]["workers"], 1)
        with self.assertRaises(ValueError):
            choose(trials[2:])

    def test_state_round_trip_and_corruption_detection(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "state.json"
            value = {"identity": "source-code-pins", "trials": [], "state": "running"}
            save_state(path, value)
            self.assertEqual(read_state(path), value)
            path.write_text(path.read_text().replace("running", "stopped"))
            with self.assertRaisesRegex(ValueError, "checksum"):
                read_state(path)


if __name__ == "__main__":
    unittest.main()
