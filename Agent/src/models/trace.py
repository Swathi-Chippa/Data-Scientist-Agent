"""
Trace Models for full observability and auditing.
Records every step of the agent pipeline for transparent file-based tracing.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class StepTrace(BaseModel):
    step_number: int
    step_name: str
    component_type: str  # "code", "assisted", "model"
    start_time: str
    end_time: str
    duration_ms: float
    status: str  # "success", "skipped", "failed", "blocked"
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PipelineRunTrace(BaseModel):
    trace_id: str
    timestamp: str
    question: str
    route_chosen: Optional[str] = None
    steps: List[StepTrace] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    status: str = "pending"
    executed_queries: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_claims_count: int = 0
    fact_check_passed: bool = True
    hard_safety_gates_passed: bool = True
    token_usage_estimate: int = 0
    final_status: str = "success"

    def add_step(
        self,
        step_number: int,
        step_name: str,
        component_type: str,
        start_dt: datetime,
        end_dt: datetime,
        status: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        notes: Optional[List[str]] = None
    ) -> StepTrace:
        duration_ms = (end_dt - start_dt).total_seconds() * 1000.0
        step = StepTrace(
            step_number=step_number,
            step_name=step_name,
            component_type=component_type,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            duration_ms=round(duration_ms, 2),
            status=status,
            inputs=inputs,
            outputs=outputs,
            notes=notes or []
        )
        self.steps.append(step)
        return step
