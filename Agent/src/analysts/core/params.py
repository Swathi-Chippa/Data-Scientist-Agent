"""Proposed, explicit parameters for the B10.0/B10.1 pure analyst core."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DQParams:
    """Data Quality Gate thresholds (B10.0)."""

    grain: str = "week"
    expected_freshness_hours: float | None = 24.0
    completeness_threshold: float = 0.95
    all_unit_drop_fraction: float = 0.70
    drift_threshold: float = 0.10


@dataclass(frozen=True)
class AnomalyParams:
    """Parameters for B10.1 anomaly detection.

    ``calibrated`` is C5 with multiplier 1.05: one 3.5-MAD screen on
    log1p(history), followed by a screened Student-t prediction interval with
    ``sqrt(1 + 1/n)``.  The multiplier and study design are recorded in
    ``docs_an1/CALIBRATION_STUDY_V2.md``.  ``legacy_normal`` is retained for
    comparisons with v1.0 and is known to be miscalibrated.
    """

    grain: str = "week"
    target_unit: str | None = None
    week_start: str = "monday"
    timezone: str = "UTC"
    confidence_level: float = 0.99
    interval_method: str = "calibrated"
    bh_q: float = 0.05
    seasonal_period: int = 52
    long_history_periods: int = 104
    fallback_history_periods: int = 52
    trailing_periods: int = 26
    minimum_history_periods: int = 26
    test_periods: int = 4
    minimum_events: int = 10
    log_interval_min_events: int = 30
    completeness_threshold: float = 0.95
    calendar_events: tuple[str, ...] = field(default_factory=tuple)
    dq: DQParams = field(default_factory=DQParams)
