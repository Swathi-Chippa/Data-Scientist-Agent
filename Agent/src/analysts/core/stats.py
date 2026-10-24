"""Seedable statistical primitives for the analyst modules.

These helpers are deliberately independent of the warehouse and of any
analyst class.  They implement the numerical pieces referenced by design
sections A4 and B10.1-B10.4; callers own the input validation and business
interpretation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from scipy import stats


def _finite_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
    return array[np.isfinite(array)]


def robust_scale(x: Iterable[float], floor: float = 1e-9) -> tuple[float, float]:
    """Return ``(median, 1.4826 * MAD)`` with a positive sigma floor."""

    if floor <= 0:
        raise ValueError("floor must be positive")
    values = _finite_array(x)
    if values.size == 0:
        return float("nan"), float(floor)
    median = float(np.median(values))
    mad_sigma = max(float(1.4826 * np.median(np.abs(values - median))), float(floor))
    return median, mad_sigma


def benjamini_hochberg(pvals: Iterable[float], q: float) -> tuple[np.ndarray, np.ndarray]:
    """Apply BH FDR control and return ``(reject, adjusted_p_values)``.

    NaN p-values are never rejected and retain NaN adjusted values.  The
    adjusted values are returned in the same order as the input.
    """

    if not 0 < q <= 1:
        raise ValueError("q must be in (0, 1]")
    p = np.asarray(list(pvals) if not isinstance(pvals, np.ndarray) else pvals, dtype=float)
    adjusted = np.full(p.shape, np.nan, dtype=float)
    reject = np.zeros(p.shape, dtype=bool)
    valid = np.isfinite(p)
    if not valid.any():
        return reject, adjusted
    valid_indices = np.flatnonzero(valid)
    order = valid_indices[np.argsort(p[valid], kind="mergesort")]
    ranked = p[order]
    m = ranked.size
    raw = ranked * m / np.arange(1, m + 1, dtype=float)
    corrected = np.minimum.accumulate(raw[::-1])[::-1]
    corrected = np.clip(corrected, 0.0, 1.0)
    adjusted[order] = corrected
    reject[valid] = adjusted[valid] <= q
    return reject, adjusted


def count_interval(mean: float, dispersion: float | None, level: float) -> tuple[int, int]:
    """Return an exact central count prediction interval.

    ``dispersion`` is the negative-binomial quadratic dispersion ``alpha``
    where variance is ``mean + alpha * mean**2``.  ``None`` or zero selects a
    Poisson distribution.  Quantiles use SciPy's exact discrete distributions.
    """

    if mean < 0:
        raise ValueError("mean must be non-negative")
    if dispersion is not None and dispersion < 0:
        raise ValueError("dispersion must be non-negative or None")
    if not 0 < level < 1:
        raise ValueError("level must be in (0, 1)")
    tail = (1.0 - level) / 2.0
    if dispersion is None or dispersion == 0 or mean == 0:
        distribution = stats.poisson(mu=mean)
    else:
        size = 1.0 / float(dispersion)
        probability = size / (size + float(mean))
        distribution = stats.nbinom(n=size, p=probability)
    lower = distribution.ppf(tail)
    upper = distribution.ppf(1.0 - tail)
    return int(lower), int(upper)


def estimate_dispersion(history_counts: Iterable[float], fitted: Iterable[float]) -> float | None:
    """Estimate negative-binomial quadratic dispersion by moments.

    Returns ``None`` when the residual variation is not over-dispersed relative
    to the fitted Poisson mean, or when the estimate is undefined.
    """

    observed = np.asarray(history_counts, dtype=float)
    expected = np.asarray(fitted, dtype=float)
    if observed.shape != expected.shape or observed.size < 2:
        return None
    valid = np.isfinite(observed) & np.isfinite(expected) & (expected > 0)
    if valid.sum() < 2:
        return None
    residual = observed[valid] - expected[valid]
    variance = float(np.mean(residual**2))
    mean_fitted = float(np.mean(expected[valid]))
    if variance <= mean_fitted:
        return None
    return float((variance - mean_fitted) / (mean_fitted**2))


def log_scale_interval(fitted_log: float, sigma_log: float, level: float) -> tuple[float, float]:
    """Return a central log-normal interval on the original count scale."""

    if sigma_log < 0 or not 0 < level < 1:
        raise ValueError("sigma_log must be non-negative and level must be in (0, 1)")
    z = float(stats.norm.ppf(0.5 + level / 2.0))
    return float(np.exp(fitted_log - z * sigma_log)), float(np.exp(fitted_log + z * sigma_log))


def cusum(standardized_residuals: Iterable[float], k: float = 0.5, h: float = 5.0) -> tuple[bool, int | None]:
    """Return whether two-sided standardized CUSUM crosses ``h`` first."""

    if k < 0 or h <= 0:
        raise ValueError("k must be non-negative and h must be positive")
    positive = negative = 0.0
    for index, residual in enumerate(np.asarray(list(standardized_residuals), dtype=float)):
        if not np.isfinite(residual):
            continue
        positive = max(0.0, positive + residual - k)
        negative = min(0.0, negative + residual + k)
        if positive >= h or abs(negative) >= h:
            return True, index
    return False, None


def _binary_segmentation(values: np.ndarray, min_size: int, penalty: float) -> dict[str, Any]:
    n = values.size
    if n < 2 * min_size:
        return {"method": "numpy_binary_segmentation", "location": None, "range": None}
    overall_sse = float(np.sum((values - values.mean()) ** 2))
    best_gain = 0.0
    best_location: int | None = None
    for location in range(min_size, n - min_size + 1):
        left, right = values[:location], values[location:]
        split_sse = float(np.sum((left - left.mean()) ** 2) + np.sum((right - right.mean()) ** 2))
        gain = overall_sse - split_sse
        if gain > best_gain:
            best_gain = gain
            best_location = location
    if best_location is None or best_gain <= penalty:
        return {"method": "numpy_binary_segmentation", "location": None, "range": None}
    return {
        "method": "numpy_binary_segmentation",
        "location": best_location,
        "range": [max(0, best_location - min_size), min(n, best_location + min_size)],
    }


def changepoint(residuals: Iterable[float], min_size: int = 3, penalty: float = 5.0) -> dict[str, Any]:
    """Find a level change with ruptures PELT or a NumPy fallback.

    The return value always records the implementation used.  Locations are
    zero-based indices and ``range`` is a small uncertainty band around it.
    """

    if min_size < 1 or penalty < 0:
        raise ValueError("min_size must be positive and penalty non-negative")
    values = _finite_array(residuals)
    if values.size < 2 * min_size:
        return {"method": "numpy_binary_segmentation", "location": None, "range": None}
    try:
        import ruptures as rpt  # type: ignore

        breakpoints = rpt.Pelt(model="l2", min_size=min_size).fit(values).predict(pen=penalty)
        candidates = [int(point) for point in breakpoints if int(point) < values.size]
        if not candidates:
            return {"method": "ruptures_pelt_l2", "location": None, "range": None}
        location = candidates[0]
        return {
            "method": "ruptures_pelt_l2",
            "location": location,
            "range": [max(0, location - min_size), min(values.size, location + min_size)],
        }
    except ImportError:
        return _binary_segmentation(values, min_size, penalty)


def bootstrap_ci(
    values: Iterable[float] | Callable[[np.random.Generator], Iterable[float]],
    n_resamples: int = 2000,
    seed: int = 0,
    cluster_ids: Iterable[Any] | None = None,
    level: float = 0.95,
) -> tuple[float, float]:
    """Return a percentile bootstrap interval for the sample mean.

    A callable is invoked once with the seeded generator to produce the rows.
    With ``cluster_ids``, clusters rather than individual rows are resampled.
    """

    if n_resamples < 1 or not 0 < level < 1:
        raise ValueError("n_resamples must be positive and level must be in (0, 1)")
    rng = np.random.default_rng(seed)
    raw = values(rng) if callable(values) else values
    observations = _finite_array(raw)
    if observations.size == 0:
        return float("nan"), float("nan")
    if cluster_ids is None:
        draws = rng.integers(0, observations.size, size=(n_resamples, observations.size))
        estimates = observations[draws].mean(axis=1)
    else:
        clusters = np.asarray(list(cluster_ids))
        if clusters.size != observations.size:
            raise ValueError("cluster_ids must have one value per observation")
        unique = np.unique(clusters)
        cluster_rows = [np.flatnonzero(clusters == cluster) for cluster in unique]
        selected = rng.integers(0, len(unique), size=(n_resamples, len(unique)))
        estimates = np.empty(n_resamples, dtype=float)
        for row, indices in enumerate(selected):
            sample_indices = np.concatenate([cluster_rows[index] for index in indices])
            estimates[row] = observations[sample_indices].mean()
    tail = (1.0 - level) / 2.0
    return float(np.quantile(estimates, tail)), float(np.quantile(estimates, 1.0 - tail))


def wilson_interval(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Return a Wilson score interval for a binomial proportion."""

    if n <= 0 or k < 0 or k > n or not 0 < level < 1:
        raise ValueError("require 0 <= k <= n, n > 0, and level in (0, 1)")
    z = float(stats.norm.ppf(0.5 + level / 2.0))
    p = k / n
    denominator = 1.0 + z**2 / n
    centre = (p + z**2 / (2.0 * n)) / denominator
    radius = z * np.sqrt(p * (1.0 - p) / n + z**2 / (4.0 * n**2)) / denominator
    return float(centre - radius), float(centre + radius)


def paired_bootstrap_diff(a: Iterable[float], b: Iterable[float], n_resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Return a percentile interval for the paired mean difference ``a - b``."""

    left, right = np.asarray(list(a), dtype=float), np.asarray(list(b), dtype=float)
    if left.shape != right.shape or left.size == 0:
        raise ValueError("a and b must be non-empty arrays with equal shape")
    differences = left - right
    return bootstrap_ci(differences, n_resamples=n_resamples, seed=seed)


def rule_of_three_upper(n: int) -> float:
    """Return the approximate one-sided 95% upper bound after zero events."""

    if n < 0:
        raise ValueError("n must be non-negative")
    return float("inf") if n == 0 else 3.0 / n


def ece(y_true: Iterable[int], p: Iterable[float], bins: int = 10) -> float:
    """Return expected calibration error using equal-width probability bins."""

    if bins < 1:
        raise ValueError("bins must be positive")
    observed = np.asarray(list(y_true), dtype=float)
    predicted = np.asarray(list(p), dtype=float)
    if observed.shape != predicted.shape or observed.size == 0:
        raise ValueError("y_true and p must be non-empty arrays with equal shape")
    if np.any(~np.isfinite(predicted)) or np.any((predicted < 0) | (predicted > 1)):
        raise ValueError("p must contain probabilities in [0, 1]")
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.minimum(np.digitize(predicted, edges[1:-1], right=False), bins - 1)
    error = 0.0
    for bucket in range(bins):
        mask = assignments == bucket
        if mask.any():
            error += mask.mean() * abs(float(observed[mask].mean()) - float(predicted[mask].mean()))
    return float(error)
