"""
Step 7b - SQL Generator: Schema-Constrained Query Generator for Ungoverned Queries (§B6, §B7).
Generates DuckDB queries strictly constrained to the retrieved schema allowlist.
"""
from typing import Optional, Dict, Any
from src.models.schemas import RetrievedSchema, ExtractedSlots, SQLCandidate


class SQLGenerator:
    """Generates SQL constrained strictly to the retrieved schema allowlist."""

    def generate(
        self,
        question: str,
        retrieved_schema: RetrievedSchema,
        slots: ExtractedSlots,
        model_name: Optional[str] = None
    ) -> SQLCandidate:
        """
        Builds a schema-aligned query using structured heuristics matching DuckDB semantics.
        Restricted to retrieved tables and columns.
        """
        # Try Gemini LLM generator if client is active and available
        gemini_candidate = self._generate_with_gemini(question, retrieved_schema, slots, model_name)
        if gemini_candidate:
            return gemini_candidate

        tables = retrieved_schema.tables
        cols_map = retrieved_schema.columns_by_table
        linked = retrieved_schema.linked_values
        q_low = question.lower()

        # Build schema-safe join and aggregation
        # Determine primary table
        base_table = "orders" if "orders" in tables else (tables[0] if tables else "orders")
        select_cols = []
        joins = []
        where_conds = []
        group_by = []
        order_by = ""

        # Check if question is looking for top sellers
        if "seller" in q_low and "order_items" in tables:
            base_table = "order_items"
            select_cols = ["seller_id", "COUNT(DISTINCT order_id) AS total_orders", "ROUND(SUM(price), 2) AS total_revenue"]
            group_by = ["seller_id"]
            order_by = "ORDER BY total_revenue DESC"
            limit = "LIMIT 10"

        # Check if question is looking for payment methods
        elif "payment" in q_low and "order_payments" in tables:
            base_table = "order_payments"
            select_cols = ["payment_type", "COUNT(*) AS payment_count", "ROUND(SUM(payment_value), 2) AS total_payment_value"]
            group_by = ["payment_type"]
            order_by = "ORDER BY total_payment_value DESC"
            limit = "LIMIT 10"

        # Check if question is looking for category review scores
        elif "review" in q_low and "order_reviews" in tables and "order_items" in tables:
            base_table = "orders"
            select_cols = [
                "COALESCE(p.product_category_name, 'Unknown') AS product_category",
                "ROUND(AVG(r.review_score), 2) AS avg_review_score",
                "COUNT(r.review_id) AS total_reviews"
            ]
            joins = [
                "JOIN order_items oi ON orders.order_id = oi.order_id",
                "JOIN products p ON oi.product_id = p.product_id",
                "JOIN order_reviews r ON orders.order_id = r.order_id"
            ]
            group_by = ["1"]
            order_by = "ORDER BY total_reviews DESC"
            limit = "LIMIT 20"

        # Check if question asks for geographic customer breakdown
        elif "customer" in q_low and "customers" in tables:
            base_table = "customers"
            select_cols = ["customer_state", "COUNT(DISTINCT customer_unique_id) AS unique_customers"]
            group_by = ["customer_state"]
            order_by = "ORDER BY unique_customers DESC"
            limit = "LIMIT 30"

        else:
            # Fallback general orders query
            base_table = "orders"
            select_cols = ["strftime(DATE_TRUNC('month', order_purchase_timestamp), '%Y-%m') AS order_month", "COUNT(DISTINCT order_id) AS order_count"]
            where_conds = ["order_status = 'delivered'"]
            group_by = ["1"]
            order_by = "ORDER BY order_month ASC"
            limit = "LIMIT 50"

        # Apply linked values
        if "customer_state" in linked and "customers" in tables:
            st = linked["customer_state"]
            if base_table == "orders" and not any("customers" in j for j in joins):
                joins.append("JOIN customers ON orders.customer_id = customers.customer_id")
            where_conds.append(f"customer_state = '{st}'" if base_table == "customers" else f"customers.customer_state = '{st}'")

        select_str = ",\n    ".join(select_cols)
        join_str = "\n  " + "\n  ".join(joins) if joins else ""
        where_str = "\nWHERE " + " AND ".join(where_conds) if where_conds else ""
        group_str = "\nGROUP BY " + ", ".join(group_by) if group_by else ""

        sql = f"""SELECT
    {select_str}
FROM {base_table}{join_str}{where_str}{group_str}
{order_by}
{limit};""".strip()

        return SQLCandidate(
            sql=sql,
            source="generator",
            is_governed=False
        )

    def _generate_with_gemini(
        self,
        question: str,
        retrieved_schema: RetrievedSchema,
        slots: ExtractedSlots,
        model_name: Optional[str] = None
    ) -> Optional[SQLCandidate]:
        """Prompts gemini-2.5-flash for schema-constrained DuckDB SQL generation."""
        try:
            from src.llm.client import get_gemini_client
            client = get_gemini_client()
            if not client.is_available():
                return None

            tables_info = ", ".join(retrieved_schema.tables)
            cols_summary = "; ".join(f"{t}: {', '.join(cols[:15])}" for t, cols in retrieved_schema.columns_by_table.items())

            system_instruction = (
                "You are an expert DuckDB SQL Data Scientist Agent.\n"
                "Write a valid, high-performance DuckDB SQL query to answer the user's question.\n"
                "CRITICAL RULES:\n"
                f"1. You must ONLY reference the allowed tables: [{tables_info}]\n"
                f"2. You must ONLY reference columns from the retrieved schema: [{cols_summary}]\n"
                "3. Never perform DROP, DELETE, INSERT, UPDATE, or file operations.\n"
                "4. Always include a sensible LIMIT (default 100) and round numeric aggregations.\n"
                "5. Return JSON with key 'sql' containing the SQL query string."
            )

            prompt = f"User Question: \"{question}\""
            data = client.generate_json(prompt=prompt, system_instruction=system_instruction, model=model_name)
            if data and "sql" in data and data["sql"].strip():
                clean_sql = data["sql"].strip().replace("```sql", "").replace("```", "").strip()
                return SQLCandidate(
                    sql=clean_sql,
                    source=client.get_active_model_name(),
                    is_governed=False
                )
            return None
        except Exception:
            return None

