"""
Unit Tests for Analysts (§B10).
Tests AnomalyAnalyst, DriverAnalyst, RiskAnalyst, and Advisor.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from src.analysts.anomaly import AnomalyAnalyst
from src.analysts.driver import DriverAnalyst
from src.analysts.risk import RiskAnalyst
from src.analysts.advisor import Advisor


class TestAnalysts(unittest.TestCase):
    def test_anomaly_analyst(self):
        analyst = AnomalyAnalyst()
        res = analyst.run({"region": "SP", "metric": "orders", "time_grain": "week"})
        self.assertEqual(res.status, "success")
        self.assertIn("median_baseline", res.metrics)
        self.assertTrue(len(res.evidence_claims) > 0)

    def test_driver_analyst(self):
        analyst = DriverAnalyst()
        res = analyst.run({"region": "SP", "metric": "orders"})
        self.assertEqual(res.status, "success")
        self.assertIn("top1_category", res.metrics)
        # Verify reconciliation
        self.assertIn("total_order_delta", res.metrics)

    def test_risk_analyst(self):
        analyst = RiskAnalyst()
        res = analyst.run({})
        self.assertEqual(res.status, "success")
        self.assertIn("gb_roc_auc", res.metrics)
        self.assertIn("one_time_buyer_pct", res.metrics)

    def test_advisor(self):
        advisor = Advisor()
        res = advisor.run({
            "driver_output": {"metrics": {"top1_category": "cama_mesa_banho", "delay_delta_days": 1.5}},
            "risk_output": {"metrics": {"top_revenue_at_risk": 50000.0}}
        })
        self.assertEqual(res.status, "success")
        self.assertTrue(len(res.tables.get("recommended_actions", [])) >= 2)


if __name__ == "__main__":
    unittest.main()
