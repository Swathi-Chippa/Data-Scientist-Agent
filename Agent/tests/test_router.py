"""
Unit Tests for Router and Extractor (§B3, §B5).
Tests route classification and slot extraction.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from src.router import Router
from src.models.schemas import RouteType


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_lookup_route(self):
        res = self.router.route_question("What was revenue by category last year?")
        self.assertEqual(res.route, RouteType.LOOKUP)
        self.assertEqual(res.slots.metric, "revenue")
        self.assertEqual(res.slots.dimension, "product_category")

    def test_anomaly_route(self):
        res = self.router.route_question("Weekly orders in SP dropped sharply last month — is that unusual?")
        self.assertEqual(res.route, RouteType.ANOMALY)
        self.assertEqual(res.slots.metric, "orders")
        self.assertEqual(res.slots.region_or_filter, "SP")

    def test_root_cause_route(self):
        res = self.router.route_question("What is driving the order drop in Rio?")
        self.assertEqual(res.route, RouteType.ROOT_CAUSE)
        self.assertEqual(res.slots.region_or_filter, "RJ")

    def test_risk_prediction_route(self):
        res = self.router.route_question("Which customer segments are we most likely to lose next quarter?")
        self.assertEqual(res.route, RouteType.RISK_PREDICTION)

    def test_ambiguous_route(self):
        res = self.router.route_question("How are sales doing?")
        self.assertEqual(res.route, RouteType.AMBIGUOUS)
        self.assertIsNotNone(res.clarification_question)

    def test_unanswerable_refusal(self):
        res = self.router.route_question("What is average customer age by state?")
        self.assertEqual(res.route, RouteType.UNANSWERABLE)
        self.assertIsNotNone(res.refusal_reason)


if __name__ == "__main__":
    unittest.main()
