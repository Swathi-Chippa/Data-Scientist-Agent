# Data Scientist Agent — APPROACH

**Diagrams:** [Architecture](docs/diagrams.md#1-architecture-diagram) · [Workflow](docs/diagrams.md#2-workflow-diagram) (sources: `docs/architecture.mmd`, `docs/workflow.mmd`) · [Glossary](#glossary)
**Full detail behind every section:** [docs/DESIGN_DETAIL.md](docs/DESIGN_DETAIL.md)

> **Reading rule.** Every number marked *target* is an acceptance goal, not a result. Measured results are committed per prototype under `eval/results/<tag>/` with model name and version, commit hash, data snapshot id and date.

---

## Glossary

Every component and store name used in this repository is defined here, once. **Type:** *code* = deterministic; *model* = a language model writes; *assisted* = a model or trained model proposes, code decides.

| Component | Type | Role |
|---|---|---|
| **Orchestrator** | code | Runs the typed workflow, budgets and retries |
| **Guard** | code | Blocks writes, DDL and injection attempts first |
| **Router and Extractor** | assisted | Chooses the route; fills slots (metric, dimension, time window) |
| **Planner** | assisted | Orders the Analysts for a compound question; code validates the plan |
| **Metric Resolver** | code | Maps business terms to governed definitions in the Metric Registry |
| **Answerability Checker** | code | Decides if the catalog can answer; otherwise refuses and names what is missing |
| **Schema Retriever** | assisted | Finds tables and columns; **Join Finder** builds approved join paths; **Value Linker** maps phrases to stored values |
| **SQL Compiler** | code | Builds SQL deterministically for fully governed metrics |
| **SQL Generator** | model | Writes SQL for everything else, against the retrieved schema only |
| **Validator** | code | Parses, checks allowlist, joins, fan-out and cost before any execution |
| **Repairer** | model | Patches rejected or failing SQL: max 2 attempts, same schema |
| **Executor** | code | Runs approved SQL read-only with timeout and row cap |
| **Reconciler** | code | Checks grain, nulls, duplicates; compares totals with the Metric Registry |
| **Analysts** (Anomaly, Driver, Risk) | code (stats/ML) | Tested modules returning numbers, intervals, or "insufficient evidence" |
| **Advisor** | code | Ranks 2–3 options from the Action Library; people approve |
| **Evidence Ledger** | code | Numbered claims linked to queries or Analyst outputs, with evidence grade |
| **Synthesizer** | model | Writes the answer from the Evidence Ledger only |
| **Fact Checker** | code | Verifies every number; blocks causal wording above its evidence grade |

| Store | Holds |
|---|---|
| **Metric Registry** | Governed metric definitions: formula, filters, grain, date column, synonyms |
| **Metadata Catalog** | DDL, descriptions, column profiles, table trust features |
| **Join Graph** | Tables, join edges, cardinalities, approval status |
| **Search Indexes** | Keyword and vector indexes over tables, columns, golden queries |
| **Value Index** | Categorical values and name n-grams for value linking |
| **Golden Store** | Verified question–SQL pairs, human-reviewed |
| **Action Library** | Curated actions linked to driver and segment types |
| **Cache** | Slot-keyed plans and results |
| **Trace Store** | Every step, timing, token count and retry |

---

## A. Problem scoping

**User and decision.** Business owners (commercial strategy, operations, retention) with a large warehouse and no SQL or statistics skills. They need to know *whether a change is unusual, what is driving it, and what to do next*, with enough evidence to defend the decision.

**Input as it arrives.** Ambiguous business language, not schema terms: synonyms, typos, relative dates ("last month", "next quarter"), undefined terms ("active customer"), and sometimes requests for data the warehouse does not hold or instructions hidden in text. Two anchor questions:
1. *"Weekly orders in one region dropped sharply last month — is that unusual, and what is driving it?"*
2. *"Which customer segments are we most likely to lose next quarter, and where should we act first?"*

**Why plain text-to-SQL fails.** It hallucinates tables and columns, cannot find the right tables among hundreds, returns rows instead of an analysis, and lets a language model do arithmetic and causal reasoning. The agent is a **controlled workflow**: *route → ground in the real schema → generate or compile SQL → validate by execution → run a tested statistical/ML module → write the answer only from recorded evidence.*

**Capabilities**

| Built | Deliberately deferred |
|---|---|
| Question routing (lookup, anomaly, root cause, risk prediction, recommendation, clarify, refuse) | Multi-turn dialogue management |
| Schema-grounded SQL with validation, bounded repair, refusal | Schema changes, any write or DDL |
| Anomaly Analyst: seasonal baseline with false-discovery control | Bayesian structural time-series |
| Driver Analyst: attribution with intervals and graded evidence | Full causal-graph estimation |
| Risk Analyst (time-split churn model vs. baseline); Advisor with human-approved options | Survival and uplift models; autonomous actions |
| Evidence Ledger, Fact Checker, step-by-step trace, metrics dashboard | Row-level security, multi-tenant scale |

**How we will know it works (measurable; thresholds are targets calibrated on the development set).**

| # | Criterion | Measure |
|---|---|---|
| 1 | **Hard gates = 0** | Executed unknown identifiers; executed writes; numeric claims with no source |
| 2 | SQL correctness beats the naive baseline | Result-match accuracy vs. gold; schema-hallucination rate |
| 3 | Modules are right | Anomaly recall and false-alert rate; driver top-3 hit rate; risk PR-AUC and calibration, all against planted ground truth |
| 4 | Honest abstention | Refusal precision and recall; over-refusal on near-miss questions |
| 5 | Causal discipline | No answer exceeds its evidence grade |
| 6 | Operations | p50/p95 latency and cost per query, per route, vs. baseline |

---

## B. System design

Diagrams: [architecture](docs/diagrams.md#1-architecture-diagram), [workflow](docs/diagrams.md#2-workflow-diagram). Full step contracts: [DESIGN_DETAIL §B3](docs/DESIGN_DETAIL.md#b3-step-contracts).

**Agent pattern.**
- **Chosen:** a fixed, typed workflow with bounded tool use. The step order is code; models are called at set points and every model output is validated by code before it runs.
- **Rejected:** an open-ended tool-using agent that picks its own steps and writes free-form SQL or Python. It is more flexible but has unbounded cost and latency, is hard to audit, can route around an allowlist, and its numbers would come from unverified code. A single-prompt text-to-SQL system is kept only as the baseline.
- **Extension rule:** a new analysis is added as a registered, tested Analyst in the Analyst registry, never as free-form code execution.

**Components and steps** (who decides each one: see *Type* in the glossary)

| # | Component | Receives → returns |
|---|---|---|
| 1 | Guard | Raw text → pass or block |
| 2 | Router and Extractor | Question → route, confidence, slots |
| 3 | Planner | Route, slots → ordered Analyst plan (depth capped) |
| 4 | Metric Resolver | Slots → governed definition, grain, filters |
| 5 | Answerability Checker | Entities → answerable, or refusal naming what is missing |
| 6 | Schema Retriever | Question → pruned tables and columns, join path, linked values, column warnings |
| 7 | SQL Compiler or SQL Generator | Retrieved schema + definitions → one SQL statement |
| 8 | Validator (Repairer on failure) | SQL → approve or reject, with cost estimate |
| 9 | Executor | Approved SQL → rows |
| 10 | Reconciler | Rows → flags; comparison with the Metric Registry |
| 11 | Analysts and Advisor | Typed tables → numbers, intervals, assumptions, or "insufficient evidence"; ranked options |
| 12 | Evidence Ledger | Analyst outputs → numbered claims with evidence grade |
| 13 | Synthesizer | Ledger only → plain-language answer |
| 14 | Fact Checker | Answer vs. ledger → pass, or remove the claim |

**Rule: a model may choose, draft and explain; it never computes a number and never decides whether a query is safe.**

**Schema Retriever (scale).** Metadata Catalog with column profiles; a Join Graph (declared keys plus a classifier that proposes undeclared joins, each verified); hybrid keyword + dense retrieval with reranking, tuned for recall; column pruning; Value Linker with a confidence score. Low confidence means clarify or refuse, never model guessing ([§B7](docs/DESIGN_DETAIL.md#b7-schema-retriever-knowledge-retrieval-and-value-linking-for-hundreds-of-tables)).

**Validator and Repairer.** Validator: single read-only SELECT → allowlist from retrieval → approved joins and fan-out check → cost gate. Executor runs read-only; Reconciler checks results. On failure: at most **2** repairs against the *same* schema, then a structured clarification. An empty result is not automatically wrong ([§B8–B9](docs/DESIGN_DETAIL.md#b8-validator-before-any-execution)).

**Analysts and Advisor** (each tested against planted ground truth; [§B10](docs/DESIGN_DETAIL.md#b10-analysts-and-advisor)):
- **Anomaly Analyst:** seasonal baseline with prediction interval (history excludes the tested period), change-point check, false-discovery control across many units, minimum-volume guard.
- **Driver Analyst:** contribution decomposition (price/volume/mix), bootstrap intervals, co-movement and comparison-group checks, capped search depth.
- **Risk Analyst:** explicit churn definition, leakage-safe chronological split, baseline vs. gradient-boosted model, calibration, lift at contact capacity, revenue at risk per segment.
- **Advisor:** actions from the Action Library ranked by impact × evidence confidence × feasibility; 2–3 options with assumptions and sensitivity.

**Evidence grading.** Every claim carries a grade: *fact → concentration → co-movement → specific to the affected unit vs. a comparison group → consistent with a cause (untested)*. "Caused" and "because" are blocked unless the top grade is attached with its limits ([§B11](docs/DESIGN_DETAIL.md#b11-evidence-grading-how-strongly-a-cause-may-be-stated)).

**Where a person approves.** (1) Answers clarifying questions; (2) approves or rejects any operational action (the agent never acts); (3) reviews a validated query before it enters the Golden Store; (4) approves changes to the Metric Registry.

**When the system cannot answer or a step fails**

| Failure | Behaviour |
|---|---|
| Data not in the catalog / retrieval confidence low | Answerability Checker or Schema Retriever triggers a refusal or clarification that names what is missing and the closest answerable question |
| SQL rejected or erroring | ≤ 2 repairs, then clarification |
| Query too expensive | Cost-gate rewrite or refusal with explanation |
| Reconciliation mismatch | One retry, then visible caveat |
| Short history or low volume | "Insufficient evidence" and what would be needed |
| Model unavailable | SQL Compiler path for governed metrics; otherwise a clear error, never a guess |
| Unsupported claim in the draft (Fact Checker) | Removed or labelled hypothesis; template answer from the ledger if needed |
| Injection in question or data | Guard treats it as data, not instructions; blocked and logged |

**Cost, latency, accuracy.** SQL Compiler fast path (no SQL model call); small model for routing help and narration, stronger model only for hard SQL and repair; pruned prompts; slot-keyed Cache (not raw similarity); per-query budgets ([§B15](docs/DESIGN_DETAIL.md#b15-accuracy-latency-and-cost-design)).

---

## C. Data and knowledge

**Three layers, each proving something different** ([§C1–C4](docs/DESIGN_DETAIL.md#c1-data-strategy-three-layers-each-testing-something-different)).

| Layer | Purpose | What it proves |
|---|---|---|
| Public text-to-SQL benchmark databases (selected after licence check) | Many real schemas, dirty values, wide enterprise-style schemas, executable gold answers | SQL grounding, retrieval, value linking, refusal and repair at scale |
| Public transactional dataset (orders, customers, products, delivery) | Realistic business time series and customer history | A believable setting for the two anchor questions |
| **Synthetic enterprise layer** from a documented generator | Enterprise mess, scale ladder (≈50 / 200 / 500 tables), and **planted ground truth** | Whether the anomaly, root-cause and risk modules are actually *correct* |

**Why this is a fair test.** Public benchmarks test the SQL half but contain no known anomalies, causes or churn labels; only data we generate can show whether a module's output is right. The synthetic layer reproduces enterprise mess: cryptic and stale or duplicated tables, undeclared keys, mixed formats and time zones, placeholder values, merged customer identities, soft-deleted and test records, truncated recent data, distractor tables, and business terms with no matching column.

**Planted ground truth.** A manifest the agent cannot read records anomalies (level shift, spike, dip, decay) with start, size and unit; the true driver and its share; **confounders** that move with the driver without causing it; **negative controls** (normal weeks, holiday peaks, small units); and a documented customer-behaviour process that yields churn labels. SQL traps (fan-out joins, cancelled orders, duplicates) each have a known correct answer.

**Provenance, licence and privacy.** Every source is recorded with name, URL, retrieval date, licence, permitted use and the split it feeds. Non-commercial or share-alike terms are respected in how the repository and deployment are described. The generator code, seeds, configuration and any prompts used are versioned in `data_gen/` and `prompts/`. No real person's personal data is used without consent; sensitive columns are masked in profiles, prompts and logs. *(The specific datasets are filled into the provenance table once access and licences are reviewed.)*

**Keeping evaluation data separate.** Two synthetic snapshots with different seeds and injection settings: *build* (for tuning) and *held-out* (final report only). Development and held-out question sets are separate and locked; for public benchmarks, build on the training split and evaluate on the development/test split. Held-out questions are checked against the Golden Store for leakage before each final run, and the held-out manifest is readable only by the scoring code.

**Knowledge representation and retrieval**

| Store | Contents | Retrieved by |
|---|---|---|
| Metadata Catalog | DDL, descriptions, null/distinct/range, formats, masked samples, table trust features (freshness, duplicates, usage) | Lookup after retrieval |
| Join Graph | Tables, edges, cardinality, approval status | Path finding over approved edges |
| Metric Registry | Metric definitions, synonyms, grain, filters, reconciliation values | Synonym + exact match |
| Search Indexes | Tables, columns, descriptions, golden queries | Hybrid retrieval + reranking |
| Value Index | Categorical values; name n-grams | Fuzzy lookup with confidence |
| Golden Store | Verified question–SQL pairs | Similarity retrieval, top few |
| Action Library | Actions linked to driver and segment types | Rule match on module outputs |
| Trace Store | Every step, timing, tokens, retries | Dashboard and trace view |

**Controlled learning.** Queries enter the Golden Store only after passing result checks *and* human review; "ran without error" is not "correct".

---

## D. Evaluation framework

**Metrics, and why** (full table: [§D1](docs/DESIGN_DETAIL.md#d1-metrics-and-why-each-one))

| Layer | Metrics | Why this one |
|---|---|---|
| Routing | Accuracy, confusion matrix | A wrong route wastes the run |
| Retrieval | Required-table and column recall@k, MRR, join-path correctness | A missing table cannot be recovered later; measured apart from generation |
| SQL safety | Schema-hallucination rate, unauthorised-reference rate, blocked-write rate | Direct measure of the project principle |
| SQL correctness | **Result match vs. gold** (not "it ran"), fan-out and status-filter tests | Execution success is not correctness |
| Anomaly | Recall on planted anomalies, **false-alert rate on negative controls**, detection delay, interval coverage | Missing a problem and crying wolf both cost the user |
| Root cause | Top-1/top-3 driver hit rate, reconciliation error, false-driver and confounder-confusion rate | Tests attribution and causal discipline |
| Risk | PR-AUC with prevalence, Brier, calibration, lift at top-k | Accuracy misleads on imbalanced outcomes |
| Recommendation | Reviewer rubric (specific, evidence-linked, assumptions, trade-offs) | Usefulness is not one number |
| Faithfulness | % numeric claims linked to the Evidence Ledger; blocked-causal-language violations | Enforces "no model math" and honest wording |
| Abstention | Refusal precision/recall; over-refusal on near-misses | "Cannot answer" must be right, and not overused |
| Operations | p50/p95 latency and cost per route and stage, retries | Trade-offs are made deliberately |

**Test cases** (target sizes; grow with each prototype; full table in [§D2](docs/DESIGN_DETAIL.md#d2-test-suite-target-sizes-grows-with-each-prototype))

| Category | ~Cases | Category | ~Cases |
|---|---|---|---|
| Governed metric lookups | 30 | **Out-of-schema refusals (with paraphrases)** | 25 |
| Multi-table joins on messy data | 30 | **Near-miss answerable questions** | 10 |
| Anomaly (8 negative controls) | 20 | **Ambiguous → clarify / hand off** | 10 |
| Root cause (with confounders) | 15 | **Causal-overclaim ("did X cause Y?")** | 10 |
| Risk prediction | 10 | **Injection and unsafe requests** | 10 |
| Recommendation | 10 | Scale ladder (same subset at 50/200/500 tables) | — |

Each answerable case stores a gold result or invariant; each analysis case stores the planted truth it must recover.

**Compared against**
- **Baseline A — naive text-to-SQL:** one prompt, flattened schema, first output, no retrieval, validation or repair.
- **Baseline B — grounded SQL only:** retrieval + validation + repair, no modules.
- **System C — full agent.**
- **Ablation ladder** (same questions, snapshot, model, budget): A → + retrieval → + value linking → + validation → + repair → + Metric Registry and SQL Compiler → + Analysts → + Fact Checker, each step's effect on accuracy, latency and cost.
- **Analyst baselines:** fixed ±2σ trailing rule for anomalies; "largest absolute change" for drivers; simple heuristic segmentation for risk.
- **Scale test** across the 50 / 200 / 500-table ladder.

Results are paired per question, with refusals and failures in the denominator; a correct refusal counts as correct.

**Pass rule.** A prototype passes only if **all** hold: (1) all hard gates are zero; (2) SQL result accuracy exceeds Baseline A with a lower hallucination rate; (3) each module meets its own threshold against planted truth; (4) refusal and over-refusal are both within threshold; (5) zero causal-overclaim answers; (6) latency and cost are within per-route budgets or the trade-off is documented. Thresholds are set on the development set before the held-out run. **Categories are never averaged to hide a failure.**

**Run on every prototype.** Tags `v0.1` → `v1.0` ([§F1](docs/DESIGN_DETAIL.md#f1-prototype-tags)); the full suite runs on each tag and results are committed. The observability view shows these problem metrics next to accuracy, latency and cost on the running system.

---

## E. Risks and responsibility

**What a wrong output does to the person relying on it**

| Wrong output | Consequence |
|---|---|
| Hallucinated or inflated figure | A decision rests on a number that does not exist |
| False anomaly alert | Seasonal noise becomes an escalation; trust erodes |
| Missed real anomaly | A real problem goes unaddressed |
| Overstated root cause | Money and time fixed on the wrong thing |
| Miscalibrated risk list | Retention budget spent on the wrong customers |
| Confident but weak recommendation | Operational harm that looks evidence-backed |

A hallucinated figure is worse than a refusal, so the agent **fails closed**: it says exactly what is missing instead of guessing.

**How the project principle is enforced** (*generate only against the retrieved schema; validate every query by execution; measure against a naive baseline*)
1. The SQL Generator and SQL Compiler receive only retrieved tables and columns; the Validator rejects anything else **before** execution.
2. Only approved joins in the Join Graph pass; fan-out is flagged.
3. Every query runs read-only behind a cost gate; errors feed a bounded repair.
4. The Reconciler's result-level checks (grain, duplicates, nulls, Metric Registry comparison), because a query that parses is not necessarily correct.
5. No retrieval match means the Answerability Checker refuses; the model never "fills the gap".
6. The Evidence Ledger and Fact Checker stop any unsourced number reaching the user.
7. Every prototype is scored against Baseline A on identical questions.

**Other safeguards.** Read-only credentials; masked sensitive columns; database and pasted text are data, never instructions; every driver analysis ends with the causal-boundary note (*association is not proven causation; unmeasured factors may explain the pattern; the evidence grade shows how strongly each statement is supported*); the agent recommends and a person approves.

**Deliberate trade-off and its cost.** The agent accepts **lower anomaly recall and more "insufficient evidence" or clarification responses** in exchange for **very few false alerts and no unsupported claims**. *Cost:* some users get "I cannot say" where an unconstrained system would give a confident answer. We keep this visible by measuring over-refusal and detection delay, and we re-tune thresholds on the development set rather than loosening the hard gates. (Other trade-offs — fixed workflow vs. open agent, cache design, model tiering — are in [§E4](docs/DESIGN_DETAIL.md#e4-trade-offs).)

**Limits stated to users.** Benchmark or synthetic data does not prove performance on a specific real enterprise; synthetic ground truth tests the methods, not the real world; association cannot establish cause; results depend on the model used, whose name and version are logged with every run.

---

*Repository map and delivery plan (README, `src/`, `data_gen/`, `prompts/`, `eval/`, `observability/`, `agent_setup/`): [DESIGN_DETAIL §F](docs/DESIGN_DETAIL.md#section-f--delivery-plan-prototypes-deployment-repository).*
