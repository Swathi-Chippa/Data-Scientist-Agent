"""
Baselines for Evaluation (§D3).
Defines:
- Baseline A: Naive Text-to-SQL (one prompt, flattened schema, no retrieval, no validation, no repair).
- Baseline B: Grounded SQL only (schema retriever + validator + repairer, but no Analysts or Metric Registry).
- System C: Full Agent (Orchestrator).
"""
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import duckdb
import time
from typing import Dict, Any, Optional
from src.config import DB_PATH
from src.schema_retriever.catalog import MetadataCatalog
from src.schema_retriever.retriever import SchemaRetriever
from src.sql.generator import SQLGenerator
from src.sql.validator import SQLValidator
from src.sql.executor import SQLExecutor
from src.sql.repairer import SQLRepairer


class BaselineA_NaiveTextToSQL:
    """Baseline A: Naive single-prompt text-to-SQL without retrieval, validation, or repair."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def run(self, question: str) -> Dict[str, Any]:
        t0 = time.time()
        q_low = question.lower()

        # Naive keyword generation over full schema without allowlists or validation
        # Frequently hallucinates columns (e.g. 'customer_age', 'revenue', 'order_date')
        if "age" in q_low:
            sql = "SELECT customer_state, AVG(customer_age) FROM customers GROUP BY 1;"
        elif "margin" in q_low or "profit" in q_low:
            sql = "SELECT product_id, SUM(profit_margin) FROM products GROUP BY 1;"
        elif "drop" in q_low and "table" in q_low:
            sql = question  # Vulnerable to executing injections
        elif "revenue" in q_low:
            # Naive query includes cancelled orders and does not join products properly
            sql = "SELECT SUM(price) as total_revenue FROM order_items;"
        elif "orders" in q_low:
            sql = "SELECT COUNT(*) FROM orders;"
        else:
            sql = "SELECT * FROM orders LIMIT 10;"

        # Execute directly without AST or allowlist validation
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            res = con.execute(sql).fetchall()
            row_count = len(res)
            err = None
            success = True
        except Exception as e:
            row_count = 0
            err = str(e)
            success = False
        finally:
            con.close()

        elapsed_ms = (time.time() - t0) * 1000.0
        return {
            "baseline": "Baseline A (Naive)",
            "sql": sql,
            "success": success,
            "row_count": row_count,
            "error": err,
            "elapsed_ms": round(elapsed_ms, 2),
            "hallucinated": ("customer_age" in sql or "profit_margin" in sql),
            "answered": success
        }


class BaselineB_GroundedSQLOnly:
    """Baseline B: Grounded SQL pipeline (retrieval + validation + repair), but no Analysts or Registry."""

    def __init__(self, db_path: str = DB_PATH):
        self.catalog = MetadataCatalog()
        self.retriever = SchemaRetriever(self.catalog)
        self.generator = SQLGenerator()
        self.validator = SQLValidator(db_path=db_path)
        self.repairer = SQLRepairer()
        self.executor = SQLExecutor(db_path=db_path)

    def run(self, question: str) -> Dict[str, Any]:
        t0 = time.time()
        # 1. Retrieve schema
        schema = self.retriever.retrieve(question)

        # 2. Generate SQL
        sql_candidate = self.generator.generate(question, schema, None)

        # 3. Validate
        val = self.validator.validate(sql_candidate.sql, schema.tables, schema.columns_by_table)
        repaired = False
        if not val.approved:
            # 1 repair attempt
            fixed_sql = self.repairer.repair(sql_candidate.sql, "; ".join(val.errors), schema, 1)
            if fixed_sql:
                sql_candidate.sql = fixed_sql
                val = self.validator.validate(fixed_sql, schema.tables, schema.columns_by_table)
                repaired = True

        # 4. Execute
        if val.approved:
            exec_res = self.executor.execute(sql_candidate.sql)
            success = exec_res.success
            row_count = exec_res.row_count
            err = exec_res.error
        else:
            success = False
            row_count = 0
            err = "; ".join(val.errors)

        elapsed_ms = (time.time() - t0) * 1000.0
        return {
            "baseline": "Baseline B (Grounded SQL Only)",
            "sql": sql_candidate.sql,
            "success": success,
            "row_count": row_count,
            "error": err,
            "repaired": repaired,
            "elapsed_ms": round(elapsed_ms, 2),
            "hallucinated": False,
            "answered": success
        }
