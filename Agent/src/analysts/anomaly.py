"""Legacy wrapper for the pure B10.0/B10.1 anomaly core."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src.analysts.base import AnalystOutput, BaseAnalyst
from src.analysts.core.anomaly import run_anomaly
from src.analysts.core.params import AnomalyParams, DQParams
from src.config import DB_PATH
from src.analysts.fetchers_olist import UnknownUnitError, fetch_weekly_orders
from src.analysts.legacy_base import legacy_output_from_v2

# TEMPORARY, Olist-specific: starts at the first sustained >=30-event run
# used by the legacy data-quality window. BE-1 table supply will replace it.
OLIST_ANALYSIS_START = "2017-01-16"  # temporary, Olist-specific


class AnomalyAnalyst(BaseAnalyst):
    """Thin compatibility wrapper; all analysis lives in the pure core."""

    def __init__(self, db_path: str = DB_PATH):
        super().__init__(name="AnomalyAnalyst")
        self.db_path = db_path

    @staticmethod
    def _insufficient(name: str, caveat: str) -> AnalystOutput:
        return AnalystOutput(analyst_name=name, status="insufficient_evidence", verdict="", summary="", caveats=[caveat])

    def run(self, context: Dict[str, Any]) -> AnalystOutput:
        defaults = {"region": "SP", "metric": "orders", "time_grain": "week"}
        region = context.get("region") or context.get("region_or_filter") or defaults["region"]
        metric = context.get("metric") or defaults["metric"]
        grain = context.get("time_grain") or defaults["time_grain"]
        try:
            series, metadata = fetch_weekly_orders(units=None, period_start=OLIST_ANALYSIS_START, period_end=None, grain=grain)
            if not isinstance(region, str) or region not in set(series.get("unit", [])):
                raise UnknownUnitError(f"Unknown customer_state value: {region!r}")
        except UnknownUnitError:
            return self._insufficient(self.name, f"Region '{str(region)[:40]}' is not in the warehouse.")
        except ValueError:
            return self._insufficient(self.name, f"Time grain '{str(grain)[:40]}' is not supported.")

        # static historical dataset: freshness is informational only.
        params = AnomalyParams(grain=grain, target_unit=str(region), dq=DQParams(grain=grain, expected_freshness_hours=None))
        core = run_anomaly(params, {"series": series, "load_meta": metadata, "as_of": datetime.now(timezone.utc)}, seed=int(context.get("seed", 0)))
        values = core.model_dump()

        def result_values(data: dict[str, Any]) -> dict[str, Any]:
            return data.get("result") or {}

        def verdict_template(data: dict[str, Any]) -> str:
            verdict = result_values(data).get("verdict", "")
            return {"unusual": "Statistically Unusual Anomaly Confirmed", "within_normal_range": "Within Normal Historical Variation", "data_issue_suspected": "Data Quality Issue Suspected", "insufficient_evidence": "Insufficient history"}.get(verdict, "")

        def summary_template(data: dict[str, Any]) -> str:
            result = result_values(data)
            if not result:
                return data.get("reason", "")
            peer = result.get("peer_rank") or {}
            peer_text = f" {peer['n_at_least_as_large']} of {peer['n_units']} states show a deviation at least this large (rank {peer['rank']})." if peer else ""
            screen_text = ""
            for flag in data.get("flags", []):
                if flag.startswith("screen_excluded_periods="):
                    periods = [item for item in flag.split("=", 1)[1].split(",") if item]
                    if periods:
                        screen_text = f" {len(periods)} earlier periods ({', '.join(periods)}) were excluded from the baseline as outliers."
            return f"{metric} in {region} ended at {result['actual']:.1f}; expected {result['expected']:.1f} with a {result['deviation_pct'] * 100.0:.1f}% deviation. Expected range: [{result['expected_range'][0]:.1f}, {result['expected_range'][1]:.1f}].{peer_text}{screen_text}"

        result = result_values(values)
        claim_templates = [(0, lambda data: f"{metric} in {region} measured {result_values(data).get('actual', 0.0):.1f} versus an expected {result_values(data).get('expected', 0.0):.1f}. {result_values(data).get('peer_rank', {}).get('n_at_least_as_large', 0)} of {result_values(data).get('peer_rank', {}).get('n_units', 0)} states show a deviation at least this large (rank {result_values(data).get('peer_rank', {}).get('rank', 0)}).", lambda data: {"actual": result_values(data).get("actual"), "expected": result_values(data).get("expected"), "peer_rank": result_values(data).get("peer_rank")})] if values.get("status") == "ok" else []
        metrics = {"region": region, "metric": metric, "median_baseline": result.get("expected"), "expected": result.get("expected"), "actual": result.get("actual"), "deviation_pct": result.get("deviation_pct"), "expected_range": result.get("expected_range"), "robust_score": result.get("robust_score"), "history_periods_used": result.get("history_periods_used"), "peer_rank": result.get("peer_rank"), "correction_used": result.get("correction_used"), "persistence": result.get("persistence"), "change_point": result.get("change_point"), "data_quality": result.get("data_quality")} if result else {}
        target_series = series[series["unit"].astype(str) == str(region)] if "unit" in series.columns else series
        tables = {"time_series": target_series.tail(12).to_dict(orient="records")} if not target_series.empty else {}
        return legacy_output_from_v2(core, analyst_name=self.name, verdict_template=verdict_template, summary_template=summary_template, claim_templates=claim_templates, metrics=metrics, tables=tables, assumptions=["The pure anomaly core excludes incomplete boundary periods before scoring."], caveats=[f"Excluded periods are recorded by the Data Quality Gate: {values.get('flags', [])}"])
