"""
Step 1 - Guard: Read-only and Prompt Injection Enforcer.
Deterministic code-based verification blocking unsafe, DDL, write, and prompt-injection operations.
Contract: Raw text -> Pass / Block + Reason.
"""
import re
from typing import Tuple, Optional
from src.config import BLOCKED_KEYWORDS, INJECTION_PATTERNS


class Guard:
    """Security Guard that inspects all user inputs and queries before processing."""

    def __init__(self):
        # Compile injection regexes
        self.injection_regexes = [
            re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS
        ]

    def check_input(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Validates user input text.
        Returns: (passed: bool, refusal_or_block_reason: Optional[str])
        """
        if not text or not text.strip():
            return False, "Empty query received."

        cleaned = text.strip()

        # 1. Check prompt injection patterns
        for pattern in self.injection_regexes:
            if pattern.search(cleaned):
                return False, "Security Guard Violation: Prompt injection attempt detected. Input treated as data, not instruction."

        # 2. Check for explicit shell or script injection indicators
        shell_indicators = ["<script>", "</script>", "eval(", "exec(", "; rm -rf", "| bash", "powershell -c"]
        for ind in shell_indicators:
            if ind in cleaned.lower():
                return False, f"Security Guard Violation: Unsafe command or script syntax detected ('{ind}')."

        # 3. Check for explicit destructive SQL verbs and operations in raw input
        destructive_pattern = r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|VIEW|INDEX|ALL)|DELETE\s+(FROM\s+)?(\w+|ALL\s+TABLES?)|TRUNCATE\s+(TABLE\s+)?\w+|ALTER\s+TABLE|INSERT\s+INTO|UPDATE\s+\w+\s+SET|REMOVE\s+ALL\s+TABLES?|WIPE\s+(OUT\s+|THE\s+|ALL\s+)?(TABLES?|DATABASE|DATA))\b"
        ddl_dml_match = re.search(destructive_pattern, cleaned, re.IGNORECASE)
        if ddl_dml_match:
            return False, f"Security Guard Violation: Destructive operation '{ddl_dml_match.group(0)}' is forbidden. Read-only warehouse mode enforced."

        # Also catch imperative natural language delete requests
        if re.search(r"\b(delete|drop|truncate|wipe|destroy|clear)\s+(all\s+)?(tables?|database|data|records?)\b", cleaned, re.IGNORECASE):
            return False, "Security Guard Violation: Destructive data deletion request blocked. Read-only warehouse mode enforced."

        return True, None

    def check_sql(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        Pre-flight check on SQL string before execution.
        """
        if not sql or not sql.strip():
            return False, "Empty SQL statement."

        # Reject stacked statements
        statements = [s.strip() for s in sql.strip().split(";") if s.strip()]
        if len(statements) > 1:
            return False, "Security Guard Violation: Stacked SQL statements (multiple ';') are prohibited."

        upper_sql = sql.upper()

        # Check for blocked keywords
        for kw in BLOCKED_KEYWORDS:
            pattern = rf"\b{kw}\b"
            if re.search(pattern, upper_sql):
                return False, f"Security Guard Violation: Disallowed SQL keyword '{kw}' detected."

        # Enforce that the query must start with SELECT or WITH
        first_token_match = re.match(r"^\s*(\w+)", upper_sql)
        if not first_token_match:
            return False, "Invalid SQL structure: missing initial keyword."

        first_token = first_token_match.group(1)
        if first_token not in ("SELECT", "WITH", "EXPLAIN"):
            return False, f"Security Guard Violation: Query must begin with SELECT or WITH (got '{first_token}')."

        return True, None
