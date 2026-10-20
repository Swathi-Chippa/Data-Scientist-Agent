"""
Synthetic Enterprise Warehouse Generator (§C1, §C2).
Simulates enterprise data warehouse anomalies, distractor tables, legacy naming,
and messy formatting to benchmark Schema Retriever and Validator at scale.
"""
import duckdb
import random
from pathlib import Path
from src.config import DB_PATH


def create_synthetic_enterprise_views(db_path: str = DB_PATH):
    """Creates synthetic enterprise mess (staging tables, distractor tables, legacy naming)."""
    con = duckdb.connect(db_path, read_only=False)
    try:
        # 1. Distractor table (looks like right answer but contains stale test records)
        con.execute("""
            CREATE OR REPLACE VIEW staging_orders_legacy_v1 AS 
            SELECT order_id, customer_id, order_status, order_purchase_timestamp 
            FROM orders 
            WHERE order_status = 'canceled'
        """)

        # 2. Cryptic legacy table
        con.execute("""
            CREATE OR REPLACE VIEW ord_hdr_dim AS 
            SELECT order_id as ord_id_pk, customer_id as c_id_fk, order_status as st_cd 
            FROM orders
        """)

        print("Synthetic enterprise views successfully created in warehouse.")
    finally:
        con.close()


if __name__ == "__main__":
    create_synthetic_enterprise_views()
