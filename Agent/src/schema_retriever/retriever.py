"""
Step 6 - Schema Retriever: Hybrid Retrieval, Join Path Resolution, and Column Pruning.
Contract: Question + Governed Definitions -> RetrievedSchema (pruned tables, columns, joins, literals, warnings).
Tuned for high recall, then disciplined pruning (§B7).
"""
from typing import List, Dict, Optional
from src.models.schemas import RetrievedSchema, GovernedMetric
from src.schema_retriever.catalog import MetadataCatalog
from src.schema_retriever.join_graph import JoinGraph
from src.schema_retriever.value_linker import ValueLinker


class SchemaRetriever:
    """Retrieves and prunes schema elements strictly relevant to the question."""

    def __init__(self, catalog: Optional[MetadataCatalog] = None, join_graph: Optional[JoinGraph] = None, min_confidence: float = 0.25):
        self.catalog = catalog or MetadataCatalog()
        self.join_graph = join_graph or JoinGraph()
        self.value_linker = ValueLinker()
        self.min_confidence = min_confidence

    def retrieve(self, question: str, governed_metric: Optional[GovernedMetric] = None) -> RetrievedSchema:
        """
        Retrieves relevant tables, columns, join paths, and linked literals.
        """
        q_low = question.lower()
        candidate_tables = set()

        # Always start with canonical base table
        if governed_metric:
            # Extract base table name from e.g. "orders o" -> "orders"
            base_tbl = governed_metric.base_table.split()[0]
            candidate_tables.add(base_tbl)

            # Add tables referenced in join path
            for jp in governed_metric.join_path:
                for word in jp.split():
                    if word in self.catalog.tables:
                        candidate_tables.add(word)
        else:
            # Heuristic keyword matching for exploratory queries
            if any(k in q_low for k in ["order", "purchase", "delivery", "status"]):
                candidate_tables.add("orders")
            if any(k in q_low for k in ["revenue", "price", "item", "freight", "product"]):
                candidate_tables.add("order_items")
                candidate_tables.add("products")
            if any(k in q_low for k in ["customer", "client", "state", "city", "region"]):
                candidate_tables.add("customers")
            if any(k in q_low for k in ["seller", "merchant"]):
                candidate_tables.add("sellers")
            if any(k in q_low for k in ["payment", "voucher", "credit card", "installments"]):
                candidate_tables.add("order_payments")
            if any(k in q_low for k in ["review", "rating", "comment", "csat"]):
                candidate_tables.add("order_reviews")

        if not candidate_tables:
            candidate_tables = {"orders", "order_items", "customers"}

        # Connect candidate tables via approved join graph
        connected_tables = set(candidate_tables)
        root = "orders" if "orders" in candidate_tables else list(candidate_tables)[0]

        join_edges_info = []
        for tbl in candidate_tables:
            if tbl != root:
                path = self.join_graph.find_join_path(root, tbl)
                if path:
                    for edge in path:
                        connected_tables.add(edge.left_table)
                        connected_tables.add(edge.right_table)
                        join_edges_info.append({
                            "left_table": edge.left_table,
                            "right_table": edge.right_table,
                            "left_key": edge.left_key,
                            "right_key": edge.right_key,
                            "cardinality": edge.cardinality
                        })

        # Prune columns: keep only keys and likely relevant dimensions/metrics
        columns_by_table: Dict[str, List[str]] = {}
        column_warnings: List[str] = []

        for tbl in connected_tables:
            if tbl in self.catalog.tables:
                all_cols = self.catalog.tables[tbl].columns
                selected_cols = []
                for col_name, prof in all_cols.items():
                    # Always keep keys and IDs
                    if col_name.endswith("_id") or "timestamp" in col_name or "date" in col_name or "status" in col_name:
                        selected_cols.append(col_name)
                    # Keep measures
                    elif col_name in ["price", "freight_value", "payment_value", "review_score", "product_category_name"]:
                        selected_cols.append(col_name)
                    # Keep dimensions
                    elif col_name in ["customer_state", "customer_city", "seller_state", "payment_type"]:
                        selected_cols.append(col_name)
                    else:
                        # Only keep if mentioned in query
                        if col_name in q_low:
                            selected_cols.append(col_name)

                    if prof.warning:
                        column_warnings.append(f"{tbl}.{col_name}: {prof.warning}")

                columns_by_table[tbl] = list(set(selected_cols))

        # Value linking
        linked_values, link_conf = self.value_linker.link_values(question)

        return RetrievedSchema(
            tables=list(connected_tables),
            columns_by_table=columns_by_table,
            join_edges=join_edges_info,
            linked_values=linked_values,
            column_warnings=column_warnings,
            retrieval_confidence=link_conf
        )
