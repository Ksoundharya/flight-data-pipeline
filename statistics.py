"""Descriptive/inferential statistics helpers used by analyze_flights.py.

Kept dependency-free (no numpy/scipy/pandas) per the "avoid unnecessary
dependencies" instruction and to keep Task 2 usable on a bare Python 3.7+
interpreter -- Task 1 already demonstrates full scientific-stack usage.
"""
from __future__ import annotations

import math
from typing import List, Dict


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def variance(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / (len(values) - 1)


def stdev(values: List[float]) -> float:
    return math.sqrt(variance(values))


def percentile(sorted_values: List[float], p: float) -> float:
    """Linear-interpolation percentile (numpy's default 'linear' method),
    matching the most common definition and the one used in Task 1.

    Requires `sorted_values` to already be sorted ascending -- callers pass
    pre-sorted lists so this can be called repeatedly (P5/P25/P50/P75/P95/P99)
    without re-sorting each time.
    """
    if not sorted_values:
        return float("nan")
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = p / 100 * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return sorted_values[lo]
    frac = rank - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def skewness(values: List[float]) -> float:
    """Sample (Fisher-Pearson adjusted) skewness."""
    n = len(values)
    if n < 3:
        return 0.0
    m = mean(values)
    s = stdev(values)
    if s == 0:
        return 0.0
    g1 = (sum((v - m) ** 3 for v in values) / n) / (s ** 3)
    return (math.sqrt(n * (n - 1)) / (n - 2)) * g1


def coefficient_of_variation(values: List[float]) -> float:
    m = mean(values)
    return stdev(values) / m if m != 0 else float("nan")


def describe(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    s = sorted(values)
    return {
        "n": len(values),
        "mean": mean(values),
        "median": percentile(s, 50),
        "stdev": stdev(values),
        "variance": variance(values),
        "min": s[0],
        "max": s[-1],
        "p5": percentile(s, 5),
        "p25": percentile(s, 25),
        "p50": percentile(s, 50),
        "p75": percentile(s, 75),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
        "iqr": percentile(s, 75) - percentile(s, 25),
        "skewness": skewness(values),
        "coefficient_of_variation": coefficient_of_variation(values),
    }


def wilson_ci(successes: int, n: int, z: float = 1.96) -> (float, float):
    """Wilson score 95% CI (default z=1.96) for a binomial proportion.

    Preferred over the normal (Wald) approximation for a small proportion
    like a ~0.5-1% dirty rate, where the Wald interval can dip below 0.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    phat = successes / n
    denom = 1 + z ** 2 / n
    center = phat + z ** 2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z ** 2 / (4 * n)) / n)
    lower = (center - margin) / denom
    upper = (center + margin) / denom
    return (max(0.0, lower), min(1.0, upper))


def herfindahl_hirschman_index(shares: List[float]) -> float:
    """HHI on shares expressed as fractions of 1 (not percent-of-100), i.e.
    sum(share_i^2), ranging (0, 1]. Multiply by 10,000 for the conventional
    0-10,000 antitrust-style scale, which we do at the call site so this
    function's contract stays unit-agnostic."""
    return sum(s ** 2 for s in shares)
