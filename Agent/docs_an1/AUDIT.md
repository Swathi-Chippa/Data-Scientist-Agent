# AN-1 Analyst Audit

Date: 2026-10-22

Scope: `src/analysts/{anomaly,driver,risk,advisor,base}.py`, the analyst call
site in `src/orchestrator.py`, the two data generators, and the analyst tests.
The findings are checked against `docs_an1/DESIGN_DETAIL_v2.md` sections A4,
B10.0-B10.4, and B11. No existing source file was changed.

## Tooling and test results

Created [`requirements-an1.txt`](../requirements-an1.txt). Observed package
versions are recorded there; DuckDB, statsmodels, and optional ruptures were
not installed in the audit environment. The database file exists at
`Agent/brazil_ecommerce.db`.

- `pytest -q tests/analysts`: failed to run, exit 4; `tests/analysts` does not
  exist (the repository has `tests/test_analysts.py`).
- `pytest -q tests/test_guard.py tests/test_router.py`: **12 passed in 2.41s**.
- `pytest -q tests`: collection failed, exit 2, with three
  `ModuleNotFoundError: No module named 'duckdb'` errors in
  `tests/test_analysts.py`, `tests/test_end_to_end.py`, and
  `tests/test_validator.py`.
- `python scripts/test_levels.py`: failed, exit 1, at orchestrator import for
  the same missing DuckDB dependency.
- DB-backed analyst/end-to-end/validator execution could not be reached. The
  DuckDB file being present does not compensate for the missing Python module.

The generator scripts were inspected but not executed: `planted_ground_truth.py`
would create an additional manifest file, and `synthetic_enterprise.py` mutates
the database by creating views. That would exceed the requested two-file write
scope.

## Findings

### A. Database ownership and SQL construction — partially confirmed

Refuted as stated for “all analysts.” Anomaly, Driver, and Risk each open
DuckDB themselves with `read_only=True`: `src/analysts/anomaly.py:38`,
`src/analysts/driver.py:40`, and `src/analysts/risk.py:38`. Each constructs SQL
with f-strings containing context-derived values: Anomaly uses region and
time grain at `anomaly.py:33-50`; Driver uses region and the two periods at
`driver.py:33-69`, `84-96`, and `103-112`; Risk uses cutoff and outcome dates
at `risk.py:35-80`.

Advisor does not open DuckDB or construct SQL; it consumes output dictionaries
from context at `src/analysts/advisor.py:113-119`. Base only defines the
contract at `src/analysts/base.py:23-32`. Thus the underlying concern is
confirmed for three analysts, not all four.

### B. Anomaly — confirmed, with one wording qualification

- The baseline is a flat median/MAD estimate, not a seasonal-by-week baseline:
  `src/analysts/anomaly.py:83-96` computes one median and one MAD from the
  training frame.
- Training is nominally the last-four-period exclusion (`anomaly.py:83-86`),
  but the scoring loop iterates over all `df` rows, not only `test_df`
  (`anomaly.py:98-127`). Therefore training weeks are scored and can enter
  `anomalies_detected`; `most_severe` is selected from all significant
  anomalies at `anomaly.py:150-151`, so it can be outside the test window.
- BH-like filtering is applied over the detected weeks of this one series:
  `m = len(df)` and the threshold loop are at `anomaly.py:129-140`. The
  `or abs(z) >= 3.0` bypass is explicit at `anomaly.py:137-139`.
- Claim text hard-codes `p < 0.01` at `anomaly.py:171-173`, although the
  implementation computes a p-value at `anomaly.py:102-107` and uses the
  configured FDR q-value elsewhere.
- “Change-point analysis” is a count of test-window weeks below `-1.5 sigma`,
  requiring at least two, at `anomaly.py:144-148`; no change-point algorithm
  is used.
- The dates `2017-06-01` and `2018-08-25` are hard-coded in the SQL at
  `anomaly.py:47-50`. The `0.4` tail heuristic is hard-coded at
  `anomaly.py:68-70`.

Qualification: the code comment calls the baseline “seasonal” and the docstring
mentions ETS, but the executable implementation is the flat median/MAD path.

### C. Driver — confirmed, except the exact grade-3 wording

- A grade-3 claim is always appended through either branch of the `if/else` at
  `src/analysts/driver.py:246-258`.
- The grade-4 claim is fixed template text at `driver.py:260-265`.
- Category order counts use `COUNT(DISTINCT o.order_id)` independently in each
  category CTE at `driver.py:43-70`. Because an order with items in multiple
  categories contributes to each category, category totals/contributions can
  fail to reconcile with order-level totals. This is also reflected in the
  unqualified assumption that the categories are mutually exclusive at
  `driver.py:294-297`.
- The bootstrap draws Poisson counts around each fixed category baseline/current
  count at `driver.py:305-318`; it is not a resampling of observed orders.
- The verdict is a fixed literal, `"Attribution and Concentration Validated"`,
  at `driver.py:275-279`.
- Empty results are not handled before `top1` is dereferenced in the summary at
  `driver.py:167-169` and `267-273`; `top1` itself is guarded in metrics, but
  the summary still fails when no category rows return.

Qualification: “always grade-3 claim” is confirmed; its text is data-dependent
  in each branch, while the claim’s presence and grade are unconditional.

### D. Risk — confirmed

- The claimed chronological split is actually `train_test_split` with
  `stratify=y` and a random seed at `src/analysts/risk.py:118-127`.
- The query orders rows by post-cutoff activity before monetary value and then
  limits to 8,000 at `risk.py:68-80`, selecting on the outcome.
- Delivery and review features are computed from historical joined fields at
  `risk.py:48-55` and then used as model features at `risk.py:120-126`; the
  delivery date and review records are not independently constrained to be
  available by the cutoff. The feature query also does not apply a delivered
  timestamp cutoff to those joined fields beyond the order-purchase filter.
- Gradient boosting is fitted and used for probabilities and reported metrics
  as the champion at `risk.py:143-151`; there is no model-selection comparison
  that can replace it.
- Segment names and actions are hard-coded in `risk.py:162-175`.
- Empty segments are skipped at `risk.py:178-194`, but `segments[0]` is
  unconditionally accessed at `risk.py:205-213`; if every segment is empty,
  the analyst fails.

### E. Advisor — confirmed

- Impact and confidence are constants in the recommendation branches:
  `src/analysts/advisor.py:128-130`, `161-163`, and `189-191`; the fallback
  also uses fixed values at `advisor.py:223-227`.
- A ranking score is a literal (`6.37`) in the fallback at `advisor.py:223-227`.
- The composite ranking multiplies impact, confidence, feasibility, and a
  scale factor at `advisor.py:130`, `163`, and `191`; the stated formula is
  repeated at `advisor.py:273-274`.

### F. Ground-truth and synthetic data generation — confirmed

- `data_gen/planted_ground_truth.py` builds a hand-typed manifest literal at
  `data_gen/planted_ground_truth.py:19-135` and only serializes it at
  `137-141`; it does not modify the database or plant anomalies/drivers/churn
  outcomes.
- Repository search finds the manifest path and writer, but no code that reads
  `ground_truth_manifest.json`; the only references are the writer and README
  documentation. This means the manifest is currently disconnected from an
  evaluator.
- `data_gen/synthetic_enterprise.py` opens DuckDB with `read_only=False` at
  `data_gen/synthetic_enterprise.py:12-15` and creates/replaces views at
  `17-29`, so its write capability is real.

### G. Analyst tests — confirmed

`tests/test_analysts.py` asserts status, selected metric-key presence, nonempty
claims, and a minimum recommendation-table size at `tests/test_analysts.py:17-46`.
It does not assert numeric correctness, determinism, empty/sparse/short inputs,
zero baselines, evidence grades, leakage safety, reconciliation, or the
orchestrator contract. It also relies on the live default database rather than
isolated typed input tables.

## Orchestrator contract

The contract below is the compatibility surface at `src/orchestrator.py:566-626`.

### Context keys written by the orchestrator

The initial `analyst_context` contains exactly:

```text
region
metric
time_grain
execution_result
```

Those assignments are at `orchestrator.py:566-571`. After each analyst runs,
the orchestrator stores the full `out.model_dump()` under exactly one key:

```text
AnomalyAnalyst -> anomaly_output
DriverAnalyst  -> driver_output
RiskAnalyst    -> risk_output
```

These writes are at `orchestrator.py:580`, `588`, and `595`. Advisor is passed
the same mutable context at `orchestrator.py:599-600`, and does not add an
`advisor_output` key. The analyst code reads `driver_output`, `risk_output`, and
`anomaly_output` in `advisor.py:117-119`.

Each serialized analyst output has the Pydantic `AnalystOutput` keys defined at
`src/analysts/base.py:11-20`:

```text
analyst_name, status, verdict, summary, metrics, tables,
assumptions, caveats, evidence_claims
```

### Output keys read by the orchestrator

For AnomalyAnalyst, DriverAnalyst, and RiskAnalyst, the orchestrator directly
reads `out.evidence_claims` and each claim's `text`, `grade`, and optional
`data` at `orchestrator.py:581-582`, `589-590`, and `596-597`. It also reads
`out.verdict` for the trace at `orchestrator.py:636-638` and serializes the
entire output via `out.model_dump()` at `orchestrator.py:637`.

For Advisor, it directly reads `out.tables`, the table named
`recommended_actions`, and each recommendation's keys

```text
rank, title, owner, lead_time, cost_class, score, trade_offs
```

at `orchestrator.py:602-622`. It also reads Advisor `out.evidence_claims` and
each claim's `text`, `grade`, and optional `data` at `orchestrator.py:625-626`,
then reads `out.verdict` and serializes the full output for the trace at
`orchestrator.py:636-638`.

The orchestrator does not directly read analyst `metrics`, `summary`,
`assumptions`, or `caveats`; they remain compatibility fields because the full
`model_dump()` is retained in context/trace and Advisor consumes selected
metrics through the context dictionaries.

## Findings not confirmed and additional observations

Not confirmed as written:

- Finding A’s universal claim (“all analysts”) is false because Advisor and
  Base do not open DuckDB; only three concrete analysts do.
- Finding C’s “grade-3 claim is always emitted” is confirmed, but the claim
  text itself is not fixed: it has two computed branches.
- Finding B’s “seasonal” wording is not an implementation property; the code
  is flat median/MAD. The behavioral defects listed in B are confirmed.

Additional observations:

- The analyst implementation violates the AGENTS.md purity rule directly:
  the three analytical modules read the database internally instead of
  accepting typed input tables.
- `src/analysts/anomaly.py:18` imports a configurable minimum-series constant,
  but the run path uses a separate hard-coded minimum of 8 at `58-65`.
- Anomaly claims use grade 0 for statistical significance at `anomaly.py:164-174`,
  and Driver emits a grade-4 “consistent with” claim at `driver.py:260-265`;
  this is a contract-level evidence-grading risk under B11.
- The orchestrator reconstructs Advisor recommendation confidence and
  feasibility as fixed `0.9` and `0.88` values at `orchestrator.py:613-616`,
  rather than preserving the values produced by Advisor.
- `risk.py:101-103` contains fallback customer counts when the aggregate query
  returns no row, which can manufacture a plausible-looking percentage instead
  of failing closed.
- The requested scripts/tests are not currently runnable end-to-end in this
  environment because DuckDB is absent; installing requirements is a necessary
  follow-up before DB-backed behavior can be assessed.

## Assumptions and limits

- “Current versions” means the versions reported by `pip show` in the active
  Python environment on 2026-10-22; uninstalled packages are explicitly marked.
- Line numbers refer to the unmodified working-tree files inspected during this
  audit.
- No source file was edited. Only `requirements-an1.txt` and this audit were
  created.

## Project runtime dependencies

`Agent/.venv` was created with Python 3.14.4. The final project runtime set
includes these packages (the first three were already listed in the initial
requirements file; the last three were discovered during project test imports):

```text
duckdb 2.0.0
pydantic 2.14.1
python-dotenv 1.2.4
PyYAML 6.0.3       # imported as yaml
sqlglot 30.24.0
networkx 3.7
```

The missing-import sequence was:

1. The first venv run of `pytest -q tests` and `scripts/test_levels.py` failed
   with `ModuleNotFoundError: No module named 'yaml'` while importing
   `src.metric_registry`, and with `No module named 'sqlglot'` while importing
   `src.sql.validator`.
2. After installing `pyyaml` and `sqlglot`, both commands failed at
   `src.schema_retriever.join_graph` with
   `ModuleNotFoundError: No module named 'networkx'`.
3. After installing `networkx`, no import failures remained.

## Runtime evidence

All measurements below used `Agent/.venv\Scripts\python.exe`. The throwaway
script `.tmp_runtime_evidence.py` used `duckdb.connect(..., read_only=True)` for
its direct queries; `AnomalyAnalyst` also opened the same database read-only.
The script was removed after capture and was not staged.

### Test and script results

`pytest -q tests` passed all 25 tests in the final run:

```text
tests/test_analysts.py::TestAnalysts::test_advisor PASSED
tests/test_analysts.py::TestAnalysts::test_anomaly_analyst PASSED
tests/test_analysts.py::TestAnalysts::test_driver_analyst PASSED
tests/test_analysts.py::TestAnalysts::test_risk_analyst PASSED
tests/test_end_to_end.py::TestEndToEnd::test_anchor_question_1_creates_evidence_ledger PASSED
tests/test_end_to_end.py::TestEndToEnd::test_anchor_question_2_churn_risk PASSED
tests/test_end_to_end.py::TestEndToEnd::test_governed_lookup_creates_trace_file PASSED
tests/test_end_to_end.py::TestEndToEnd::test_refusal_on_unanswerable PASSED
tests/test_end_to_end.py::TestEndToEnd::test_security_block PASSED
tests/test_guard.py::TestGuard::test_blocked_ddl_sql PASSED
tests/test_guard.py::TestGuard::test_delete_all_tables_blocked PASSED
tests/test_guard.py::TestGuard::test_drop_table_blocked PASSED
tests/test_guard.py::TestGuard::test_prompt_injection_blocked PASSED
tests/test_guard.py::TestGuard::test_safe_query_passes PASSED
tests/test_guard.py::TestGuard::test_stacked_statements_blocked PASSED
tests/test_router.py::TestRouter::test_ambiguous_route PASSED
tests/test_router.py::TestRouter::test_anomaly_route PASSED
tests/test_router.py::TestRouter::test_lookup_route PASSED
tests/test_router.py::TestRouter::test_risk_prediction_route PASSED
tests/test_router.py::TestRouter::test_root_cause_route PASSED
tests/test_router.py::TestRouter::test_unanswerable_refusal PASSED
tests/test_validator.py::TestValidator::test_disallowed_table_rejected PASSED
tests/test_validator.py::TestValidator::test_non_select_rejected PASSED
tests/test_validator.py::TestValidator::test_star_select_rejected PASSED
tests/test_validator.py::TestValidator::test_valid_select_passes PASSED

25 passed in 10.78s
```

`python scripts/test_levels.py` completed all 16 cases across all 8 levels and
returned exit code 0. Each case reported `Status: SUCCESS`, `CLARIFICATION`,
`REFUSAL`, or `BLOCKED` as expected by its level; no traceback was emitted.
The script wrote its normal `eval/results/v1.0/level_test_results.json`; that
generated result was not staged.

### A. Anomaly runtime measurement: SP

The analyst returned `status=success`, scored 65 rows, returned the last 12
rows in its `time_series` table, and reported no anomaly:

```text
ANOMALY_STATUS success
ANOMALY_SCORED_ROWS 65
ANOMALY_SCORED_SERIES [["2017-05-29", 175], ["2017-06-05", 319], ["2017-06-12", 284], ["2017-06-19", 275], ["2017-06-26", 302], ["2017-07-03", 311], ["2017-07-10", 367], ["2017-07-17", 382], ["2017-07-24", 354], ["2017-07-31", 369], ["2017-08-07", 348], ["2017-08-14", 433], ["2017-08-21", 346], ["2017-08-28", 372], ["2017-09-04", 334], ["2017-09-11", 400], ["2017-09-18", 387], ["2017-09-25", 360], ["2017-10-02", 379], ["2017-10-09", 370], ["2017-10-16", 438], ["2017-10-23", 367], ["2017-10-30", 357], ["2017-11-06", 486], ["2017-11-13", 529], ["2017-11-20", 1108], ["2017-11-27", 835], ["2017-12-04", 668], ["2017-12-11", 569], ["2017-12-18", 395], ["2017-12-25", 366], ["2018-01-01", 548], ["2018-01-08", 714], ["2018-01-15", 738], ["2018-01-22", 667], ["2018-01-29", 627], ["2018-02-05", 628], ["2018-02-12", 699], ["2018-02-19", 660], ["2018-02-26", 705], ["2018-03-05", 628], ["2018-03-12", 659], ["2018-03-19", 769], ["2018-03-26", 629], ["2018-04-02", 730], ["2018-04-09", 678], ["2018-04-16", 680], ["2018-04-23", 718], ["2018-04-30", 756], ["2018-05-07", 800], ["2018-05-14", 900], ["2018-05-21", 532], ["2018-05-28", 490], ["2018-06-04", 648], ["2018-06-11", 656], ["2018-06-18", 662], ["2018-06-25", 618], ["2018-07-02", 571], ["2018-07-09", 351], ["2018-07-16", 680], ["2018-07-23", 720], ["2018-07-30", 958], ["2018-08-06", 881], ["2018-08-13", 900], ["2018-08-20", 534]]
ANOMALY_SERIES_ROWS_RETURNED 12
ANOMALY_LAST4 [{"period": "2018-07-30", "actual": 958.0, "expected": 548.0, "lower_bound": 65.6, "upper_bound": 1030.4, "is_anomaly": false}, {"period": "2018-08-06", "actual": 881.0, "expected": 548.0, "lower_bound": 65.6, "upper_bound": 1030.4, "is_anomaly": false}, {"period": "2018-08-13", "actual": 900.0, "expected": 548.0, "lower_bound": 65.6, "upper_bound": 1030.4, "is_anomaly": false}, {"period": "2018-08-20", "actual": 534.0, "expected": 548.0, "lower_bound": 65.6, "upper_bound": 1030.4, "is_anomaly": false}]
ANOMALY_REPORTED_PERIODS []
ANOMALY_VERDICT Within Normal Historical Variation
```

There was no reported anomaly period in this run, so the inside-versus-training
classification is not applicable. The four-week test window used by the code
was 2018-07-30 through 2018-08-20.

### B. Driver runtime measurement: SP, 2018-05 to 2018-06

```text
DRIVER_CATEGORY_ROWS 65
DRIVER_CATEGORY_SUM_ORDERS_BASE 3167
DRIVER_CATEGORY_SUM_ORDERS_CURR 2767
DRIVER_TRUE_DISTINCT_ORDERS_BASE 3138
DRIVER_TRUE_DISTINCT_ORDERS_CURR 2738
DRIVER_DIFFERENCE_BASE_CATEGORY_MINUS_TRUE 29
DRIVER_DIFFERENCE_CURR_CATEGORY_MINUS_TRUE 29
```

### C-D. Risk runtime measurements: cutoff 2018-03-01, outcome end 2018-06-01

```text
RISK_SAMPLE_ROWS 8000
RISK_SAMPLE_CHURN_COUNT 7608
RISK_SAMPLE_CHURN_PREVALENCE 0.951
RISK_FULL_ROWS 55525
RISK_FULL_CHURN_COUNT 55133
RISK_FULL_CHURN_PREVALENCE 0.9929401170643855
RISK_SAMPLE_FREQ_EQ_1 7358
RISK_FULL_FREQ_EQ_1 53902
```

These are measurements of the implemented queries and sample; no additional
inference is made here about model quality or causal impact.
