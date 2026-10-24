"""P3 legacy-window regression checks."""

import os
from pathlib import Path

import pytest
import pandas as pd

from src.config import DB_PATH
from src.analysts.fetchers_olist import _metadata, fetch_risk_features, fetch_weekly_orders
from src.analysts.anomaly import AnomalyAnalyst
from src.analysts.driver import DriverAnalyst
from src.analysts.risk import RiskAnalyst


def test_legacy_anomaly_series_matches_v1_window():
    if not Path(DB_PATH).exists():
        if os.getenv("ALLOW_NO_DB") == "1":
            pytest.skip("DuckDB file is absent and ALLOW_NO_DB=1")
        pytest.fail(f"DuckDB file is absent: {DB_PATH}")

    frame, metadata = fetch_weekly_orders("SP", "2017-06-01", "2018-08-25", "week")
    assert len(frame) == 65
    assert frame.iloc[0]["period"] == "2017-05-29"
    assert frame.iloc[-1]["period"] == "2018-08-20"
    assert frame.iloc[-1]["value"] == 534
    assert frame["period"].dtype == object
    assert metadata["partial_periods"]["days_covered_first"] == 4
    assert metadata["partial_periods"]["days_covered_last"] == 5


@pytest.mark.parametrize("region", ["XX", "SP'; DROP TABLE orders; --"])
def test_legacy_analysts_fail_closed_for_unknown_units(region):
    for analyst in (AnomalyAnalyst(), DriverAnalyst()):
        result = analyst.run({"region": region})
        assert result.status == "insufficient_evidence"
        assert result.verdict == ""
        assert "not in the warehouse" in result.caveats[0]


def test_risk_features_are_stable_for_fixed_legacy_window():
    # The original v1 ORDER BY had monetary ties at LIMIT 8000 and was
    # non-deterministic under parallel DuckDB execution. Compare stable NEW
    # retrieval aggregates/features rather than unstable OLD model metrics.
    first, _ = fetch_risk_features("2018-03-01", "2018-06-01")
    second, _ = fetch_risk_features("2018-03-01", "2018-06-01")
    first = first.sort_values("customer_unique_id").reset_index(drop=True)
    second = second.sort_values("customer_unique_id").reset_index(drop=True)
    assert len(first) == len(second) == 8000
    assert int(first["churn_label"].sum()) == int(second["churn_label"].sum())
    assert int((first["freq"] == 1).sum()) == int((second["freq"] == 1).sum())
    pd.testing.assert_frame_equal(first, second, check_dtype=False)


@pytest.mark.parametrize("grain", ["decade", "week; DROP TABLE x"])
def test_all_legacy_analysts_fail_closed_for_invalid_grain(grain):
    for analyst in (AnomalyAnalyst(), DriverAnalyst()):
        result = analyst.run({"region": "SP", "time_grain": grain})
        assert result.status == "insufficient_evidence"
        assert "Time grain" in result.caveats[0]
    result = RiskAnalyst().run({"time_grain": grain})
    assert result.status == "insufficient_evidence"
    assert "Time grain" in result.caveats[0]


@pytest.mark.parametrize("grain", ["quarter", "year"])
def test_supported_extended_grains_do_not_raise(grain):
    for analyst in (AnomalyAnalyst(), DriverAnalyst()):
        assert analyst.run({"region": "SP", "time_grain": grain}).status in {"success", "insufficient_evidence"}
    assert RiskAnalyst().run({"time_grain": grain}).status == "success"


def test_full_week_window_not_partial_for_afternoon_first_order():
    frame = pd.DataFrame({
        "period": ["2024-01-01"],
        "event_timestamp": [pd.Timestamp("2024-01-01 14:30")],
        "min_event_timestamp": [pd.Timestamp("2024-01-01 14:30")],
    })
    metadata = _metadata(frame, date_column="event_timestamp", grain="week", period_start="2024-01-01", period_end="2024-01-08")
    assert metadata["partial_periods"]["first"] is False
    assert metadata["partial_periods"]["days_covered_first"] == 7
