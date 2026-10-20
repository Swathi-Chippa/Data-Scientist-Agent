"""
Metadata Catalog & Column Profiler (§B7, §C6).
Profiles tables, column types, distinct values, null rates, and trust features.
Prefers canonical maintained tables over raw/staged copies.
"""
import duckdb
from typing import Dict, List, Any, Optional
from src.config import DB_PATH


class ColumnProfile:
    def __init__(self, name: str, data_type: str, null_rate: float, distinct_count: int, sample_values: List[Any], warning: Optional[str] = None):
        self.name = name
        self.data_type = data_type
        self.null_rate = null_rate
        self.distinct_count = distinct_count
        self.sample_values = sample_values
        self.warning = warning

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "null_rate": round(self.null_rate, 4),
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values[:5],
            "warning": self.warning
        }


class TableMetadata:
    def __init__(self, name: str, row_count: int, is_canonical: bool, trust_score: float, description: str):
        self.name = name
        self.row_count = row_count
        self.is_canonical = is_canonical
        self.trust_score = trust_score
        self.description = description
        self.columns: Dict[str, ColumnProfile] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "is_canonical": self.is_canonical,
            "trust_score": self.trust_score,
            "description": self.description,
            "columns": {k: v.to_dict() for k, v in self.columns.items()}
        }


class MetadataCatalog:
    """Manages table catalog, profiles, and trust scores."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.tables: Dict[str, TableMetadata] = {}
        self._build_catalog()

    def _build_catalog(self):
        """Builds profile for canonical e-commerce tables."""
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            # Canonical table descriptions and trust metadata
            table_defs = {
                "orders": ("Primary orders table containing purchase milestones, statuses, and delivery dates.", True, 1.0),
                "order_items": ("Line item level details with prices, freight values, seller, and product IDs.", True, 1.0),
                "customers": ("Customer master table with unique customer UUIDs, cities, and states.", True, 1.0),
                "products": ("Product catalog with categories, dimensions, and photo counts.", True, 1.0),
                "sellers": ("Seller directory with seller city, state, and zip code prefix.", True, 1.0),
                "order_payments": ("Payment records including payment method, installments, and values.", True, 1.0),
                "order_reviews": ("Customer reviews with ratings (1-5) and survey timestamps.", True, 1.0),
                "category_translation": ("Translation map from Portuguese category names to English.", True, 0.95),
                "geolocation": ("Geographic coordinates and zip code mappings across Brazil.", True, 0.9),
                # Staged duplicates have low trust score (§C2)
                "olist_orders_dataset": ("Raw staging copy of orders table.", False, 0.4),
                "olist_order_items_dataset": ("Raw staging copy of order items table.", False, 0.4),
                "olist_customers_dataset": ("Raw staging copy of customers table.", False, 0.4),
                "olist_products_dataset": ("Raw staging copy of products table.", False, 0.4)
            }

            for tbl, (desc, is_canon, trust) in table_defs.items():
                try:
                    cnt_res = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()
                    row_cnt = cnt_res[0] if cnt_res else 0
                except Exception:
                    continue

                t_meta = TableMetadata(tbl, row_cnt, is_canon, trust, desc)

                # Profile columns
                col_info = con.execute(f"PRAGMA table_info({tbl})").fetchall()
                for c in col_info:
                    c_name = c[1]
                    c_type = c[2]

                    # Basic sample and stats
                    warning = None
                    null_rate = 0.0
                    distinct_cnt = 0
                    samples = []

                    try:
                        stats = con.execute(f"""
                            SELECT 
                                count(CASE WHEN {c_name} IS NULL THEN 1 END) * 1.0 / count(*),
                                count(DISTINCT {c_name})
                            FROM {tbl}
                        """).fetchone()
                        null_rate = stats[0] if stats and stats[0] is not None else 0.0
                        distinct_cnt = stats[1] if stats and stats[1] is not None else 0

                        # Check for high null warnings (§B7)
                        if null_rate > 0.3:
                            warning = f"High null rate: {round(null_rate * 100, 1)}% of rows are NULL"

                        sample_rows = con.execute(f"""
                            SELECT DISTINCT {c_name} FROM {tbl} 
                            WHERE {c_name} IS NOT NULL 
                            LIMIT 3
                        """).fetchall()
                        samples = [str(r[0]) for r in sample_rows]
                    except Exception:
                        pass

                    profile = ColumnProfile(c_name, c_type, null_rate, distinct_cnt, samples, warning)
                    t_meta.columns[c_name] = profile

                self.tables[tbl] = t_meta

        finally:
            con.close()

    def get_canonical_tables(self) -> List[str]:
        """Returns list of canonical tables with highest trust."""
        return [name for name, t in self.tables.items() if t.is_canonical]

    def get_column_allowlist(self, tables: List[str]) -> Dict[str, List[str]]:
        """Returns map of allowed column names for selected tables."""
        res = {}
        for tbl in tables:
            if tbl in self.tables:
                res[tbl] = list(self.tables[tbl].columns.keys())
        return res
