"""TEMPORARY Olist fetchers, to be replaced by BE-1 table supply.

This is the only temporary warehouse boundary. Values are always bound with
DuckDB parameters; caller text is never interpolated into SQL.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

import duckdb
import pandas as pd

from src.config import DB_PATH

_GRAIN_SQL = {
    "day": "strftime(DATE_TRUNC('day', o.order_purchase_timestamp), '%Y-%m-%d')",
    "week": "strftime(DATE_TRUNC('week', o.order_purchase_timestamp), '%Y-%m-%d')",
    "month": "strftime(DATE_TRUNC('month', o.order_purchase_timestamp), '%Y-%m-%d')",
    "quarter": "strftime(DATE_TRUNC('quarter', o.order_purchase_timestamp), '%Y-%m-%d')",
    "year": "strftime(DATE_TRUNC('year', o.order_purchase_timestamp), '%Y-%m-%d')",
}
_GRAIN_PERIOD_SQL = {
    "day": "DATE_TRUNC('day', o.order_purchase_timestamp)",
    "week": "DATE_TRUNC('week', o.order_purchase_timestamp)",
    "month": "DATE_TRUNC('month', o.order_purchase_timestamp)",
    "quarter": "DATE_TRUNC('quarter', o.order_purchase_timestamp)",
    "year": "DATE_TRUNC('year', o.order_purchase_timestamp)",
}
_ALLOWED_GRAINS = frozenset(_GRAIN_SQL)


class UnknownUnitError(ValueError):
    """Raised when a requested unit is not present in the database allowlist."""


def _grain_sql(grain: str, *, period: bool = False) -> str:
    if grain not in _ALLOWED_GRAINS:
        raise ValueError(f"grain must be one of {sorted(_ALLOWED_GRAINS)}")
    return (_GRAIN_PERIOD_SQL if period else _GRAIN_SQL)[grain]


def validate_grain(grain: str) -> None:
    """Validate a caller-provided grain without exposing SQL fragments."""
    _grain_sql(grain)


def _connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def _allowlisted_units(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {str(row[0]) for row in con.execute(
        "SELECT DISTINCT customer_state FROM customers WHERE customer_state IS NOT NULL ORDER BY customer_state"
    ).fetchall()}


def _validated_units(con: duckdb.DuckDBPyConnection, units: str | Iterable[str] | None) -> list[str] | None:
    if units is None:
        return None
    requested = [units] if isinstance(units, str) else list(units)
    if not requested:
        raise UnknownUnitError("no units requested")
    if len(requested) > 50:
        raise UnknownUnitError("at most 50 units may be requested")
    if any(not isinstance(unit, str) for unit in requested):
        raise UnknownUnitError("units must be strings")
    allowed = _allowlisted_units(con)
    invalid = [unit for unit in requested if unit not in allowed]
    if invalid:
        raise UnknownUnitError(f"Unknown customer_state value(s): {invalid}")
    return requested


def _where_window(start: str | date | datetime | None, end: str | date | datetime | None) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if start is not None:
        clauses.append("o.order_purchase_timestamp >= ?")
        params.append(start)
    if end is not None:
        clauses.append("o.order_purchase_timestamp < ?")
        params.append(end)
    return clauses, params


def _metadata(frame: pd.DataFrame, *, date_column: str, period_column: str = "period", grain: str = "week",
              period_start: str | date | datetime | None = None,
              period_end: str | date | datetime | None = None) -> dict[str, Any]:
    empty = {
        "data_range": {"min_date": None, "max_date": None, "last_loaded_timestamp": None},
        "partial_periods": {"first": False, "last": False, "first_period": None, "last_period": None,
                            "days_covered_first": 0, "days_covered_last": 0},
    }
    if frame.empty or date_column not in frame:
        return empty
    dates = pd.to_datetime(frame[date_column], errors="coerce").dropna()
    if dates.empty:
        return empty
    first = pd.to_datetime(frame.get("min_event_timestamp", frame[date_column]), errors="coerce").dropna().min()
    last = dates.max()
    periods = frame[period_column].dropna() if period_column in frame else pd.Series(dtype=object)
    first_period = str(periods.iloc[0]) if not periods.empty else None
    last_period = str(periods.iloc[-1]) if not periods.empty else None
    # pandas 3.0 still requires the Period aliases M/Q/Y (not ME/QE/YE).
    period_freq = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q", "year": "Y"}[grain]
    first_start = pd.Timestamp(first_period).to_period(period_freq).start_time if first_period else first.to_period(period_freq).start_time
    last_start = pd.Timestamp(last_period).to_period(period_freq).start_time if last_period else last.to_period(period_freq).start_time
    last_end = last_start.to_period(period_freq).end_time
    # With no explicit bound, observed min/max dates define the effective window.
    window_start = pd.Timestamp(period_start) if period_start is not None else first
    window_end = pd.Timestamp(period_end) if period_end is not None else last + pd.Timedelta(days=1)
    first_lo = max(first.normalize(), window_start.normalize())
    first_hi = min(first_start.to_period(period_freq).end_time.normalize(), window_end.normalize() - pd.Timedelta(days=1))
    last_lo = max(last_start.normalize(), window_start.normalize())
    last_hi = min(last.normalize(), window_end.normalize() - pd.Timedelta(days=1))
    first_days = max(0, int((first_hi - first_lo).days + 1))
    last_days = max(0, int((last_hi - last_lo).days + 1))
    first_full_days = int((first_start.to_period(period_freq).end_time.normalize() - first_start.normalize()).days + 1)
    last_full_days = int((last_end.normalize() - last_start.normalize()).days + 1)
    return {
        "data_range": {"min_date": first.date().isoformat(), "max_date": last.date().isoformat(),
                       "last_loaded_timestamp": last.isoformat()},
        "partial_periods": {"first": first_days < first_full_days, "last": last_days < last_full_days,
                            "first_period": first_period, "last_period": last_period,
                            "days_covered_first": first_days, "days_covered_last": last_days},
    }


def _run(sql: str, params: list[Any], *, date_column: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    con = _connection()
    try:
        frame = con.execute(sql, params).df()
    finally:
        con.close()
    return frame, _metadata(frame, date_column=date_column)


def fetch_weekly_orders(units: str | Iterable[str] | None = None, period_start: str | date | datetime | None = None,
                        period_end: str | date | datetime | None = None, grain: str = "week") -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch the ``series`` contract for a half-open time window."""
    period_expr = _grain_sql(grain)
    con = _connection()
    try:
        selected = _validated_units(con, units)
        clauses, params = _where_window(period_start, period_end)
        clauses.insert(0, "o.order_status = ?")
        params.insert(0, "delivered")
        if selected is not None:
            clauses.append("c.customer_state IN (" + ",".join("?" for _ in selected) + ")")
            params.extend(selected)
        sql = (f"SELECT {period_expr} AS period, COUNT(DISTINCT o.order_id) AS value, c.customer_state AS unit, "
               "MIN(o.order_purchase_timestamp) AS min_event_timestamp, MAX(o.order_purchase_timestamp) AS event_timestamp "
               "FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE " + " AND ".join(clauses) +
               " GROUP BY 1, 3 ORDER BY 1, 3")
        frame = con.execute(sql, params).df()
    finally:
        con.close()
    frame = frame[["period", "value", "unit", "event_timestamp", "min_event_timestamp"]].copy()
    frame["period"] = frame["period"].astype(object)
    return frame, _metadata(frame, date_column="event_timestamp", grain=grain, period_start=period_start, period_end=period_end)


def fetch_order_lines(period_start: str | date | datetime | None = None, period_end: str | date | datetime | None = None,
                      units: str | Iterable[str] | None = None, grain: str = "month") -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch the ``contrib`` contract for a half-open time window."""
    period_expr = _grain_sql(grain, period=True)
    con = _connection()
    try:
        selected = _validated_units(con, units)
        clauses, params = _where_window(period_start, period_end)
        clauses.insert(0, "o.order_status = ?")
        params.insert(0, "delivered")
        if selected is not None:
            clauses.append("c.customer_state IN (" + ",".join("?" for _ in selected) + ")")
            params.extend(selected)
        sql = (f"SELECT {period_expr} AS period, c.customer_state AS unit, COALESCE(p.product_category_name, 'other') AS dimension, "
               "SUM(oi.price) AS value, COUNT(DISTINCT o.order_id) AS volume, AVG(oi.price) AS price, "
               "MIN(o.order_purchase_timestamp) AS min_event_timestamp, MAX(o.order_purchase_timestamp) AS event_timestamp "
               "FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN order_items oi ON o.order_id = oi.order_id "
               "LEFT JOIN products p ON oi.product_id = p.product_id WHERE " + " AND ".join(clauses) +
               " GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
        frame = con.execute(sql, params).df()
    finally:
        con.close()
    return frame[["period", "unit", "dimension", "value", "volume", "price", "event_timestamp", "min_event_timestamp"]], _metadata(frame, date_column="event_timestamp", grain=grain, period_start=period_start, period_end=period_end)


def fetch_indicators(period_start: str | date | datetime | None = None, period_end: str | date | datetime | None = None,
                     units: str | Iterable[str] | None = None, grain: str = "month") -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch the ``indicators`` contract for a half-open time window."""
    period_expr = _grain_sql(grain, period=True)
    con = _connection()
    try:
        selected = _validated_units(con, units)
        filters, base_params = _where_window(period_start, period_end)
        filters.insert(0, "o.order_status = ?")
        base_params.insert(0, "delivered")
        if selected is not None:
            filters.append("c.customer_state IN (" + ",".join("?" for _ in selected) + ")")
            base_params.extend(selected)
        where = " AND ".join(filters)
        sql = (f"SELECT {period_expr} AS period, c.customer_state AS dimension, 'delivery_days' AS name, AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp))/86400.0) AS value, MAX(o.order_purchase_timestamp) AS event_timestamp FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN order_items oi ON o.order_id = oi.order_id LEFT JOIN order_reviews r ON o.order_id = r.order_id WHERE {where} GROUP BY 1, 2 "
               f"UNION ALL SELECT {period_expr}, c.customer_state, 'csat', AVG(r.review_score), MAX(o.order_purchase_timestamp) FROM orders o JOIN customers c ON o.customer_id = c.customer_id LEFT JOIN order_reviews r ON o.order_id = r.order_id WHERE {where} GROUP BY 1, 2 "
               f"UNION ALL SELECT {period_expr}, c.customer_state, 'freight_ratio', SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0), MAX(o.order_purchase_timestamp) FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE {where} GROUP BY 1, 2 ORDER BY 1, 2, 3")
        frame = con.execute(sql, base_params * 3).df()
    finally:
        con.close()
    return frame[["period", "dimension", "name", "value", "event_timestamp"]], _metadata(frame, date_column="event_timestamp", grain=grain, period_start=period_start, period_end=period_end)


def fetch_customer_orders(period_start: str | date | datetime | None = None, period_end: str | date | datetime | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch the temporary ``orders``/``customers`` contract for a half-open window."""
    clauses, params = _where_window(period_start, period_end)
    clauses.insert(0, "o.order_status = ?")
    params.insert(0, "delivered")
    sql = ("SELECT o.order_id, o.customer_id, c.customer_unique_id, c.customer_state, o.order_purchase_timestamp, o.order_status, o.order_delivered_customer_date, COALESCE(SUM(oi.price), 0) AS order_value "
           "FROM orders o JOIN customers c ON o.customer_id = c.customer_id LEFT JOIN order_items oi ON o.order_id = oi.order_id WHERE " + " AND ".join(clauses) +
           " GROUP BY o.order_id, o.customer_id, c.customer_unique_id, c.customer_state, o.order_purchase_timestamp, o.order_status, o.order_delivered_customer_date ORDER BY o.order_purchase_timestamp, o.order_id")
    return _run(sql, params, date_column="order_purchase_timestamp")


def fetch_risk_features(cutoff_date: str | date | datetime, outcome_end_date: str | date | datetime) -> tuple[pd.DataFrame, dict[str, Any]]:
    """TEMPORARY exact v1 risk feature fetch; replaced by BE-1 risk tables."""
    sql = """
        WITH pre_cutoff_customers AS (
            SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS freq,
                   ROUND(SUM(oi.price), 2) AS monetary,
                   ROUND(MIN(date_diff('day', o.order_purchase_timestamp, CAST(? AS TIMESTAMP))), 1) AS recency_days,
                   ROUND(AVG(date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 1) AS avg_delivery_days,
                   ROUND(AVG(r.review_score), 2) AS avg_review_score, MAX(c.customer_state) AS state
            FROM customers c JOIN orders o ON c.customer_id = o.customer_id
            JOIN order_items oi ON o.order_id = oi.order_id LEFT JOIN order_reviews r ON o.order_id = r.order_id
            WHERE o.order_status = ? AND o.order_purchase_timestamp < CAST(? AS TIMESTAMP) GROUP BY 1
        ), post_cutoff_activity AS (
            SELECT DISTINCT c.customer_unique_id FROM customers c JOIN orders o ON c.customer_id = o.customer_id
            WHERE o.order_status = ? AND o.order_purchase_timestamp >= CAST(? AS TIMESTAMP) AND o.order_purchase_timestamp < CAST(? AS TIMESTAMP)
        )
        SELECT p.customer_unique_id, p.freq, p.monetary, p.recency_days,
               COALESCE(p.avg_delivery_days, 12.0) AS delivery_days,
               COALESCE(p.avg_review_score, 4.0) AS review_score, p.state,
               CASE WHEN act.customer_unique_id IS NULL THEN 1 ELSE 0 END AS churn_label
        FROM pre_cutoff_customers p LEFT JOIN post_cutoff_activity act ON p.customer_unique_id = act.customer_unique_id
        -- Stable tie-breaker for the legacy 8,000-row boundary. The v1 query
        -- omitted this key and DuckDB may choose tied rows differently.
        ORDER BY (act.customer_unique_id IS NOT NULL) DESC, p.monetary DESC, p.customer_unique_id LIMIT 8000
    """
    stats_sql = """
        SELECT COUNT(DISTINCT customer_unique_id), COUNT(DISTINCT CASE WHEN order_count = 1 THEN customer_unique_id END)
        FROM (SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_count FROM customers c
              JOIN orders o ON c.customer_id = o.customer_id WHERE o.order_status = ? GROUP BY 1)
    """
    con = _connection()
    try:
        params = [cutoff_date, "delivered", cutoff_date, "delivered", cutoff_date, outcome_end_date]
        frame = con.execute(sql, params).df()
        total, one_time = con.execute(stats_sql, ["delivered"]).fetchone()
    finally:
        con.close()
    metadata = _metadata(pd.DataFrame({"event_timestamp": [pd.Timestamp(cutoff_date)]}), date_column="event_timestamp",
                         period_start=cutoff_date, period_end=outcome_end_date)
    metadata["buyer_stats"] = (total, one_time)
    return frame, metadata


def fetch_service_events(period_start: str | date | datetime | None = None, period_end: str | date | datetime | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch the temporary ``service`` contract for a half-open window."""
    clauses, params = _where_window(period_start, period_end)
    clauses.insert(0, "o.order_status = ?")
    params.insert(0, "delivered")
    sql = ("SELECT o.order_id, c.customer_state AS unit, o.order_purchase_timestamp AS event_timestamp, o.order_delivered_customer_date, EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp))/86400.0 AS delivery_days, r.review_score, oi.freight_value, oi.price "
           "FROM orders o JOIN customers c ON o.customer_id = c.customer_id LEFT JOIN order_reviews r ON o.order_id = r.order_id JOIN order_items oi ON o.order_id = oi.order_id WHERE " + " AND ".join(clauses) + " ORDER BY o.order_purchase_timestamp, o.order_id")
    return _run(sql, params, date_column="event_timestamp")
