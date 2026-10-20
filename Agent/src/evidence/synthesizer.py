"""
Step 13 - Synthesizer: Executive Response Generator (§B12).
Synthesizes clear, executive-grade answers strictly from the Evidence Ledger,
analyst tables, and verified executed queries.
"""
from typing import Dict, Any, List, Optional
from src.models.schemas import FinalAnswer, EvidenceLedger, AdvisorRecommendation, SQLCandidate, ExecutionResult
from src.config import CAUSAL_BOUNDARY_NOTE


class Synthesizer:
    """Generates complete, evidence-backed executive responses."""

    def synthesize(
        self,
        trace_id: str,
        question: str,
        route: str,
        route_reason: str,
        ledger: EvidenceLedger,
        analyst_outputs: Dict[str, Any],
        executed_sql: Optional[SQLCandidate],
        execution_result: Optional[ExecutionResult],
        recommendations: List[AdvisorRecommendation],
        caveats: List[str],
        has_causal_analysis: bool = False,
        run_metrics: Optional[Dict[str, Any]] = None
    ) -> FinalAnswer:
        """
        Assembles the comprehensive FinalAnswer contract defined in §B12.
        """
        # Determine status
        status = "success"

        # Build Scope
        scope = {
            "question": question,
            "route": route,
            "database": "brazil_ecommerce.db (DuckDB read-only)"
        }

        # Build Conclusion from ledger and analyst summaries
        analyst_summaries = []
        if "AnomalyAnalyst" in analyst_outputs:
            analyst_summaries.append(analyst_outputs["AnomalyAnalyst"].summary)
        if "DriverAnalyst" in analyst_outputs:
            analyst_summaries.append(analyst_outputs["DriverAnalyst"].summary)
        if "RiskAnalyst" in analyst_outputs:
            analyst_summaries.append(analyst_outputs["RiskAnalyst"].summary)

        # Try Gemini LLM synthesis if active and available
        gemini_conclusion = self._synthesize_with_gemini(question, ledger.claims, analyst_summaries)
        if gemini_conclusion:
            conclusion_text = gemini_conclusion
        else:
            conclusions = list(analyst_summaries)
            if not conclusions and execution_result and execution_result.success:
                row_count = execution_result.row_count
                rows = execution_result.rows
                cols = execution_result.columns
                if row_count == 1 and rows and len(rows[0]) == 1 and cols[0] == "metric_value":
                    val = rows[0][0]
                    if val is None or val == 0:
                        conclusions.append("No transactions recorded for the requested period (Total: R$ 0.00). Note: Warehouse data covers September 2016 through October 2018.")
                    else:
                        conclusions.append(f"Grounded warehouse query completed successfully. Total calculated value is R$ {val:,.2f}.")
                else:
                    conclusions.append(f"Grounded warehouse query completed successfully returning {row_count} records.")

            conclusion_text = " ".join(conclusions) if conclusions else "Analysis completed based on recorded evidence."

        # Attach causal boundary note if causal analysis was performed
        causal_boundary = CAUSAL_BOUNDARY_NOTE if has_causal_analysis else None

        sql_text = executed_sql.sql if executed_sql else None
        sql_timing = execution_result.execution_time_ms if execution_result else None
        row_cnt = execution_result.row_count if execution_result else None
        query_cols = execution_result.columns if execution_result else None
        query_rows = execution_result.rows if execution_result else None

        return FinalAnswer(
            trace_id=trace_id,
            route=route,
            route_reason=route_reason,
            status=status,
            conclusion=conclusion_text,
            scope=scope,
            claims=ledger.claims,
            executed_sql=sql_text,
            sql_execution_time_ms=sql_timing,
            query_row_count=row_cnt,
            query_columns=query_cols,
            query_rows=query_rows,
            recommendations=recommendations,
            caveats=caveats,
            causal_boundary=causal_boundary,
            run_metrics=run_metrics or {}
        )

    def _synthesize_with_gemini(
        self,
        question: str,
        claims: List[Any],
        analyst_summaries: List[str]
    ) -> Optional[str]:
        """Calls Unified LLM client (qwen2.5-coder:latest / Gemini) to produce executive synthesis grounded in evidence."""
        try:
            from src.llm.client import get_llm_client
            client = get_llm_client()
            if not client.is_available():
                return None

            claims_text = "\n".join(f"- [Grade {c.evidence_grade}]: {c.text}" for c in claims)
            analyst_text = "\n".join(analyst_summaries) if analyst_summaries else "None"

            system_instruction = (
                "You are an Executive Data Science Synthesizer for an enterprise e-commerce platform.\n"
                "Write a clear, authoritative, 2-3 sentence executive summary answering the business question.\n"
                "CRITICAL RULES:\n"
                "1. Strictly cite ONLY facts and numbers present in the verified Evidence Ledger claims below.\n"
                "2. Never hallucinate numbers, dates, or causes not provided.\n"
                "3. If evidence does not prove causation, use correlational language ('associated with', 'observed during').\n"
                "4. Return plain text only."
            )

            prompt = (
                f"Question: \"{question}\"\n\n"
                f"Verified Evidence Claims:\n{claims_text}\n\n"
                f"Analyst Summaries:\n{analyst_text}\n\n"
                "Executive Summary:"
            )

            text = client.generate_text(prompt=prompt, system_instruction=system_instruction)
            return text.strip() if text else None
        except Exception:
            return None

