"""
Step 3 - Planner: Ordered Module Execution Planning.
Translates route and extracted slots into a deterministic, validated sequence of Analyst modules.
Contract: Route + Slots -> Ordered Analyst Plan (depth-capped, validated against registry).
"""
from typing import List, Set
from src.config import MAX_PLAN_DEPTH
from src.models.schemas import RouteType, RouteResult, AnalystPlan, PlanStep


class Planner:
    """Plans multi-step analytical workflows validated against an allowlist registry."""

    # Governed allowlist of available Analysts (§B3, §B10)
    REGISTERED_ANALYSTS: Set[str] = {
        "AnomalyAnalyst",
        "DriverAnalyst",
        "RiskAnalyst",
        "Advisor"
    }

    def create_plan(self, route_result: RouteResult, raw_question: str) -> AnalystPlan:
        """
        Creates an ordered sequence of Analyst steps based on route and question intent.
        Enforces maximum depth and verifies that all planned modules exist in the registry.
        """
        steps: List[PlanStep] = []
        q_lower = raw_question.lower()

        route = route_result.route

        if route == RouteType.LOOKUP:
            # Lookup does not require an Analyst module
            return AnalystPlan(steps=[], depth=0, validated=True)

        elif route == RouteType.ANOMALY:
            # Check if this is a compound anomaly + root-cause question
            has_driver_intent = any(k in q_lower for k in ["what is driving", "driver", "why", "root cause"])
            has_action_intent = any(k in q_lower for k in ["what to do", "act", "recommend", "next"])

            steps.append(PlanStep(
                step_id=1,
                analyst_name="AnomalyAnalyst",
                purpose="Evaluate statistical significance of change against seasonal baseline",
                depends_on=[]
            ))

            if has_driver_intent:
                steps.append(PlanStep(
                    step_id=2,
                    analyst_name="DriverAnalyst",
                    purpose="Decompose change across dimensions and identify primary contributors",
                    depends_on=[1]
                ))

            if has_action_intent or has_driver_intent:
                steps.append(PlanStep(
                    step_id=len(steps) + 1,
                    analyst_name="Advisor",
                    purpose="Recommend high-feasibility operational interventions based on driver outputs",
                    depends_on=[len(steps)]
                ))

        elif route == RouteType.ROOT_CAUSE:
            steps.append(PlanStep(
                step_id=1,
                analyst_name="DriverAnalyst",
                purpose="Attribute variance across categories, sellers, regions and operational indicators",
                depends_on=[]
            ))
            steps.append(PlanStep(
                step_id=2,
                analyst_name="Advisor",
                purpose="Recommend actions mapped to primary identified drivers",
                depends_on=[1]
            ))

        elif route == RouteType.RISK_PREDICTION:
            steps.append(PlanStep(
                step_id=1,
                analyst_name="RiskAnalyst",
                purpose="Train and evaluate churn risk model on chronological split and aggregate segments",
                depends_on=[]
            ))
            steps.append(PlanStep(
                step_id=2,
                analyst_name="Advisor",
                purpose="Rank retention interventions by expected revenue at risk",
                depends_on=[1]
            ))

        elif route == RouteType.RECOMMENDATION:
            steps.append(PlanStep(
                step_id=1,
                analyst_name="Advisor",
                purpose="Rank candidate actions from the Action Library",
                depends_on=[]
            ))

        # Enforce max depth
        capped_steps = steps[:MAX_PLAN_DEPTH]

        # Validate against registry
        for s in capped_steps:
            if s.analyst_name not in self.REGISTERED_ANALYSTS:
                return AnalystPlan(
                    steps=[],
                    depth=0,
                    validated=False,
                    validation_error=f"Unregistered analyst module: '{s.analyst_name}'"
                )

        return AnalystPlan(
            steps=capped_steps,
            depth=len(capped_steps),
            validated=True
        )
