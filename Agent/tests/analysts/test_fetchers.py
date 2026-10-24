"""Security and contract smoke tests for the temporary Olist fetchers."""

from pathlib import Path

import pytest

from src.config import DB_PATH
from src.analysts.fetchers_olist import (
    UnknownUnitError,
    fetch_customer_orders,
    fetch_indicators,
    fetch_order_lines,
    fetch_service_events,
    fetch_weekly_orders,
)


pytestmark = pytest.mark.skipif(not Path(DB_PATH).exists(), reason="DuckDB file is absent")


def test_allowlist_rejects_injection_string():
    with pytest.raises(ValueError):
        fetch_weekly_orders("SP'; DROP TABLE orders; --")


def test_injection_value_is_not_embedded_in_fetch_sql(monkeypatch):
    executed: list[str] = []

    class Cursor:
        def fetchall(self):
            return [("SP",)]

    class Connection:
        def execute(self, sql, *args):
            executed.append(sql)
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr("src.analysts.fetchers_olist._connection", lambda: Connection())
    injection = "SP'; DROP TABLE orders; --"
    with pytest.raises(UnknownUnitError):
        fetch_weekly_orders(injection)
    assert all(injection not in sql for sql in executed)


def test_fetchers_return_contract_columns_and_partial_metadata():
    series, series_meta = fetch_weekly_orders("SP")
    assert {"period", "value", "unit"}.issubset(series.columns)
    assert "partial_periods" in series_meta
    assert {"first", "last", "first_period", "last_period"}.issubset(series_meta["partial_periods"])

    lines, _ = fetch_order_lines("2017-01-01", "2018-01-01", "SP")
    assert {"period", "dimension", "value", "volume", "price"}.issubset(lines.columns)

    indicators, _ = fetch_indicators("2017-01-01", "2018-01-01", "SP")
    assert {"period", "dimension", "name", "value"}.issubset(indicators.columns)

    orders, _ = fetch_customer_orders()
    assert {"order_id", "customer_id", "customer_unique_id", "customer_state", "order_purchase_timestamp"}.issubset(orders.columns)

    service, _ = fetch_service_events()
    assert {"order_id", "unit", "event_timestamp", "delivery_days"}.issubset(service.columns)
