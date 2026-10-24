"""Seeded in-memory data generators for analyst unit tests."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def _negative_binomial(rng: np.random.Generator, means: np.ndarray, dispersion: float) -> np.ndarray:
    means = np.maximum(means, 0.0)
    if dispersion <= 0:
        return rng.poisson(means).astype(int)
    size = 1.0 / dispersion
    probability = size / (size + means)
    return rng.negative_binomial(size, probability).astype(int)


def weekly_counts(
    n_weeks: int,
    base: float = 100.0,
    growth_per_year: float = 0.0,
    yearly_amplitude: float = 0.0,
    holiday_weeks: Iterable[int] = (),
    dispersion: float = 0.1,
    seed: int = 0,
) -> pd.DataFrame:
    """Generate negative-binomial weekly counts with trend and 52-week seasonality."""

    if n_weeks < 0 or base < 0 or dispersion < 0:
        raise ValueError("n_weeks, base, and dispersion must be non-negative")
    rng = np.random.default_rng(seed)
    week = np.arange(n_weeks, dtype=float)
    trend = 1.0 + growth_per_year * week / 52.0
    season = 1.0 + yearly_amplitude * np.sin(2.0 * np.pi * week / 52.0)
    holiday_set = set(int(value) for value in holiday_weeks)
    holiday_multiplier = np.array([0.65 if int(index) in holiday_set else 1.0 for index in week])
    means = np.maximum(0.0, base * trend * season * holiday_multiplier)
    values = _negative_binomial(rng, means, dispersion)
    periods = pd.date_range("2020-01-06", periods=n_weeks, freq="7D")
    return pd.DataFrame({"period": periods, "value": values})


def multi_unit_series(
    n_units: int,
    n_weeks: int = 52,
    base: float = 100.0,
    growth_per_year: float = 0.0,
    yearly_amplitude: float = 0.0,
    holiday_weeks: Iterable[int] = (),
    dispersion: float = 0.1,
    seed: int = 0,
) -> pd.DataFrame:
    """Generate units sharing one calendar and independent seeded counts."""

    if n_units < 0:
        raise ValueError("n_units must be non-negative")
    frames = []
    for unit in range(n_units):
        frame = weekly_counts(n_weeks, base, growth_per_year, yearly_amplitude, holiday_weeks, dispersion, seed + unit)
        frame.insert(0, "unit", f"unit_{unit + 1}")
        frames.append(frame)
    if not frames:
        return pd.DataFrame({"unit": pd.Series(dtype=str), "period": pd.Series(dtype="datetime64[ns]"), "value": pd.Series(dtype=int)})
    return pd.concat(frames, ignore_index=True)


def transactions(
    n_orders: int = 100,
    n_customers: int = 40,
    seed: int = 0,
    regions: tuple[str, ...] = ("north", "south"),
    categories: tuple[str, ...] = ("home", "beauty", "sports"),
    multi_item_probability: float = 0.35,
) -> pd.DataFrame:
    """Generate line-level orders, including multi-category orders."""

    if n_orders < 0 or n_customers < 1 or not 0 <= multi_item_probability <= 1:
        raise ValueError("invalid transaction generator arguments")
    if not regions or not categories:
        raise ValueError("regions and categories must be non-empty")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for order_number in range(n_orders):
        order_id = f"O{order_number + 1:05d}"
        customer_id = f"C{int(rng.integers(0, n_customers)) + 1:04d}"
        date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 180)))
        region = regions[int(rng.integers(0, len(regions)))]
        selected = [categories[order_number % len(categories)]]
        if len(categories) > 1 and (order_number == 0 or rng.random() < multi_item_probability):
            second = categories[(categories.index(selected[0]) + 1) % len(categories)]
            selected.append(second)
        for category in selected:
            rows.append({"order_id": order_id, "customer_id": customer_id, "order_date": date, "region": region, "category": category, "amount": round(float(rng.uniform(10.0, 150.0)), 2)})
    return pd.DataFrame(rows, columns=["order_id", "customer_id", "order_date", "region", "category", "amount"])


def customers_orders(
    n_customers: int = 100,
    process: str = "covariate_hazard",
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate orders, service events, and true churn labels for two processes."""

    if n_customers < 1:
        raise ValueError("n_customers must be positive")
    if process not in {"covariate_hazard", "bgnbd_like"}:
        raise ValueError("unknown process")
    rng = np.random.default_rng(seed)
    orders: list[dict[str, object]] = []
    service: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    cutoff = pd.Timestamp("2025-01-01")
    for customer_number in range(n_customers):
        customer_id = f"C{customer_number + 1:05d}"
        spend = float(rng.lognormal(mean=3.5, sigma=0.6))
        if process == "covariate_hazard":
            frequency = int(rng.poisson(2.0 + spend / 100.0))
            frequency = max(1, frequency)
            churn_probability = float(np.clip(0.75 - 0.10 * min(frequency, 5) + 0.05 * (spend < 30.0), 0.05, 0.95))
        else:
            frequency = int(rng.geometric(0.45))
            churn_probability = float(np.clip(0.85 - 0.08 * min(frequency, 6), 0.05, 0.95))
        for order_number in range(frequency):
            order_date = cutoff - pd.Timedelta(days=int(rng.integers(1, 180)))
            orders.append({"order_id": f"O{customer_number:05d}_{order_number:02d}", "customer_id": customer_id, "order_date": order_date, "amount": round(float(rng.lognormal(3.5, 0.45)), 2)})
        service.append({"customer_id": customer_id, "event_date": cutoff - pd.Timedelta(days=int(rng.integers(1, 120))), "kind": "delivery_days", "value": round(float(rng.normal(4.0, 0.8)), 2)})
        labels.append({"customer_id": customer_id, "churn_label": int(rng.random() < churn_probability)})
    return (
        pd.DataFrame(orders, columns=["order_id", "customer_id", "order_date", "amount"]),
        pd.DataFrame(service, columns=["customer_id", "event_date", "kind", "value"]),
        pd.DataFrame(labels, columns=["customer_id", "churn_label"]),
    )
