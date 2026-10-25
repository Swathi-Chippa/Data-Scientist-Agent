import pandas as pd

from src.analysts.core.anomaly import run_anomaly
from src.analysts.core.data_quality import check_data_quality
from src.analysts.core.params import AnomalyParams, DQParams


def test_boundary_completeness_is_named_and_not_severe():
    series = pd.DataFrame({"period": ["2024-01-01", "2024-01-08"], "value": [10, 11]})
    result = check_data_quality(
        series,
        {"partial_periods": {"first_period": "2024-01-01", "days_covered_first": 4}},
        DQParams(grain="week"),
        "2024-01-15T00:00:00Z",
    )
    check = next(item for item in result.checks if item.name == "period_completeness")
    assert check.status == "warn"
    assert "2024-01-01" in check.detail
    assert result.passed


def test_all_units_dropping_is_a_data_issue():
    series = pd.DataFrame(
        {"period": ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"] * 10,
         "unit": [f"U{i}" for i in range(10) for _ in range(4)],
         "value": [100, 100, 100, 10] * 10}
    )
    result = check_data_quality(series, {}, DQParams(grain="week"), "2024-01-29T00:00:00Z")
    check = next(item for item in result.checks if item.name == "all_unit_drop")
    assert check.status == "fail"
    assert not result.passed


def test_definition_drift_only_uses_supplied_history_rates():
    result = check_data_quality(
        pd.DataFrame({"period": ["2024-01-01"], "value": [1]}),
        {"null_rate": 0.2, "history_null_rate": 0.0},
        DQParams(),
        "2024-01-02T00:00:00Z",
    )
    check = next(item for item in result.checks if item.name == "definition_drift")
    assert check.status == "fail"


def test_dq_is_deterministic_for_same_as_of():
    series = pd.DataFrame({"period": ["2024-01-01"], "value": [1]})
    meta = {"data_range": {"last_loaded_timestamp": "2024-01-01T00:00:00Z"}}
    params = DQParams(expected_freshness_hours=24.0)
    first = check_data_quality(series, meta, params, "2024-01-02T00:00:00Z")
    second = check_data_quality(series, meta, params, "2024-01-02T00:00:00Z")
    assert first.model_dump() == second.model_dump()


def test_static_dataset_freshness_is_informational():
    result = check_data_quality(
        pd.DataFrame({"period": ["2024-01-01"], "value": [1]}),
        {"data_range": {"last_loaded_timestamp": "1900-01-01T00:00:00Z"}},
        DQParams(expected_freshness_hours=None),
        "2024-01-02T00:00:00Z",
    )
    freshness = next(item for item in result.checks if item.name == "freshness")
    assert freshness.status == "unknown"
    assert freshness.detail == "no freshness expectation configured (static historical dataset)"
    assert result.passed


def test_static_dataset_can_pass_dq_and_still_report_an_unusual_result():
    periods = pd.date_range("2020-01-06", periods=60, freq="W-MON").strftime("%Y-%m-%d")
    series = pd.DataFrame({"period": periods, "value": [95, 105] * 29 + [95, 130]})
    output = run_anomaly(
        AnomalyParams(test_periods=1, dq=DQParams(expected_freshness_hours=None)),
        {"series": series, "load_meta": {"data_range": {"last_loaded_timestamp": "1900-01-01T00:00:00Z"}}, "as_of": "2020-01-01T00:00:00Z"},
        seed=10,
    )
    assert output.result is not None
    assert output.result.data_quality.passed
    assert output.result.verdict == "unusual"
