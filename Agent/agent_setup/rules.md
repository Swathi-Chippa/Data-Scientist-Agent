# Coding Agent Setup & Development Rules (§F3)

This directory documents the coding agent pair-programming configuration, guidelines, and behavioral contracts used to build the Data Scientist Agent repository.

## 1. Core Principles
- **No Free-form Code Execution:** Models draft, choose, and explain; models NEVER execute arbitrary Python or SQL code in production. All statistical analyses are deterministic, tested registered functions.
- **Fail Closed (§E1):** A clear refusal naming what is missing is always preferred over an invented or ungrounded number.
- **Trace Everything in Files:** Every execution writes both a structured JSON file (`traces/*.json`) and a human-readable Markdown file (`traces/*.md`) to enable immediate auditability.
- **Strict Evidence Hierarchy (§B11):** Claims carry grades 0 to 4. Causal assertions without Grade 4 labels and explicit boundary limits are blocked before delivery.
