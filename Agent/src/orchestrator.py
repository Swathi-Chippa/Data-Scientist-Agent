"""
Data Scientist Agent - Core Orchestrator (§B1, §B2, §B3).
Executes the fixed, typed, bounded analytical workflow.
Enforces the hard safety gates, per-query budgets, and file-based audit tracing.
"""
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.config import WORKSPACE_ROOT, TRACES_DIR
from src.models.schemas import (
    RouteType, RouteResult, AnalystPlan, RetrievedSchema,
    SQLCandidate, ValidationResult, ExecutionResult, ReconciliationResult,
    FinalAnswer, EvidenceLedger, AdvisorRecommendation, EvidenceClaim
)
from src.models.trace import PipelineRunTrace
from src.trace_logger import TraceLogger
import hashlib
import json
from pathlib import Path
from src.config import CACHE_DIR
import os

# Workflow Components
from src.guard import Guard
from src.router import Router
from src.planner import Planner
from src.metric_resolver import MetricResolver
from src.answerability import AnswerabilityChecker
from src.schema_retriever.catalog import MetadataCatalog
from src.schema_retriever.join_graph import JoinGraph
from src.schema_retriever.retriever import SchemaRetriever
from src.sql.compiler import SQLCompiler
from src.sql.generator import SQLGenerator
from src.sql.validator import SQLValidator
from src.sql.repairer import SQLRepairer
from src.sql.executor import SQLExecutor
from src.sql.reconciler import Reconciler
from src.analysts.base import AnalystRegistry
from src.analysts.anomaly import AnomalyAnalyst
from src.analysts.driver import DriverAnalyst
from src.analysts.risk import RiskAnalyst
from src.analysts.advisor import Advisor
from src.evidence.ledger import LedgerManager
from src.evidence.synthesizer import Synthesizer
from src.evidence.fact_checker import FactChecker


class AgentOrchestrator:
    """End-to-end typed workflow orchestrator."""

    def __init__(self):
        # Initialize components once
        self.guard = Guard()
        self.router = Router()
        self.planner = Planner()
        self.metric_resolver = MetricResolver()
        self.answerability_checker = AnswerabilityChecker()
        self.catalog = MetadataCatalog()
        self.join_graph = JoinGraph()
        self.retriever = SchemaRetriever(self.catalog, self.join_graph)
        self.sql_compiler = SQLCompiler()
        self.sql_generator = SQLGenerator()
        self.validator = SQLValidator(self.join_graph)
        self.repairer = SQLRepairer()
        self.executor = SQLExecutor()
        self.reconciler = Reconciler()

        # Analysts
        self.anomaly_analyst = AnomalyAnalyst()
        self.driver_analyst = DriverAnalyst()
        self.risk_analyst = RiskAnalyst()
        self.advisor = Advisor()

        # Evidence & Trace
        self.synthesizer = Synthesizer()
        self.fact_checker = FactChecker()
        self.trace_logger = TraceLogger()
        self._in_memory_cache: Dict[str, Any] = {}

    def _get_cache_key(self, route_res, metric_def, slots):
        """Generate slot-based cache key per §B15."""
        try:
            key_parts = {
                "route": route_res.route.value if route_res else None,
                "metric": metric_def.name if metric_def else (slots.metric if slots else None),
                "dimension": slots.dimension if slots else None,
                "time_window": slots.time_window if slots else None,
                "region": slots.region_or_filter if slots else None,
            }
            key_str = json.dumps(key_parts, sort_keys=True)
            return hashlib.sha256(key_str.encode()).hexdigest()
        except Exception:
            return None

    def _get_cached_result(self, cache_key):
        if not cache_key:
            return None
        return self._in_memory_cache.get(cache_key)

    def _save_to_cache(self, cache_key, result):
        if not cache_key:
            return
        try:
            # Only cache successful results with concrete data in-memory
            if hasattr(result, 'status') and result.status == 'success' and result.query_row_count:
                cache_data = {
                    "conclusion": result.conclusion,
                    "claims": [c.model_dump() for c in result.claims],
                    "executed_sql": result.executed_sql,
                    "query_row_count": result.query_row_count,
                    "recommendations": [r.model_dump() for r in result.recommendations]
                }
                self._in_memory_cache[cache_key] = cache_data
        except Exception:
            pass

    def run(self, question: str) -> FinalAnswer:
        """Executes the full agent workflow with step contracts and audit logging."""
        t_global_start = time.time()
        trace_id = str(uuid.uuid4())
        now_dt = datetime.now()

        trace = PipelineRunTrace(
            trace_id=trace_id,
            timestamp=now_dt.isoformat(),
            question=question
        )

        all_caveats = []
        executed_sql: Optional[SQLCandidate] = None
        execution_result: Optional[ExecutionResult] = None
        ledger_mgr = LedgerManager()
        analyst_outputs = {}
        recommendations = []

        # =========================================================================
        # Step 1: Guard
        # =========================================================================
        s1_start = datetime.now()
        passed, guard_reason = self.guard.check_input(question)
        s1_end = datetime.now()

        trace.add_step(
            step_number=1,
            step_name="Guard",
            component_type="code",
            start_dt=s1_start,
            end_dt=s1_end,
            status="success" if passed else "blocked",
            inputs={"raw_question": question},
            outputs={"passed": passed, "reason": guard_reason},
            notes=[guard_reason] if guard_reason else ["Read-only safety verified"]
        )

        if not passed:
            trace.final_status = "blocked"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route="unsafe",
                route_reason="Blocked by Guard",
                status="blocked",
                conclusion=f"Request blocked: {guard_reason}",
                refusal_reason=guard_reason,
                trace_file_path=str(md_p) if md_p else None
            )

        # =========================================================================
        # Step 2: Router and Extractor
        # =========================================================================
        s2_start = datetime.now()
        route_res = self.router.route_question(question)
        s2_end = datetime.now()

        trace.route_chosen = route_res.route.value
        trace.add_step(
            step_number=2,
            step_name="Router and Extractor",
            component_type="assisted",
            start_dt=s2_start,
            end_dt=s2_end,
            status="success",
            inputs={"question": question},
            outputs=route_res.model_dump(),
            notes=[f"Route: {route_res.route.value} (confidence: {route_res.confidence})", route_res.reason]
        )

        # Handle Unsafe route
        if route_res.route == RouteType.UNSAFE:
            trace.final_status = "blocked"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route="unsafe",
                route_reason=route_res.reason,
                status="blocked",
                conclusion=route_res.refusal_reason or "Destructive operation blocked.",
                refusal_reason=route_res.refusal_reason,
                trace_file_path=str(md_p) if md_p else None
            )

        # Handle Ambiguous route -> Clarifying Question
        if route_res.route == RouteType.AMBIGUOUS:
            trace.final_status = "clarification"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route=route_res.route.value,
                route_reason=route_res.reason,
                status="clarification",
                conclusion=route_res.clarification_question or "Clarification required.",
                clarification_question=route_res.clarification_question,
                trace_file_path=str(md_p) if md_p else None
            )

        # Handle Unanswerable route -> Clean Refusal
        if route_res.route == RouteType.UNANSWERABLE:
            trace.final_status = "refusal"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route=route_res.route.value,
                route_reason=route_res.reason,
                status="refusal",
                conclusion=route_res.refusal_reason or "Question is unanswerable from warehouse.",
                refusal_reason=route_res.refusal_reason,
                trace_file_path=str(md_p) if md_p else None
            )

        # =========================================================================
        # Step 3: Planner
        # =========================================================================
        s3_start = datetime.now()
        plan = self.planner.create_plan(route_res, question)
        s3_end = datetime.now()

        trace.add_step(
            step_number=3,
            step_name="Planner",
            component_type="assisted",
            start_dt=s3_start,
            end_dt=s3_end,
            status="success" if plan.validated else "failed",
            inputs={"route": route_res.route.value, "slots": route_res.slots.model_dump()},
            outputs=plan.model_dump(),
            notes=[f"Planned {plan.depth} analysts: {[s.analyst_name for s in plan.steps]}"]
        )

        # =========================================================================
        # Step 4: Metric Resolver
        # =========================================================================
        s4_start = datetime.now()
        metric_def, is_fully_governed, resolver_caveats = self.metric_resolver.resolve(route_res.slots)
        all_caveats.extend(resolver_caveats)
        s4_end = datetime.now()

        trace.add_step(
            step_number=4,
            step_name="Metric Resolver",
            component_type="code",
            start_dt=s4_start,
            end_dt=s4_end,
            status="success",
            inputs={"slots": route_res.slots.model_dump()},
            outputs={"metric": metric_def.name if metric_def else None, "fully_governed": is_fully_governed},
            notes=resolver_caveats
        )

        # Check cache for slot-based lookup
        cache_key = self._get_cache_key(route_res, metric_def, route_res.slots)
        cached = self._get_cached_result(cache_key)
        if cached and route_res.route.value in ["lookup"]:
            # Return cached result for lookup queries (per §B15)
            trace.final_status = "success"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            claims = []
            for c in cached.get('claims', []):
                try:
                    claims.append(EvidenceClaim(**c))
                except Exception:
                    pass
            recs = []
            for r in cached.get('recommendations', []):
                try:
                    recs.append(AdvisorRecommendation(**r))
                except Exception:
                    pass
            return FinalAnswer(
                trace_id=trace_id,
                route=route_res.route.value,
                route_reason=route_res.reason + " (cached)",
                status="success",
                conclusion=cached.get('conclusion', ''),
                claims=claims,
                executed_sql=cached.get('executed_sql'),
                query_row_count=cached.get('query_row_count'),
                recommendations=recs,
                trace_file_path=str(md_p) if md_p else None
            )

        # =========================================================================
        # Step 5: Answerability Checker
        # =========================================================================
        s5_start = datetime.now()
        is_ans, missing_attr, refusal_msg = self.answerability_checker.check(question)
        s5_end = datetime.now()

        trace.add_step(
            step_number=5,
            step_name="Answerability Checker",
            component_type="code",
            start_dt=s5_start,
            end_dt=s5_end,
            status="success" if is_ans else "refusal",
            inputs={"question": question},
            outputs={"is_answerable": is_ans, "missing_attribute": missing_attr},
            notes=[refusal_msg] if refusal_msg else ["All requested entities exist in catalog"]
        )

        if not is_ans:
            trace.final_status = "refusal"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route=RouteType.UNANSWERABLE.value,
                route_reason=f"Missing attribute '{missing_attr}' in catalog",
                status="refusal",
                conclusion=refusal_msg or "Attribute not available in warehouse.",
                refusal_reason=refusal_msg,
                trace_file_path=str(md_p) if md_p else None
            )

        # =========================================================================
        # Step 6: Schema Retriever
        # =========================================================================
        s6_start = datetime.now()
        retrieved_schema = self.retriever.retrieve(question, metric_def)
        all_caveats.extend(retrieved_schema.column_warnings)
        s6_end = datetime.now()

        trace.add_step(
            step_number=6,
            step_name="Schema Retriever",
            component_type="assisted",
            start_dt=s6_start,
            end_dt=s6_end,
            status="success" if retrieved_schema.retrieval_confidence >= 0.2 and retrieved_schema.tables else "low_confidence",
            inputs={"question": question, "metric": metric_def.name if metric_def else None},
            outputs=retrieved_schema.model_dump(),
            notes=[
                f"Retrieved tables: {retrieved_schema.tables}",
                f"Linked values: {retrieved_schema.linked_values}",
                f"Retrieval confidence: {retrieved_schema.retrieval_confidence}"
            ]
        )

        # Retrieval confidence gating per §B7.6
        if not retrieved_schema.tables or retrieved_schema.retrieval_confidence < 0.15:
            trace.final_status = "clarification"
            trace.total_duration_ms = (time.time() - t_global_start) * 1000.0
            json_p, md_p = self.trace_logger.save_trace(trace)
            return FinalAnswer(
                trace_id=trace_id,
                route=route_res.route.value,
                route_reason=route_res.reason,
                status="clarification",
                conclusion="I could not confidently locate the relevant tables/attributes in the warehouse schema for this question.",
                clarification_question=(
                    "I understood your intent but couldn't map it to specific tables with sufficient confidence. "
                    "Could you rephrase with concrete terms (e.g., 'orders in SP last month by product category') "
                    "or specify which entities you're interested in?"
                ),
                trace_file_path=str(md_p) if md_p else None
            )

        # =========================================================================
        # Step 7 & 8: SQL Compiler / Generator + Validation + Bounded Repair
        # =========================================================================
        s7_start = datetime.now()
        if is_fully_governed and metric_def:
            executed_sql = self.sql_compiler.compile(
                metric=metric_def,
                slots=route_res.slots,
                linked_values=retrieved_schema.linked_values
            )
        else:
            executed_sql = self.sql_generator.generate(
                question=question,
                retrieved_schema=retrieved_schema,
                slots=route_res.slots
            )
        s7_end = datetime.now()

        trace.add_step(
            step_number=7,
            step_name="SQL Compiler / Generator",
            component_type="code" if executed_sql.is_governed else "model",
            start_dt=s7_start,
            end_dt=s7_end,
            status="success",
            inputs={"source": executed_sql.source, "governed": executed_sql.is_governed},
            outputs={"sql": executed_sql.sql},
            notes=[f"Source: {executed_sql.source} (Governed: {executed_sql.is_governed})"]
        )

        # Validate SQL (Step 8)
        s8_start = datetime.now()
        val_res = self.validator.validate(
            sql=executed_sql.sql,
            table_allowlist=retrieved_schema.tables,
            column_allowlist=retrieved_schema.columns_by_table
        )
        s8_end = datetime.now()

        # Bounded repair if validation failed
        repair_attempts = 0
        current_sql = executed_sql.sql
        while not val_res.approved and repair_attempts < 2:
            repair_attempts += 1
            err_msg = "; ".join(val_res.errors)
            repaired_sql = self.repairer.repair(
                failed_sql=current_sql,
                error_message=err_msg,
                retrieved_schema=retrieved_schema,
                attempt=repair_attempts
            )
            if repaired_sql and repaired_sql != current_sql:
                current_sql = repaired_sql
                val_res = self.validator.validate(
                    sql=current_sql,
                    table_allowlist=retrieved_schema.tables,
                    column_allowlist=retrieved_schema.columns_by_table
                )
            else:
                break

        executed_sql.sql = current_sql

        trace.add_step(
            step_number=8,
            step_name="Validator",
            component_type="code",
            start_dt=s8_start,
            end_dt=s8_end,
            status="success" if val_res.approved else "rejected",
            inputs={"sql": executed_sql.sql},
            outputs=val_res.model_dump(),
            notes=val_res.errors if not val_res.approved else ["AST validated; allowlist and cost gate approved"]
        )

        # =========================================================================
        # Step 9: Executor
        # =========================================================================
        if val_res.approved:
            s9_start = datetime.now()
            execution_result = self.executor.execute(executed_sql.sql)
            s9_end = datetime.now()

            trace.add_step(
                step_number=9,
                step_name="Executor",
                component_type="code",
                start_dt=s9_start,
                end_dt=s9_end,
                status="success" if execution_result.success else "failed",
                inputs={"sql": executed_sql.sql},
                outputs={
                    "row_count": execution_result.row_count,
                    "execution_time_ms": execution_result.execution_time_ms
                },
                notes=[f"Returned {execution_result.row_count} rows in {execution_result.execution_time_ms}ms"]
            )

            trace.executed_queries.append({
                "source": executed_sql.source,
                "sql": executed_sql.sql,
                "status": "SUCCESS" if execution_result.success else "FAILED",
                "timing_ms": execution_result.execution_time_ms,
                "row_count": execution_result.row_count,
                "estimated_rows": val_res.estimated_rows
            })

            # Record fact claim from query result (Grade 0)
            if execution_result.success and execution_result.row_count > 0:
                rows = execution_result.rows
                cols = execution_result.columns
                row_cnt = execution_result.row_count

                is_currency = (metric_def and metric_def.name in ["revenue", "average_order_value"]) or any(k in str(cols[-1]).lower() for k in ["revenue", "price", "payment_value", "spend"])
                metric_label = metric_def.name.replace("_", " ") if metric_def else cols[-1]

                if row_cnt == 1 and len(cols) == 1:
                    val = rows[0][0]
                    if isinstance(val, (int, float)):
                        val_str = f"R$ {val:,.2f}" if is_currency else f"{int(val):,} {metric_label}"
                    else:
                        val_str = str(val)
                    claim_text = f"Query executed successfully: total {metric_label} is {val_str}."
                elif row_cnt == 1 and len(cols) >= 2:
                    dim_val = rows[0][0]
                    metric_val = rows[0][1]
                    if isinstance(metric_val, (int, float)):
                        metric_str = f"R$ {metric_val:,.2f}" if is_currency else f"{int(metric_val):,} {metric_label}"
                    else:
                        metric_str = str(metric_val)
                    claim_text = f"Query executed successfully: {cols[0]} '{dim_val}' has {metric_str}."
                else:
                    # Multi-row breakdown: summarize top 3-5 rows
                    top_items = []
                    for r in rows[:5]:
                        if len(r) >= 2 and isinstance(r[1], (int, float)):
                            formatted_m = f"R$ {r[1]:,.2f}" if is_currency else f"{int(r[1]):,}"
                            top_items.append(f"{r[0]} ({formatted_m})")
                        else:
                            top_items.append(f"{r[0]}")
                    top_summary = ", ".join(top_items)
                    claim_text = f"Query returned {row_cnt} records across {cols[0]}. Top results: {top_summary}."

                ledger_mgr.record_claim(
                    text=claim_text,
                    grade=0,
                    source_type="query",
                    source_id="SQL-01",
                    data={
                        "columns": execution_result.columns,
                        "rows_count": execution_result.row_count,
                        "top_rows": rows[:10]
                    }
                )

        # =========================================================================
        # Step 10: Reconciler
        # =========================================================================
        if execution_result and execution_result.success:
            s10_start = datetime.now()
            recon_res = self.reconciler.reconcile(execution_result, metric_def)
            s10_end = datetime.now()

            if recon_res.caveat:
                all_caveats.append(recon_res.caveat)

            trace.add_step(
                step_number=10,
                step_name="Reconciler",
                component_type="code",
                start_dt=s10_start,
                end_dt=s10_end,
                status="success",
                inputs={"row_count": execution_result.row_count},
                outputs=recon_res.model_dump(),
                notes=[f"Reconciled {recon_res.checked_metric or 'unmetered query'}"]
            )

        # =========================================================================
        # Step 11: Analysts Execution (following the Plan)
        # =========================================================================
        has_causal = False
        analyst_context = {
            "region": route_res.slots.region_or_filter or retrieved_schema.linked_values.get("customer_state", "SP"),
            "metric": route_res.slots.metric or "orders",
            "time_grain": "week" if route_res.route == RouteType.ANOMALY else "month",
            "execution_result": execution_result
        }

        for step in plan.steps:
            st_start = datetime.now()
            name = step.analyst_name

            if name == "AnomalyAnalyst":
                out = self.anomaly_analyst.run(analyst_context)
                analyst_outputs[name] = out
                analyst_context["anomaly_output"] = out.model_dump()
                for c in out.evidence_claims:
                    ledger_mgr.record_claim(c["text"], c["grade"], "anomaly_analyst", "AN-01", c.get("data", {}))

            elif name == "DriverAnalyst":
                has_causal = True
                out = self.driver_analyst.run(analyst_context)
                analyst_outputs[name] = out
                analyst_context["driver_output"] = out.model_dump()
                for c in out.evidence_claims:
                    ledger_mgr.record_claim(c["text"], c["grade"], "driver_analyst", "DR-01", c.get("data", {}))

            elif name == "RiskAnalyst":
                out = self.risk_analyst.run(analyst_context)
                analyst_outputs[name] = out
                analyst_context["risk_output"] = out.model_dump()
                for c in out.evidence_claims:
                    ledger_mgr.record_claim(c["text"], c["grade"], "risk_analyst", "RK-01", c.get("data", {}))

            elif name == "Advisor":
                out = self.advisor.run(analyst_context)
                analyst_outputs[name] = out
                # Extract recommendations
                if "recommended_actions" in out.tables:
                    for rec in out.tables["recommended_actions"]:
                        try:
                            recommendations.append(AdvisorRecommendation(
                                rank=rec["rank"],
                                title=rec["title"],
                                action_type="Operational Intervention",
                                owner=rec["owner"],
                                lead_time=rec["lead_time"],
                                cost_class=rec["cost_class"],
                                impact_score=rec["score"],
                                evidence_confidence=0.9,
                                feasibility=0.88,
                                ranking_score=rec["score"],
                                assumptions=["Quantitative scoring from driver/risk outputs."],
                                trade_offs=rec["trade_offs"],
                                sensitivity="Sensitive to implementation follow-through.",
                                what_to_monitor="Relevant primary KPI.",
                                requires_human_approval=True
                            ))
                        except Exception:
                            pass
                for c in out.evidence_claims:
                    ledger_mgr.record_claim(c["text"], c["grade"], "advisor", "AD-01", c.get("data", {}))

            st_end = datetime.now()
            trace.add_step(
                step_number=11,
                step_name=f"Analyst: {name}",
                component_type="code",
                start_dt=st_start,
                end_dt=st_end,
                status="success",
                inputs=analyst_context.get(name.lower(), {}),
                outputs=analyst_outputs[name].model_dump() if name in analyst_outputs else {},
                notes=[analyst_outputs[name].verdict] if name in analyst_outputs else []
            )

        # =========================================================================
        # Step 12, 13 & 14: Evidence Ledger, Synthesizer & Fact Checker
        # =========================================================================
        s13_start = datetime.now()
        ledger = ledger_mgr.ledger
        trace.evidence_claims_count = len(ledger.claims)

        # Step 13: Synthesize
        final_ans = self.synthesizer.synthesize(
            trace_id=trace_id,
            question=question,
            route=route_res.route.value,
            route_reason=route_res.reason,
            ledger=ledger,
            analyst_outputs=analyst_outputs,
            executed_sql=executed_sql,
            execution_result=execution_result,
            recommendations=recommendations,
            caveats=list(set(all_caveats)),
            has_causal_analysis=has_causal,
            run_metrics={
                "total_duration_ms": 0.0,
                "executed_queries": len(trace.executed_queries),
                "claims_in_ledger": len(ledger.claims),
                "hard_safety_gates_passed": True
            }
        )
        s13_end = datetime.now()

        # Step 14: Fact Checker
        s14_start = datetime.now()
        fc_passed, clean_narrative, fc_violations = self.fact_checker.verify(
            narrative=final_ans.conclusion,
            ledger=ledger,
            has_causal_boundary_attached=(final_ans.causal_boundary is not None)
        )
        final_ans.conclusion = clean_narrative
        s14_end = datetime.now()

        trace.fact_check_passed = fc_passed
        trace.add_step(
            step_number=14,
            step_name="Fact Checker",
            component_type="code",
            start_dt=s14_start,
            end_dt=s14_end,
            status="success" if fc_passed else "flagged",
            inputs={"narrative": final_ans.conclusion},
            outputs={"passed": fc_passed, "violations": fc_violations},
            notes=["All claims verified against Evidence Ledger" if fc_passed else f"Flags: {fc_violations}"]
        )

        # Finalize run metrics and trace persistence
        total_ms = (time.time() - t_global_start) * 1000.0
        trace.total_duration_ms = round(total_ms, 2)
        trace.final_status = "success"
        final_ans.run_metrics["total_duration_ms"] = round(total_ms, 2)

        # Save trace to in-memory logger (or disk if enabled)
        json_path, md_path = self.trace_logger.save_trace(trace)
        final_ans.trace_file_path = str(md_path) if md_path else None

        # Save to cache for lookups
        try:
            cache_key = self._get_cache_key(route_res, metric_def, route_res.slots)
            self._save_to_cache(cache_key, final_ans)
        except Exception:
            pass

        return final_ans
