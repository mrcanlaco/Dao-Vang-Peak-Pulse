# 🏛️ DAO VANG (PeakPulse AI) — System Architecture

Welcome to the **DAO VANG (PeakPulse AI)** architectural documentation. This document provides an end-to-end technical overview of how the system ingests data, engineers features, calibrates predictive models, scans live cryptocurrency futures, and delivers signals to users.

---

## 🧭 1. Core Architectural Tenets

1. **Zero Lookahead Bias (Strict Point-in-Time Correctness):**
   - For any candle timestamp $t$, feature calculations and inference strictly consume only information available at or before $t$.
   - Time-series joins are strictly performed via DuckDB `as-of` matching.
2. **Deterministic Data & Query Engine:**
   - Powered by **DuckDB** and **Apache Parquet**, allowing sub-second columnar scans over hundreds of thousands of candles across 150+ trading pairs.
3. **Frozen Model Bundles & Out-of-fold Calibration:**
   - Inference models are versioned, serialized, and calibrated with Out-of-fold/Isotonic regression to ensure predicted probability accurately reflects empirical distribution frequency (ECE $\le 0.05$).
4. **Human-in-the-Loop (Analytical Radar, No Auto-Trading):**
   - The platform serves as an early-warning signal radar. It does not execute automatic market orders.

---

## 🔄 2. End-to-End Dataflow & Pipeline

```mermaid
flowchart TD
    subgraph DataIngestion["1. Data Ingestion & Storage"]
        BinanceAPI["Binance USD-M Futures REST"]
        Collectors["Data Collectors (Klines, OI, Funding, Taker, Ratios)"]
        DuckDBStorage[("DuckDB & Parquet Storage")]
        BinanceAPI --> Collectors --> DuckDBStorage
    end

    subgraph FeatureLabel["2. Features & Ground Truth"]
        DuckDBStorage --> FeatureRegistry["Feature Registry & Builders"]
        DuckDBStorage --> LabelEngine["Label Engine (Distribution 8% drop / MAE <= 4%)"]
        FeatureRegistry --> FeatureMatrix["Point-in-Time Feature Matrix"]
    end

    subgraph MLValidation["3. ML Training & Validation"]
        FeatureMatrix --> WFValidation["Walk-Forward Splitter (Zero Leakage)"]
        LabelEngine --> WFValidation
        WFValidation --> ModelTraining["Model Training & Calibration (ECE <= 0.05)"]
        ModelTraining --> FrozenBundle[("Frozen Model Bundle")]
    end

    subgraph LiveDaemon["4. 24/7 Live Scanner Daemon"]
        LiveScan["Live 5m Cycle Scanner"]
        CandFilter["Candidate Filter v2 & Pump Filter"]
        Scorer["Distribution Scorer & BTC Context Scorer"]
        AnomalyRadar["Independent Market Anomaly Radar"]
        OutcomeTracker["PnL & Empirical Precision Tracker"]
        
        LiveScan --> CandFilter
        CandFilter --> Scorer
        CandFilter --> AnomalyRadar
        FrozenBundle -.-> Scorer
        Scorer --> OutcomeTracker
    end

    subgraph Delivery["5. Signal Delivery & UI"]
        Scorer -->|Quality Gate Passed (>= 70%)| TelegramBot["Telegram Alert Bot (VI/EN)"]
        Scorer --> HttpServer["ThreadingHTTPServer REST API"]
        AnomalyRadar --> HttpServer
        HttpServer --> ReactUI["React 19 + TypeScript + Vite Web Dashboard"]
    end
```

---

## 📂 3. Source Code Organization (`src/dao_vang/`)

The backend follows a **Modular Monolith** pattern organized cleanly by domain and functionality:

| Module Directory | Responsibility | Key Classes / Entrypoints |
| :--- | :--- | :--- |
| [`domain/`](file:///d:/Coding/dao_vang/src/dao_vang/domain) | Core domain types, enumerations, error definitions, and timezone-aware datetime helpers. | `DistributionEvent`, `MarketRegime`, `AppError` |
| [`config/`](file:///d:/Coding/dao_vang/src/dao_vang/config) | Pydantic v2 settings loading from `.env` and `configs/live.yaml`. | `AppSettings`, `get_settings()` |
| [`logging/`](file:///d:/Coding/dao_vang/src/dao_vang/logging) | Structured JSON/Console logging with automated sensitive secret redaction. | `get_logger()`, `redact_secrets()` |
| [`data/`](file:///d:/Coding/dao_vang/src/dao_vang/data) | Ingestion clients (Binance USD-M, Binance Agent OS token data, optional CoinGecko price cross-reference), schemas, data quality validation, and DuckDB storage. | `BinanceClient`, `KlinesCollector`, `DuckDBStorage` |
| [`features/`](file:///d:/Coding/dao_vang/src/dao_vang/features) | Point-in-time feature builders for Price, Open Interest, Funding Rate, Taker Volume, and Top Trader Ratios. | `FeatureRegistry`, `PriceFeatureBuilder`, `OIFeatureBuilder` |
| [`labels/`](file:///d:/Coding/dao_vang/src/dao_vang/labels) | Ground-truth labeling engine (identifying distribution tops: $\ge 8\%$ drop within 6-24h, MAE $\le 4\%$). | `LabelEngineV1`, `DistributionShortSpec` |
| [`baselines/`](file:///d:/Coding/dao_vang/src/dao_vang/baselines) | Rule-based heuristics and logistic regression baseline models for performance comparison. | `RuleBasedBaseline`, `LogisticBaseline` |
| [`validation/`](file:///d:/Coding/dao_vang/src/dao_vang/validation) | Strict Walk-Forward validation, embargo splitting, data leakage audits, and Brier / ECE calibration metrics. | `WalkForwardSplitter`, `LeakageAuditor`, `CalibrationMetrics` |
| [`experiments/`](file:///d:/Coding/dao_vang/src/dao_vang/experiments) | ML training runner, forward testing, ablation studies, and automated self-learning feedback loops. | `ExperimentRunner`, `SelfLearningDaemon` |
| [`scoring/`](file:///d:/Coding/dao_vang/src/dao_vang/scoring) | Live scoring engine combining Frozen ML model probabilities, BTC Macro context, and evidence explanations (SHAP). | `DistributionScorer`, `BTCContextScorer`, `EvidenceGenerator` |
| [`scanner/`](file:///d:/Coding/dao_vang/src/dao_vang/scanner) | 24/7 background scanner daemon, pump pattern detector, independent Market Anomaly Radar, Candidate Filter v2, watchlist manager, and signal outcome tracking. | `ScannerDaemon`, `PumpFilter`, `MarketAnomaly`, `TrackingWatchlist`, `CandidateFilterV2` |
| [`alerts/`](file:///d:/Coding/dao_vang/src/dao_vang/alerts) | Telegram alert delivery manager, bilingual message formatting (Vietnamese/English), and alert dedup store. | `TelegramAlertManager`, `AlertStore` |
| [`alpha_lab/`](file:///d:/Coding/dao_vang/src/dao_vang/alpha_lab) | Advanced alpha research module: Triple Barrier method, Meta-Labeling, Market Regime classification, Drift Guardian. | `AlphaBacktester`, `DriftGuardian`, `RegimeClassifier` |
| [`reports/`](file:///d:/Coding/dao_vang/src/dao_vang/reports) | HTML / Markdown summary report generator for backtest benchmarks and live operational audits. | `ReportGenerator` |
| [`web/`](file:///d:/Coding/dao_vang/src/dao_vang/web) | Custom threaded HTTP server providing REST endpoints and static frontend files. | `api_server.py`, `run.py` |
| [`cli/`](file:///d:/Coding/dao_vang/src/dao_vang/cli) | Typer CLI commands for manual data collection, backtesting, scanning, and model training. | `main.py` (`dao-vang`) |

---

## 💻 4. Frontend Architecture (`frontend/`)

The Web Dashboard is built with **React 19 + TypeScript + Vite**:

- **`src/components/MainWorkspace.tsx`**: Main trading cockpit containing interactive candlestick charts, live metrics (OI 24h, Funding, Taker Sell %, RSI), risk ratings, and deep analysis accordion.
- **`src/components/Sidebar.tsx`**: Navigation menu for Dashboard, Live Scanner, Signals Feed, Watchlist, Alpha Lab, and System Settings.
- **`src/components/SignalFeed.tsx`**: Polling-refreshed signal stream with hit/miss outcome badges, lead-time stats, and quick filtering.
- **`src/components/WatchlistPanel.tsx`**: Polling-refreshed watchlist tracking symbols under accumulation/distribution observation.
- **`src/components/AlphaLab.tsx`**: Visual research workbench for running Triple Barrier backtests, regime audits, and SHAP feature attribution.

---

## 🗄️ 5. Storage & Database Schema

DAO VANG utilizes a dual storage strategy:
1. **DuckDB Database (`dev.duckdb` / `live.duckdb`):**
   - Tables: `kline`, `open_interest`, `funding_rate`, `taker_ratio`, `top_position_ratio`, `scan_results`, `tracked_signals`, `alerts_sent`.
2. **Apache Parquet Files (`data/` / `data_live/`):**
   - Partitioned by `symbol/year/month` for high-throughput immutable historical storage.

---

## 🛡️ 6. Security & Operational Isolation

- **Separate Data Environments:** Development testing runs against `data/` and port `8000/5173`; Live production runs against `data_live/` and port `8001` or system services.
- **Credential Protection:** All tokens (Telegram API keys, webhooks) are loaded via environment variables and sanitized in all log outputs by `redact_secrets`.
