"""
Step 7a - SQL Compiler: Deterministic Query Builder for Governed Metrics (§B6).
Generates strictly governed DuckDB SQL without language model calls.
Zero hallucination risk, lowest latency and cost.
"""
from typing import Optional, Dict
from src.models.schemas import GovernedMetric, ExtractedSlots, SQLCandidate


class SQLCompiler:
    """Compiles deterministic SQL for governed metrics."""

    def compile(
        self,
        metric: GovernedMetric,
        slots: ExtractedSlots,
        linked_values: Dict[str, str],
        time_grain: Optional[str] = None
    ) -> SQLCandidate:
        """
        Builds executable DuckDB SQL from governed definition, slots, and linked literals.
        """
        select_parts = []
        group_by_parts = []
        where_clauses = list(metric.required_filters)
        joins = list(metric.join_path)
        order_by = ""

        # 1. Handle Dimensions
        dim = slots.dimension
        if dim:
            dim_col = self._map_dimension_column(dim)
            select_parts.append(f"{dim_col} AS dimension_value")
            group_by_parts.append("1")

        # 2. Handle Temporal Grain (Time series)
        grain = time_grain or slots.time_window
        if grain in ["week", "weekly"]:
            date_expr = f"strftime(DATE_TRUNC('week', {metric.date_column}), '%Y-%m-%d')"
            select_parts.append(f"{date_expr} AS time_period")
            group_by_parts.append(f"{len(select_parts)}")
            order_by = "ORDER BY time_period ASC"
        elif grain in ["month", "monthly", "last_year", "2018", "2017"]:
            date_expr = f"strftime(DATE_TRUNC('month', {metric.date_column}), '%Y-%m')"
            select_parts.append(f"{date_expr} AS time_period")
            group_by_parts.append(f"{len(select_parts)}")
            order_by = "ORDER BY time_period ASC"

        # 3. Handle Measure Formula
        select_parts.append(f"{metric.formula} AS metric_value")

        # 4. Handle Filters from Linked Values & Slots
        if slots.region_or_filter or "customer_state" in linked_values:
            st = slots.region_or_filter or linked_values["customer_state"]
            where_clauses.append(f"c.customer_state = '{st}'")
            # Ensure customers table is joined
            if not any("customers" in j for j in joins):
                joins.append("LEFT JOIN customers c ON o.customer_id = c.customer_id")

        if "product_category_name" in linked_values:
            cat = linked_values["product_category_name"]
            where_clauses.append(f"p.product_category_name = '{cat}'")
            if not any("products" in j for j in joins):
                joins.append("LEFT JOIN products p ON oi.product_id = p.product_id")

        if "payment_type" in linked_values:
            pt = linked_values["payment_type"]
            where_clauses.append(f"pay.payment_type = '{pt}'")
            if not any("order_payments" in j for j in joins):
                joins.append("LEFT JOIN order_payments pay ON o.order_id = pay.order_id")

        # Year/Quarter filter if specified
        import re
        if slots.time_window and re.match(r'^\d{4}$', slots.time_window):
            where_clauses.append(f"EXTRACT(YEAR FROM {metric.date_column}) = {slots.time_window}")
        elif slots.time_window and re.match(r'^\d{4}-q[1-4]$', slots.time_window.lower()):
            m = re.match(r'^(\d{4})-q([1-4])$', slots.time_window.lower())
            if m:
                year = m.group(1)
                quarter = m.group(2)
                where_clauses.append(f"EXTRACT(YEAR FROM {metric.date_column}) = {year} AND EXTRACT(QUARTER FROM {metric.date_column}) = {quarter}")

        # Construct final SQL
        select_clause = ",\n    ".join(select_parts)
        join_clause = "\n".join(f"  {j}" for j in joins)
        where_clause = f"\nWHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        group_clause = f"\nGROUP BY {', '.join(group_by_parts)}" if group_by_parts else ""
        if not order_by:
            order_by = "ORDER BY metric_value DESC"

        limit_clause = "LIMIT 100"

        sql = f"""SELECT
    {select_clause}
FROM {metric.base_table}
{join_clause}{where_clause}{group_clause}
{order_by}
{limit_clause};""".strip()

        return SQLCandidate(
            sql=sql,
            source="compiler",
            is_governed=True,
            metric_name=metric.name
        )

    def _map_dimension_column(self, dim: str) -> str:
        d_lower = dim.lower()
        if "category" in d_lower:
            return "COALESCE(p.product_category_name, 'Unknown')"
        elif "state" in d_lower or "region" in d_lower:
            return "c.customer_state"
        elif "city" in d_lower:
            return "c.customer_city"
        elif "payment" in d_lower:
            return "pay.payment_type"
        elif "status" in d_lower:
            return "o.order_status"
        elif "seller" in d_lower:
            return "s.seller_state"
        return "c.customer_state"
