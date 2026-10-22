# Proposed AN-1 Contract Changes

PR description for Ganesh (Lead) and Abdul (FE-1) to approve under
`Product.md` 7.4. This PR adds the machine-readable analyst contract and
fixture surface described by `Interfaces.md` section 4 and `Product.md` 5.3.
The legacy `src/analysts/base.py::AnalystOutput` is intentionally unchanged.

## Summary

Add Pydantic V2 contracts, exported JSON Schemas, realistic JSON examples for
all analyst verdict/status branches, tiny Parquet input fixtures, and contract
tests. Python class names carry `V2`; JSON Schema titles retain the shared
names (`AnalystInput`, `AnalystOutput`, and result names) for FE-1/BE-1.

## Field and enum changes

| Contract | Change | Reason |
|---|---|---|
| `TableRef` | New Pydantic model with `query_id`, typed/role-labelled columns, `row_count`, and Parquet `uri`. | Gives BE-1 a stable provenance and table-loading reference. |
| `AnalystInput` | `metric` is optional; `seed` is required rather than optional. | Modules may receive an ungoverned/no-metric run, while reproducibility is mandatory. |
| `AnalystOutput` | New `flags[]`; `reason` is validated as required for `insufficient_evidence`. | Flags carry non-fatal caveats, and fail-closed behavior becomes machine-enforced. |
| `AnalystOutput` | Generic result is nullable for insufficient evidence. | A module can explain missing evidence without fabricating a result payload. |
| `DQResult` | New `passed` plus named checks for freshness, period completeness, all-unit drop, and definition drift. | Surfaces the revised-design data-quality gate to FE-1 and BE-1. |
| `AnomalyResult.verdict` | Adds `data_issue_suspected`. | Separates data-quality suspicion from statistical normality. |
| `AnomalyResult` | Adds `deviation_abs`, `level`, `history_periods_used`, `fallback_reason`, `peer_rank`, `change_point`, and `data_quality`. | Makes uncertainty, fallback behavior, peer context, change-point evidence, and DQ explicit. |
| `AnomalyResult` | `baseline_kind` uses `seasonal_stl`, `trailing_robust`, or `none`; `correction_used` is nullable. | Names the revised baseline choices and allows an uncorrected/insufficient path. |
| `DriverResult` | Adds `baseline_source`, `shares_shown`, `gross_positive`, and `gross_negative`. | Distinguishes baseline provenance and represents offsetting contributions without false shares. |
| `DriverResult.dimensions` | Replaces the flat `drivers[]` shape with dimension-level concentration and nested contributions. | Supports multiple decompositions and FE rendering of contribution tables. |
| `DriverResult` | Adds `indicator_tests`, optional `comparison_group`, `graded_claims.criteria_met`, `allowed_wording`, and `data_needed_to_strengthen`. | Carries revised statistical checks, comparison power, and B11 evidence discipline. |
| `DriverResult` | Contribution `share` is nullable. | Offset/negative contributions may be shown without a misleading normalized share. |
| `RiskResult.target` | Replaces `churn_definition` with `kind`, `window_days`, `window_source`, `cutoff`, and `population`. | Supports both churn and second-purchase branches and records how the window was chosen. |
| `RiskResult.model_used` | Adds `bgnbd`. | Exposes the revised-design customer-value baseline. |
| `RiskResult.metrics` | Adds 95% intervals to PR-AUC, prevalence, ROC-AUC, Brier, ECE, and lift at 5/10/20. | Makes uncertainty and contact-capacity comparisons explicit. |
| `RiskResult` | Adds `baselines_compared`, `champion_rule_met`, `dims`, customer counts, observed/predicted loss rates, `risk_drivers`, and `limits`. | Makes model comparison, segment definitions, calibration context, and limitations consumable. |
| `RiskResult` | Adds constant `exposure_note`: `ranked by exposure, not by expected response`. | Preserves the causal/intervention boundary in every risk result. |
| `AdvisorInput` | Adds candidate `options[]` and constraints as the typed advisor input. | Lets BE-1 replay/rank candidates without coupling to legacy analyst dictionaries. |
| `AdvisorOutput` | New dedicated output with status/reason, `options[]`, assumptions, sources, artifacts, and flags. | Gives FE-1 a stable recommendation envelope, including information gathering. |
| `AdvisorOption` | Adds addressable-impact interval, recovery-fraction range, impact range, evidence grade, structured feasibility, assumptions, trade-offs, sensitivity, monitors, and ranking-change data. | Makes recommendations bounded, evidence-labelled, and reviewable. |
| `AdvisorOutput` | Removes the composite `scoring[]` / `score` field. | Prevents a single opaque composite score from being mistaken for an intervention effect. |
| Examples | Adds top-level `_example: true` metadata. | Allows fixture discovery without adding non-contract fields to exported schemas. |

## Compatibility and approval request

The legacy class remains available for the current orchestrator. New consumers
should import `src.analysts.contracts` and use the exported schema files under
`contracts/schemas/analysts/`. Please approve the proposed shared-contract
changes and the fixture shape before BE-1 wires runtime adapters and FE-1
builds the evidence/recommendation views.

