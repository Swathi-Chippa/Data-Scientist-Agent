# Subagent Architecture & Responsibilities (§F3)

The architecture delegates specialized analytical subtasks across bounded components:

| Subagent / Module | Type | Primary Function |
|---|---|---|
| **Guard** | Code | Pre-flight security, DDL/DML interception, and prompt injection filtering |
| **Router & Extractor** | Assisted | Multi-signal route classification and entity/slot extraction |
| **Planner** | Assisted | Ordered execution planning validated against `AnalystRegistry` |
| **Schema Retriever** | Assisted | Hybrid keyword/vector retrieval, join path finding, column pruning, and value linking |
| **SQL Compiler** | Code | Deterministic DuckDB compilation for pre-governed metrics |
| **SQL Generator** | Model | Schema-constrained query generation against allowlist only |
| **Validator** | Code | sqlglot AST verification, allowlist enforcement, and cost gating |
| **Repairer** | Model/Rules | Bounded 2-attempt error patching without schema widening |
| **Anomaly Analyst** | Code (Stats) | Robust median/MAD baseline, prediction intervals, Benjamini-Hochberg FDR control |
| **Driver Analyst** | Code (Stats) | Variance decomposition, bootstrap intervals, Difference-in-Differences check |
| **Risk Analyst** | Code (ML) | Chronological time-split churn modeling (GBDT), segment valuation |
| **Advisor** | Code | Multi-factor action ranking (`Impact × Confidence × Feasibility`) |
| **Evidence Ledger & Fact Checker**| Code | Claim numbering, numeric verification, and causal language enforcement |
