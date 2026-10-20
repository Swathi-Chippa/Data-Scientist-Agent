# Data Scientist Agent — Brazilian E-Commerce Warehouse

> A controlled, schema-grounded analytical agent built over a DuckDB database (`brazil_ecommerce.db`), designed according to the architecture in [DESIGN_DETAIL.md](DESIGN_DETAIL.md) and [APPROACH.md](APPROACH.md).

---

## Highlights

- **Typed, Fixed Workflow:** Plain code enforces safety, schema allowlists, execution gates, and evidence verification. Models assist in slot extraction and narrative synthesis; statistical and machine learning modules are deterministic and tested.
- **Fail-Closed Design:** Unanswerable questions trigger honest refusals naming what is missing; ambiguous prompts trigger structured clarifying questions.
- **Evidence Grading (Grades 0 to 4):** Every assertion is bound to an Evidence Ledger. Words like "caused" or "due to" are blocked unless Grade 4 is attached and causal boundary limitations are explicitly stated.
- **Trace Everything to Files:** Every query run automatically logs a structured JSON trace (`traces/*.json`) and a human-readable Markdown summary (`traces/*.md`) with millisecond timings and AST verification logs.
- **Public Interactive Web UI:** Complete executive dashboard with Chart.js visualizations, deep trace inspector, benchmark metrics, and schema explorer.

---

## Repository Structure

```text
c:\D_drive\Data_Scientist_Agent\
├── src/                          # Core Agent Engine
│   ├── guard.py                  # Step 1: Pre-flight security & injection filter
│   ├── router.py                 # Step 2: Multi-signal router & slot extractor
│   ├── planner.py                # Step 3: Ordered execution planner
│   ├── metric_registry.py        # Central store of governed metric definitions
│   ├── metric_resolver.py        # Step 4: Governed metric resolver
│   ├── answerability.py          # Step 5: Catalog boundary & refusal checker
│   ├── schema_retriever/         # Step 6: Hybrid retrieval, join graph, value linker
│   │   ├── catalog.py            # Metadata profiler & table trust scoring
│   │   ├── join_graph.py         # Approved join paths & fan-out detector
│   │   ├── value_linker.py       # Trigram & fuzzy entity linker
│   │   └── retriever.py          # Schema pruning & column allowlist
│   ├── sql/                      # Steps 7-10: SQL Generation, AST validation, execution
│   │   ├── compiler.py           # Step 7a: Deterministic SQL compiler
│   │   ├── generator.py          # Step 7b: Allowlist-constrained SQL generator
│   │   ├── validator.py          # Step 8: sqlglot AST & cost gate validator
│   │   ├── repairer.py           # Step 8b: Bounded 2-attempt query repairer
│   │   ├── executor.py           # Step 9: Safe read-only DuckDB executor
│   │   └── reconciler.py         # Step 10: Grain & metric reconciler
│   ├── analysts/                 # Step 11: Statistical & ML modules
│   │   ├── base.py               # Base analyst & registry
│   │   ├── anomaly.py            # Step 11a: Seasonality-aware anomaly detector (FDR)
│   │   ├── driver.py             # Step 11b: Driver attribution & DiD (Bootstrap CI)
│   │   ├── risk.py               # Step 11c: Chronological churn model (GBDT)
│   │   └── advisor.py            # Step 11d: Action Library & multi-factor ranking
│   ├── evidence/                 # Steps 12-14: Evidence Ledger & Fact Checker
│   │   ├── ledger.py             # Step 12: Evidence Ledger manager
│   │   ├── synthesizer.py        # Step 13: Executive narrative synthesizer
│   │   └── fact_checker.py       # Step 14: Numeric verification & causal language blocker
│   ├── orchestrator.py           # End-to-end typed workflow orchestrator
│   ├── trace_logger.py           # File-based trace logger (JSON & Markdown)
│   └── app.py                    # FastAPI server & API endpoints
├── static/                       # Modern Glassmorphic Web Application
│   ├── index.html                # Executive Assistant & Dashboard UI
│   ├── style.css                 # State-of-the-art responsive dark mode styling
│   └── app.js                    # Chart.js integration, trace explorer, query forms
├── data_gen/                     # Synthetic enterprise & ground-truth generator
│   ├── planted_ground_truth.py   # Generates evaluation ground-truth manifest
│   └── synthetic_enterprise.py   # Generates staging views & distractor tables
├── eval/                         # Comprehensive Evaluation Framework (§Section D)
│   ├── baselines.py              # Baseline A (Naive), Baseline B (Grounded), System C
│   ├── eval_suite.py             # 25 curated test cases across Table D2
│   ├── runner.py                 # Evaluation benchmark runner
│   ├── ground_truth_manifest.json# Planted evaluation ground truth
│   └── results/v1.0/             # Committed evaluation results
│       └── evaluation_report.json
├── prompts/                      # Versioned prompt pack
├── traces/                       # Audit trace output directory (run_*.json, run_*.md)
├── tests/                        # 24 unit and integration tests (100% passing)
├── APPROACH.md                   # System glossary and methodology
├── DESIGN_DETAIL.md              # Long-form architectural specification
├── ARTEFACT.md                   # Architectural verification report
└── brazil_ecommerce.db           # DuckDB database file (166 MB)
```

---

## Quick Start

### 1. Requirements & Setup
Ensure Python 3.10+ is installed with dependencies:
```bash
pip install duckdb sqlglot pandas numpy scipy scikit-learn statsmodels networkx pydantic fastapi uvicorn
```

### 2. Run the Unit & Integration Tests
All 24 unit and integration tests verify Guard, Router, AST Validator, Analysts, and End-to-End tracing:
```bash
python -m unittest discover tests
```

### 3. Run the Evaluation Benchmark
Executes Baseline A (Naive), Baseline B (Grounded SQL Only), and System C (Full Agent) across all 25 test cases:
```bash
python eval/runner.py
```
Results are committed to `eval/results/v1.0/evaluation_report.json`.

### 4. Launch the Web Application
```bash
python src/app.py
```
Open your browser to:
```
http://localhost:8000
```

---

## File-Based Tracing

Every query run creates two persistent files in `traces/`:
1. `traces/run_<timestamp>_<id>.json`: Complete machine-readable state, AST checks, row counts, and timings.
2. `traces/run_<timestamp>_<id>.md`: Human-readable markdown audit trail with tabular timeline, executed SQL, and verification status.

Recent traces can also be inspected directly in the Web UI under the **Trace Inspector** tab.
