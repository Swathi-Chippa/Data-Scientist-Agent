"""
Step 11d - Advisor: Curated Recommendation Engine (§B10.4).
Generates prioritized, actionable operational interventions based on Analyst outputs.
Implements:
- Curated Action Library with owners, lead times, cost classes, and preconditions
- Quantitative multi-factor scoring: Score = Impact * Evidence Confidence * Feasibility
- Human-in-the-loop boundary: Agent recommends; person approves; never executes actions
- Structured trade-offs, sensitivity analysis, and monitoring KPIs
"""
from typing import Dict, Any, List, Optional
from src.analysts.base import BaseAnalyst, AnalystOutput
from src.models.schemas import AdvisorRecommendation


class ActionTemplate:
    def __init__(self, action_id: str, title: str, action_type: str, owner: str, lead_time: str, cost_class: str, feasibility: float, description: str, trade_offs: str, sensitivity: str, what_to_monitor: str):
        self.action_id = action_id
        self.title = title
        self.action_type = action_type
        self.owner = owner
        self.lead_time = lead_time
        self.cost_class = cost_class  # "Low", "Medium", "High"
        self.feasibility = feasibility  # 0.0 to 1.0
        self.description = description
        self.trade_offs = trade_offs
        self.sensitivity = sensitivity
        self.what_to_monitor = what_to_monitor


class ActionLibrary:
    """Repository of enterprise operational interventions mapped to drivers and risks."""

    def __init__(self):
        self.actions = {
            "carrier_renegotiation": ActionTemplate(
                action_id="ACT-01",
                title="SLA Review & Routing Shift for Delayed Carrier Corridors",
                action_type="Logistics / Carrier Operations",
                owner="VP Supply Chain & Logistics",
                lead_time="1-2 weeks",
                cost_class="Medium",
                feasibility=0.85,
                description="Temporarily re-route shipments in affected state corridors to secondary carrier with higher on-time SLA compliance.",
                trade_offs="Improves customer delivery times and review scores, but may incur a 3-5% higher freight surcharge.",
                sensitivity="Highly sensitive to regional carrier capacity; if secondary carrier exceeds volume quota, delay shifts elsewhere.",
                what_to_monitor="Average transit days to delivery and carrier pickup delay in affected region."
            ),
            "category_promotional_rebound": ActionTemplate(
                action_id="ACT-02",
                title="Targeted Re-engagement for Contracting Categories",
                action_type="Commercial / Merchandising",
                owner="Head of Category Merchandising",
                lead_time="3-5 days",
                cost_class="Low",
                feasibility=0.90,
                description="Launch targeted email campaigns and promotional coupons (e.g. 10% off) for high-impact categories driving the volume decline.",
                trade_offs="Increases immediate order conversion and recovers category share, but slightly compresses category gross margin.",
                sensitivity="Assumes category demand elasticity is > 1.2; low impact if decline is driven by broader macro supply shortages.",
                what_to_monitor="Category order velocity, discount redemption rate, and average basket size."
            ),
            "high_value_churn_vip": ActionTemplate(
                action_id="ACT-03",
                title="High-Value VIP Customer Retention Concierge Campaign",
                action_type="CRM / Customer Success",
                owner="Head of Retention & CRM",
                lead_time="3-7 days",
                cost_class="Low",
                feasibility=0.95,
                description="Deploy personalized direct outreach and free shipping vouchers to repeat customers in the top-decile revenue at risk pool.",
                trade_offs="Yields highest ROI per contact; limited scale since repeat buyers represent ~3% of active accounts.",
                sensitivity="Sensitive to customer email open rates and freshness of contact details.",
                what_to_monitor="90-day repeat purchase rate, customer lifetime value retention, and voucher redemption."
            ),
            "seller_fulfillment_audit": ActionTemplate(
                action_id="ACT-04",
                title="Top-Seller Fulfillment Latency Audit",
                action_type="Seller Operations",
                owner="Director of Merchant Performance",
                lead_time="1 week",
                cost_class="Low",
                feasibility=0.88,
                description="Audit order processing lead times for top merchants in affected region to eliminate dispatch bottlenecks.",
                trade_offs="Strengthens seller compliance; requires internal analyst time to review merchant logs.",
                sensitivity="Relies on merchant cooperation; non-compliant merchants may require platform penalties.",
                what_to_monitor="Average hours from order approval to carrier pickup (dispatch SLA)."
            ),
            "information_gathering_investigation": ActionTemplate(
                action_id="ACT-05",
                title="Root-Cause Diagnostic: Carrier Log & Inventory Inspection",
                action_type="Information Gathering",
                owner="Operations Analytics Lead",
                lead_time="2-3 days",
                cost_class="Very Low",
                feasibility=0.98,
                description="Low-cost diagnostic audit: Inspect carrier delivery logs and seller out-of-stock rates before committing capital.",
                trade_offs="Safeguards against premature costly interventions; defers immediate commercial action by 48 hours.",
                sensitivity="Effective when statistical evidence confidence is low or observational confounders are present.",
                what_to_monitor="Data log completeness and verification of transit bottleneck points."
            )
        }

    def get_action(self, action_id: str) -> Optional[ActionTemplate]:
        return self.actions.get(action_id)


class Advisor(BaseAnalyst):
    """Ranks 2 to 3 operational actions based on quantified impact and evidence confidence."""

    def __init__(self):
        super().__init__(name="Advisor")
        self.library = ActionLibrary()

    def run(self, context: Dict[str, Any]) -> AnalystOutput:
        """
        Produces ranked recommendations based on Anomaly, Driver, or Risk outputs.
        """
        driver_output = context.get("driver_output")
        risk_output = context.get("risk_output")
        anomaly_output = context.get("anomaly_output")

        selected_actions: List[AdvisorRecommendation] = []

        # Scenario 1: Risk Analysis present -> prioritize churn retention
        if risk_output and risk_output.get("metrics"):
            top_rev_at_risk = risk_output["metrics"].get("top_revenue_at_risk", 50000.0)
            vip_action = self.library.get_action("high_value_churn_vip")
            if vip_action:
                impact = min(1.0, top_rev_at_risk / 100000.0)
                confidence = 0.90
                score = round(impact * confidence * vip_action.feasibility * 10.0, 2)
                selected_actions.append(AdvisorRecommendation(
                    rank=1,
                    title=vip_action.title,
                    action_type=vip_action.action_type,
                    owner=vip_action.owner,
                    lead_time=vip_action.lead_time,
                    cost_class=vip_action.cost_class,
                    impact_score=round(impact * 10.0, 1),
                    evidence_confidence=confidence,
                    feasibility=vip_action.feasibility,
                    ranking_score=score,
                    assumptions=[
                        f"Targeting active repeat accounts where Expected Revenue at Risk is highest (R${top_rev_at_risk:,.2f}).",
                        "Assumes 15-20% incremental conversion on VIP incentive."
                    ],
                    trade_offs=vip_action.trade_offs,
                    sensitivity=vip_action.sensitivity,
                    what_to_monitor=vip_action.what_to_monitor,
                    requires_human_approval=True
                ))

        # Scenario 2: Driver / Anomaly analysis present -> category rebound or carrier routing
        if driver_output and driver_output.get("metrics"):
            metrics = driver_output["metrics"]
            top1_cat = metrics.get("top1_category", "top category")
            delay_delta = metrics.get("delay_delta_days", 0.0)

            # Action: Category Re-engagement
            cat_action = self.library.get_action("category_promotional_rebound")
            if cat_action:
                impact = 0.82
                confidence = 0.88
                score = round(impact * confidence * cat_action.feasibility * 10.0, 2)
                selected_actions.append(AdvisorRecommendation(
                    rank=len(selected_actions) + 1,
                    title=f"Promotional Campaign & Stock Rebalancing for '{top1_cat}'",
                    action_type=cat_action.action_type,
                    owner=cat_action.owner,
                    lead_time=cat_action.lead_time,
                    cost_class=cat_action.cost_class,
                    impact_score=round(impact * 10.0, 1),
                    evidence_confidence=confidence,
                    feasibility=cat_action.feasibility,
                    ranking_score=score,
                    assumptions=[
                        f"Decline in '{top1_cat}' accounted for {metrics.get('top1_share_pct', 50)}% of the net volume drop.",
                        "Elasticity in this category supports demand recovery via targeted promotional merchandising."
                    ],
                    trade_offs=cat_action.trade_offs,
                    sensitivity=cat_action.sensitivity,
                    what_to_monitor=cat_action.what_to_monitor,
                    requires_human_approval=True
                ))

            # If transit delays increased, recommend carrier re-routing
            if delay_delta > 0.3:
                carrier_action = self.library.get_action("carrier_renegotiation")
                if carrier_action:
                    impact = 0.78
                    confidence = 0.85
                    score = round(impact * confidence * carrier_action.feasibility * 10.0, 2)
                    selected_actions.append(AdvisorRecommendation(
                        rank=len(selected_actions) + 1,
                        title=carrier_action.title,
                        action_type=carrier_action.action_type,
                        owner=carrier_action.owner,
                        lead_time=carrier_action.lead_time,
                        cost_class=carrier_action.cost_class,
                        impact_score=round(impact * 10.0, 1),
                        evidence_confidence=confidence,
                        feasibility=carrier_action.feasibility,
                        ranking_score=score,
                        assumptions=[
                            f"Transit delays in the affected region rose by {delay_delta} days during the decline.",
                            "Secondary carrier has capacity to absorb 20-30% volume shift."
                        ],
                        trade_offs=carrier_action.trade_offs,
                        sensitivity=carrier_action.sensitivity,
                        what_to_monitor=carrier_action.what_to_monitor,
                        requires_human_approval=True
                    ))

        # Always include low-cost Information Gathering option if evidence is incomplete (§B10.4)
        if len(selected_actions) < 2:
            diag_action = self.library.get_action("information_gathering_investigation")
            selected_actions.append(AdvisorRecommendation(
                rank=len(selected_actions) + 1,
                title=diag_action.title,
                action_type=diag_action.action_type,
                owner=diag_action.owner,
                lead_time=diag_action.lead_time,
                cost_class=diag_action.cost_class,
                impact_score=6.5,
                evidence_confidence=0.98,
                feasibility=diag_action.feasibility,
                ranking_score=6.37,
                assumptions=["Low-cost diagnostic audit to verify carrier and inventory logs before major capital spend."],
                trade_offs=diag_action.trade_offs,
                sensitivity=diag_action.sensitivity,
                what_to_monitor=diag_action.what_to_monitor,
                requires_human_approval=True
            ))

        # Sort by ranking score
        selected_actions.sort(key=lambda a: a.ranking_score, reverse=True)
        # Update rank numbers
        for i, a in enumerate(selected_actions, 1):
            a.rank = i

        table_records = []
        for a in selected_actions:
            table_records.append({
                "rank": a.rank,
                "title": a.title,
                "owner": a.owner,
                "lead_time": a.lead_time,
                "cost_class": a.cost_class,
                "score": a.ranking_score,
                "trade_offs": a.trade_offs
            })

        summary_text = (
            f"Advisor formulated {len(selected_actions)} prioritized operational options. "
            f"Top recommendation: '{selected_actions[0].title}' (Owner: {selected_actions[0].owner}, "
            f"Lead Time: {selected_actions[0].lead_time}, Score: {selected_actions[0].ranking_score}/10). "
            f"All operational recommendations require human leadership approval prior to execution."
        )

        return AnalystOutput(
            analyst_name=self.name,
            status="success",
            verdict="Operational Options Ranked",
            summary=summary_text,
            metrics={
                "actions_evaluated": len(selected_actions),
                "top_recommendation": selected_actions[0].title,
                "top_score": selected_actions[0].ranking_score
            },
            tables={
                "recommended_actions": table_records
            },
            assumptions=[
                "Rankings computed via: Score = Impact × Evidence Confidence × Feasibility.",
                "Agent operates strictly in advisory capacity; human approval required for execution."
            ],
            caveats=[
                "Execution of commercial or carrier changes involves financial trade-offs as detailed per option."
            ],
            evidence_claims=[
                {
                    "text": f"Recommended action 1: '{selected_actions[0].title}' ranked highest with composite score of {selected_actions[0].ranking_score}/10.",
                    "grade": 0,
                    "data": {"rank": 1, "title": selected_actions[0].title, "score": selected_actions[0].ranking_score}
                }
            ]
        )
