"""
Step 5 - Answerability Checker: Verifies catalog coverage before query generation.
Contract: Requested entities/text -> Answerable / Refusal naming missing attributes.
Enforces the fail-closed principle (§E1): a refusal is better than a hallucinated number.
"""
import re
from typing import Tuple, Optional, List


class AnswerabilityChecker:
    """Inspects question entities against known metadata catalog boundaries."""

    # Explicit list of unanswerable domain concepts and helpful alternatives
    UNANSWERABLE_MAP = {
        "customer age": ("Customer age / demographic birth dates", "customer geographic state or order history"),
        "age of customer": ("Customer age", "customer geographic state or order history"),
        "customer gender": ("Customer gender", "customer geographic state or order history"),
        "profit margin": ("Profit margin / cost data", "gross revenue (order price) or freight charges"),
        "product cost": ("Product wholesale cost / supplier COGS", "product item retail price"),
        "employee": ("Employee records / staff headcount", "sellers distribution across regions"),
        "headcount": ("Internal headcount", "sellers distribution across regions"),
        "warehouse temperature": ("IoT warehouse sensor telemetry", "delivery delay and transit duration"),
        "ad spend": ("Marketing advertising spend / campaign cost", "order volume trends across states"),
        "inventory": ("Warehouse live inventory / stock levels", "fulfilled order item volumes")
    }

    # Near-miss cases that SHOULD be answered and NOT over-refused (§D2)
    # e.g., "average delivery duration" contains "average" and "delivery", answerable via timestamps
    # e.g., "how old is the platform's earliest order" contains "old", answerable via min(order_purchase_timestamp)
    NEAR_MISS_PATTERNS = [
        r"earliest\s+order",
        r"first\s+purchase",
        r"oldest\s+order",
        r"average\s+(delivery|delay|shipping|review|order\s+value)"
    ]

    def check(self, question: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates whether the requested question can be answered by the warehouse.
        Returns: (is_answerable: bool, missing_attribute: Optional[str], refusal_message: Optional[str])
        """
        q_lower = question.lower()

        # 1. Check near-misses first to prevent false over-refusal
        for pattern in self.NEAR_MISS_PATTERNS:
            if re.search(pattern, q_lower):
                return True, None, None

        # 2. Check for missing warehouse attributes
        for term, (missing_desc, suggested_alt) in self.UNANSWERABLE_MAP.items():
            if re.search(rf"\b{re.escape(term)}\b", q_lower):
                refusal_msg = (
                    f"Refusal: The warehouse metadata catalog does not contain '{missing_desc}'. "
                    f"Our database records transactions, customers, products, payments, reviews, and delivery milestones, "
                    f"but lacks internal cost/demographic tracking. "
                    f"Closest answerable question: Would you like to analyze {suggested_alt} instead?"
                )
                return False, missing_desc, refusal_msg

        return True, None, None
