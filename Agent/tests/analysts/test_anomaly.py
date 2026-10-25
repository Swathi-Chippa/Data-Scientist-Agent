from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.analysts.core.anomaly import run_anomaly
from src.analysts.core.params import AnomalyParams, DQParams
from src.analysts.anomaly import AnomalyAnalyst
import src.analysts.anomaly as anomaly_module
from dataclasses import replace
from datetime import date, timedelta
from src.analysts.fetchers_olist import fetch_weekly_orders as real_fetch_weekly_orders


FIXTURE = Path(__file__).parent / "fixtures" / "sp_weekly_orders.csv"


def _fixture_through(period: str) -> pd.DataFrame:
    frame = pd.read_csv(FIXTURE)
    return frame[frame["period"] <= period].copy()


def test_fixture_spike_is_unusual_and_excludes_boundary_period():
    frame = _fixture_through("2018-07-09")
    output = run_anomaly(
        AnomalyParams(test_periods=1, dq=DQParams(grain="week")),
        {"series": frame, "load_meta": {}},
        seed=7,
    )
    result = output.result
    assert output.status == "ok"
    assert result.verdict == "unusual"
    assert 600 <= result.expected <= 730
    assert -0.55 <= result.deviation_pct <= -0.40
    assert result.actual < result.expected_range[0]
    assert "excluded_periods=[]" in output.flags[0]


def test_fixture_last_partial_boundary_is_excluded():
    output = run_anomaly(AnomalyParams(dq=DQParams()), {"series": pd.read_csv(FIXTURE)}, seed=7)
    assert "2018-08-27" in output.flags[0]
    assert "2017-01-16" not in output.flags[0]


def test_calendar_event_without_history_cannot_be_unusual():
    frame = _fixture_through("2017-11-20")
    calendar = pd.DataFrame({"period": ["2017-11-20/2017-11-26"], "event": ["Black Friday"]})
    output = run_anomaly(
        AnomalyParams(test_periods=1, dq=DQParams(grain="week")),
        {"series": frame, "calendar": calendar, "load_meta": {}},
        seed=1,
    )
    assert output.status == "insufficient_evidence"
    assert output.reason == "calendar event without history"


def test_training_outlier_is_not_scored_as_test_anomaly():
    frame = _synthetic([100] * 30 + [500] + [100] * 4)
    output = run_anomaly(
        AnomalyParams(test_periods=1, dq=DQParams(grain="week")),
        {"series": frame, "load_meta": {}},
        seed=1,
    )
    assert output.result is not None
    assert output.result.verdict != "unusual"


def test_empty_and_all_nan_inputs_are_insufficient_not_exceptions():
    params = AnomalyParams(dq=DQParams())
    for frame in (pd.DataFrame(columns=["period", "value"]), pd.DataFrame({"period": ["2024-01-01"], "value": [float("nan")] })):
        output = run_anomaly(params, {"series": frame}, seed=0)
        assert output.status == "insufficient_evidence"


def _synthetic(values, units=None):
    frame = pd.DataFrame({"period": pd.date_range("2020-01-06", periods=len(values), freq="W-MON"), "value": values})
    frame["period"] = frame["period"].dt.strftime("%Y-%m-%d")
    if units is not None:
        frame["unit"] = units
    return frame


def test_black_friday_without_calendar_is_unusual_with_sufficient_history():
    output = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _fixture_through("2017-11-20")}, seed=2)
    assert output.result is not None
    assert output.result.verdict == "unusual"


def test_planted_level_shift_is_detected():
    output = run_anomaly(AnomalyParams(test_periods=4, dq=DQParams()), {"series": _synthetic([100] * 56 + [125] * 4)}, seed=3)
    assert output.result is not None
    assert output.result.verdict == "unusual"
    assert output.result.persistence == "sustained"


def test_one_week_spike_is_one_off():
    output = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic([95, 105] * 29 + [130])}, seed=4)
    assert output.result is not None
    assert output.result.verdict == "unusual"
    assert output.result.persistence == "one_off"


def test_growth_with_moving_holiday_has_no_normal_week_alert():
    values = [round(100 * (1.30 ** (i / 52))) for i in range(60)]
    output = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic(values)}, seed=5)
    assert output.result is not None
    assert output.result.verdict != "unusual"


def test_short_history_and_volume_guard_are_insufficient():
    short = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic([100] * 20)}, seed=6)
    low = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic([5] * 40)}, seed=6)
    assert short.status == "insufficient_evidence"
    assert low.status == "insufficient_evidence"
    assert "Volume guard" in low.reason


def test_calibrated_interval_is_used_for_10_to_29_events():
    values = [20] * 59 + [21]
    output = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic(values)}, seed=7)
    assert output.result is not None
    assert output.parameters["interval_method"] == "calibrated"
    assert output.result.verdict == "unusual"
    assert any(flag == "window_route=sidak_any" for flag in output.flags)


def test_same_seed_is_deterministic():
    tables = {"series": _synthetic([100] * 59 + [150])}
    first = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), tables, seed=8)
    second = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), tables, seed=8)
    assert first.model_dump() == second.model_dump()


def test_peer_rank_and_bh_scan_all_units():
    periods = pd.date_range("2020-01-06", periods=60, freq="W-MON").strftime("%Y-%m-%d")
    frame = pd.concat([
        pd.DataFrame({"period": periods, "value": [100] * 59 + [250], "unit": "SP"}),
        pd.DataFrame({"period": periods, "value": [100] * 60, "unit": "RJ"}),
        pd.DataFrame({"period": periods, "value": [100] * 60, "unit": "MG"}),
    ], ignore_index=True)
    output = run_anomaly(AnomalyParams(test_periods=1, target_unit="SP", dq=DQParams()), {"series": frame}, seed=9)
    assert output.result is not None
    assert output.result.peer_rank.n_units == 3
    assert output.result.correction_used == "not applied: single unit requested"


def test_single_unit_interval_verdict_and_range_are_consistent():
    normal = run_anomaly(AnomalyParams(test_periods=1, target_unit="SP", dq=DQParams()), {"series": _synthetic([100] * 59 + [100], units=["SP"] * 60)}, seed=9)
    unusual = run_anomaly(AnomalyParams(test_periods=1, target_unit="SP", dq=DQParams()), {"series": _synthetic([100] * 59 + [60], units=["SP"] * 60)}, seed=9)

    assert normal.result is not None
    assert normal.result.verdict == "within_normal_range"
    assert normal.result.expected_range[0] <= normal.result.actual <= normal.result.expected_range[1]
    assert any(flag == "window_route=none" for flag in normal.flags)
    assert unusual.result is not None
    assert unusual.result.verdict == "unusual"
    assert not (unusual.result.expected_range[0] <= unusual.result.actual <= unusual.result.expected_range[1])
    assert any(flag == "window_route=sidak_any" for flag in unusual.flags)
    assert unusual.result.correction_used == "not applied: single unit requested"


def test_insufficient_evidence_has_no_window_route():
    output = run_anomaly(AnomalyParams(test_periods=1, target_unit="SP", dq=DQParams()), {"series": _synthetic([100] * 20, units=["SP"] * 20)}, seed=9)
    assert output.status == "insufficient_evidence"
    assert not any(flag.startswith("window_route=") for flag in output.flags)


def test_expected_range_matches_decision_interval_for_both_verdicts():
    for value in (60, 100):
        output = run_anomaly(AnomalyParams(test_periods=1, target_unit="SP", dq=DQParams()), {"series": _synthetic([100] * 59 + [value], units=["SP"] * 60)}, seed=9)
        assert output.result is not None
        lower, upper = output.result.expected_range
        inside = lower <= output.result.actual <= upper
        assert inside == (output.result.verdict == "within_normal_range")


def test_legacy_wrapper_shape_and_fail_closed_inputs():
    output = AnomalyAnalyst().run({"region": "SP", "time_grain": "week"})
    assert {"status", "verdict", "summary", "metrics", "tables", "evidence_claims"}.issubset(output.model_dump())
    assert output.evidence_claims
    for context in ({"region": "XX"}, {"region": "SP'; DROP TABLE orders; --"}, {"region": "SP", "time_grain": "decade"}):
        assert AnomalyAnalyst().run(context).status == "insufficient_evidence"


def test_legacy_peer_rank_sentence_for_real_windows(monkeypatch):
    real_run = anomaly_module.run_anomaly
    for window in ("2018-05-28", "2018-07-09"):
        end = (date.fromisoformat(window) + timedelta(days=7)).isoformat()
        monkeypatch.setattr(anomaly_module, "fetch_weekly_orders", lambda **kwargs: real_fetch_weekly_orders(None, "2017-01-16", end, "week"))
        monkeypatch.setattr(anomaly_module, "run_anomaly", lambda params, tables, seed=0: real_run(replace(params, test_periods=1), tables, seed))
        output = AnomalyAnalyst().run({"region": "SP", "time_grain": "week"})
        peer = output.metrics["peer_rank"]
        sentence = f"{peer['n_at_least_as_large']} of {peer['n_units']} states show a deviation at least this large (rank {peer['rank']})"
        assert sentence in output.summary
        assert sentence in output.evidence_claims[0]["text"]


def _wilson(successes, trials):
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    margin = z * ((p * (1 - p) / trials + z * z / (4 * trials * trials)) ** 0.5) / denominator
    return centre - margin, centre + margin


def test_null_false_alert_rates_and_interval_coverage():
    # Seeded generator: 2,000 series, 60 weekly Poisson(lambda=100) periods,
    # 26-period trailing history and four scored periods.  The window decision
    # uses the same C5 k=1.05 formula as the core, including Sidak for four.
    rng = np.random.default_rng(20260424)
    values = rng.poisson(100, size=(2000, 60)).astype(float)
    history = np.log1p(values[:, 30:56])
    centre = np.median(history, axis=1)
    sigma = np.maximum(1.4826 * np.median(np.abs(history - centre[:, None]), axis=1), 1e-9)
    kept = np.abs(history - centre[:, None]) <= 3.5 * sigma[:, None]
    screened = np.where(kept, history, np.nan)
    n = np.maximum(np.sum(kept, axis=1), 2)
    mean = np.nanmean(screened, axis=1)
    sd = np.nan_to_num(np.nanstd(screened, axis=1, ddof=1), nan=1e-9)

    def bounds(level):
        q = stats.t.ppf(0.5 + level / 2.0, n - 1)
        half = 1.05 * q * np.sqrt(1 + 1 / n) * np.maximum(sd, 1e-9)
        return np.expm1(mean - half), np.expm1(mean + half)

    lower, upper = bounds(0.99 ** 0.25)
    lower99, upper99 = bounds(0.99)
    scored = values[:, 56:60]
    adjusted_outside = (scored < lower[:, None]) | (scored > upper[:, None])
    unadjusted_outside = (scored < lower99[:, None]) | (scored > upper99[:, None])
    period_alerts = int(adjusted_outside.sum())
    window_alerts = int((adjusted_outside.any(axis=1) | (unadjusted_outside[:, :-1] & unadjusted_outside[:, 1:]).any(axis=1)).sum())
    total_periods = values.shape[0] * 4
    per_period = period_alerts / total_periods
    per_window = window_alerts / values.shape[0]
    coverage = 1 - period_alerts / total_periods
    print({"per_series_week": per_period, "per_4_week_window": per_window, "wilson_week": _wilson(period_alerts, total_periods), "wilson_window": _wilson(window_alerts, values.shape[0]), "coverage_per_period": coverage})
    assert per_period <= 0.016
    assert per_window <= 0.025

    contaminated = values.copy()
    contaminated[:, 30] = np.rint(contaminated[:, 30] * 2.5)
    contaminated[:, 31] = np.rint(contaminated[:, 31] * 0.4)
    contaminated_history = np.log1p(contaminated[:, 30:56])
    contaminated_centre = np.median(contaminated_history, axis=1)
    contaminated_sigma = np.maximum(1.4826 * np.median(np.abs(contaminated_history - contaminated_centre[:, None]), axis=1), 1e-9)
    contaminated_kept = np.abs(contaminated_history - contaminated_centre[:, None]) <= 3.5 * contaminated_sigma[:, None]
    contaminated_screened = np.where(contaminated_kept, contaminated_history, np.nan)
    contaminated_n = np.maximum(np.sum(contaminated_kept, axis=1), 2)
    contaminated_mean = np.nanmean(contaminated_screened, axis=1)
    contaminated_sd = np.nan_to_num(np.nanstd(contaminated_screened, axis=1, ddof=1), nan=1e-9)
    contaminated_q = stats.t.ppf(0.5 + (0.99 ** 0.25) / 2.0, contaminated_n - 1)
    contaminated_half = 1.05 * contaminated_q * np.sqrt(1 + 1 / contaminated_n) * np.maximum(contaminated_sd, 1e-9)
    contaminated_lower = np.expm1(contaminated_mean - contaminated_half)
    contaminated_upper = np.expm1(contaminated_mean + contaminated_half)
    contaminated_alerts = ((scored < contaminated_lower[:, None]) | (scored > contaminated_upper[:, None])).sum()
    assert contaminated_alerts / total_periods <= 0.016


def test_contaminated_history_safety_and_excluded_period_listing():
    values = [100] * 26
    values[4] = 400
    values.extend([100, 100, 100, 60])
    output = run_anomaly(AnomalyParams(test_periods=4, dq=DQParams()), {"series": _synthetic(values)}, seed=12)
    assert output.result is not None
    assert any(flag.startswith("screen_excluded_periods=") and "2020-02-03" in flag for flag in output.flags)


def test_single_sharp_drop_is_unusual():
    output = run_anomaly(AnomalyParams(test_periods=1, dq=DQParams()), {"series": _synthetic([100] * 59 + [55])}, seed=13)
    assert output.result is not None
    assert output.result.verdict == "unusual"


def test_window_routes_sidak_and_consecutive():
    sidak = run_anomaly(AnomalyParams(test_periods=4, dq=DQParams()), {"series": _synthetic([100] * 59 + [60])}, seed=14)
    consecutive = run_anomaly(AnomalyParams(test_periods=2, dq=DQParams()), {"series": _synthetic([100] * 58 + [70, 70])}, seed=15)
    assert any(flag == "window_route=sidak_any" for flag in sidak.flags)
    assert any(flag in {"window_route=consecutive_unadjusted", "window_route=sidak_any+consecutive_unadjusted"} for flag in consecutive.flags)
    for output in (sidak, consecutive):
        assert output.result is not None
        assert output.result.verdict == "unusual"
        assert not (output.result.expected_range[0] <= output.result.actual <= output.result.expected_range[1])
