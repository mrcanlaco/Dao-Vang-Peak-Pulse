# MASTER BACKLOG — PHASE 2 MVP

## M0 — Repository Foundation

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M0-FOUND-001 | Scaffold Python project | P0 | - |
| M0-DOMAIN-001 | Core domain types and errors | P0 | M0-FOUND-001 |
| M0-CONFIG-001 | Typed configuration system | P0 | M0-FOUND-001 |
| M0-LOG-001 | Structured logging | P1 | M0-FOUND-001 |
| M0-CI-001 | CI quality gates | P0 | M0-FOUND-001 |
| M0-CLI-001 | CLI skeleton | P1 | M0-CONFIG-001 |

## M1 — Storage and Source Client

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M1-STORAGE-001 | Atomic filesystem and checksums | P0 | M0-DOMAIN-001 |
| M1-MANIFEST-001 | Collection/dataset manifests | P0 | M1-STORAGE-001 |
| M1-BINANCE-001 | Binance USD-M HTTP client | P0 | M0-CONFIG-001, M0-LOG-001 |
| M1-KLINES-001 | Klines collector | P0 | M1-BINANCE-001, M1-STORAGE-001 |
| M1-FUNDING-001 | Funding collector | P0 | M1-BINANCE-001, M1-STORAGE-001 |
| M1-OI-001 | Open interest history collector | P0 | M1-BINANCE-001, M1-STORAGE-001 |
| M1-TAKER-001 | Taker ratio collector | P0 | M1-BINANCE-001, M1-STORAGE-001 |
| M1-RATIOS-001 | Global/top trader ratio collectors | P0 | M1-BINANCE-001, M1-STORAGE-001 |

## M2 — Normalize, Quality and Alignment

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M2-SCHEMA-001 | Pydantic normalized schemas | P0 | M0-DOMAIN-001 |
| M2-NORM-001 | Normalizers for all MVP data | P0 | M2-SCHEMA-001, M1 collectors |
| M2-QUALITY-001 | Data quality engine | P0 | M2-NORM-001 |
| M2-PARQUET-001 | Normalized Parquet writer | P0 | M2-NORM-001, M1-STORAGE-001 |
| M2-DUCKDB-001 | DuckDB query layer | P1 | M2-PARQUET-001 |
| M2-ALIGN-001 | Canonical timeline and exact joins | P0 | M2-QUALITY-001 |
| M2-ASOF-001 | Backward as-of funding join | P0 | M2-ALIGN-001 |
| M2-DATASET-001 | Dataset builder and fingerprint | P0 | M2-ASOF-001, M1-MANIFEST-001 |

## M3 — Label Engine

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M3-LABEL-MODEL-001 | Label result models | P0 | M0-DOMAIN-001 |
| M3-LABEL-001 | Distribution Label v0.1 engine | P0 | M3-LABEL-MODEL-001, M2-DATASET-001 |
| M3-LABEL-QA-001 | Label diagnostics and edge-case suite | P0 | M3-LABEL-001 |

## M4 — Feature Engine

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M4-FEATURE-REG-001 | Feature registry/version model | P0 | M0-DOMAIN-001 |
| M4-PRICE-001 | Price features | P0 | M4-FEATURE-REG-001, M2-DATASET-001 |
| M4-FUNDING-001 | Funding features | P0 | M4-FEATURE-REG-001, M2-DATASET-001 |
| M4-OI-001 | Open interest features | P0 | M4-FEATURE-REG-001, M2-DATASET-001 |
| M4-TAKER-001 | Taker features | P0 | M4-FEATURE-REG-001, M2-DATASET-001 |
| M4-RATIOS-001 | Ratio features | P0 | M4-FEATURE-REG-001, M2-DATASET-001 |
| M4-FEATURESET-001 | Feature table builder | P0 | M4 feature tasks |

## M5 — Baselines and Validation

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M5-SPLIT-001 | Chronological split and embargo | P0 | M4-FEATURESET-001, M3-LABEL-001 |
| M5-METRICS-001 | Metrics and event-level cooldown | P0 | M5-SPLIT-001 |
| M5-BASELINE-RULES-001 | Rule baselines B0–B4 | P0 | M5-METRICS-001 |
| M5-LOGREG-001 | Logistic regression baseline | P0 | M5-SPLIT-001 |
| M5-CALIBRATION-001 | Calibration metrics and curves | P1 | M5-LOGREG-001 |
| M5-WALKFORWARD-001 | Walk-forward runner | P0 | M5 baseline tasks |
| M5-BOOTSTRAP-001 | Confidence intervals | P1 | M5-METRICS-001 |
| M5-LEAKAGE-001 | Full leakage audit suite | P0 | M5-WALKFORWARD-001 |

## M6 — Experiment and Reporting

| ID | Task | Priority | Depends |
|---|---|---:|---|
| M6-EXPERIMENT-001 | Experiment config and runner | P0 | M5-WALKFORWARD-001 |
| M6-ARTIFACT-001 | Artifact registry | P0 | M6-EXPERIMENT-001 |
| M6-REPORT-001 | Markdown/JSON experiment report | P0 | M6-ARTIFACT-001 |
| M6-CLI-001 | End-to-end CLI commands | P0 | M6-REPORT-001 |
| M6-E2E-001 | End-to-end smoke test | P0 | M6-CLI-001 |
| M6-MVP-RC-001 | MVP release candidate evidence | P0 | M6-E2E-001, M5-LEAKAGE-001 |

## Phase 3 — Documentation v1.1

| ID | Task | Depends |
|---|---|---|
| P3-DOC-AUDIT-001 | Compare docs vs implementation | M6-MVP-RC-001 |
| P3-ADR-001 | Record implementation decisions | P3-DOC-AUDIT-001 |
| P3-DOC-UPDATE-001 | Publish Documentation v1.1 | P3-ADR-001 |
