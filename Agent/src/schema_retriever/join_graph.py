"""
Join Graph & Path Finder (§B7, §B8).
Maintains verified join edges, cardinalities, and approved shortest-path join resolution.
Detects fan-out join hazards.
"""
import networkx as nx
from typing import List, Dict, Optional, Tuple, Set


class JoinEdge:
    def __init__(self, left_table: str, right_table: str, left_key: str, right_key: str, cardinality: str, approved: bool = True):
        self.left_table = left_table
        self.right_table = right_table
        self.left_key = left_key
        self.right_key = right_key
        self.cardinality = cardinality  # "1:1", "1:N", "N:1", "N:M"
        self.approved = approved

    def to_sql_join(self, left_alias: Optional[str] = None, right_alias: Optional[str] = None) -> str:
        l_name = left_alias or self.left_table
        r_name = right_alias or self.right_table
        return f"JOIN {self.right_table} {r_name} ON {l_name}.{self.left_key} = {r_name}.{self.right_key}"


class JoinGraph:
    """Graph of approved relationships between tables in the warehouse."""

    def __init__(self):
        self.graph = nx.Graph()
        self.edges_by_pair: Dict[Tuple[str, str], JoinEdge] = {}
        self._populate_approved_edges()

    def _populate_approved_edges(self):
        """Populates domain-verified canonical join edges from semantic_layer/joins.yaml or fallback."""
        from pathlib import Path
        import yaml
        yaml_path = Path(__file__).resolve().parent.parent.parent / "semantic_layer" / "joins.yaml"
        approved_edges = []

        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "relationships" in data:
                        for r in data["relationships"]:
                            approved_edges.append(JoinEdge(
                                left_table=r["left_table"],
                                right_table=r["right_table"],
                                left_key=r["left_key"],
                                right_key=r["right_key"],
                                cardinality=r.get("cardinality", "N:1"),
                                approved=r.get("approved", True)
                            ))
            except Exception as e:
                print(f"Warning: Failed to load joins.yaml: {e}")

        if not approved_edges:
            approved_edges = [
                # orders <-> customers (N:1)
                JoinEdge("orders", "customers", "customer_id", "customer_id", "N:1"),
                # orders <-> order_items (1:N)
                JoinEdge("orders", "order_items", "order_id", "order_id", "1:N"),
                # orders <-> order_payments (1:N)
                JoinEdge("orders", "order_payments", "order_id", "order_id", "1:N"),
                # orders <-> order_reviews (1:N)
                JoinEdge("orders", "order_reviews", "order_id", "order_id", "1:N"),
                # order_items <-> products (N:1)
                JoinEdge("order_items", "products", "product_id", "product_id", "N:1"),
                # order_items <-> sellers (N:1)
                JoinEdge("order_items", "sellers", "seller_id", "seller_id", "N:1"),
                # products <-> category_translation (N:1)
                JoinEdge("products", "category_translation", "product_category_name", "product_category_name", "N:1"),
                # customers <-> geolocation (N:N, but prefix lookup)
                JoinEdge("customers", "geolocation", "customer_zip_code_prefix", "geolocation_zip_code_prefix", "N:M")
            ]

        for e in approved_edges:
            self.graph.add_edge(e.left_table, e.right_table, weight=1.0, edge_data=e)
            self.edges_by_pair[(e.left_table, e.right_table)] = e
            # Add reverse edge representation
            rev_card = "N:1" if e.cardinality == "1:N" else ("1:N" if e.cardinality == "N:1" else e.cardinality)
            rev_edge = JoinEdge(e.right_table, e.left_table, e.right_key, e.left_key, rev_card, e.approved)
            self.edges_by_pair[(e.right_table, e.left_table)] = rev_edge

    def is_join_approved(self, table_a: str, table_b: str) -> bool:
        """Verifies if an edge is in the approved join graph."""
        return (table_a, table_b) in self.edges_by_pair and self.edges_by_pair[(table_a, table_b)].approved

    def find_join_path(self, start_table: str, end_table: str) -> Optional[List[JoinEdge]]:
        """Finds shortest join path between two tables using approved edges."""
        if start_table == end_table:
            return []
        try:
            node_path = nx.shortest_path(self.graph, source=start_table, target=end_table, weight="weight")
            edge_path = []
            for i in range(len(node_path) - 1):
                u, v = node_path[i], node_path[i+1]
                edge = self.edges_by_pair.get((u, v))
                if not edge or not edge.approved:
                    return None
                edge_path.append(edge)
            return edge_path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def check_fan_out_risk(self, tables_in_query: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Detects potential Cartesian/fan-out explosion when aggregating over multiple 1:N relations.
        For example: joining orders + order_items + order_payments simultaneously without CTE pre-aggregation.
        """
        tbl_set = set(tables_in_query)
        has_items = "order_items" in tbl_set
        has_payments = "order_payments" in tbl_set
        has_reviews = "order_reviews" in tbl_set

        # If more than one 1:N child table is joined directly to orders
        one_to_many_children = [t for t in [has_items, has_payments, has_reviews] if t]
        if len(one_to_many_children) > 1:
            return True, (
                "Fan-out join risk detected: Direct join across multiple 1:N relations "
                "(e.g., order_items and order_payments). Aggregating over this join will artificially multiply metric values. "
                "Use CTE pre-aggregation or separate queries."
            )

        return False, None
