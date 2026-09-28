"""Disproportionality statistics for FAERS drug-pair signals.

For a pair (A, B) and an event E, "exposed" means a report lists both A and B:

                      E        not E
    A and B           a          b          a + b = n(A and B)
    not (A and B)     c          d          c = n(E) - a,  d = N - n(A and B) - c

- PRR = [a / (a+b)] / [c / (c+d)]
- ROR = (a*d) / (b*c), 95% CI exp(ln ROR ± 1.96 * sqrt(1/a + 1/b + 1/c + 1/d))
- chi-square with Yates' correction = N (|ad - bc| - N/2)^2 / ((a+b)(c+d)(a+c)(b+d))

A signal is **surfaced** only if it meets the Evans criteria (PRR >= 2, chi-square
>= 4, a >= 3), the ROR's lower 95% bound is above 1, and neither drug explains it
on its own: the pair's event rate a / n(A and B) must be at least `min_excess`
times the event rate of A in reports without B, and of B in reports without A:

    rate(A without B) = (n(A and E) - a) / (n(A) - n(A and B))

Evans SJW, Waller PC, Davis S. Use of proportional reporting ratios (PRRs) for
signal generation from spontaneous adverse drug reaction reports.
Pharmacoepidemiol Drug Saf. 2001;10(6):483-486. doi:10.1002/pds.677
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Thresholds:
    min_prr: float = 2.0
    min_chi2: float = 4.0
    min_reports: int = 3
    min_ror_lower: float = 1.0        # strictly greater than
    min_excess: float = 2.0           # pair rate / single-drug rate, for both drugs


@dataclass(frozen=True)
class PairEventCounts:
    """openFDA counts for one pair and one event."""
    total: int          # N: all reports
    n_a: int            # reports listing A
    n_b: int            # reports listing B
    n_ab: int           # reports listing A and B
    n_e: int            # reports with the event
    n_ae: int           # A and the event
    n_be: int           # B and the event
    n_abe: int          # A, B and the event (= a)


@dataclass
class SignalStats:
    event: str
    a: int
    b: int
    c: int
    d: int
    prr: Optional[float]
    ror: Optional[float]
    ror_ci_low: Optional[float]
    ror_ci_high: Optional[float]
    chi2: Optional[float]
    pair_rate: Optional[float]
    rate_a_without_b: Optional[float]
    rate_b_without_a: Optional[float]
    surfaced: bool = False
    reasons: List[str] = field(default_factory=list)     # why it was suppressed

    def to_dict(self) -> dict:
        return asdict(self)


def two_by_two(c: PairEventCounts):
    a = c.n_abe
    b = c.n_ab - a
    cc = c.n_e - a
    d = c.total - c.n_ab - cc
    if min(a, b, cc, d) < 0:
        raise ValueError(f"inconsistent counts: {c}")
    return a, b, cc, d


def prr(a: int, b: int, c: int, d: int) -> Optional[float]:
    if a + b == 0 or c + d == 0 or c == 0:
        return None
    return (a / (a + b)) / (c / (c + d))


def ror_ci(a: int, b: int, c: int, d: int, z: float = 1.959964):
    """ROR and its 95% CI; None where a cell is 0 (no continuity correction)."""
    if min(a, b, c, d) == 0:
        return None, None, None
    ror = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return ror, math.exp(math.log(ror) - z * se), math.exp(math.log(ror) + z * se)


def chi2_yates(a: int, b: int, c: int, d: int) -> Optional[float]:
    n = a + b + c + d
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        return None
    return n * max(abs(a * d - b * c) - n / 2, 0) ** 2 / den


def _rate(num: int, den: int) -> Optional[float]:
    return num / den if den > 0 else None


def assess(event: str, counts: PairEventCounts, th: Thresholds = Thresholds(),
           names: tuple = ("drug A", "drug B")) -> SignalStats:
    a, b, c, d = two_by_two(counts)
    p = prr(a, b, c, d)
    r, lo, hi = ror_ci(a, b, c, d)
    x2 = chi2_yates(a, b, c, d)
    pair_rate = _rate(a, counts.n_ab)
    ra = _rate(counts.n_ae - a, counts.n_a - counts.n_ab)
    rb = _rate(counts.n_be - a, counts.n_b - counts.n_ab)
    reasons = []
    if a < th.min_reports:
        reasons.append(f"fewer than {th.min_reports} reports")
    if p is None or p < th.min_prr:
        reasons.append(f"PRR below {th.min_prr:g}")
    if x2 is None or x2 < th.min_chi2:
        reasons.append(f"chi-square below {th.min_chi2:g}")
    if lo is None or lo <= th.min_ror_lower:
        reasons.append(f"ROR lower 95% bound not above {th.min_ror_lower:g}")
    for drug, rate in ((names[0], ra), (names[1], rb)):
        if pair_rate is not None and rate is not None and pair_rate < th.min_excess * rate:
            reasons.append(f"explained by {drug} alone (pair rate < {th.min_excess:g} x its rate without the other drug)")
    rnd = lambda v, k=3: None if v is None else round(v, k)
    return SignalStats(event, a, b, c, d, rnd(p), rnd(r), rnd(lo), rnd(hi), rnd(x2, 2), rnd(pair_rate, 5),
                       rnd(ra, 5), rnd(rb, 5), surfaced=not reasons, reasons=reasons)
