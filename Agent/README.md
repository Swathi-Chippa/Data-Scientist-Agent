# Data Scientist Agent — Brazilian E-Commerce Warehouse

> A schema-grounded, statistically disciplined analytical engine built over DuckDB (`brazil_ecommerce.db`), architected according to [DESIGN_DETAIL.md](DESIGN_DETAIL.md), [APPROACH.md](APPROACH.md), [Product.md](Product.md), and [Interfaces.md](Interfaces.md).

---

## Highlights

- **14-Step Bounded Pipeline:** Deterministic code enforces safety boundaries, schema allowlists, AST validation, execution budgets, and evidence verification. Models assist in slot extraction and explanation; statistical and machine learning modules are deterministic, tested, and grounded.
- **Zero-Hallucination Evidence Ledger:** Every numeric assertion is bound to an Evidence Ledger claim with an Evidence Grade (0 to 4). Words like *"caused"*, *"due to"*, or *"because of"* are blocked unless Grade 4 is attached and causal boundary limitations are explicitly stated.
- **Fail-Closed Governance:** Out-of-schema attributes trigger honest, precise refusals naming what is missing; underspecified prompts trigger structured clarifying questions.
- **Local & Cloud Dual-LLM Support:** Native support for local Ollama (`qwen2.5-coder:latest` at `http://127.0.0.1:11434`, achieving **150ms–800ms** latency) and Google Gemini (`gemini-2.5-flash`), configurable via `.env`.
- **Full `Interfaces.md` Compliance:** Implements the complete API specification, including asynchronous job flow (`POST /api/ask`), Server-Sent Events (SSE) streaming (`GET /api/runs/{run_id}/events`), typed `AnswerEnvelope` responses (`GET /api/runs/{run_id}`), human decision logging, and administrative review endpoints.
- **In-Memory Audit Tracing (Zero Disk Footprint):** All execution traces, step metrics, and lookup caches operate strictly in-memory during runtime. No `.cache/` or `traces/` folders are created on disk.
- **Interactive Web Dashboard:** Executive dashboard with glassmorphic UI, Chart.js visualizations, deep step-by-step audit trail timeline, evaluation benchmark scoreboards, and schema explorer.
- **100% Passing Test Suite:** 25 automated unit and integration tests covering security guards, router classifications, AST validators, statistical analysts, and end-to-end execution.

---

## 14-Step Analytical Workflow

The agent follows the strict controlled analytical workflow defined in **DESIGN_DETAIL.md** (§B1–B14) and **Interfaces.md**:

```text
User Question
     │
     ▼
[Step 1: Guard] ───────────────► Blocked (DML/DDL injection, write attempts)
     │
     ▼
[Step 2: Router & Extractor] ──► Clarify (Ambiguous) / Refusal (Unanswerable)
     │
     ▼
[Step 3: Planner] ─────────────► Validated execution plan against Analyst Registry
     │
     ▼
[Step 4: Metric Resolver] ─────► Governed metric resolution & dimension validation
     │
     ▼
[Step 5: Answerability] ───────► Rejects questions requiring absent schema entities
     │
     ▼
[Step 6: Schema Retriever] ────► Hybrid retrieval, approved join paths, value linking
     │
     ▼
[Step 7: SQL Compiler / Gen] ──► Deterministic Compiler (governed) / Generator (ungoverned)
     │
     ▼
[Step 8: Validator & Repairer] ─► 10 AST & cost safety checks; max 2 repair attempts
     │
     ▼
[Step 9: Safe Executor] ───────► DuckDB read-only connection (20s timeout, 1000 row cap)
     │
     ▼
[Step 10: Reconciler] ─────────► Grain, null, duplicate, and metric registry checks
     │
     ▼
[Step 11: Statistical Analysts]
     ├── Anomaly Analyst ──────► Seasonal baseline, robust Z-score/MAD, Benjamini-Hochberg FDR
     ├── Driver Analyst ───────► Metric tree decomposition, bootstrap CIs, Grade 0-4
     ├── Risk Analyst ─────────► 90-day churn definition, chronological split, GBDT/Logistic
     └── Advisor ──────────────► Ranked interventions (Impact × Confidence × Feasibility)
     │
     ▼
[Step 12: Evidence Ledger] ────► Structured claims (C1, C2...) linked to query results
     │
     ▼
[Step 13: Synthesizer] ────────► Executive narrative synthesis strictly from ledger claims
     │
     ▼
[Step 14: Fact Checker] ───────► Verifies numbers against query rows; blocks causal wording
     │
     ▼
AnswerEnvelope / FinalAnswer
```

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
│   │   ├── validator.py          # Step 8: sqlglot AST & cost gate validator (10 checks)
│   │   ├── repairer.py           # Step 8b: Bounded 2-attempt query repairer
│   │   ├── executor.py           # Step 9: Safe read-only DuckDB executor
│   │   └── reconciler.py         # Step 10: Grain & metric reconciler
│   ├── analysts/                 # Step 11: Statistical & ML modules
│   │   ├── base.py               # Base analyst & module registry
│   │   ├── anomaly.py            # Step 11a: Seasonality-aware anomaly detector (FDR)
│   │   ├── driver.py             # Step 11b: Driver attribution & DiD (Bootstrap CI)
│   │   ├── risk.py               # Step 11c: Chronological churn model (GBDT/Logistic)
│   │   └── advisor.py            # Step 11d: Action Library & multi-factor ranking
│   ├── evidence/                 # Steps 12-14: Evidence Ledger & Fact Checker
│   │   ├── ledger.py             # Step 12: Evidence Ledger manager
│   │   ├── synthesizer.py        # Step 13: Executive narrative synthesizer
│   │   └── fact_checker.py       # Step 14: Numeric verification & causal language blocker
│   ├── llm/                      # LLM Gateway
│   │   └── client.py             # Unified client supporting Ollama (Qwen) & Gemini
│   ├── models/                   # Typed Schemas & Contracts
│   │   ├── schemas.py            # AnswerEnvelope, FinalAnswer, LedgerClaim, etc.
│   │   └── trace.py              # PipelineRunTrace & PipelineStepAudit
│   ├── orchestrator.py           # End-to-end typed workflow orchestrator
│   ├── trace_logger.py           # In-memory execution trace manager
│   ├── config.py                 # Core configurations, limits, and security patterns
│   └── app.py                    # FastAPI server implementing Interfaces.md API
├── static/                       # Glassmorphic Executive Dashboard
│   ├── index.html                # Executive Assistant & Dashboard UI
│   ├── style.css                 # Responsive dark mode design system
│   └── app.js                    # Chart.js visualization, trace explorer, query forms
├── semantic_layer/               # Governed Semantic Layer
│   ├── metrics.yaml              # Governed metrics (Revenue, Orders, Freight, etc.)
│   └── joins.yaml                # Approved schema relationships
├── data_gen/                     # Synthetic enterprise & ground-truth generator
│   ├── planted_ground_truth.py   # Injects planted anomalies, drivers, and churn truth
│   └── synthetic_enterprise.py   # Generates staging views & distractor tables
├── eval/                         # Comprehensive Evaluation Framework (§Section D)
│   ├── baselines.py              # Baseline A (Naive), Baseline B (Grounded SQL Only)
│   ├── eval_suite.py             # 25 curated test cases across Table D2
│   ├── runner.py                 # Evaluation benchmark runner
│   ├── ground_truth_manifest.json# Planted evaluation ground truth
│   └── results/v1.0/             # Benchmark results and multi-level evaluation logs
├── scripts/                      # Utility and verification scripts
│   └── test_levels.py            # Comprehensive 16-query test across 8 functional levels
├── tests/                        # Automated unit & integration test suite (25 tests)
├── prompts/                      # Versioned prompt pack
├── APPROACH.md                   # Problem definition, glossary, and core philosophy
├── DESIGN_DETAIL.md              # Long-form architectural specification (Sections A-F)
├── Product.md                    # Team work contract and component ownership
├── Interfaces.md                 # Complete input/output interface contracts
├── brazil_ecommerce.db           # Brazilian E-Commerce DuckDB database file
└── .env.example                  # Environment configuration template
```

---

## API Reference (`Interfaces.md` Compliant)

The application provides a REST and Server-Sent Events (SSE) API matching `Interfaces.md` §2 and `Product.md` §5.1:

### 1. Ask Flow & Runs

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ask` | Starts an analytical run; returns `{ "contract_version": "1.0.0", "run_id": "<uuid>" }` |
| `GET` | `/api/runs/{run_id}` | Retrieves the standard typed `AnswerEnvelope` (conclusion, claims, queries, actions) |
| `GET` | `/api/runs/{run_id}/events` | **Server-Sent Events (SSE)** streaming `step_started`, `step_finished`, `clarify`, and `answer` |
| `GET` | `/api/runs/{run_id}/trace` | Returns full step-by-step audit trace with duration and notes |
| `GET` | `/api/runs` | Lists recent runs with status, latency, route labels, and timestamps |
| `POST` | `/api/runs/{run_id}/actions/{action_id}/decision` | Records human decision (`approve` / `reject`) on advisor recommendations |
| `POST` | `/api/runs/{run_id}/review-request` | Requests analyst review on low-confidence or sensitive answers |
| `GET` | `/api/artifacts/{artifact_id}` | Returns chart data or table artifacts for evidence views |

### 2. Direct Query & Web UI Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/query` | Direct synchronous execution endpoint returning the full result payload |
| `GET` | `/api/traces` | Lists all in-memory execution traces for the dashboard timeline |
| `GET` | `/api/traces/{trace_id}` | Returns detailed trace JSON for the Web UI trace inspector |
| `GET` | `/api/eval/report` | Returns committed evaluation benchmark results |
| `GET` | `/api/health` | Health check endpoint reporting DuckDB connection and engine status |

### 3. Warehouse Onboarding & Review Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/warehouse/connect` | Initiates warehouse introspection |
| `GET` | `/api/onboarding/{job_id}/report`| Returns catalog report (tables, columns, masked entities, verified joins) |
| `GET` | `/api/joins` | Lists approved join graph relationships |
| `GET` | `/api/columns/sensitive` | Lists masked sensitive column definitions |
| `GET` | `/api/golden/candidates` | Lists candidate queries for Golden Store review |
| `GET` | `/api/metrics` | Dashboard evaluation metrics (hallucination rate, accuracy, latency) |

---

## Quick Start

### 1. Requirements & Installation

- Python 3.10+
- (Optional, recommended) [Ollama](https://ollama.com/) for fast local LLM inference

Install Python dependencies:
```bash
pip install -r requirements.txt
```
*(or manually: `pip install duckdb sqlglot pandas numpy scipy scikit-learn statsmodels networkx pydantic fastapi uvicorn requests python-dotenv`)*

### 2. Configure Environment (`.env`)

Copy the example file:
```bash
cp .env.example .env
```

Configure your LLM provider in `.env`:

**Option A: Local Ollama (Recommended — Ultra Fast, Zero Cloud Costs)**
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:latest
```
*Make sure Ollama is running: `ollama run qwen2.5-coder:latest`*

**Option B: Google Gemini Cloud**
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Run Automated Tests

Run the full unit and integration test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
*Expected: 25 tests pass (`OK`). Traces and cache folders remain strictly in memory.*

### 4. Run the 8-Level Multi-Question Test

Test 16 varied questions across all 8 functional complexity levels:
```bash
python scripts/test_levels.py
```
*Results are logged to `eval/results/v1.0/level_test_results.json`.*

### 5. Launch the Web Application

Start the FastAPI application:
```bash
python -m uvicorn src.app:app --host 127.0.0.1 --port 8000
```

Open your browser to:
```
http://localhost:8000
```

---

## In-Memory Tracing & Zero-Disk Footprint

To ensure high performance and prevent cluttering the repository with thousands of ephemeral runtime files:
- **Zero On-Disk Files:** Traces are maintained in-memory inside `TraceLogger` (`_traces` and `_index`).
- **Zero Disk Cache:** Lookup queries are cached in-memory with slot-based hashing (`self._in_memory_cache`).
- **Full Trace Accessibility:** Traces can be inspected at any time via `GET /api/traces`, `GET /api/runs/{run_id}/trace`, and directly inside the Web UI's **Trace Inspector** tab.
- **Permanent Setting:** `ENABLE_DISK_TRACING = False` and `ENABLE_DISK_CACHE = False` in `src/config.py` guarantee that neither `traces/` nor `.cache/` will ever be created on disk when queries are run.

---

## Evaluation Benchmark (§Section D)

The repository includes a complete evaluation harness that benchmarks the system against planted ground truth:

```bash
python eval/runner.py
```

It compares three systems across 25 curated test cases:
1. **Baseline A (Naive):** Single prompt, flattened schema, unvalidated SQL.
2. **Baseline B (Grounded SQL Only):** Hybrid retrieval, AST validation, and bounded repair without statistical analysts or governed semantic layer.
3. **System C (Full Data Scientist Agent):** The complete 14-step workflow, Evidence Ledger, statistical analysts, and Fact Checker.

Benchmark reports are saved to `eval/results/v1.0/evaluation_report.json` and rendered in the Web UI **Benchmark & Evaluation** tab.
