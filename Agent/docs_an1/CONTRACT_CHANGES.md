# Proposed AN-1 Contract Changes

This change tightens the P1 analyst hand-off contracts for FE-1 and BE-1. The
legacy `src/analysts/base.py::AnalystOutput` remains unchanged.

## Breaking changes

- `DriverResult.dimensions` replaces the flat `drivers[]` shape. Each dimension
  reconciles to `total_change`; `shares_shown` controls whether contribution
  shares may be populated.
- `RiskResult.target` replaces `churn_definition` and records the target kind,
  window, cutoff, and population. `second_purchase` uses `one_time_buyers`.
- `AdvisorOutput` has no `scoring[]` or `score`; options carry bounded impact
  ranges and evidence grades instead.
- `AnalystInput.seed` is required for reproducible analyst runs.
- `AdvisorInput` now carries optional `anomaly`, `driver`, and `risk` module
  results, an `action_library_ref`, and `constraints.max_options` (default 3).
  It no longer accepts pre-built candidate options.

## Required consumer changes

FE-1 must render dimensioned driver contributions, honor `shares_shown`, and
surface `data_issue_suspected` and the full risk `exposure_note`. It must not
render or depend on a score. It should display contract version `2.0` when
present and treat impact as the ordered low/base/high range.

BE-1 must supply `seed`, load the referenced input-table metadata and
`action_library_ref`, pass module results into `AdvisorInput`, and remove all
score usage. Adapters must preserve `reconciliation_error`, correction
metadata, and artifact references when forwarding results.

## Additive changes

All analyst and advisor envelopes carry `contract_version` (default `2.0`).
Outputs retain `artifacts`, while driver results expose
`reconciliation_error`, `price_volume_mix`, `candidates_examined`, and
`correction_used`. Anomaly results enforce expected-range and deviation
consistency plus data-quality gating. Driver claims reject causal wording;
risk metrics include prevalence with an interval; advisor impacts must satisfy
`low <= base <= high`. JSON Schemas and examples under `contracts/` are
regenerated from the Pydantic models.
