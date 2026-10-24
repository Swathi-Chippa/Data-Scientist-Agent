"""Compatibility wrapper from V2 analyst results to the legacy output contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from src.analysts.base import AnalystOutput


# TEMPORARY: reproduces v1.0 behaviour; removed when the analyst is rewritten
# in P4-P6. Values are copied from the original analyst SQL/defaults.
LEGACY_WINDOWS = {
    "anomaly": {
        "period_start": "2017-06-01",
        "period_end": "2018-08-25",
        "defaults": {"region": "SP", "metric": "orders", "time_grain": "week"},
    },
    "driver": {
        "defaults": {"region": "SP", "metric": "orders", "period_baseline": "2018-05", "period_current": "2018-06"},
    },
    "risk": {
        "period_start": None,
        "defaults": {"cutoff_date": "2018-03-01", "outcome_end_date": "2018-06-01"},
    },
}


def legacy_output_from_v2(
    result: Any,
    *,
    analyst_name: str,
    verdict_template: str | Callable[[Mapping[str, Any]], str],
    summary_template: str | Callable[[Mapping[str, Any]], str],
    claim_templates: list[tuple[int, str | Callable[[Mapping[str, Any]], str], str | Callable[[Mapping[str, Any]], str]]] | None = None,
    metrics: dict[str, Any] | None = None,
    tables: dict[str, list[dict[str, Any]]] | None = None,
    assumptions: list[str] | None = None,
    caveats: list[str] | None = None,
) -> AnalystOutput:
    """Map a V2 model/result to ``AnalystOutput`` without changing the V2 result.

    Templates receive computed result fields and must use placeholders or a
    callable; literal measured values do not belong in template text.  Claim
    data is copied from the supplied computed fields for ledger consumers.
    """
    values = result.model_dump() if hasattr(result, "model_dump") else dict(result)

    def render(template: str | Callable[[Mapping[str, Any]], str]) -> str:
        return template(values) if callable(template) else template.format(**values)

    claims: list[dict[str, Any]] = []
    for grade, text_template, data_template in claim_templates or []:
        data = data_template(values) if callable(data_template) else {"value": data_template.format(**values)}
        claims.append({"text": render(text_template), "grade": grade, "data": data})

    status = "success" if values.get("status") in {"ok", "success"} else "insufficient_evidence"
    reason = values.get("reason")
    return AnalystOutput(
        analyst_name=analyst_name,
        status=status,
        verdict=render(verdict_template),
        summary=render(summary_template) if status == "success" else (reason or render(summary_template)),
        metrics=metrics if metrics is not None else (values.get("result") or {}),
        tables=tables or {},
        assumptions=assumptions or values.get("assumptions", []),
        caveats=caveats or values.get("flags", []),
        evidence_claims=claims,
    )


# Descriptive alias for later prompt/analyst migrations.
map_v2_to_legacy = legacy_output_from_v2
