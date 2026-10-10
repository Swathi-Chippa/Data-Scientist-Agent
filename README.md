Data Scientist Agent
An enterprise-grade autonomous data science agent that bridges the gap between natural language business questions and large data warehouses. Instead of ungrounded text-to-SQL or LLM-hallucinated math, Atlas routes questions to specialized deterministic data-science modules (Lookups, Anomaly Detection, Root-Cause/Driver Decomposition, and Predictive Churn), generates SQL strictly constrained to an authorized active workspace schema, validates queries via Abstract Syntax Tree (AST) execution gates, and outputs evidence-backed findings.


Key Capabilities
Grounded Intent Routing: Classifies complex business queries into deterministic modules (lookup, anomaly, drivers, churn, clarify, refuse).

Hybrid Schema Retrieval: BM25 lexical search combined with dense MiniLM vector embeddings and Reciprocal Rank Fusion (RRF) over warehouse metadata and certified join-graphs.

Workspace Isolation: Generates SQL against an explicit context-bound active schema workspace, preventing hallucinated tables and columns.

AST Validation & Auto-Repair: Enforces SELECT-only semantics, role-based allowlists, and join boundaries using SQLGlot AST validation, with up to 2 automated repair attempts before graceful refusal.

Deterministic Code/ML Analytics: LLMs never perform arithmetic. Anomalies are scored via Median Absolute Deviation (MAD) robust z-scores; drivers are decomposed via exposure-shift algorithms; churn is predicted via calibrated gradient boosting.

Evidence-Backed Synthesis: Final answers separate correlation from causation, linking every stated metric directly to executed query outputs.

System Architecture & Workflow
Plaintext
User Question
    │
    ▼
[API Gateway / FastAPI] ──► PII Scrubbing & Trace ID Generation
    │
    ▼
[Intent & Route Parser] ──► Rules + LLM Fallback (Lookup / Anomaly / Drivers / Churn / Refuse)
    │
    ▼
[Hybrid Schema Retrieval] ─► BM25 + MiniLM + RRF Join-Graph Search
    │
    ▼
[Workspace Builder] ──────► Assemble certified tables, columns, and metric registry
    │
    ▼
[SQL Planner] ────────────► Constrained JSON Query Plan (Workspace-only)
    │
    ▼
[SQLGlot AST Validator] ──► Enforce SELECT-only, check allowlists (≤2 repairs or refuse)
    │
    ▼
[DuckDB Warehouse] ───────► Read-only execution with role caps
    │
    ▼
[Deterministic ML Engine] ─► MAD Z-scores / Driver Decomposition / Churn Scoring
    │
    ▼
[Evidence Synthesis] ─────► Fact-checked explanation, query traces, and audit logs

Security & Guardrails
AST Read-Only Enforcement: Queries are parsed and verified using sqlglot. Operations including DROP, INSERT, UPDATE, DELETE, ALTER, and nested sub-query leaks are rejected before reaching the database.

No Database Writes: The DuckDB connection is initialized with read-only flags (read_only=True).

Strict Refusal Mechanism: Questions targeting non-existent fields, uncertified calculations, or restricted columns (e.g., PII) return deterministic refusals and offer narrower, supported lookups instead of fabricating responses.