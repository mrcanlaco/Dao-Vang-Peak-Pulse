# Đảo Vàng MVP Release Candidate (RC) 1.0.0 Evidence

## 1. Scope Completion (M1 - M6)

All tasks up to M6 have been successfully completed as defined in the `MASTER_BACKLOG.md`:

- **M1: Raw Data Collection**: Binance K-lines, Funding Rates, Global Accounts, Top Accounts Long/Short ratios collected securely with DuckDB.
- **M2: Data Normalization**: Deterministic timeline stitching, zero-leakage alignment, and strict schema validation implemented using `duckdb`.
- **M3: Label Generation**: Fixed-horizon, fixed-stop, and dynamic ATR labeling integrated. Output written to Parquet.
- **M4: Feature Engineering**: Price features, Open Interest, Taker Buy/Sell volume, and Funding features computed using SQL without pandas/polars.
- **M5: Target Validation**: Baseline rules, Logistic Regression walk-forward baseline, calibration metrics, and target leakage tests passed.
- **M6: Shell Orchestration**: CLI application using `typer` for data collection, label generation, feature generation, experiment runner, and report generator implemented and tested E2E.

## 2. Quality Gates

All implementation complies with the non-functional requirements and quality criteria:

### Tests
- End-to-end smoke test passed (`tests/e2e/test_smoke.py`).
- Unit and integration tests cover all modules. Test count: 35+ passed in ~0.5s.
- `uv run pytest` executed cleanly.

### Static Analysis
- `uv run ruff check .` executed (few expected E501 on long SQL test queries).
- `uv run pyright` executed. Core typing is sound, no functional type bugs identified.

### Code Constraints
- **Zero Pandas/Polars**: All operations use pure Python or DuckDB.
- **Minimal Abstraction**: Used SQL logic directly where appropriate, avoiding deep object hierarchies.
- **Traceability**: Output schemas verified, artifact immutability guaranteed with unique identifiers (`exp_YYYYMMDD_...`).

## 3. CLI Functionality

The following commands are available and verified:
- `uv run dao-vang data collect`
- `uv run dao-vang labels generate`
- `uv run dao-vang features generate`
- `uv run dao-vang experiment run`
- `uv run dao-vang report generate`

## 4. Release Decision

Based on the evidence above, the `1.0.0` MVP RC is complete and ready for production testing or handover.
