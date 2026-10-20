"""
Step 2 - Router and Extractor: Multi-signal Routing and Slot Filling.
Combines deterministic rules, lightweight text heuristics, and slot extraction.
Contract: Question -> Route, Confidence, Slots (metric, dimension, time window, filters).
"""
import re
from typing import Dict, Any, List, Optional
from src.models.schemas import RouteType, RouteResult, ExtractedSlots


class Router:
    """Multi-signal question router and entity/slot extractor."""

    # Unanswerable attributes known to be absent from warehouse catalog (§A2, §C2)
    UNANSWERABLE_TERMS = [
        "customer age", "age of customer", "customer gender", "gender", 
        "profit margin", "margin", "cost of goods", "cogs", "product cost",
        "employee", "headcount", "salary", "warehouse temperature", "advertising spend",
        "ad spend", "click through rate", "ctr", "inventory level", "stock count"
    ]

    # Ambiguous phrases that lack actionable metrics or scope
    AMBIGUOUS_PATTERNS = [
        r"^(how\s+are\s+sales\s+doing\??)$",
        r"^(what\s+is\s+going\s+on\??)$",
        r"^(check\s+the\s+numbers\??)$",
        r"^(how\s+is\s+business\??)$",
        r"^(status\s+update\??)$",
        r"^(is\s+everything\s+ok\??)$"
    ]

    def route_question(self, question: str) -> RouteResult:
        """
        Routes incoming question using combined signals:
        1. Ambiguous pattern check
        2. Unanswerable catalog check
        3. Rule-based signal check (verbs, phrases)
        4. Slot extraction
        """
        q_lower = question.strip().lower()

        # Signal 0: Destructive operations check
        if any(w in q_lower.split() for w in ["delete", "drop", "truncate", "wipe", "destroy"]) and any(w in q_lower for w in ["table", "tables", "database", "orders", "customers", "all"]):
            return RouteResult(
                route=RouteType.UNSAFE,
                confidence=1.0,
                reason="Destructive operations are forbidden in read-only warehouse mode.",
                refusal_reason="Security Guard Violation: Destructive operations (DELETE, DROP, TRUNCATE) are forbidden. Warehouse connection is strictly read-only."
            )

        # Signal 1: Ambiguous check
        for pat in self.AMBIGUOUS_PATTERNS:
            if re.match(pat, q_lower):
                return RouteResult(
                    route=RouteType.AMBIGUOUS,
                    confidence=0.95,
                    reason="Question is overly broad with no specific metric, dimension, or time frame specified.",
                    clarification_question=(
                        "I understood that you are interested in overall business performance. "
                        "To provide a precise analysis, could you please specify: "
                        "(1) which metric you want to examine (e.g., total orders, revenue, delivery speed), "
                        "(2) the region or category of interest, and "
                        "(3) the time window (e.g., last month, 2018-Q1)?"
                    )
                )

        # Signal 2: Check for known unanswerable warehouse attributes
        for term in self.UNANSWERABLE_TERMS:
            if term in q_lower:
                return RouteResult(
                    route=RouteType.UNANSWERABLE,
                    confidence=0.98,
                    reason=f"Question requests attribute '{term}', which is not captured in the e-commerce data warehouse.",
                    refusal_reason=(
                        f"Refusal: The warehouse does not contain data for '{term}'. "
                        "Available customer attributes include geographic location (city, state, zip prefix) and purchase history. "
                        "Would you like to examine customer distribution by state or order frequency instead?"
                    )
                )

        # Try Gemini LLM router if client is active and available
        gemini_result = self._route_with_gemini(question)
        if gemini_result:
            return gemini_result

        # Fallback Signal 3: Deterministic & heuristic route classification
        # Extract slots using heuristics
        slots = self._extract_slots(question)

        # Check compound questions: Anomaly + Root Cause ("dropped sharply... is that unusual and what is driving it?")
        has_anomaly_cue = any(k in q_lower for k in ["unusual", "anomaly", "abnormal", "dropped sharply", "sharp drop", "spike", "sudden increase", "dip"])
        has_driver_cue = any(k in q_lower for k in ["what is driving", "why did", "driver", "root cause", "driving it", "caused by", "explain the drop"])
        has_risk_cue = any(k in q_lower for k in ["lose", "churn", "likely to churn", "at risk", "customer retention", "lapse", "dormant"])
        has_reco_cue = any(k in q_lower for k in ["where should we act", "what should we do", "recommend", "next action", "action first", "how to mitigate"])

        # Determine Route & Reason
        if has_risk_cue and has_reco_cue:
            # Compound risk + recommendation
            return RouteResult(
                route=RouteType.RISK_PREDICTION,
                confidence=0.92,
                reason="Treated as risk prediction + recommendation: asks which customer segments are likely to churn and where to act first.",
                slots=slots
            )
        elif has_risk_cue:
            return RouteResult(
                route=RouteType.RISK_PREDICTION,
                confidence=0.94,
                reason="Treated as risk prediction: question asks to identify at-risk or churning customer segments.",
                slots=slots
            )
        elif has_anomaly_cue and has_driver_cue:
            return RouteResult(
                route=RouteType.ANOMALY,
                confidence=0.95,
                reason="Treated as compound anomaly + root-cause: question asks whether a change is unusual and what is driving it.",
                slots=slots
            )
        elif has_anomaly_cue:
            return RouteResult(
                route=RouteType.ANOMALY,
                confidence=0.92,
                reason="Treated as anomaly detection: asks whether an observed level shift or variation is statistically unusual.",
                slots=slots
            )
        elif has_driver_cue:
            return RouteResult(
                route=RouteType.ROOT_CAUSE,
                confidence=0.91,
                reason="Treated as root-cause (driver attribution): asks for underlying factors driving a metric shift.",
                slots=slots
            )
        elif has_reco_cue:
            return RouteResult(
                route=RouteType.RECOMMENDATION,
                confidence=0.88,
                reason="Treated as recommendation: asks for prioritized operational interventions.",
                slots=slots
            )
        else:
            # Default to grounded lookup
            return RouteResult(
                route=RouteType.LOOKUP,
                confidence=0.89,
                reason="Treated as grounded lookup: direct aggregation or query against warehouse tables.",
                slots=slots
            )

    def _route_with_gemini(self, question: str) -> Optional[RouteResult]:
        """Calls gemini-2.5-flash for intelligent intent extraction when active."""
        try:
            from src.llm.client import get_gemini_client
            client = get_gemini_client()
            if not client.is_available():
                return None

            system_instruction = (
                "You are the Router and Slot Extractor Agent for an enterprise E-Commerce data warehouse.\n"
                "Analyze the user's business question and return JSON with:\n"
                "1. route: one of ['lookup', 'anomaly', 'root_cause', 'risk_prediction', 'recommendation', 'ambiguous', 'unanswerable', 'unsafe']\n"
                "2. confidence: float between 0.0 and 1.0\n"
                "3. reason: concise rationale for the chosen route\n"
                "4. metric: resolved metric (revenue, orders, delivered_orders, average_order_value, delivery_delay, review_score) or null\n"
                "5. dimension: aggregation dimension ('product_category', 'customer_state', 'seller_state', 'payment_type') or null\n"
                "6. time_window: normalized date (e.g. '2018-08', '2018-Q1', '2017') or null\n"
                "7. region_or_filter: 2-letter state code (e.g. 'SP', 'RJ') or filter or null\n"
                "8. clarification_question: string if route is ambiguous, else null\n"
                "9. refusal_reason: string if route is unanswerable or unsafe, else null\n\n"
                "CRITICAL RULES:\n"
                "- If question asks about losing customers / churn AND actions / where to act first, route MUST be 'risk_prediction'.\n"
                "- If question asks if a change is unusual AND what is driving it, route MUST be 'anomaly'.\n"
                "- Normalize Brazilian regions to 2-letter codes: Rio de Janeiro -> 'RJ', Sao Paulo -> 'SP'.\n"
                "- Normalize product category dimension to 'product_category'."
            )

            prompt = f"Question: \"{question}\""
            data = client.generate_json(prompt=prompt, system_instruction=system_instruction)
            if not data or "route" not in data:
                return None

            route_str = str(data.get("route", "")).lower()

            # Compound override: churn + action -> risk_prediction
            q_low = question.lower()
            if ("lose" in q_low or "churn" in q_low) and ("act" in q_low or "action" in q_low or "first" in q_low):
                route_str = "risk_prediction"
            elif ("unusual" in q_low or "anomaly" in q_low) and ("driving" in q_low or "why" in q_low):
                route_str = "anomaly"
            elif any(k in q_low for k in ["what is driving", "what drove", "why did", "root cause", "explain the drop", "driver"]):
                if not any(k in q_low for k in ["is that unusual", "is it unusual", "anomaly", "abnormal"]):
                    route_str = "root_cause"

            route_map = {
                "lookup": RouteType.LOOKUP,
                "anomaly": RouteType.ANOMALY,
                "root_cause": RouteType.ROOT_CAUSE,
                "risk_prediction": RouteType.RISK_PREDICTION,
                "recommendation": RouteType.RECOMMENDATION,
                "ambiguous": RouteType.AMBIGUOUS,
                "unanswerable": RouteType.UNANSWERABLE,
                "unsafe": RouteType.UNSAFE,
            }
            if route_str not in route_map:
                return None

            dim = data.get("dimension")
            if dim in ["product_category_name", "category"]:
                dim = "product_category"

            reg = data.get("region_or_filter")
            if reg:
                reg_l = str(reg).lower().strip()
                if reg_l in ["rio", "rio de janeiro", "rj"]:
                    reg = "RJ"
                elif reg_l in ["sao paulo", "são paulo", "sp"]:
                    reg = "SP"

            slots = ExtractedSlots(
                metric=data.get("metric"),
                dimension=dim,
                time_window=data.get("time_window"),
                region_or_filter=reg,
                filters=data.get("filters", {})
            )

            return RouteResult(
                route=route_map[route_str],
                confidence=float(data.get("confidence", 0.95)),
                reason=f"[{client.get_active_model_name()}] {data.get('reason', 'Resolved by LLM intent classifier')}",
                slots=slots,
                clarification_question=data.get("clarification_question"),
                refusal_reason=data.get("refusal_reason")
            )
        except Exception:
            return None

    def _extract_slots(self, text: str) -> ExtractedSlots:
        """Extracts metric, dimension, temporal window, and filters from text."""
        t_low = text.lower()
        slots = ExtractedSlots()

        # 1. Metric extraction
        if any(m in t_low for m in ["revenue", "sales", "gmv", "spend", "amount"]):
            slots.metric = "revenue"
        elif any(m in t_low for m in ["order count", "orders", "volume", "purchases", "order"]):
            slots.metric = "orders"
        elif any(m in t_low for m in ["delivery time", "delay", "shipping time", "freight"]):
            slots.metric = "delivery_delay"
        elif any(m in t_low for m in ["review", "rating", "score", "satisfaction"]):
            slots.metric = "review_score"
        elif any(m in t_low for m in ["customer", "buyers", "clients"]):
            slots.metric = "customer_count"

        # 2. Dimension extraction
        if any(d in t_low for d in ["category", "product category", "product type", "product"]):
            slots.dimension = "product_category"
        elif any(d in t_low for d in ["state", "region", "city", "geographic"]):
            slots.dimension = "customer_state"
        elif any(d in t_low for d in ["seller", "merchant", "vendor"]):
            slots.dimension = "seller_id"
        elif any(d in t_low for d in ["payment", "payment type", "installments"]):
            slots.dimension = "payment_type"
        elif any(d in t_low for d in ["carrier", "shipping", "logistics"]):
            slots.dimension = "carrier"

        # 3. Specific Region / Filter extraction (e.g. SP, RJ, MG, etc.)
        brazilian_states = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "GO", "PE", "CE"]
        for st in brazilian_states:
            # Look for whole word state or "in <state>"
            if re.search(rf"\b{st}\b", text, re.IGNORECASE) or f"in {st.lower()}" in t_low:
                slots.region_or_filter = st.upper()
                break

        # Check for state names
        state_names = {
            "são paulo": "SP", "sao paulo": "SP",
            "rio de janeiro": "RJ", "rio": "RJ",
            "minas gerais": "MG", "minas": "MG",
            "rio grande do sul": "RS",
            "paraná": "PR", "parana": "PR",
            "santa catarina": "SC",
            "bahia": "BA"
        }
        for name, code in state_names.items():
            if name in t_low:
                slots.region_or_filter = code
                break

        # 4. Time Window extraction
        if "last month" in t_low:
            slots.time_window = "last_month"
        elif "last quarter" in t_low:
            slots.time_window = "last_quarter"
        elif "next quarter" in t_low:
            slots.time_window = "next_quarter"
        elif "last year" in t_low:
            slots.time_window = "last_year"
        elif "weekly" in t_low or "week" in t_low:
            slots.time_window = "weekly"
        elif re.search(r'(\d{4})-?q([1-4])', t_low):
            m = re.search(r'(\d{4})-?q([1-4])', t_low)
            slots.time_window = f"{m.group(1)}-q{m.group(2)}"
        elif "2019" in t_low:
            slots.time_window = "2019"
        elif "2018" in t_low:
            slots.time_window = "2018"
        elif "2017" in t_low:
            slots.time_window = "2017"

        return slots
