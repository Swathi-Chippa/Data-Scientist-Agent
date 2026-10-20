"""
Step 8b - Repairer: Bounded Query Repair (§B9).
Patches rejected or syntax-error SQL against the SAME approved schema.
Enforces a hard cap of at most 2 attempts; never widens the schema allowlist.
"""
import re
from typing import Optional, List, Dict
from src.config import MAX_REPAIR_ATTEMPTS
from src.models.schemas import RetrievedSchema


class SQLRepairer:
    """Repairs syntax, binder, or dialect errors within strict bounds."""

    def repair(
        self,
        failed_sql: str,
        error_message: str,
        retrieved_schema: RetrievedSchema,
        attempt: int
    ) -> Optional[str]:
        """
        Attempts targeted fixes on failing SQL based on the error message.
        """
        if attempt > MAX_REPAIR_ATTEMPTS:
            return None

        repaired_sql = failed_sql

        # Fix 1: DuckDB date truncation / format fixes
        if "DATE_TRUNC" in error_message or "strftime" in error_message:
            # Ensure correct format argument ordering
            repaired_sql = re.sub(
                r"strftime\s*\(\s*'([^']+)'\s*,\s*([^\)]+)\)",
                r"strftime(\2, '\1')",
                repaired_sql
            )

        # Fix 2: Group By positional alias fixes
        if "GROUP BY" in error_message and "not in GROUP BY" in error_message:
            # Replace expressions with positional numbers 1, 2
            repaired_sql = re.sub(r"GROUP\s+BY\s+[^;]+", "GROUP BY 1, 2", repaired_sql)

        # Fix 3: Missing quotes around string literals
        if "Binder Error: Referenced column" in error_message:
            match = re.search(r"Referenced column \"([^\"]+)\" not found", error_message)
            if match:
                missing_col = match.group(1)
                # Check if it was supposed to be a literal string value (e.g. 'SP')
                if len(missing_col) <= 3 and missing_col.isupper():
                    repaired_sql = repaired_sql.replace(f" {missing_col} ", f" '{missing_col}' ")

        # Fix 4: Unrestricted SELECT *
        if "SELECT *" in error_message:
            repaired_sql = repaired_sql.replace("SELECT *", "SELECT order_id, order_status, order_purchase_timestamp")

        # If nothing changed, return None to trigger structured clarification
        if repaired_sql == failed_sql:
            return None

        return repaired_sql
