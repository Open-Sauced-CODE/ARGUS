"""Small statistics helpers (no scipy needed): Wilson interval, exact McNemar test, Cohen's kappa."""

import math


def wilson(successes, n, z=1.96):
    """Wilson 95% interval for a proportion. Returns (low, high); (0.0, 1.0) when n is 0."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def fmt_rate(successes, n):
    """'41/60 = 68.3% [55.8, 78.8]' for a report."""
    if n == 0:
        return "0/0 = n/a"
    lo, hi = wilson(successes, n)
    return "{}/{} = {:.1f}% [{:.1f}, {:.1f}]".format(successes, n, 100.0 * successes / n, 100.0 * lo, 100.0 * hi)


def mcnemar_exact(b, c):
    """Exact two-sided McNemar p-value. b = items only model A got right, c = items only model B got right."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def cohen_kappa(labels_a, labels_b):
    """Cohen's kappa for two equally long lists of labels. Returns (kappa, observed_agreement). kappa is None if undefined."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return None, None
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    cats = set(labels_a) | set(labels_b)
    expected = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in cats)
    if expected >= 1.0:
        return None, observed
    return (observed - expected) / (1.0 - expected), observed
