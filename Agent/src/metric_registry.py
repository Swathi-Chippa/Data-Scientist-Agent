"""
Metric Registry: Central store of governed metrics (§B6).
Defines formulas, required filters, grains, date columns, allowed dimensions,
join paths, caveats, and reconciliation queries.

Loads declaratively from semantic_layer/metrics.yaml with fallback defaults.
"""
from pathlib import Path
from typing import Dict, Optional, List
import yaml
from src.models.schemas import GovernedMetric

SEMANTIC_LAYER_DIR = Path(__file__).resolve().parent.parent / "semantic_layer"
METRICS_YAML_PATH = SEMANTIC_LAYER_DIR / "metrics.yaml"


def load_metric_registry() -> Dict[str, GovernedMetric]:
    """Loads governed metrics from semantic_layer/metrics.yaml or fallback definitions."""
    registry = {}

    if METRICS_YAML_PATH.exists():
        try:
            with open(METRICS_YAML_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "metrics" in data:
                    for m in data["metrics"]:
                        m_obj = GovernedMetric(
                            name=m["name"],
                            synonyms=m.get("synonyms", []),
                            formula=m["formula"],
                            required_filters=m.get("required_filters", []),
                            time_grain=m.get("time_grain", "month"),
                            date_column=m["date_column"],
                            allowed_dimensions=m.get("allowed_dimensions", []),
                            base_table=m["base_table"],
                            join_path=m.get("join_path", []),
                            caveats=m.get("caveats", []),
                            reconciliation_query=m.get("reconciliation_query", "").strip() or None
                        )
                        registry[m["name"]] = m_obj
            if registry:
                return registry
        except Exception as e:
            print(f"Warning: Failed to load metrics.yaml: {e}. Falling back to default definitions.")

    # Fallback default hardcoded definitions
    return {
        "revenue": GovernedMetric(
            name="revenue",
            synonyms=["sales", "gmv", "spend", "total revenue", "total sales", "turnover"],
            formula="ROUND(SUM(oi.price), 2)",
            required_filters=["o.order_status = 'delivered'"],
            time_grain="month",
            date_column="o.order_purchase_timestamp",
            allowed_dimensions=["customer_state", "product_category_name", "seller_state", "payment_type"],
            base_table="orders o",
            join_path=[
                "JOIN order_items oi ON o.order_id = oi.order_id",
                "LEFT JOIN customers c ON o.customer_id = c.customer_id",
                "LEFT JOIN products p ON oi.product_id = p.product_id"
            ],
            caveats=[
                "Revenue is computed only on delivered orders.",
                "Freight value is excluded from revenue.",
                "Cancelled and unavailable orders are excluded."
            ],
            reconciliation_query=(
                "SELECT ROUND(SUM(oi.price), 2) "
                "FROM orders o "
                "JOIN order_items oi ON o.order_id = oi.order_id "
                "WHERE o.order_status = 'delivered'"
            )
        ),
        "orders": GovernedMetric(
            name="orders",
            synonyms=["order count", "volume", "purchases", "total orders", "order volume"],
            formula="COUNT(DISTINCT o.order_id)",
            required_filters=["o.order_status NOT IN ('canceled', 'unavailable')"],
            time_grain="week",
            date_column="o.order_purchase_timestamp",
            allowed_dimensions=["customer_state", "order_status", "product_category_name"],
            base_table="orders o",
            join_path=[
                "LEFT JOIN customers c ON o.customer_id = c.customer_id"
            ],
            caveats=[
                "Includes delivered, shipped, and processing orders.",
                "Excludes cancelled and unavailable orders."
            ],
            reconciliation_query=(
                "SELECT COUNT(DISTINCT order_id) "
                "FROM orders "
                "WHERE order_status NOT IN ('canceled', 'unavailable')"
            )
        )
    }


METRIC_REGISTRY: Dict[str, GovernedMetric] = load_metric_registry()
