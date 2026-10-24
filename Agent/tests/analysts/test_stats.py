"""Fast deterministic tests for the shared stats toolkit and generators."""

import numpy as np
import pandas as pd

from src.analysts.core.stats import (
    benjamini_hochberg,
    bootstrap_ci,
    changepoint,
    count_interval,
    cusum,
    ece,
    estimate_dispersion,
    log_scale_interval,
    paired_bootstrap_diff,
    robust_scale,
    rule_of_three_upper,
    wilson_interval,
)
from tests.analysts.synthetic import customers_orders, multi_unit_series, transactions, weekly_counts


def test_bh_matches_hand_computed_example() -> None:
    reject, adjusted = benjamini_hochberg([0.01, 0.04, 0.03, 0.20], q=0.05)
    np.testing.assert_array_equal(reject, [True, False, False, False])
    np.testing.assert_allclose(adjusted, [0.04, 0.0533333333, 0.0533333333, 0.20])


def test_count_interval_has_nominal_poisson_coverage() -> None:
    rng = np.random.default_rng(17)
    mean = 12.0
    lower, upper = count_interval(mean, dispersion=0.0, level=0.95)
    draws = rng.poisson(mean, size=5000)
    coverage = np.mean((draws >= lower) & (draws <= upper))
    assert abs(coverage - 0.95) <= 0.03


def test_robust_scale_and_dispersion() -> None:
    median, sigma = robust_scale([1, 2, 3, 4, 100], floor=0.5)
    assert median == 3.0
    assert sigma >= 0.5
    assert estimate_dispersion([1, 1, 10, 1, 12], [5, 5, 5, 5, 5]) is not None
    assert estimate_dispersion([4, 5, 6, 5], [5, 5, 5, 5]) is None
    assert log_scale_interval(np.log(10.0), 0.1, 0.95)[0] < 10 < log_scale_interval(np.log(10.0), 0.1, 0.95)[1]


def test_cusum_and_changepoint_planted_shift() -> None:
    noise = np.random.default_rng(23).normal(0, 0.5, size=80)
    assert cusum(noise, k=0.5, h=5.0) == (False, None)
    shifted = np.r_[np.zeros(30), np.full(30, 2.0)]
    crossed, index = cusum(shifted, k=0.5, h=5.0)
    assert crossed and index is not None and index >= 30
    result = changepoint(shifted, min_size=3, penalty=5.0)
    assert result["location"] is not None
    assert abs(result["location"] - 30) <= 3
    assert result["method"] in {"numpy_binary_segmentation", "ruptures_pelt_l2"}


def test_bootstrap_mean_coverage_over_repetitions() -> None:
    generator = np.random.default_rng(31)
    covered = 0
    for repetition in range(300):
        sample = generator.normal(loc=2.0, scale=1.0, size=35)
        low, high = bootstrap_ci(sample, n_resamples=400, seed=repetition)
        covered += int(low <= 2.0 <= high)
    coverage = covered / 300
    assert 0.88 <= coverage <= 0.99


def test_bootstrap_cluster_and_paired_are_deterministic() -> None:
    values = np.array([1.0, 2.0, 4.0, 5.0])
    clusters = ["a", "a", "b", "b"]
    assert bootstrap_ci(values, n_resamples=100, seed=9, cluster_ids=clusters) == bootstrap_ci(values, n_resamples=100, seed=9, cluster_ids=clusters)
    assert paired_bootstrap_diff(values, values - 1, n_resamples=100, seed=9) == paired_bootstrap_diff(values, values - 1, n_resamples=100, seed=9)


def test_wilson_rule_of_three_and_ece() -> None:
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert round(high, 6) == 0.277533
    assert rule_of_three_upper(100) == 0.03
    assert rule_of_three_upper(0) == float("inf")
    assert np.isclose(ece([0, 1, 1, 0], [0.1, 0.9, 0.8, 0.2], bins=2), 0.15)


def test_seeded_synthetic_generators_and_multi_category_orders() -> None:
    first = weekly_counts(30, base=100, yearly_amplitude=0.2, holiday_weeks=[3], seed=4)
    second = weekly_counts(30, base=100, yearly_amplitude=0.2, holiday_weeks=[3], seed=4)
    pd.testing.assert_frame_equal(first, second)
    units = multi_unit_series(3, n_weeks=8, seed=5)
    assert units["period"].nunique() == 8
    assert len(units) == 24
    lines = transactions(n_orders=30, n_customers=10, seed=6)
    assert list(lines.columns) == ["order_id", "customer_id", "order_date", "region", "category", "amount"]
    assert (lines.groupby("order_id")["category"].nunique() > 1).any()
    orders_a, service_a, labels_a = customers_orders(40, process="covariate_hazard", seed=7)
    orders_b, service_b, labels_b = customers_orders(40, process="covariate_hazard", seed=7)
    pd.testing.assert_frame_equal(orders_a, orders_b)
    pd.testing.assert_frame_equal(service_a, service_b)
    pd.testing.assert_frame_equal(labels_a, labels_b)
    assert set(labels_a["churn_label"].unique()) <= {0, 1}
    assert not customers_orders(40, process="bgnbd_like", seed=7)[0].empty
