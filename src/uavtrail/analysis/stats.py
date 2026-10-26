"""The two statistics the analysis needs, without a dependency."""

from __future__ import annotations

import math


def binom_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    p = min(max(p, 1e-12), 1 - 1e-12)
    log_terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p)
        for i in range(k, n + 1)
    ]
    top = max(log_terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in log_terms))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - r) / d), min(1.0, (c + r) / d)


def hypergeom_tail(k: int, population: int, successes: int, draws: int) -> float:
    """P(X >= k) for X ~ Hypergeometric: `draws` items taken from `population` holding `successes` marked ones.
    The one-sided Fisher exact test of a 2x2 table."""

    def log_comb(n: int, r: int) -> float:
        return math.lgamma(n + 1) - math.lgamma(r + 1) - math.lgamma(n - r + 1)

    top = min(successes, draws)
    if k > top:
        return 0.0
    lo = max(k, draws - (population - successes), 0)
    terms = [
        log_comb(successes, i) + log_comb(population - successes, draws - i) - log_comb(population, draws)
        for i in range(lo, top + 1)
    ]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))
