# Changelog

All notable changes to the Đảo Vàng project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0-rc.2] - 2026-08-27

### Changed
- Synchronized backend, frontend, and version-history reporting on the `2.0.0-rc.2` release candidate.
- Disabled live Git updates by default and removed automatic destructive checkout recovery.
- Updated the CI frontend job to use Node 22, the lockfile cache, and `npm ci`.

### Security
- Replaced plaintext password headers, query parameters, localStorage persistence, and cookies with a short-lived signed `HttpOnly` session cookie.
- Added opt-in CORS allowlisting and baseline response security headers.
- Added login attempt throttling and fail-closed behavior when no access password is configured.

### Model contract
- The active frozen bundle remains `frozen_20260811_082824_96df7ec9` with `distribution_short_v1`, 24-hour horizon, 25 serving features, and 0.60 high-confidence / 0.45 watch thresholds.
- Bundles using `identity_v1` calibration now fail closed for alerting until a fitted calibration artifact is supplied and validated.

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
