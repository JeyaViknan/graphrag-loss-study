"""Regression tests for the estimators, against scipy/statsmodels on toy data.

The point is not to re-derive the arithmetic but to pin this package's wrappers
to reference implementations, so a refactor cannot quietly change a headline
number's meaning.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats as sp_stats
from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar

from graphrag_loss import stats


def test_estimate_carries_value_interval_n_and_method():
    e = stats.bootstrap_proportion([True, False, True, True], seed=0)
    assert isinstance(e, stats.Estimate)
    assert e.n == 4
    assert e.ci_low <= e.value <= e.ci_high
    assert "bootstrap" in e.method


def test_census_has_a_degenerate_interval():
    """KB §D.4: E1 enumerates the graph, so there is nothing to resample."""
    e = stats.census(0.37, n=1000)
    assert e.value == e.ci_low == e.ci_high == 0.37
    assert e.method == "census"


def test_bootstrap_proportion_point_estimate_is_the_sample_proportion():
    successes = [True] * 30 + [False] * 70
    e = stats.bootstrap_proportion(successes, seed=0)
    assert e.value == pytest.approx(0.30)


def test_bootstrap_proportion_interval_brackets_the_normal_approximation():
    successes = [True] * 30 + [False] * 70
    e = stats.bootstrap_proportion(successes, n_boot=20_000, seed=0)
    se = math.sqrt(0.3 * 0.7 / 100)
    assert e.ci_low == pytest.approx(0.3 - 1.96 * se, abs=0.03)
    assert e.ci_high == pytest.approx(0.3 + 1.96 * se, abs=0.03)


def test_bootstrap_mean_matches_scipy_bootstrap():
    rng = np.random.default_rng(0)
    x = rng.normal(loc=5.0, scale=2.0, size=200)
    ours = stats.bootstrap_mean(x, n_boot=20_000, seed=0)
    reference = sp_stats.bootstrap(
        (x,), np.mean, n_resamples=20_000, method="percentile", random_state=0
    )
    assert ours.value == pytest.approx(float(np.mean(x)))
    assert ours.ci_low == pytest.approx(reference.confidence_interval.low, abs=0.05)
    assert ours.ci_high == pytest.approx(reference.confidence_interval.high, abs=0.05)


def test_paired_bootstrap_recovers_a_known_difference():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 1, size=300)
    a = base + 0.5
    b = base
    e = stats.paired_bootstrap_diff(a, b, n_boot=5000, seed=0)
    assert e.value == pytest.approx(0.5, abs=1e-9)
    assert e.ci_low > 0  # pairing removes the shared variance entirely


def test_paired_bootstrap_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="equal shape"):
        stats.paired_bootstrap_diff([1, 2, 3], [1, 2])


def test_mcnemar_matches_statsmodels():
    a = [True] * 40 + [False] * 60
    b = [True] * 25 + [False] * 15 + [True] * 20 + [False] * 40
    ours = stats.mcnemar_test(a, b, exact=True)

    x, y = np.array(a), np.array(b)
    table = [
        [int(np.sum(x & y)), int(np.sum(x & ~y))],
        [int(np.sum(~x & y)), int(np.sum(~x & ~y))],
    ]
    reference = sm_mcnemar(table, exact=True)

    assert ours.b == table[0][1]
    assert ours.c == table[1][0]
    assert ours.p_value == pytest.approx(float(reference.pvalue))


def test_mcnemar_counts_only_discordant_pairs():
    a = [True, True, False, False]
    b = [True, False, True, False]
    result = stats.mcnemar_test(a, b)
    assert (result.b, result.c) == (1, 1)


def test_mcnemar_on_identical_arms_is_not_significant():
    a = [True, False] * 50
    result = stats.mcnemar_test(a, a)
    assert (result.b, result.c) == (0, 0)
    assert result.p_value == pytest.approx(1.0)


def test_cohens_h_is_zero_for_equal_proportions():
    assert stats.cohens_h(0.4, 0.4) == pytest.approx(0.0)


def test_cohens_h_sign_follows_the_argument_order():
    assert stats.cohens_h(0.6, 0.4) > 0
    assert stats.cohens_h(0.4, 0.6) < 0


def test_cohens_d_matches_the_textbook_formula():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([2.0, 3.0, 4.0, 5.0])
    pooled = math.sqrt((x.var(ddof=1) + y.var(ddof=1)) / 2)
    assert stats.cohens_d(x, y) == pytest.approx((x.mean() - y.mean()) / pooled)


def test_kappa_is_one_for_perfect_agreement():
    labels = ["i", "ii", "iii", "i", "ii"]
    assert stats.cohens_kappa(labels, labels).value == pytest.approx(1.0)


def test_kappa_matches_sklearn_reference():
    from sklearn.metrics import cohen_kappa_score

    a = ["i", "i", "ii", "iii", "ii", "i", "iii", "ii", "i", "iii"]
    b = ["i", "ii", "ii", "iii", "ii", "i", "ii", "ii", "i", "iii"]
    assert stats.cohens_kappa(a, b).value == pytest.approx(float(cohen_kappa_score(a, b)))


def test_kappa_near_zero_for_independent_labels():
    rng = np.random.default_rng(3)
    a = list(rng.choice(["i", "ii", "iii"], size=600))
    b = list(rng.choice(["i", "ii", "iii"], size=600))
    assert abs(stats.cohens_kappa(a, b).value) < 0.12


def test_kappa_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="equal length"):
        stats.cohens_kappa(["i"], ["i", "ii"])


def test_partial_correlation_removes_a_pure_degree_confound():
    """KB §D.5: if the metric is only degree, it must lose its variance."""
    rng = np.random.default_rng(4)
    degree = rng.normal(0, 1, size=500)
    x = 3 * degree + rng.normal(0, 0.01, size=500)
    y = 2 * degree + rng.normal(0, 0.01, size=500)

    raw = float(np.corrcoef(x, y)[0, 1])
    partial = stats.partial_correlation(x, y, degree)

    assert raw > 0.99
    assert abs(partial.value) < 0.25


def test_partial_correlation_preserves_a_genuine_association():
    rng = np.random.default_rng(5)
    degree = rng.normal(0, 1, size=500)
    shared = rng.normal(0, 1, size=500)
    x = degree + shared
    y = degree + shared
    partial = stats.partial_correlation(x, y, degree)
    assert partial.value > 0.9


def test_partial_correlation_matches_the_residual_definition():
    rng = np.random.default_rng(6)
    z = rng.normal(size=200)
    x = rng.normal(size=200) + 0.5 * z
    y = rng.normal(size=200) + 0.5 * z

    design = np.column_stack([np.ones(200), z])
    rx = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
    ry = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    expected = float(sp_stats.pearsonr(rx, ry)[0])

    assert stats.partial_correlation(x, y, z).value == pytest.approx(expected)


def test_holm_bonferroni_matches_statsmodels():
    from statsmodels.stats.multitest import multipletests

    p = [0.001, 0.02, 0.04, 0.3]
    ours = stats.holm_bonferroni(p)
    reject, adjusted, _, _ = multipletests(p, alpha=0.05, method="holm")
    assert [x[0] for x in ours] == pytest.approx(list(adjusted))
    assert [x[1] for x in ours] == list(reject)


def test_holm_is_more_conservative_than_no_correction():
    p = [0.04, 0.04, 0.04]
    assert all(adj >= raw for (adj, _), raw in zip(stats.holm_bonferroni(p), p, strict=True))


def test_weight_quartiles_split_into_four_strata():
    q = stats.weight_quartiles(list(range(100)))
    assert set(q.dropna()) == {"Q1", "Q2", "Q3", "Q4"}
    assert q.value_counts().to_dict() == {"Q1": 25, "Q2": 25, "Q3": 25, "Q4": 25}


def test_weight_quartiles_survive_heavy_ties():
    """GraphRAG relationship weights tie constantly; rank-binning must cope."""
    q = stats.weight_quartiles([1.0] * 50 + [2.0] * 50)
    assert len(set(q.dropna())) == 4


def test_stratified_sample_draws_evenly():
    import pandas as pd

    df = pd.DataFrame({"stratum": ["Q1"] * 100 + ["Q2"] * 100, "x": range(200)})
    sample = stats.stratified_sample(df, strata_col="stratum", n_per_stratum=25, seed=0)
    assert sample["stratum"].value_counts().to_dict() == {"Q1": 25, "Q2": 25}


def test_stratified_sample_reports_short_strata_rather_than_topping_up():
    import pandas as pd

    df = pd.DataFrame({"stratum": ["Q1"] * 10 + ["Q2"] * 100, "x": range(110)})
    sample = stats.stratified_sample(df, strata_col="stratum", n_per_stratum=25, seed=0)
    assert sample["stratum"].value_counts().to_dict() == {"Q1": 10, "Q2": 25}


def test_stratified_sample_is_deterministic():
    import pandas as pd

    df = pd.DataFrame({"stratum": ["Q1"] * 50 + ["Q2"] * 50, "x": range(100)})
    a = stats.stratified_sample(df, strata_col="stratum", n_per_stratum=10, seed=3)
    b = stats.stratified_sample(df, strata_col="stratum", n_per_stratum=10, seed=3)
    assert a.equals(b)


def test_stratified_sample_rejects_a_missing_column():
    import pandas as pd

    with pytest.raises(ValueError, match="stratification column"):
        stats.stratified_sample(pd.DataFrame({"a": [1]}), strata_col="nope", n_per_stratum=1)


def test_empty_inputs_return_nan_rather_than_raising():
    e = stats.bootstrap_proportion([])
    assert math.isnan(e.value)
    assert e.n == 0
