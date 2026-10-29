import itertools
import math
import unittest

from scripts.audit_statistics import (
    by_adjusted_pvalues,
    conformal_tail_pvalues,
    maximum_switch_margin_change,
    removal_contribution_bounds,
    switches_to_reverse,
)


class AuditStatisticsTests(unittest.TestCase):
    def test_conformal_ranks_are_conservative_with_ties(self):
        self.assertEqual(conformal_tail_pvalues([1, 2, 2, 3], [0, 2, 3, 4]), [1, 0.8, 0.4, 0.2])
        self.assertEqual(conformal_tail_pvalues([7, 7], [7]), [1])
        for calibration, test in (([], [1]), ([math.nan], [1]), ([1], [math.inf])):
            with self.assertRaises(ValueError):
                conformal_tail_pvalues(calibration, test)

    def test_by_matches_step_up_decisions_for_every_threshold(self):
        pvalues = [0.7, 0.0001, 0.02, 0.02, 0.1]
        adjusted = by_adjusted_pvalues(pvalues)
        order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
        h = sum(1 / i for i in range(1, len(pvalues) + 1))
        for alpha in (0.001, 0.01, 0.05, 0.1, 0.2, 0.5):
            accepted_ranks = [
                rank
                for rank, index in enumerate(order, 1)
                if pvalues[index] <= alpha * rank / (len(pvalues) * h)
            ]
            expected = set(order[: max(accepted_ranks, default=0)])
            actual = {i for i, p in enumerate(adjusted) if p <= alpha}
            self.assertEqual(actual, expected)
        self.assertEqual(adjusted[2], adjusted[3])
        self.assertEqual(by_adjusted_pvalues([]), [])
        for invalid in ([-0.1], [1.1], [math.nan]):
            with self.assertRaises(ValueError):
                by_adjusted_pvalues(invalid)

    def test_removal_bounds_exhaust_all_feasible_anonymous_subsets(self):
        # Enumerate every assignment, including blank/null ballots and empty sets.
        for a, b, other in itertools.product(range(5), repeat=3):
            for r in range(a + b + other + 1):
                for at_most in (False, True):
                    feasible = [
                        x - y
                        for x in range(a + 1)
                        for y in range(b + 1)
                        for z in range(other + 1)
                        if (x + y + z <= r if at_most else x + y + z == r)
                    ]
                    self.assertEqual(
                        removal_contribution_bounds(a, b, other, r, at_most=at_most),
                        (min(feasible), max(feasible)),
                    )

    def test_switch_threshold_really_reverses_and_is_minimal(self):
        for margin in range(1, 100):
            switches = switches_to_reverse(margin)
            self.assertLess(margin - 2 * switches, 0)
            self.assertGreaterEqual(margin - 2 * (switches - 1), 0)
        self.assertEqual(maximum_switch_margin_change(10, 50), 20)
        self.assertEqual(maximum_switch_margin_change(100, 3), 6)

    def test_invalid_count_constraints(self):
        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                removal_contribution_bounds(bad, 1, 0, 0)
        with self.assertRaises(ValueError):
            removal_contribution_bounds(1, 1, 0, 3)
        with self.assertRaises(ValueError):
            switches_to_reverse(0)


if __name__ == "__main__":
    unittest.main()
