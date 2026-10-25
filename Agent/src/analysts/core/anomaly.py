"""Pure B10.1 anomaly core: typed tables and parameters in, typed result out."""

from __future__ import annotations

from datetime import datetime, timezone
from math import exp, log
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from src.analysts.contracts import AnalystOutputV2, AnomalyResultV2, ChangePointV2, PeerRankV2
from src.analysts.core.data_quality import check_data_quality
from src.analysts.core.params import AnomalyParams
from src.analysts.core.stats import (
    benjamini_hochberg,
    changepoint,
    count_interval,
    cusum,
    estimate_dispersion,
    log_scale_interval,
    robust_scale,
)


CALIBRATED_K = 1.05


def _c5_interval(values: np.ndarray, level: float, multiplier: float = CALIBRATED_K) -> tuple[float, float, float, list[int]]:
    """C5 screened t prediction interval on non-negative counts."""
    clean = np.asarray(values, dtype=float)
    finite = np.isfinite(clean)
    log_values = np.log1p(np.clip(clean[finite], 0.0, None))
    if log_values.size < 2:
        return 0.0, 0.0, 1.0, []
    median = float(np.median(log_values))
    mad_sigma = max(float(1.4826 * np.median(np.abs(log_values - median))), 1e-9)
    kept_mask = np.abs(log_values - median) <= 3.5 * mad_sigma
    kept = log_values[kept_mask]
    removed = np.flatnonzero(finite)[~kept_mask].tolist()
    if kept.size < 2:
        kept = log_values
        removed = []
    centre = float(np.mean(kept))
    sd = float(np.std(kept, ddof=1)) if kept.size > 1 else 1e-9
    quantile = float(stats.t.ppf(0.5 + level / 2.0, kept.size - 1))
    half_width = multiplier * quantile * np.sqrt(1.0 + 1.0 / kept.size) * max(sd, 1e-9)
    lower, upper = np.expm1(centre - half_width), np.expm1(centre + half_width)
    scale = max(float((upper - lower) / (2.0 * stats.norm.ppf(0.5 + level / 2.0))), 1.0)
    return float(max(0.0, lower)), float(max(0.0, upper)), scale, removed


def _interval(values: np.ndarray, expected: float, level: float, params: AnomalyParams) -> tuple[float, float, float, list[int]]:
    if params.interval_method == "calibrated":
        return _c5_interval(values, level)
    if params.interval_method != "legacy_normal":
        raise ValueError(f"unsupported interval method: {params.interval_method}")
    residual_log = np.log1p(np.clip(values, 0.0, None)) - np.log1p(expected)
    _, log_sigma = robust_scale(residual_log)
    lower, upper = log_scale_interval(log(expected), log_sigma, level)
    scale = max(expected * log_sigma, 1.0)
    return lower, upper, scale, []


def _as_period(value: Any, grain: str) -> pd.Period:
    aliases = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q", "year": "Y"}
    return pd.Timestamp(value).to_period(aliases[grain])


def _excluded_periods(series: pd.DataFrame, load_meta: dict[str, Any], params: AnomalyParams) -> list[str]:
    excluded: list[str] = []
    partial = load_meta.get("partial_periods", {})
    for flag, period_key in (("days_covered_first", "first_period"), ("days_covered_last", "last_period")):
        period, covered = partial.get(period_key), partial.get(flag)
        if period is not None and covered is not None:
            current = _as_period(period, params.grain)
            full = (current.end_time.normalize() - current.start_time.normalize()).days + 1
            if covered < params.completeness_threshold * full:
                excluded.append(str(period))
    if "days_covered" in series.columns:
        for _, row in series.iterrows():
            if pd.notna(row.get("days_covered")):
                current = _as_period(row["period"], params.grain)
                full = (current.end_time.normalize() - current.start_time.normalize()).days + 1
                if float(row["days_covered"]) < params.completeness_threshold * full:
                    excluded.append(str(row["period"]))
    return list(dict.fromkeys(excluded))


def _regular_series(series: pd.DataFrame, params: AnomalyParams) -> pd.DataFrame:
    frame = series.copy()
    frame["period_key"] = frame["period"].map(lambda value: _as_period(value, params.grain))
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame[np.isfinite(frame["value"])].copy()
    if frame.empty:
        return pd.DataFrame(columns=["period_key", "period", "value"])
    group_columns = ["period_key"] + (["unit"] if "unit" in frame.columns else [])
    frame = frame.groupby(group_columns, as_index=False)["value"].sum()
    frame["period"] = frame["period_key"].astype(str)
    return frame.sort_values(group_columns)


def _result(
    *, params: AnomalyParams, dq: Any, verdict: str, reason: str | None = None,
    window: str = "", actual: float = 0.0, expected: float = 0.0,
    expected_range: tuple[float, float] = (0.0, 0.0), deviation_pct: float = 0.0,
    deviation_abs: float = 0.0, robust_score: float = 0.0, persistence: str = "unknown",
    calendar_effects: list[str] | None = None, baseline_kind: str = "none",
    history_periods_used: int = 0, fallback_reason: str | None = None,
    peer_rank: PeerRankV2 | None = None, change_point: ChangePointV2 | None = None,
    correction_used: str | None = None,
    flags: list[str] | None = None,
) -> AnalystOutputV2[AnomalyResultV2]:
    if verdict == "insufficient_evidence":
        return AnalystOutputV2[AnomalyResultV2](module="anomaly", status="insufficient_evidence", reason=reason or "Insufficient evidence.", parameters=params.__dict__, assumptions=[], sources=[], artifacts=[], flags=flags or [])
    result = AnomalyResultV2(
        verdict=verdict, window=window, actual=float(actual), expected=float(expected),
        expected_range=(float(expected_range[0]), float(expected_range[1])), deviation_pct=float(deviation_pct),
        deviation_abs=float(deviation_abs), robust_score=float(robust_score), persistence=persistence,
        level=1.0 - params.confidence_level, calendar_effects=calendar_effects or [], baseline_kind=baseline_kind,
        history_periods_used=history_periods_used, fallback_reason=fallback_reason,
        peer_rank=peer_rank or PeerRankV2(rank=1, n_units=1, n_at_least_as_large=1),
        change_point=change_point, correction_used=correction_used, data_quality=dq,
    )
    return AnalystOutputV2[AnomalyResultV2](module="anomaly", status="ok", result=result, parameters=params.__dict__, assumptions=[], sources=[], artifacts=[], flags=flags or [])


def run_anomaly(params: AnomalyParams, tables: dict[str, Any], seed: int = 0) -> AnalystOutputV2[AnomalyResultV2]:
    """Run the pure anomaly pipeline (B10.0 then B10.1)."""
    del seed  # All calculations are deterministic; stochastic extensions receive this explicitly later.
    series = tables.get("series")
    if series is None:
        series = pd.DataFrame(columns=["period", "value"])
    load_meta = tables.get("load_meta") or {}
    as_of = tables.get("as_of", pd.Timestamp("1970-01-01", tz="UTC"))
    dq = check_data_quality(series, load_meta, params.dq, as_of)
    excluded = _excluded_periods(series, load_meta, params)
    if series.empty:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="The supplied series is empty.")
    frame = _regular_series(series, params)
    if frame.empty:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="The supplied series contains no finite values.")
    all_frame = frame.copy()
    unit = None
    if "unit" in frame.columns:
        unit = tables.get("unit") or params.target_unit
        if unit is None:
            units = list(frame["unit"].dropna().unique())
            unit = units[0] if units else None
        frame = frame[frame["unit"] == unit].copy()
    frame = frame[~frame["period_key"].astype(str).isin([str(_as_period(x, params.grain)) for x in excluded])].copy()
    frame = frame.sort_values("period_key")
    if len(frame) <= params.test_periods:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="Not enough complete periods for a test window.", flags=[f"excluded_periods={excluded}"])
    test = frame.tail(params.test_periods).copy()
    history = frame.iloc[:-params.test_periods].copy()
    calendar_effects: list[str] = []
    calendar = tables.get("calendar")
    event_periods: set[str] = set()
    if calendar is not None and not calendar.empty:
        for _, row in calendar.iterrows():
            period = str(row.get("period"))
            event = str(row.get("event", row.get("name", "calendar_event")))
            event_periods.add(period)
            calendar_effects.append(f"{period}: {event}")
    fit = history[~history["period_key"].astype(str).isin(event_periods)].copy()
    if fit.empty:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="calendar event without history", flags=[f"excluded_periods={excluded}"])
    if calendar is not None:
        for period in test["period_key"].astype(str):
            if period in event_periods and not any(str(value) == period for value in history["period_key"].astype(str)):
                return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="calendar event without history", window=period, calendar_effects=calendar_effects, flags=[f"excluded_periods={excluded}"])

    if len(history) < params.minimum_history_periods:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="History is shorter than the proposed minimum.", flags=[f"excluded_periods={excluded}"])

    if len(history) >= params.long_history_periods:
        baseline_kind, fallback_reason = "seasonal_stl", None
        # Robust seasonal positions are deterministic and do not fit the test window.
        phase = history["period_key"].map(lambda p: p.week if params.grain == "week" else p.month).to_numpy()
        phase_values = {key: float(np.median(fit.loc[phase == key, "value"])) for key in np.unique(phase) if np.any(phase == key)}
        expected_values = [phase_values.get(p.week if params.grain == "week" else p.month, float(fit["value"].median())) for p in test["period_key"]]
        fit_expected = fit["period_key"].map(lambda p: phase_values.get(p.week if params.grain == "week" else p.month, float(fit["value"].median()))).to_numpy()
    else:
        baseline_kind = "trailing_robust" if len(history) >= params.fallback_history_periods else "none"
        fallback_reason = "history below 104 periods; no yearly seasonal term" if baseline_kind != "none" else None
        fit_tail = fit.tail(params.trailing_periods)
        expected_values = [float(fit_tail["value"].median())] * len(test)
        fit_expected = np.full(len(fit_tail), float(fit_tail["value"].median()))
    expected = float(expected_values[-1])
    actual = float(test["value"].iloc[-1])
    if expected < params.minimum_events or actual < params.minimum_events:
        return _result(params=params, dq=dq, verdict="insufficient_evidence", reason="Volume guard: fewer than the proposed minimum events per period.", window=str(test["period"].iloc[-1]), expected=expected, actual=actual, baseline_kind=baseline_kind, history_periods_used=len(history), fallback_reason=fallback_reason, calendar_effects=calendar_effects, flags=[f"excluded_periods={excluded}"])

    interval_fit = fit.tail(min(params.trailing_periods, len(fit)))
    interval_values = interval_fit["value"].to_numpy(dtype=float)
    scored_count = len(test)
    # Sidak allocates the family alpha: alpha_m = 1 - confidence**(1/m),
    # therefore the interval confidence is confidence**(1/m).
    adjusted_level = params.confidence_level if scored_count == 1 else params.confidence_level ** (1.0 / scored_count)
    lower, upper, scale, removed_indices = _interval(interval_values, expected, adjusted_level, params)
    _, _, unadjusted_scale, _ = _interval(interval_values, expected, params.confidence_level, params)
    unadjusted_lower, unadjusted_upper, _, _ = _interval(interval_values, expected, params.confidence_level, params)
    test_values = test["value"].to_numpy(dtype=float)
    # Scores use the unadjusted scale for persistence and peer comparisons.
    test_scores = (test_values - np.asarray(expected_values)) / unadjusted_scale
    outside_adjusted = (test_values < lower) | (test_values > upper)
    outside_unadjusted = (test_values < unadjusted_lower) | (test_values > unadjusted_upper)
    # The serialized result exposes one actual/range pair, so the window route
    # is based on the final scored period.  This keeps the route, verdict, and
    # contract validation aligned when an earlier period in a multi-period
    # window was unusual but the final period returned to normal.
    route_a = bool(outside_adjusted[-1])
    route_b = bool(outside_unadjusted[-2] and outside_unadjusted[-1]) if scored_count > 1 else False
    outside = bool(outside_adjusted[-1])
    dq_severe = dq.passed is False or any(check.status == "fail" for check in dq.checks)
    cusum_crossed, _ = cusum(test_scores)
    sustained = bool(cusum_crossed or np.sum(np.abs(test_scores) >= stats.norm.ppf(0.5 + params.confidence_level / 2.0)) >= 2)
    persistence = "sustained" if sustained else "one_off"
    residuals = frame["value"].to_numpy(dtype=float) - np.median(expected_values)
    cp = changepoint(residuals, min_size=3)
    change_point = ChangePointV2(method=cp["method"], location=str(frame.iloc[cp["location"]]["period_key"]) if cp.get("location") is not None and cp["location"] < len(frame) else None, range=[str(value) for value in cp["range"]] if cp.get("range") else None)
    unit_scores: dict[str, float] = {str(unit) if unit is not None else "__target__": float(np.max(np.abs(test_scores)))}
    if "unit" in all_frame.columns:
        for peer_unit in all_frame["unit"].dropna().astype(str).unique():
            peer_frame = all_frame[all_frame["unit"].astype(str) == peer_unit].sort_values("period_key")
            peer_frame = peer_frame[~peer_frame["period_key"].astype(str).isin([str(_as_period(x, params.grain)) for x in excluded])]
            if len(peer_frame) <= params.test_periods + params.minimum_history_periods:
                unit_scores[peer_unit] = 0.0
                continue
            peer_history = peer_frame.iloc[:-params.test_periods]
            peer_test = peer_frame.tail(params.test_periods)
            peer_fit = peer_history.tail(params.trailing_periods)
            peer_expected = float(peer_fit["value"].median())
            if peer_expected < params.minimum_events:
                unit_scores[peer_unit] = 0.0
                continue
            if params.interval_method == "calibrated":
                _, _, peer_scale, _ = _interval(peer_fit["value"].to_numpy(dtype=float), peer_expected, params.confidence_level, params)
            elif peer_expected >= params.log_interval_min_events:
                peer_residual = np.log1p(peer_fit["value"].clip(lower=0).to_numpy()) - np.log1p(peer_expected)
                _, peer_sigma = robust_scale(peer_residual)
                peer_scale = max(peer_expected * peer_sigma, 1.0)
            else:
                peer_dispersion = estimate_dispersion(peer_fit["value"], np.full(len(peer_fit), peer_expected))
                peer_lower, peer_upper = count_interval(peer_expected, peer_dispersion, params.confidence_level)
                peer_scale = max((peer_upper - peer_lower) / (2.0 * stats.norm.ppf(0.5 + params.confidence_level / 2.0)), 1.0)
            peer_scores = (peer_test["value"].to_numpy(dtype=float) - peer_expected) / peer_scale
            unit_scores[peer_unit] = float(np.max(np.abs(peer_scores)))
    unit_keys = list(unit_scores)
    unit_pvals = np.asarray([2.0 * stats.norm.sf(unit_scores[key]) for key in unit_keys])
    single_unit_requested = params.target_unit is not None
    single_unit_analysis = single_unit_requested or len(unit_scores) == 1
    if single_unit_analysis:
        unit_rejected = np.zeros(len(unit_keys), dtype=bool)
    else:
        unit_rejected, _ = benjamini_hochberg(unit_pvals, params.bh_q)
    target_key = str(unit) if unit is not None else "__target__"
    target_rejected = bool(unit_rejected[unit_keys.index(target_key)])
    correction_used = "not applied: single unit requested" if single_unit_analysis else "benjamini_hochberg_0.05"
    window_alert = route_a or route_b
    if dq_severe:
        verdict = "data_issue_suspected"
    elif window_alert and (single_unit_analysis or target_rejected):
        verdict = "unusual"
    else:
        verdict = "within_normal_range"
    target_score = float(np.max(np.abs(test_scores)))
    peer = PeerRankV2(rank=1 + sum(score > target_score for score in unit_scores.values()), n_units=max(1, len(unit_scores)), n_at_least_as_large=sum(score >= target_score for score in unit_scores.values()))
    deviation_abs = actual - expected
    deviation_pct = deviation_abs / expected if expected else 0.0
    route = "sidak_any" if route_a else "consecutive_unadjusted" if route_b else "none"
    if route_a and route_b:
        route = "sidak_any+consecutive_unadjusted"
    if route == "none" and verdict == "data_issue_suspected":
        route = "data_quality"
    screened = [str(interval_fit.iloc[index]["period_key"]) for index in removed_indices if index < len(interval_fit)]
    flags = [f"excluded_periods={excluded}", f"window_route={route}", f"screen_excluded_periods={','.join(screened)}"]
    return _result(params=params, dq=dq, verdict=verdict, window=str(test["period"].iloc[-1]), actual=actual, expected=expected, expected_range=(lower, upper), deviation_pct=deviation_pct, deviation_abs=deviation_abs, robust_score=float(test_scores[-1]), persistence=persistence, calendar_effects=calendar_effects, baseline_kind=baseline_kind, history_periods_used=len(history), fallback_reason=fallback_reason, peer_rank=peer, change_point=change_point, correction_used=correction_used, flags=flags)
