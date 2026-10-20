"""
Pydantic Schemas and Contracts for Data Scientist Agent.
Implements typed contracts specified in DESIGN_DETAIL.md (§B3, §B11, §B12).
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RouteType(str, Enum):
    LOOKUP = "lookup"
    ANOMALY = "anomaly"
    ROOT_CAUSE = "root_cause"
    RISK_PREDICTION = "risk_prediction"
    RECOMMENDATION = "recommendation"
    AMBIGUOUS = "ambiguous"
    UNANSWERABLE = "unanswerable"
    UNSAFE = "unsafe"


class ExtractedSlots(BaseModel):
    metric: Optional[str] = None
    dimension: Optional[str] = None
    time_window: Optional[str] = None
    region_or_filter: Optional[str] = None
    comparison_period: Optional[str] = None
    raw_entities: List[str] = Field(default_factory=list)


class RouteResult(BaseModel):
    route: RouteType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    slots: ExtractedSlots = Field(default_factory=ExtractedSlots)
    clarification_question: Optional[str] = None
    refusal_reason: Optional[str] = None


class PlanStep(BaseModel):
    step_id: int
    analyst_name: str
    purpose: str
    depends_on: List[int] = Field(default_factory=list)


class AnalystPlan(BaseModel):
    steps: List[PlanStep] = Field(default_factory=list)
    depth: int = 0
    validated: bool = True
    validation_error: Optional[str] = None


class GovernedMetric(BaseModel):
    name: str
    synonyms: List[str]
    formula: str
    required_filters: List[str] = Field(default_factory=list)
    time_grain: str = "month"
    date_column: str
    allowed_dimensions: List[str] = Field(default_factory=list)
    base_table: str
    join_path: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    reconciliation_query: Optional[str] = None


class RetrievedSchema(BaseModel):
    tables: List[str]
    columns_by_table: Dict[str, List[str]]
    join_edges: List[Dict[str, str]] = Field(default_factory=list)
    linked_values: Dict[str, str] = Field(default_factory=dict)
    column_warnings: List[str] = Field(default_factory=list)
    retrieval_confidence: float = 1.0


class SQLCandidate(BaseModel):
    sql: str
    source: str  # "compiler" or "generator"
    is_governed: bool = False
    metric_name: Optional[str] = None


class ValidationResult(BaseModel):
    approved: bool
    ast_valid: bool = True
    allowlist_valid: bool = True
    join_valid: bool = True
    fan_out_safe: bool = True
    cost_gate_passed: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    estimated_rows: int = 0


class ExecutionResult(BaseModel):
    success: bool
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class ReconciliationResult(BaseModel):
    passed: bool
    grain_checked: bool = True
    duplicates_checked: bool = True
    checked_metric: Optional[str] = None
    expected_total: Optional[float] = None
    observed_total: Optional[float] = None
    diff_pct: Optional[float] = None
    caveat: Optional[str] = None


class EvidenceClaim(BaseModel):
    claim_id: int
    text: str
    evidence_grade: int  # 0 to 4
    source_type: str  # "query", "anomaly_analyst", "driver_analyst", "risk_analyst"
    source_id: str
    data_points: Dict[str, Any] = Field(default_factory=dict)
    verified: bool = True


class EvidenceLedger(BaseModel):
    claims: List[EvidenceClaim] = Field(default_factory=list)

    def add_claim(self, text: str, grade: int, source_type: str, source_id: str, data: Dict[str, Any]) -> EvidenceClaim:
        cid = len(self.claims) + 1
        claim = EvidenceClaim(
            claim_id=cid,
            text=text,
            evidence_grade=grade,
            source_type=source_type,
            source_id=source_id,
            data_points=data,
            verified=True
        )
        self.claims.append(claim)
        return claim


class AdvisorRecommendation(BaseModel):
    rank: int
    title: str
    action_type: str
    owner: str
    lead_time: str
    cost_class: str
    impact_score: float
    evidence_confidence: float
    feasibility: float
    ranking_score: float
    assumptions: List[str] = Field(default_factory=list)
    trade_offs: str
    sensitivity: str
    what_to_monitor: str
    requires_human_approval: bool = True


class FinalAnswer(BaseModel):
    trace_id: str
    route: str
    route_reason: str
    status: str  # "success", "clarification", "refusal", "blocked"
    conclusion: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    claims: List[EvidenceClaim] = Field(default_factory=list)
    executed_sql: Optional[str] = None
    sql_execution_time_ms: Optional[float] = None
    query_row_count: Optional[int] = None
    query_columns: Optional[List[str]] = None
    query_rows: Optional[List[List[Any]]] = None
    recommendations: List[AdvisorRecommendation] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    causal_boundary: Optional[str] = None
    clarification_question: Optional[str] = None
    refusal_reason: Optional[str] = None
    run_metrics: Dict[str, Any] = Field(default_factory=dict)
    trace_file_path: Optional[str] = None

    def to_answer_envelope(self) -> "AnswerEnvelope":
        """Adapts internal FinalAnswer representation to standard AnswerEnvelope (Interfaces.md §5.2)."""
        from datetime import datetime, timezone

        status_map = {
            "success": "answered",
            "clarification": "clarify",
            "refusal": "refused",
            "blocked": "blocked"
        }
        env_status = status_map.get(self.status, "answered")

        route_dict = {
            "labels": [self.route],
            "confidence": float(self.run_metrics.get("route_confidence", 0.95)),
            "reason": self.route_reason
        }

        ledger_claims = []
        for c in self.claims:
            cid = f"C{c.claim_id}" if isinstance(c.claim_id, int) else str(c.claim_id)
            nums = []
            if hasattr(c, "data_points") and isinstance(c.data_points, dict):
                for k, v in c.data_points.items():
                    if isinstance(v, (int, float)):
                        nums.append({"token": str(v), "value": float(v)})
            grade_kind_map = {
                0: "fact",
                1: "concentration",
                2: "co_movement",
                3: "comparison",
                4: "consistent_with"
            }
            ledger_claims.append(LedgerClaim(
                claim_id=cid,
                text=c.text,
                numbers=nums,
                source={"type": "query" if c.source_type == "sql" else "artifact", "id": c.source_id or "Q1"},
                grade=c.evidence_grade,
                kind=grade_kind_map.get(c.evidence_grade, "hypothesis")
            ))

        evidence_blocks = []
        if self.query_rows is not None and self.query_columns is not None:
            evidence_blocks.append(EvidenceBlock(
                module="lookup" if self.route in ["lookup", "ambiguous", "unanswerable", "unsafe"] else self.route,
                output={
                    "query_id": "Q1",
                    "columns": [{"name": col, "type": "varchar"} for col in self.query_columns],
                    "rows": self.query_rows[:100],
                    "row_count": self.query_row_count or len(self.query_rows),
                    "truncated": bool(self.query_row_count and self.query_row_count > 100)
                },
                source_claims=[c.claim_id for c in ledger_claims]
            ))

        queries = []
        if self.executed_sql:
            queries.append(QueryRecord(
                query_id="Q1",
                sql=self.executed_sql,
                status="ok",
                duration_ms=float(self.sql_execution_time_ms or 0.0),
                rows_scanned=self.query_row_count or 0,
                origin="compiler" if self.scope.get("is_governed") else "generator"
            ))

        actions = []
        for r in self.recommendations:
            actions.append(ActionOption(
                action_id=f"act_{r.rank}",
                title=r.title,
                rank=r.rank,
                assumptions=r.assumptions if isinstance(r.assumptions, list) else [str(r.assumptions)],
                trade_offs=[r.trade_offs] if isinstance(r.trade_offs, str) else r.trade_offs,
                sensitivity=r.sensitivity,
                monitor=[r.what_to_monitor] if isinstance(r.what_to_monitor, str) else r.what_to_monitor,
                data_that_would_change_ranking=["Order trends shift", "Logistics partner SLA updates"],
                kind="intervention" if "act" in r.action_type.lower() else "information_gathering"
            ))

        clarify_payload = None
        if self.clarification_question:
            clarify_payload = {
                "what_understood": self.route_reason,
                "what_needs_clarification": self.clarification_question
            }

        refusal_payload = None
        if self.refusal_reason:
            refusal_payload = {
                "missing": [self.refusal_reason],
                "closest_answerable": "What was total revenue by category?"
            }

        block_payload = None
        if self.status == "blocked":
            block_payload = {
                "reason": "injection" if "injection" in (self.refusal_reason or "").lower() else "unsafe",
                "detail": self.refusal_reason or "Blocked by Guard"
            }

        run_mets = {
            "latency_ms": float(self.run_metrics.get("total_duration_ms", 0.0)),
            "tokens": int(self.run_metrics.get("tokens_estimated", 0)),
            "queries": 1 if self.executed_sql else 0,
            "rows": int(self.query_row_count or 0),
            "retries": int(self.run_metrics.get("repair_attempts", 0))
        }

        prov = {
            "model_name": "qwen2.5-coder:latest",
            "model_version": "ollama-local",
            "commit": "master",
            "snapshot_id": "brazil_ecommerce_duckdb",
            "catalog_version": "v1.0",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return AnswerEnvelope(
            contract_version="1.0.0",
            run_id=self.trace_id,
            status=env_status,
            route=route_dict,
            conclusion=self.conclusion,
            scope=self.scope,
            evidence=evidence_blocks,
            claims=ledger_claims,
            method=[{"name": self.route, "params": self.scope}],
            queries=queries,
            caveats=self.caveats,
            causal_boundary_note=self.causal_boundary,
            next_actions=actions,
            clarification=clarify_payload,
            refusal=refusal_payload,
            block=block_payload,
            run_metrics=run_mets,
            provenance=prov
        )


# =============================================================================
# Standard Contract Types as defined in Interfaces.md (§2, §5.2, §5.4)
# =============================================================================

class LedgerClaim(BaseModel):
    claim_id: str
    text: str
    numbers: List[Dict[str, Any]] = Field(default_factory=list)
    source: Dict[str, str] = Field(default_factory=dict)
    grade: int = 0
    kind: str = "fact"


class QueryRecord(BaseModel):
    query_id: str
    sql: str
    status: str = "ok"
    duration_ms: float = 0.0
    rows_scanned: Optional[int] = None
    origin: str = "compiler"


class ActionOption(BaseModel):
    action_id: str
    title: str
    rank: int
    assumptions: List[str] = Field(default_factory=list)
    trade_offs: List[str] = Field(default_factory=list)
    sensitivity: str = "normal"
    monitor: List[str] = Field(default_factory=list)
    data_that_would_change_ranking: List[str] = Field(default_factory=list)
    kind: str = "intervention"


class EvidenceBlock(BaseModel):
    module: str
    output: Any
    source_claims: List[str] = Field(default_factory=list)


class AnswerEnvelope(BaseModel):
    contract_version: str = "1.0.0"
    run_id: str
    status: str  # "answered" | "clarify" | "refused" | "blocked" | "insufficient_evidence" | "error"
    route: Dict[str, Any]
    conclusion: Optional[str] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[EvidenceBlock] = Field(default_factory=list)
    claims: List[LedgerClaim] = Field(default_factory=list)
    method: List[Dict[str, Any]] = Field(default_factory=list)
    queries: List[QueryRecord] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    causal_boundary_note: Optional[str] = None
    next_actions: List[ActionOption] = Field(default_factory=list)
    clarification: Optional[Dict[str, Any]] = None
    refusal: Optional[Dict[str, Any]] = None
    block: Optional[Dict[str, Any]] = None
    run_metrics: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    clarification_of: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"
    note: Optional[str] = None


class ReviewRequest(BaseModel):
    reason: Optional[str] = None


class ConnectRequest(BaseModel):
    dialect: str = "duckdb"
    connection_ref: str = "brazil_ecommerce"
    schemas_include: Optional[List[str]] = None
    schemas_exclude: Optional[List[str]] = None
    mode: Optional[str] = "initial"
