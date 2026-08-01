# ACTIVE WORK BOARD

## Sprint M0 — Foundation

Goal: Dựng repository Python có quality gates và module boundaries theo Documentation v1.0.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M0-FOUND-001 | Scaffold Python project | Codex-Integrator | merged | root, pyproject, src/tests skeleton | full | - | 651d174 |
| M0-DOMAIN-001 | Domain types/errors | Codex-Agent-A | merged | src/dao_vang/domain/*, tests/unit/domain/* | unit+type | M0-FOUND-001 | e2c3058 |
| M0-CONFIG-001 | Typed config | Codex-Agent-B | merged | src/dao_vang/config/*, tests/unit/config/* | unit+type | M0-FOUND-001 | 29deab1 |
| M0-LOG-001 | Structured logging | Codex-Agent-C | merged | src/dao_vang/logging/*, tests/unit/logging/* | unit | M0-FOUND-001 | f3fd9a7 |
| M0-CI-001 | CI workflow | Codex-Agent-D | merged | .github/workflows/* | CI | M0-FOUND-001 | 5b24b42 |
| M0-CLI-001 | CLI skeleton | Codex-Agent-A | merged | src/dao_vang/cli/*, tests/unit/cli/* | unit | M0-CONFIG-001 | ddedb7d |

## Sprint M1 — Raw Data

Goal: Xây dựng layer collection cho Binance USD-M, raw storage atomic, checksum, path policy.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M1-STORAGE-001 | Atomic storage/checksum | Codex-Integrator | merged | src/dao_vang/data/storage/* | unit | M0-DOMAIN-001 | 77d4baf |
| M1-BINANCE-001 | Binance HTTP client | Codex-Integrator | merged | src/dao_vang/data/collectors/binance_client.py | unit | M0-CONFIG-001 | 77d4baf |

| M1-MANIFEST-001 | Manifest models | Codex-Integrator | merged | src/dao_vang/data/manifest.py | unit | M1-STORAGE-001 | 9ef2c0f |
| M1-KLINES-001 | Klines collector | Codex-Integrator | merged | src/dao_vang/data/collectors/klines.py | unit | M1-BINANCE-001 | e7da9b0 |
| M1-FUNDING-001 | Funding collector | Codex-Integrator | merged | src/dao_vang/data/collectors/funding.py | unit | M1-BINANCE-001 | 5045288 |
| M1-OI-001 | Open interest collector | Codex-Integrator | merged | src/dao_vang/data/collectors/open_interest.py | unit | M1-BINANCE-001 | 0da2203 |
| M1-TAKER-001 | Taker ratio collector | Codex-Integrator | merged | src/dao_vang/data/collectors/taker.py | unit | M1-BINANCE-001 | 669f9ee |
| M1-RATIOS-001 | Global/top trader ratio collectors | Codex-Integrator | merged | src/dao_vang/data/collectors/ratios.py | unit | M1-BINANCE-001 | 92adb94 |

## Sprint M2 — Normalize, Quality and Alignment

Goal: Normalize raw JSON to typed models, apply quality filters, and store as canonical dataset.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M2-SCHEMA-001 | Pydantic normalized schemas | Codex-Integrator | merged | src/dao_vang/data/schemas.py | unit | M0-DOMAIN-001 | cb92482 |
| M2-NORM-001 | Normalizers for all MVP data | Codex-Integrator | merged | src/dao_vang/data/normalization/normalizers.py | unit | M2-SCHEMA-001 | 6a92dd4 |
| M2-QUALITY-001 | Data quality engine | Codex-Integrator | merged | src/dao_vang/data/quality.py | unit | M2-NORM-001 | 6038bc5 |
| M2-PARQUET-001 | Normalized Parquet writer | Codex-Integrator | merged | src/dao_vang/data/storage/parquet.py | unit | M2-NORM-001, M1-STORAGE-001 | 0a3ccac |
| M2-DUCKDB-001 | DuckDB query layer | Codex-Integrator | merged | src/dao_vang/data/storage/duckdb.py | unit | M2-PARQUET-001 | 781dfd7 |
| M2-ALIGN-001 | Canonical timeline and exact joins | Codex-Integrator | merged | src/dao_vang/data/timeline.py | unit | M2-QUALITY-001, M2-DUCKDB-001 | 781dfd7 |
| M2-ASOF-001 | Backward as-of funding join | Codex-Integrator | merged | src/dao_vang/data/timeline.py | unit | M2-ALIGN-001 | 781dfd7 |
| M2-DATASET-001 | Dataset builder and fingerprint | Codex-Integrator | merged | src/dao_vang/data/dataset.py | unit | M2-ASOF-001, M1-MANIFEST-001 | 781dfd7 |

## Sprint M3 — Label Engine

Goal: Gắn nhãn Distribution v0.1 với đầy đủ edge cases.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M3-LABEL-MODEL-001 | Label result models | Codex-Integrator | merged | src/dao_vang/labels/models.py | unit | M0-DOMAIN-001 | 781dfd7 |
| M3-LABEL-001 | Distribution Label v0.1 engine | Codex-Integrator | merged | src/dao_vang/labels/engine.py | unit | M3-LABEL-MODEL-001, M2-DATASET-001 | 781dfd7 |
| M3-LABEL-QA-001 | Label diagnostics and edge-case suite | Codex-Integrator | merged | tests/unit/labels/test_engine.py | unit | M3-LABEL-001 | 781dfd7 |

## Sprint M4 — Feature Engine

Goal: Xây dựng feature engine dựa trên DuckDB CTEs, loại bỏ Pandas/Polars.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M4-CORE-001 | Feature Registry & Models | Codex-Integrator | merged | src/dao_vang/features/models.py, registry.py | unit | M0-DOMAIN-001 | 5543fac |
| M4-PRICE-001 | Price Features | Codex-Integrator | merged | src/dao_vang/features/builders/price.py | unit | M4-CORE-001 | 5543fac |
| M4-FUNDING-001 | Funding Features | Codex-Integrator | merged | src/dao_vang/features/builders/funding.py | unit | M4-CORE-001 | 5543fac |
| M4-OI-001 | Open Interest Features | Codex-Integrator | merged | src/dao_vang/features/builders/open_interest.py | unit | M4-CORE-001 | 5543fac |
| M4-TAKER-001 | Taker Features | Codex-Integrator | merged | src/dao_vang/features/builders/taker.py | unit | M4-CORE-001 | 5543fac |
| M4-RATIOS-001 | Ratio Features | Codex-Integrator | merged | src/dao_vang/features/builders/ratios.py | unit | M4-CORE-001 | 5543fac |
| M4-FEATURESET-001 | Feature Table Builder | Codex-Integrator | merged | src/dao_vang/features/builder.py | unit | M4-PRICE-001, ... | 5543fac |

## Sprint M5 — Validation & Metrics

Goal: Chống leakage và thiết lập metrics.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M5-SPLIT-001 | Chronological split and embargo | Codex-Integrator | merged | src/dao_vang/validation/splits.py | unit | M4-FEATURESET-001 | e04dec9 |
| M5-METRICS-001 | Metrics and event-level cooldown | Codex-Integrator | merged | src/dao_vang/validation/metrics.py | unit | M5-SPLIT-001 | 44a47e0 |
| M5-BASELINE-RULES-001 | Rule baselines B0–B4 | Codex-Integrator | merged | src/dao_vang/baselines/rules.py | unit | M5-METRICS-001 | eaa77b3 |
| M5-LOGREG-001 | Logistic regression baseline | Codex-Integrator | merged | src/dao_vang/baselines/logistic.py | unit, leakage | M5-BASELINE-RULES-001 | dd6ce30 |
| M5-CALIBRATION-001 | Calibration metrics and curves | Codex-Integrator | merged | src/dao_vang/validation/calibration.py | unit | M5-LOGREG-001 | dae0f5d |
| M5-BOOTSTRAP-001 | Confidence intervals | Codex-Integrator | merged | src/dao_vang/validation/bootstrap.py | unit | M5-CALIBRATION-001 | d3e0718 |
| M5-WALKFORWARD-001 | Walk-forward runner | Codex-Integrator | merged | src/dao_vang/validation/walk_forward.py | unit | M5-BOOTSTRAP-001 | 0aaf429 |
| M5-LEAKAGE-001 | Full leakage audit suite | Codex-Integrator | merged | src/dao_vang/validation/leakage.py | unit | M5-WALKFORWARD-001 | c610b3b |

## Sprint M6 — Experiment and Reporting

Goal: Provide artifact registry, reporting and E2E CLI.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M6-EXPERIMENT-001 | Experiment config and runner | Codex-Integrator | merged | src/dao_vang/experiments/runner.py | unit | M5-WALKFORWARD-001 | 83d147b |

## Ownership rule

Mỗi file chỉ một owner trong cùng wave.

## Status values

`waiting`, `ready`, `in_progress`, `ready_for_review`, `changes_requested`, `merged`, `blocked`.
