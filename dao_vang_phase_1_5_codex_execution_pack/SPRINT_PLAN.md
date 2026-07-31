# SPRINT PLAN

## Sprint M0 — Foundation

### Wave 1
- M0-FOUND-001

### Wave 2
- M0-DOMAIN-001
- M0-CONFIG-001
- M0-LOG-001
- M0-CI-001

### Wave 3
- M0-CLI-001

Exit gate: repo scaffold, lint/type/test/CI pass.

## Sprint M1 — Raw Data

### Wave 1
- M1-STORAGE-001
- M1-BINANCE-001

### Wave 2
- M1-MANIFEST-001
- M1-KLINES-001
- M1-FUNDING-001

### Wave 3
- M1-OI-001
- M1-TAKER-001
- M1-RATIOS-001

Exit gate: all collectors idempotent, raw-before-normalize, contract tests pass.

## Sprint M2 — Normalized Dataset

### Wave 1
- M2-SCHEMA-001
- M2-PARQUET-001

### Wave 2
- M2-NORM-001
- M2-QUALITY-001

### Wave 3
- M2-DUCKDB-001
- M2-ALIGN-001

### Wave 4
- M2-ASOF-001
- M2-DATASET-001

Exit gate: point-in-time aligned dataset with fingerprint.

## Sprint M3 — Labels

### Wave 1
- M3-LABEL-MODEL-001

### Wave 2
- M3-LABEL-001

### Wave 3
- M3-LABEL-QA-001

Exit gate: Label v0.1 deterministic and all edge cases pass.

## Sprint M4 — Features

### Wave 1
- M4-FEATURE-REG-001

### Wave 2
- M4-PRICE-001
- M4-FUNDING-001
- M4-OI-001

### Wave 3
- M4-TAKER-001
- M4-RATIOS-001

### Wave 4
- M4-FEATURESET-001

Exit gate: feature table and future-insertion invariance pass.

## Sprint M5 — Validation

### Wave 1
- M5-SPLIT-001
- M5-METRICS-001

### Wave 2
- M5-BASELINE-RULES-001
- M5-LOGREG-001

### Wave 3
- M5-CALIBRATION-001
- M5-BOOTSTRAP-001

### Wave 4
- M5-WALKFORWARD-001
- M5-LEAKAGE-001

Exit gate: walk-forward and leakage report.

## Sprint M6 — MVP Integration

### Wave 1
- M6-EXPERIMENT-001
- M6-ARTIFACT-001

### Wave 2
- M6-REPORT-001
- M6-CLI-001

### Wave 3
- M6-E2E-001

### Wave 4
- M6-MVP-RC-001

Exit gate: one-command MVP run and evidence package.
