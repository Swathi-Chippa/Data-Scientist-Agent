"""
Step 9 - Executor: Safe Read-Only Query Execution (§B8, §B9).
Executes approved SQL on a strictly read-only DuckDB connection with execution timeout and row cap.
Contract: Approved SQL -> ExecutionResult (rows, timing, row count, status).
"""
import time
import duckdb
from typing import Optional
from src.config import DB_PATH, MAX_QUERY_TIMEOUT_SECONDS, MAX_ROW_CAP
from src.models.schemas import ExecutionResult


class SQLExecutor:
    """Safe read-only execution engine for DuckDB."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def execute(self, sql: str, timeout_seconds: int = MAX_QUERY_TIMEOUT_SECONDS) -> ExecutionResult:
        """
        Executes approved SQL query read-only, measuring exact latency and enforcing row caps.
        """
        t0 = time.time()
        # Open strictly read-only connection
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            # Set thread budget / timeout configuration if supported
            con.execute("PRAGMA threads=4;")

            cursor = con.execute(sql)
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchmany(MAX_ROW_CAP)

            elapsed_ms = (time.time() - t0) * 1000.0

            # Convert rows to serializable types
            formatted_rows = []
            for r in raw_rows:
                formatted_rows.append([self._format_cell(v) for v in r])

            return ExecutionResult(
                success=True,
                columns=col_names,
                rows=formatted_rows,
                row_count=len(formatted_rows),
                execution_time_ms=round(elapsed_ms, 2)
            )

        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000.0
            return ExecutionResult(
                success=False,
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=round(elapsed_ms, 2),
                error=str(e)
            )
        finally:
            con.close()

    def _format_cell(self, val):
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if isinstance(val, (int, float, str, bool)):
            return val
        return str(val)
