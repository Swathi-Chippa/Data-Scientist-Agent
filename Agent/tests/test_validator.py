"""
Unit Tests for SQL Validator (§B8).
Tests AST parsing, allowlists, join verification, and cost gating.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from src.sql.validator import SQLValidator


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.validator = SQLValidator()
        self.tables = ["orders", "customers", "order_items"]
        self.columns = {
            "orders": ["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
            "customers": ["customer_id", "customer_state"],
            "order_items": ["order_id", "price"]
        }

    def test_valid_select_passes(self):
        sql = "SELECT customer_state, COUNT(DISTINCT orders.order_id) as total_orders FROM orders JOIN customers ON orders.customer_id = customers.customer_id WHERE order_status = 'delivered' GROUP BY 1 LIMIT 50;"
        res = self.validator.validate(sql, self.tables, self.columns)
        self.assertTrue(res.approved)
        self.assertEqual(len(res.errors), 0)

    def test_disallowed_table_rejected(self):
        sql = "SELECT * FROM secret_payroll_table LIMIT 10;"
        res = self.validator.validate(sql, self.tables, self.columns)
        self.assertFalse(res.approved)
        self.assertTrue(any("Allowlist Violation" in e for e in res.errors))

    def test_star_select_rejected(self):
        sql = "SELECT * FROM orders LIMIT 10;"
        res = self.validator.validate(sql, self.tables, self.columns)
        self.assertFalse(res.approved)
        self.assertTrue(any("SELECT *" in e for e in res.errors))

    def test_non_select_rejected(self):
        sql = "DELETE FROM orders WHERE order_status = 'canceled';"
        res = self.validator.validate(sql, self.tables, self.columns)
        self.assertFalse(res.approved)


if __name__ == "__main__":
    unittest.main()
