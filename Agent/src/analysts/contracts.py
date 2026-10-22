"""Typed AN-1 analyst contracts (Interfaces.md sections 4 and 9).

The V2 suffix is deliberately limited to Python names.  JSON Schema titles use
the names shared with FE-1 and BE-1 so the serialized contract remains stable.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Shared permissive envelope for fixture metadata and forward compatibility."""

    model_config = ConfigDict(extra="ignore")


class ColumnSpecV2(ContractModel):
    name: str
    type: str
    role: Literal["dimension", "measure", "time", "key", "label"]


class TableRefV2(ContractModel):
    model_config = ConfigDict(title="TableRef", extra="ignore")

    query_id: str
    columns: list[ColumnSpecV2]
    row_count: int = Field(ge=0)
    uri: str


class AnalystInputV2(ContractModel):
    model_config = ConfigDict(title="AnalystInput", extra="ignore")

    module: str
    params: dict[str, Any]
    tables: dict[str, TableRefV2]
    metric: Optional[str] = None
    run_id: str
    seed: int


class ArtifactRefV2(ContractModel):
    artifact_id: str
    kind: Literal["chart_data", "table", "model_card"]
    uri: str


T = TypeVar("T")


class AnalystOutputV2(ContractModel, Generic[T]):
    model_config = ConfigDict(title="AnalystOutput", extra="ignore")

    module: str
    status: Literal["ok", "insufficient_evidence"]
    reason: Optional[str] = None
    result: Optional[T] = None
    parameters: dict[str, Any]
    assumptions: list[str]
    sources: list[str]
    artifacts: list[ArtifactRefV2]
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reason_required_for_insufficient(self) -> "AnalystOutputV2[T]":
        if self.status == "insufficient_evidence" and not self.reason:
            raise ValueError("reason is required when status is insufficient_evidence")
        return self


class DQCheckV2(ContractModel):
    name: Literal["freshness", "period_completeness", "all_unit_drop", "definition_drift"]
    status: Literal["pass", "warn", "fail", "unknown"]
    detail: str


class DQResultV2(ContractModel):
    model_config = ConfigDict(title="DQResult", extra="ignore")

    passed: bool
    checks: list[DQCheckV2]


class PeerRankV2(ContractModel):
    rank: int = Field(ge=1)
    n_units: int = Field(ge=1)
    n_at_least_as_large: int = Field(ge=0)


class ChangePointV2(ContractModel):
    method: str
    location: Optional[str] = None
    range: Optional[list[str]] = None


class AnomalyResultV2(ContractModel):
    model_config = ConfigDict(title="AnomalyResult", extra="ignore")

    verdict: Literal[
        "unusual",
        "within_normal_range",
        "insufficient_evidence",
        "data_issue_suspected",
    ]
    window: str
    actual: float
    expected: float
    expected_range: tuple[float, float]
    deviation_pct: float
    deviation_abs: float
    robust_score: float
    persistence: Literal["one_off", "sustained", "drift", "unknown"]
    level: float = Field(ge=0, le=1)
    correction_used: Optional[str] = None
    calendar_effects: list[str]
    baseline_kind: Literal["seasonal_stl", "trailing_robust", "none"]
    history_periods_used: int = Field(ge=0)
    fallback_reason: Optional[str] = None
    peer_rank: PeerRankV2
    change_point: Optional[ChangePointV2] = None
    data_quality: DQResultV2


class ContributionV2(ContractModel):
    value: str
    baseline: float
    actual: float
    contribution: float
    share: Optional[float] = None
    interval: tuple[float, float]
    sample_size: int = Field(ge=0)
    unstable: bool


class DimensionContributionV2(ContractModel):
    dimension: str
    concentration: float = Field(ge=0, le=1)
    contributions: list[ContributionV2]


class PriceVolumeMixV2(ContractModel):
    volume: float
    price: float
    mix: float


class IndicatorTestV2(ContractModel):
    indicator: str
    lag: int
    effect_size: float
    p_adjusted: float = Field(ge=0, le=1)
    onset_not_later_than_metric: bool


class ComparisonGroupV2(ContractModel):
    did_estimate: float
    pretrend_p: float = Field(ge=0, le=1)
    placebo_rank: int = Field(ge=1)
    n_controls: int = Field(ge=0)
    limited_power: bool


class GradedClaimV2(ContractModel):
    claim_key: str
    grade: Literal[0, 1, 2, 3, 4]
    criteria_met: dict[str, bool]
    allowed_wording: str


class DriverResultV2(ContractModel):
    model_config = ConfigDict(title="DriverResult", extra="ignore")

    metric: str
    current_period: str
    comparison_period: str
    baseline_source: Literal[
        "anomaly_expected",
        "same_period_last_year",
        "previous_period_not_adjusted",
    ]
    total_change: float
    shares_shown: bool
    gross_positive: float
    gross_negative: float
    dimensions: list[DimensionContributionV2]
    reconciliation_error: float
    price_volume_mix: Optional[PriceVolumeMixV2] = None
    indicator_tests: list[IndicatorTestV2]
    comparison_group: Optional[ComparisonGroupV2] = None
    graded_claims: list[GradedClaimV2]
    data_needed_to_strengthen: list[str]
    candidates_examined: int = Field(ge=0)
    correction_used: Optional[str] = None


class RiskTargetV2(ContractModel):
    kind: Literal["churn", "second_purchase"]
    window_days: int = Field(ge=1)
    window_source: Literal["registry", "data_p90_gap"]
    cutoff: str
    population: str


class MetricWithIntervalV2(ContractModel):
    value: float
    interval: tuple[float, float]


class RiskMetricsV2(ContractModel):
    pr_auc: MetricWithIntervalV2
    prevalence: MetricWithIntervalV2
    roc_auc: MetricWithIntervalV2
    brier: MetricWithIntervalV2
    ece: MetricWithIntervalV2
    lift_at_k: dict[int, MetricWithIntervalV2]


class RiskSegmentV2(ContractModel):
    segment: str
    dims: dict[str, str]
    customers: int = Field(ge=0)
    mean_risk: float = Field(ge=0, le=1)
    value_at_risk: float = Field(ge=0)
    interval: tuple[float, float]
    observed_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)
    predicted_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)


class RiskDriverV2(ContractModel):
    feature: str
    importance: float


class RiskResultV2(ContractModel):
    model_config = ConfigDict(title="RiskResult", extra="ignore")

    target: RiskTargetV2
    one_time_buyer_share: float = Field(ge=0, le=1)
    model_used: Literal["heuristic", "bgnbd", "logistic", "gradient_boosted"]
    metrics: RiskMetricsV2
    baselines_compared: list[str]
    champion_rule_met: bool
    segments: list[RiskSegmentV2]
    risk_drivers: list[RiskDriverV2]
    limits: list[str]
    exposure_note: Literal["ranked by exposure, not by expected response"] = (
        "ranked by exposure, not by expected response"
    )


class FeasibilityV2(ContractModel):
    lead_time: str
    cost_class: str
    owner: str


class ImpactRangeV2(ContractModel):
    low: float
    base: float
    high: float


class MaxAddressableImpactV2(ContractModel):
    value: float
    interval: tuple[float, float]


class AdvisorOptionV2(ContractModel):
    action_id: str
    title: str
    kind: Literal["intervention", "information_gathering"]
    rank: int = Field(ge=1)
    max_addressable_impact: MaxAddressableImpactV2
    recovery_fraction: ImpactRangeV2
    impact: ImpactRangeV2
    evidence_grade: Literal[0, 1, 2, 3, 4]
    feasibility: FeasibilityV2
    assumptions: list[str]
    trade_offs: list[str]
    sensitivity: str
    monitor: list[str]
    data_that_would_change_ranking: list[str]


class AdvisorInputV2(ContractModel):
    model_config = ConfigDict(title="AdvisorInput", extra="ignore")

    options: list[AdvisorOptionV2]
    constraints: dict[str, Any] = Field(default_factory=dict)


class AdvisorOutputV2(ContractModel):
    model_config = ConfigDict(title="AdvisorOutput", extra="ignore")

    module: Literal["advisor"] = "advisor"
    status: Literal["ok", "insufficient_evidence"]
    reason: Optional[str] = None
    options: list[AdvisorOptionV2]
    assumptions: list[str]
    sources: list[str]
    artifacts: list[ArtifactRefV2]
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reason_required_for_insufficient(self) -> "AdvisorOutputV2":
        if self.status == "insufficient_evidence" and not self.reason:
            raise ValueError("reason is required when status is insufficient_evidence")
        return self

