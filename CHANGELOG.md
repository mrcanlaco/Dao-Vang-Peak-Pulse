# Changelog

All notable changes to the Đảo Vàng project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc.1] - 2026-08-01

### Added
- **M1 (Raw Data Collection)**: Binance collectors for K-lines, Funding Rates, Global Accounts, and Top Accounts.
- **M2 (Data Normalization)**: DuckDB-based timeline alignment without pandas/polars.
- **M3 (Label Generation)**: Fixed-horizon, fixed-stop, and dynamic ATR labeling engine.
- **M4 (Feature Engineering)**: Price, Open Interest, Funding, and Taker features calculated via SQL.
- **M5 (Target Validation)**: Baseline rules, Logistic Regression walk-forward, calibration metrics, and leakage tests.
- **M6 (Shell Orchestration)**: CLI application using `typer` to orchestrate data, labels, features, experiments, and reports.

### Changed
- Refactored all pipelines to use pure Python + DuckDB.
- Maintained zero dependency on Pandas/Polars throughout the codebase.

### Fixed
- Fixed data leakage in target generation and timeline stitching by using deterministic `ASOF` joins and shifted metrics.
