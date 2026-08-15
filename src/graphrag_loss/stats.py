"""Estimators, resampling, and agreement measures.

Every headline number in this study is returned as an :class:`Estimate` — a
point value with a confidence interval, a sample size, and the name of the
method that produced it. ``CONTEXT.md`` §8 and ``KNOWLEDGE_BASE.md`` §D.1 both
require effect sizes and intervals rather than bare p-values, because at
125–500 questions essentially everything reaches significance.

Census quantities (E1) return a degenerate interval with ``method="census"``:
E1 counts every edge in the graph, so there is no sampling distribution to
resample (``KNOWLEDGE_BASE.md`` §D.4).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar
from statsmodels.stats.multitest import multipletests

__all__ = [
    "Estimate",
    "McNemarResult",
    "census",
    "bootstrap_proportion",
    "bootstrap_mean",
    "paired_bootstrap_diff",
    "mcnemar_test",
    "cohens_h",
    "cohens_d",
    "cohens_kappa",
    "partial_correlation",
    "holm_bonferroni",
    "stratified_sample",
    "weight_quartiles",
]

DEFAULT_N_BOOT = 10_000
DEFAULT_ALPHA = 0.05


class Estimate(NamedTuple):
    """A number that is safe to put in a paper.

    Attributes
    ----------
    value: the point estimate.
    ci_low, ci_high: bounds of the confidence interval. For a census these
        equal ``value`` — the quantity is measured, not estimated.
    n: sample size backing the estimate.
    method: how it was computed, carried into the report verbatim.
    """

    value: float
    ci_low: float
    ci_high: float
    n: int
    method: str


class McNemarResult(NamedTuple):
    """Discordant-pair counts and the test outcome.

    ``b`` = first arm correct, second wrong. ``c`` = first wrong, second right.
    """

    b: int
    c: int
    statistic: float
    p_value: float
    method: str


def census(value: float, n: int) -> Estimate:
    """Wrap a fully-enumerated quantity.

    The interval is degenerate by construction. E1 counts every edge in the
    graph; reporting a bootstrap interval around a census would imply a
    sampling process that does not exist (``KNOWLEDGE_BASE.md`` §D.4).
    """
    return Estimate(value=float(value), ci_low=float(value), ci_high=float(value), n=int(n), method="census")


def _percentile_ci(draws: np.ndarray, alpha: float) -> tuple[float, float]:
    lo = float(np.percentile(draws, 100 * alpha / 2))
    hi = float(np.percentile(draws, 100 * (1 - alpha / 2)))
    return lo, hi


def bootstrap_proportion(
    successes: Sequence[bool] | np.ndarray,
    *,
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = 0,
) -> Estimate:
    """Bootstrap CI for a proportion over a boolean sample."""
    x = np.asarray(successes, dtype=bool)
    n = int(x.size)
    if n == 0:
        return Estimate(math.nan, math.nan, math.nan, 0, "bootstrap-percentile")
    rng = np.random.default_rng(seed)
    draws = rng.binomial(n, x.mean(), size=n_boot) / n
    lo, hi = _percentile_ci(draws, alpha)
    return Estimate(float(x.mean()), lo, hi, n, f"bootstrap-percentile[{n_boot}]")


def bootstrap_mean(
    x: Sequence[float] | np.ndarray,
    *,
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = 0,
) -> Estimate:
    """Bootstrap CI for a mean."""
    a = np.asarray(x, dtype=float)
    n = int(a.size)
    if n == 0:
        return Estimate(math.nan, math.nan, math.nan, 0, "bootstrap-percentile")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    draws = a[idx].mean(axis=1)
    lo, hi = _percentile_ci(draws, alpha)
    return Estimate(float(a.mean()), lo, hi, n, f"bootstrap-percentile[{n_boot}]")


def paired_bootstrap_diff(
    a: Sequence[float] | np.ndarray,
    b: Sequence[float] | np.ndarray,
    *,
    n_boot: int = DEFAULT_N_BOOT,
    alpha: float = DEFAULT_ALPHA,
    seed: int = 0,
) -> Estimate:
    """Bootstrap CI for the paired difference ``mean(a) - mean(b)``.

    Resamples *questions*, not observations, keeping each pair intact. The unit
    of analysis is the question (``KNOWLEDGE_BASE.md`` §D.2), so an
    independent-samples interval would understate the precision available from
    the pairing and would not answer G4's question.
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.shape != y.shape:
        msg = f"paired arrays must have equal shape, got {x.shape} and {y.shape}"
        raise ValueError(msg)
    n = int(x.size)
    if n == 0:
        return Estimate(math.nan, math.nan, math.nan, 0, "paired-bootstrap")
    d = x - y
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    draws = d[idx].mean(axis=1)
    lo, hi = _percentile_ci(draws, alpha)
    return Estimate(float(d.mean()), lo, hi, n, f"paired-bootstrap[{n_boot}]")


def mcnemar_test(
    a_correct: Sequence[bool] | np.ndarray,
    b_correct: Sequence[bool] | np.ndarray,
    *,
    exact: bool = True,
) -> McNemarResult:
    """McNemar's test on paired binary correctness.

    Only the discordant pairs carry information: ``b`` questions where arm A
    succeeded and B failed, ``c`` where the reverse. Used for G4 alongside the
    paired bootstrap interval and Cohen's h.
    """
    x = np.asarray(a_correct, dtype=bool)
    y = np.asarray(b_correct, dtype=bool)
    if x.shape != y.shape:
        msg = f"paired arrays must have equal shape, got {x.shape} and {y.shape}"
        raise ValueError(msg)
    b = int(np.sum(x & ~y))
    c = int(np.sum(~x & y))
    table = [[int(np.sum(x & y)), b], [c, int(np.sum(~x & ~y))]]
    res = sm_mcnemar(table, exact=exact, correction=not exact)
    method = "mcnemar-exact-binomial" if exact else "mcnemar-chi2-continuity-corrected"
    return McNemarResult(b=b, c=c, statistic=float(res.statistic), p_value=float(res.pvalue), method=method)


def cohens_h(p1: float, p2: float) -> float:
    """Effect size for the difference between two proportions."""
    return float(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)))


def cohens_d(x: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray) -> float:
    """Standardised mean difference with a pooled standard deviation."""
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    na, nb = a.size, b.size
    if na < 2 or nb < 2:
        return math.nan
    pooled_var = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if pooled_var == 0:
        return math.nan
    return float((a.mean() - b.mean()) / math.sqrt(pooled_var))


def cohens_kappa(
    labels_a: Sequence[str],
    labels_b: Sequence[str],
    *,
    categories: Sequence[str] | None = None,
    alpha: float = DEFAULT_ALPHA,
) -> Estimate:
    """Cohen's κ between two annotators, with a normal-approximation interval.

    Gate preconditions in E5 and E8 both require κ ≥ 0.7 before an automated
    label is trusted (``KNOWLEDGE_BASE.md`` §D.6, §D.7).
    """
    a = list(labels_a)
    b = list(labels_b)
    if len(a) != len(b):
        msg = f"annotator label vectors must be equal length, got {len(a)} and {len(b)}"
        raise ValueError(msg)
    n = len(a)
    if n == 0:
        return Estimate(math.nan, math.nan, math.nan, 0, "cohens-kappa")

    cats = list(categories) if categories is not None else sorted(set(a) | set(b))
    index = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    table = np.zeros((k, k), dtype=float)
    for la, lb in zip(a, b, strict=True):
        table[index[la], index[lb]] += 1

    po = float(np.trace(table) / n)
    row = table.sum(axis=1) / n
    col = table.sum(axis=0) / n
    pe = float(np.dot(row, col))
    kappa = 1.0 if pe == 1.0 else (po - pe) / (1 - pe)

    # Standard normal-approximation SE (Fleiss, Cohen & Everitt 1969 form).
    if pe == 1.0 or n < 2:
        se = math.nan
    else:
        se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    z = sp_stats.norm.ppf(1 - alpha / 2)
    lo = kappa - z * se if not math.isnan(se) else math.nan
    hi = kappa + z * se if not math.isnan(se) else math.nan
    return Estimate(float(kappa), float(lo), float(hi), n, "cohens-kappa[normal-approx]")


def partial_correlation(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    control: Sequence[float] | np.ndarray,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> Estimate:
    """Pearson correlation of ``x`` and ``y`` after regressing out ``control``.

    ``KNOWLEDGE_BASE.md`` §D.5 requires every multi-topic or centrality-adjacent
    metric to control for ``entities.degree``; without it a reviewer will
    reasonably say the metric rediscovered degree. Implemented as
    residual-on-residual Pearson rather than pulling in a dependency, so the
    arithmetic is visible and directly testable.
    """
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    z = np.asarray(control, dtype=float)
    n = int(a.size)
    if not (a.shape == b.shape == z.shape):
        msg = "x, y and control must have identical shape"
        raise ValueError(msg)
    if n < 4:
        return Estimate(math.nan, math.nan, math.nan, n, "partial-pearson")

    design = np.column_stack([np.ones(n), z])
    res_a = a - design @ np.linalg.lstsq(design, a, rcond=None)[0]
    res_b = b - design @ np.linalg.lstsq(design, b, rcond=None)[0]
    if res_a.std() == 0 or res_b.std() == 0:
        return Estimate(math.nan, math.nan, math.nan, n, "partial-pearson")

    r = float(np.corrcoef(res_a, res_b)[0, 1])
    # Fisher z interval, losing one extra df for the control variable.
    dof = n - 3
    if dof <= 0 or abs(r) >= 1.0:
        return Estimate(r, math.nan, math.nan, n, "partial-pearson")
    zr = math.atanh(r)
    se = 1 / math.sqrt(dof)
    crit = sp_stats.norm.ppf(1 - alpha / 2)
    lo = math.tanh(zr - crit * se)
    hi = math.tanh(zr + crit * se)
    return Estimate(r, float(lo), float(hi), n, "partial-pearson[fisher-z]")


def holm_bonferroni(
    p_values: Sequence[float], *, alpha: float = DEFAULT_ALPHA
) -> list[tuple[float, bool]]:
    """Holm–Bonferroni correction within one metric family.

    Applied *within* a family (all E1 variants together, all E9 arms together),
    never across the whole paper — over-correction destroys real findings
    (``KNOWLEDGE_BASE.md`` §D.3).
    """
    if not len(p_values):
        return []
    reject, adjusted, _, _ = multipletests(list(p_values), alpha=alpha, method="holm")
    return [(float(p), bool(r)) for p, r in zip(adjusted, reject, strict=True)]


def weight_quartiles(weights: Sequence[float] | pd.Series) -> pd.Series:
    """Label each weight with its quartile, ``Q1`` (lowest) through ``Q4``.

    Uses rank-based binning so that heavily tied weight distributions — common
    in GraphRAG relationship weights — still split into four usable strata.
    """
    s = pd.Series(list(weights), dtype=float)
    if s.empty:
        return pd.Series([], dtype="object")
    ranks = s.rank(method="first")
    labels = ["Q1", "Q2", "Q3", "Q4"]
    binned = pd.qcut(ranks, q=4, labels=labels, duplicates="drop")
    return binned.astype("object")


def stratified_sample(
    df: pd.DataFrame,
    *,
    strata_col: str,
    n_per_stratum: int,
    seed: int = 0,
) -> pd.DataFrame:
    """Draw ``n_per_stratum`` rows from each stratum without replacement.

    Strata smaller than ``n_per_stratum`` contribute every row they have; the
    shortfall is visible in the returned frame's stratum counts and must be
    reported rather than silently topped up from elsewhere.
    """
    if strata_col not in df.columns:
        msg = f"stratification column {strata_col!r} not in frame; have {sorted(df.columns)}"
        raise ValueError(msg)
    parts = [
        group.sample(n=min(n_per_stratum, len(group)), random_state=seed)
        for _, group in df.groupby(strata_col, sort=True)
    ]
    if not parts:
        return df.head(0).copy()
    return pd.concat(parts, ignore_index=True)
