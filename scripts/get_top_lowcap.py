import duckdb
import pandas as pd
import joblib
import numpy as np
from pathlib import Path
import os
import sys

# Append src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.experiments.forward_test import load_frozen_model

DB_PATH = "D:/Quant-trading/data_lake/quant_master.duckdb"
MODEL_ID = "frozen_20260906_105716_bc3c369b"
ARTIFACT_DIR = Path("artifacts")

def get_top_coins():
    print("Connecting to DB...")
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    max_time = conn.execute("SELECT MAX(close_time) FROM klines_5m").fetchone()[0]
    
    # Get low cap coins
    query_lc = """
    SELECT symbol, SUM(quote_volume) / 365.0 as avg_daily_vol
    FROM klines_5m
    WHERE close_time >= ? - INTERVAL '365 days'
    GROUP BY symbol
    HAVING avg_daily_vol >= 10000000 AND avg_daily_vol <= 500000000
    """
    lowcap_coins = [r[0] for r in conn.execute(query_lc, [max_time]).fetchall()]
    
    # Process symbol chunk logic from run_lowcap_backtest
    sym_sql = ", ".join(repr(s) for s in lowcap_coins)
    
    query_data = f"""
    WITH k AS (
        SELECT symbol, close_time AS feature_time, open, high, low, close, volume, quote_volume, taker_buy_volume,
               (close - open) / NULLIF(open, 0) AS return_5m, (high - low) / NULLIF(open, 0) AS volatility_5m
        FROM klines_5m WHERE symbol IN ({sym_sql}) AND close_time >= ? - INTERVAL '365 days'
    ),
    m AS (
        SELECT symbol, timestamp, open_interest AS oi_contracts, top_trader_account_ratio AS top_acct_ratio,
               global_account_ratio AS global_ls_ratio, taker_buy_sell_ratio AS taker_bs_ratio
        FROM metrics_5m WHERE symbol IN ({sym_sql}) AND timestamp >= ? - INTERVAL '365 days'
    ),
    f AS (
        SELECT symbol, funding_time, funding_rate
        FROM funding_history WHERE symbol IN ({sym_sql}) AND funding_time >= ? - INTERVAL '365 days'
    ),
    km AS (
        SELECT k.*, m.oi_contracts, m.top_acct_ratio, m.global_ls_ratio, m.taker_bs_ratio
        FROM k LEFT JOIN m ON k.symbol = m.symbol AND k.feature_time = m.timestamp
    )
    SELECT km.*, f.funding_rate
    FROM km LEFT JOIN f ON km.symbol = f.symbol AND km.feature_time = f.funding_time
    """
    
    print("Fetching data...")
    df = conn.execute(query_data, [max_time, max_time, max_time]).fetchdf()
    
    float_cols = df.select_dtypes(include=["float64"]).columns
    df[float_cols] = df[float_cols].astype("float32")
    df["funding_rate_raw"] = df["funding_rate"].fillna(0.0)
    df["volatility_24h"] = df.groupby("symbol")["return_5m"].transform(lambda x: x.rolling(288, min_periods=10).std())
    df["return_1h"] = df.groupby("symbol")["close"].transform(lambda x: x.pct_change(12))
    df["return_4h"] = df.groupby("symbol")["close"].transform(lambda x: x.pct_change(48))
    df["return_24h"] = df.groupby("symbol")["close"].transform(lambda x: x.pct_change(288))
    df["taker_ratio"] = df["taker_buy_volume"] / df["volume"].replace(0, 1)
    df["vol_surge_24h"] = df["volume"] / df.groupby("symbol")["volume"].transform(lambda x: x.rolling(288, min_periods=10).mean()).replace(0, 1)
    df["oi_change_1h"] = df.groupby("symbol")["oi_contracts"].transform(lambda x: x.pct_change(12))
    df["oi_change_4h"] = df.groupby("symbol")["oi_contracts"].transform(lambda x: x.pct_change(48))

    future_low = df.groupby("symbol")["low"].transform(lambda x: x.iloc[::-1].rolling(144, min_periods=10).min().iloc[::-1])
    future_high = df.groupby("symbol")["high"].transform(lambda x: x.iloc[::-1].rolling(144, min_periods=10).max().iloc[::-1])

    max_dd = (future_low - df["close"]) / df["close"]
    max_mae = (future_high - df["close"]) / df["close"]
    df["label"] = ((max_dd <= -0.08) & (max_mae <= 0.04)).astype(int)

    df["is_candidate"] = (df["return_24h"] >= 0.08) | (df["funding_rate_raw"] > 0.0002)
    df_cand = df[df["is_candidate"] == True].copy()
    
    core_req = ["return_5m", "volatility_5m", "return_1h", "return_4h", "return_24h", "label"]
    df_cand = df_cand.dropna(subset=core_req).sort_values("feature_time").reset_index(drop=True)
    
    print("Loading model...")
    model_dir = ARTIFACT_DIR / "frozen_models" / MODEL_ID
    frozen_info = load_frozen_model(MODEL_ID, ARTIFACT_DIR)
    threshold = 0.41 # using the optimal threshold
    
    pipeline = joblib.load(model_dir / "model.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib") if (model_dir / "calibrator.joblib").exists() else None
    
    feature_cols = list(frozen_info.feature_cols)
    X = df_cand[feature_cols].replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0) # Simple imputation just to not crash
    
    print("Predicting...")
    raw_probs = pipeline.predict_proba(X)[:, 1]
    if calibrator:
        calibrated_probs = calibrator.transform(raw_probs)
    else:
        calibrated_probs = raw_probs
        
    df_cand["prob"] = calibrated_probs
    df_cand["pred"] = (df_cand["prob"] >= threshold).astype(int)
    
    # Filter only signals that the model actually triggered
    triggered = df_cand[df_cand["pred"] == 1].copy()
    
    print("Calculating stats per coin...")
    stats = triggered.groupby("symbol").agg(
        total_signals=("label", "count"),
        wins=("label", "sum")
    )
    stats["win_rate"] = stats["wins"] / stats["total_signals"]
    
    # Filter out coins with too few signals to avoid 100% win rate on 1 trade
    stats = stats[stats["total_signals"] >= 10]
    stats = stats.sort_values("win_rate", ascending=False)
    
    print("\n--- TOP LOW-CAP COINS BY WIN RATE ---")
    for idx, (sym, row) in enumerate(stats.head(20).iterrows(), 1):
        print(f"{idx:2d}. {sym:12s} | Winrate: {row['win_rate']*100:5.2f}% | Lệnh thắng: {row['wins']:3.0f}/{row['total_signals']:3.0f}")

if __name__ == "__main__":
    get_top_coins()
