"""Statistical-audit primitives; these do not identify fraud or fit a model.

Rank calibration requires an appropriate exchangeable reference and a frozen
score. BY correction requires valid null p-values. Neither assumption is supplied
by these functions. Impact bounds are conditional arithmetic scenarios.
"""

import math
from bisect import bisect_left
from collections.abc import Iterable


def conformal_tail_pvalues(
    calibration_scores: Iterable[float], test_scores: Iterable[float]
) -> list[float]:
    """Conservative upper-tail ranks, counting ties against rejection.

    Scores must be computed by the same frozen scoring function. Shared
    calibration and clustered observations induce dependence; interpreting ranks
    as null p-values requires assumptions stated in research/analysis-plan.md.
    """
    calibration = sorted(float(s) for s in calibration_scores)
    scores = [float(s) for s in test_scores]
    if not calibration or not all(math.isfinite(s) for s in calibration + scores):
        raise ValueError("Need nonempty finite calibration scores and finite test scores")
    n = len(calibration)
    return [(1 + n - bisect_left(calibration, s)) / (n + 1) for s in scores]


def by_adjusted_pvalues(pvalues: Iterable[float]) -> list[float]:
    """Benjamini–Yekutieli adjusted p-values, in the input order.

    Valid null p-values are required even though arbitrary dependence between
    them is allowed. The caller must define the testing family in advance.
    """
    values = [float(p) for p in pvalues]
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
        raise ValueError("p-values must be finite and between zero and one")
    n = len(values)
    if not n:
        return []
    harmonic = math.fsum(1 / i for i in range(1, n + 1))
    order = sorted(range(n), key=values.__getitem__)
    adjusted = [1.0] * n
    running = 1.0
    for rank in range(n, 0, -1):
        index = order[rank - 1]
        running = min(running, values[index] * n * harmonic / rank)
        adjusted[index] = running
    return adjusted


def nonnegative_count(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def removal_contribution_bounds(
    a: int, b: int, other: int, affected: int, *, at_most: bool = False
) -> tuple[int, int]:
    """Sharp A-minus-B contribution bounds for an anonymous removed subset.

    Exactly `affected` ballots are removed unless `at_most` is true. `other`
    includes blank/null ballots under the same ballot-count definition. Choices
    within the subset are unknown. For corrected margin bounds, subtract the
    upper/lower contributions from the national margin in reverse order.
    """
    for name, value in (("a", a), ("b", b), ("other", other), ("affected", affected)):
        nonnegative_count(value, name)
    if affected > a + b + other:
        raise ValueError("Affected ballots exceed the section total")
    if at_most:
        return -min(affected, b), min(affected, a)
    lower = max(0, affected - b - other) - min(affected, b)
    upper = min(affected, a) - max(0, affected - a - other)
    return lower, upper


def switches_to_reverse(margin: int) -> int:
    """Minimum A-to-B switches for a strict B win when A currently leads."""
    nonnegative_count(margin, "margin")
    if margin == 0:
        raise ValueError("A strictly positive leading margin is required")
    return margin // 2 + 1


def maximum_switch_margin_change(winner_votes: int, affected_cap: int) -> int:
    """Adverse change from switching at most q currently A ballots to B.

    Covers only that mechanism; it does not bound suppression, additions,
    blank/null conversions or other unmodeled alterations.
    """
    nonnegative_count(winner_votes, "winner_votes")
    nonnegative_count(affected_cap, "affected_cap")
    return 2 * min(winner_votes, affected_cap)
