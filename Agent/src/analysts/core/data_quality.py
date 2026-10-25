"""Pure B10.0 Data Quality Gate checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.analysts.contracts import DQCheckV2, DQResultV2
from src.analysts.core.params import DQParams


def _full_period_days(period: Any, grain: str) -> int:
    timestamp = pd.Timestamp(period)
    if grain == "day":
        return 1
    if grain == "week":
        return 7
    if grain == "month":
        return int((timestamp.to_period("M").end_time.normalize() - timestamp.to_period("M").start_time.normalize()).days + 1)
    if grain == "quarter":
        period_value = timestamp.to_period("Q")
        return int((period_value.end_time.normalize() - period_value.start_time.normalize()).days + 1)
    if grain == "year":
        period_value = timestamp.to_period("Y")
        return int((period_value.end_time.normalize() - period_value.start_time.normalize()).days + 1)
    return 7


def _meta_value(load_meta: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in load_meta:
        return load_meta[key]
    return load_meta.get("data_range", {}).get(key, default)


def check_data_quality(series: pd.DataFrame, load_meta: dict[str, Any] | None, params: DQParams, as_of: Any) -> DQResultV2:
    """Run freshness, completeness, simultaneous-movement and drift checks (B10.0)."""
    meta = load_meta or {}
    checks: list[DQCheckV2] = []

    latest = _meta_value(meta, "last_loaded_timestamp")
    if params.expected_freshness_hours is None:
        checks.append(DQCheckV2(name="freshness", status="unknown", detail="no freshness expectation configured (static historical dataset)"))
    elif latest is None:
        checks.append(DQCheckV2(name="freshness", status="unknown", detail="No load timestamp was supplied."))
    else:
        try:
            loaded_at = pd.Timestamp(latest)
            if loaded_at.tzinfo is None:
                loaded_at = loaded_at.tz_localize(timezone.utc)
            observed_at = pd.Timestamp(as_of)
            if observed_at.tzinfo is None:
                observed_at = observed_at.tz_localize(timezone.utc)
            age_hours = (observed_at - loaded_at).total_seconds() / 3600.0
            # The fetcher supplies the latest order timestamp, not a warehouse load watermark.
            status = "pass" if age_hours <= params.expected_freshness_hours else "warn"
            checks.append(DQCheckV2(name="freshness", status=status, detail=f"Latest returned order timestamp is {age_hours:.1f} hours old."))
        except (TypeError, ValueError):
            checks.append(DQCheckV2(name="freshness", status="unknown", detail="Load timestamp could not be parsed."))

    partial = meta.get("partial_periods", {})
    excluded: list[str] = []
    for key, period_key in (("days_covered_first", "first_period"), ("days_covered_last", "last_period")):
        covered = partial.get(key)
        period = partial.get(period_key)
        if covered is not None and period is not None:
            full = _full_period_days(period, params.__dict__.get("grain", "week"))
            if covered < params.completeness_threshold * full:
                excluded.append(str(period))
    # A per-row days_covered column is also accepted for BE-1-supplied tables.
    if "days_covered" in series.columns and not series.empty:
        grain = params.__dict__.get("grain", "week")
        for _, row in series.iterrows():
            if pd.notna(row.get("days_covered")) and pd.notna(row.get("period")):
                if float(row["days_covered"]) < params.completeness_threshold * _full_period_days(row["period"], grain):
                    excluded.append(str(row["period"]))
    excluded = list(dict.fromkeys(excluded))
    # Boundary periods are excluded from scoring; they are not a severe DQ
    # failure by themselves because the caller supplied an explicit window.
    status = "warn" if excluded else "pass"
    detail = "Excluded incomplete periods: " + ", ".join(excluded) if excluded else "All boundary periods meet the coverage threshold."
    checks.append(DQCheckV2(name="period_completeness", status=status, detail=detail))

    if "unit" not in series.columns or series["unit"].nunique(dropna=True) < 2:
        checks.append(DQCheckV2(name="all_unit_drop", status="unknown", detail="Unit comparison was not available."))
    else:
        work = series.copy()
        work["value"] = pd.to_numeric(work["value"], errors="coerce")
        last_period = work["period"].max()
        last = work[work["period"] == last_period]
        dropped = 0
        units = list(work["unit"].dropna().unique())
        for unit in units:
            history = work[(work["unit"] == unit) & (work["period"] < last_period)]["value"].dropna()
            if len(history) >= 3 and len(last[last["unit"] == unit]) > 0:
                expected = float(history.median())
                scale = max(float(np.median(np.abs(history - expected)) * 1.4826), 1.0)
                if float(last[last["unit"] == unit]["value"].iloc[0]) < expected - 2.576 * scale:
                    dropped += 1
        fraction = dropped / len(units) if units else 0.0
        movement_status = "fail" if fraction >= params.all_unit_drop_fraction else "pass"
        checks.append(DQCheckV2(name="all_unit_drop", status=movement_status, detail=f"{dropped}/{len(units)} units below their expected range."))

    null_rate = meta.get("null_rate")
    duplicate_rate = meta.get("duplicate_key_rate")
    history_null = meta.get("history_null_rate")
    history_duplicate = meta.get("history_duplicate_key_rate")
    drifted = []
    if null_rate is not None and history_null is not None and abs(float(null_rate) - float(history_null)) > params.drift_threshold:
        drifted.append("null_rate")
    if duplicate_rate is not None and history_duplicate is not None and abs(float(duplicate_rate) - float(history_duplicate)) > params.drift_threshold:
        drifted.append("duplicate_key_rate")
    drift_status = "fail" if drifted else ("pass" if null_rate is not None or duplicate_rate is not None else "unknown")
    checks.append(DQCheckV2(name="definition_drift", status=drift_status, detail="Drifted fields: " + ", ".join(drifted) if drifted else "No supplied definition drift exceeded the threshold."))

    return DQResultV2(passed=not any(check.status == "fail" for check in checks), checks=checks)
