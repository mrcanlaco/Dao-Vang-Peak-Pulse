import duckdb
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import datetime, timedelta
from sklearn.impute import SimpleImputer
import time

def _fold_boundaries(start_dt, end_dt, n_folds=10, warmup_days=60):
    total_duration = end_dt - start_dt
    fold_duration = total_duration / n_folds
    boundaries = []
    for i in range(n_folds):
        t_start = start_dt + i * fold_duration
        if i == n_folds - 1:
            t_end = end_dt
        else:
            t_end = start_dt + (i + 1) * fold_duration
        boundaries.append({
            "test_start": t_start,
            "test_end": t_end
        })
    return boundaries

def simulate_trade_strategy(
    highs, lows, closes, entry_price, fee=0.0020,
    dca_pump_pct=0.12, sl_pct=0.15, tp_pct=0.35, time_limit_bars=288
):
    n_bars = len(highs)
    if n_bars == 0 or entry_price <= 0: return -fee

    dca_filled = False
    p_dca = entry_price * (1.0 + dca_pump_pct)

    for b in range(min(864, n_bars)):
        curr_high = highs[b]
        curr_low = lows[b]

        if not dca_filled:
            if curr_high >= entry_price * (1.0 + sl_pct): return 0.5 * (-sl_pct) - fee
            if curr_low <= entry_price * (1.0 - tp_pct): return 0.5 * tp_pct - fee
            if curr_high >= p_dca:
                dca_filled = True
                avg_entry = (entry_price + p_dca) / 2.0
                target_price_full = avg_entry * (1.0 - tp_pct)
                sl_price_full = entry_price * (1.0 + sl_pct)
        else:
            if curr_high >= sl_price_full:
                loss_pct = (sl_price_full - avg_entry) / avg_entry
                return -loss_pct - fee
            if curr_low <= target_price_full:
                return tp_pct - fee
                
        if b == time_limit_bars - 1:
            current_drop = (avg_entry - closes[b]) / avg_entry if dca_filled else (entry_price - closes[b]) / entry_price
            if current_drop < 0.02:
                if dca_filled: return (avg_entry - closes[b]) / avg_entry - fee
                else: return 0.5 * ((entry_price - closes[b]) / entry_price) - fee

    if dca_filled: return (avg_entry - closes[863]) / avg_entry - fee
    else: return 0.5 * ((entry_price - closes[863]) / entry_price) - fee

def evaluate_signals(df_signals, sym_klines, params):
    total_profit = 0.0
    total_loss = 0.0
    
    for row in df_signals.itertuples():
        sym = row.symbol
        t_sig = row.feature_time.to_datetime64()
        entry = row.close
        
        k = sym_klines.get(sym)
        if not k: continue
            
        times = k["times"]
        idx = np.searchsorted(times, t_sig)
        if idx >= len(times) - 1: continue
            
        idx += 1
        highs = k["high"][idx:idx+864]
        lows = k["low"][idx:idx+864]
        closes = k["close"][idx:idx+864]
        
        pnl = simulate_trade_strategy(highs, lows, closes, entry, **params)
        
        if pnl > 0: total_profit += pnl
        else: total_loss += abs(pnl)
            
    pf = total_profit / total_loss if total_loss > 0 else 999.0
    expected_return = (total_profit - total_loss) / len(df_signals) if len(df_signals) > 0 else 0
    return pf, expected_return, len(df_signals)

def main():
    print("1. Loading features...")
    df = pd.read_parquet('artifacts/lowcap_dual_features_cache.parquet')
    feature_cols = [c for c in df.columns if c not in ["symbol", "feature_time", "close", "label_20_10"]]
    
    as_of = df["feature_time"].max()
    window_start = df["feature_time"].min()
    evaluation_end = as_of - pd.Timedelta(hours=72)
    embargo = timedelta(hours=48)
    boundaries = _fold_boundaries(window_start, evaluation_end, n_folds=10)
    
    print("2. Running Walk-Forward LightGBM to generate probabilities...")
    oos_records = []
    
    for fold_idx, b in enumerate(boundaries, start=1):
        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < (b["test_start"] - embargo))].copy()
        test = df[(df["feature_time"] >= b["test_start"]) & (df["feature_time"] < b["test_end"])].copy()
        
        if len(train) < 200 or len(test) == 0: continue
        
        y_fit = train["label_20_10"].astype(int).to_numpy()
        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(train[feature_cols])
        x_test = imputer.transform(test[feature_cols])
        
        lgb_model = lgb.LGBMClassifier(
            random_state=42 + fold_idx, n_estimators=200, learning_rate=0.05,
            max_depth=5, num_leaves=31, subsample=0.8, colsample_bytree=0.8,
            deterministic=True, force_col_wise=True, verbosity=-1, n_jobs=2
        )
        lgb_model.fit(x_fit, y_fit)
        
        test["prob"] = lgb_model.predict_proba(x_test)[:, 1]
        oos_records.append(test[["symbol", "feature_time", "close", "prob"]])
        print(f"   Fold {fold_idx}/10 complete.")
        
    oos_df = pd.concat(oos_records, ignore_index=True)
    oos_df["feature_time"] = pd.to_datetime(oos_df["feature_time"], utc=True)
    
    print("3. Loading duckdb price data...")
    db_path = r"D:\Quant-trading\data_lake\quant_master.duckdb"
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.register("sym_df", pd.DataFrame({"symbol": oos_df['symbol'].unique().tolist()}))
    klines_df = conn.execute("""
        SELECT k.symbol, k.close_time, k.high, k.low, k.close
        FROM klines_5m k
        INNER JOIN sym_df s ON k.symbol = s.symbol
        WHERE k.close_time >= '2025-08-25' AND k.close_time <= '2026-09-01'
        ORDER BY k.symbol, k.close_time ASC
    """).fetchdf()
    conn.close()
    
    sym_klines = {}
    for sym, g in klines_df.groupby("symbol"):
        sym_klines[sym] = {
            "times": g["close_time"].dt.tz_convert("UTC").values,
            "high": g["high"].values.astype(np.float32),
            "low": g["low"].values.astype(np.float32),
            "close": g["close"].values.astype(np.float32),
        }
        
    print("4. Sweeping Thresholds and Money Management...")
    # Test strict thresholds
    quantiles = [0.98, 0.985, 0.99, 0.992, 0.995] 
    
    # Best MM params from previous test
    mm_configs = [
        {'dca_pump_pct': 0.12, 'tp_pct': 0.35, 'sl_pct': 0.15, 'time_limit_bars': 288},
        {'dca_pump_pct': 0.10, 'tp_pct': 0.35, 'sl_pct': 0.15, 'time_limit_bars': 288},
        {'dca_pump_pct': 0.15, 'tp_pct': 0.40, 'sl_pct': 0.15, 'time_limit_bars': 288}
    ]
    
    results = []
    
    for q in quantiles:
        threshold = oos_df["prob"].quantile(q)
        sig_df = oos_df[oos_df["prob"] >= threshold]
        
        for mm in mm_configs:
            pf, er, trades = evaluate_signals(sig_df, sym_klines, mm)
            res = {'quantile': q, 'trades': trades, 'pf': pf, 'er': er, 'mm': mm}
            results.append(res)
            print(f"Top {100*(1-q):.1f}% | Trades: {trades} | PF: {pf:.4f} | ER: {er:.4f} | MM: {mm['dca_pump_pct']}/{mm['tp_pct']}")
            
    print("\n--- ULTIMATE OPTIMIZATION: TOP 5 ---")
    results.sort(key=lambda x: x['pf'], reverse=True)
    for i, r in enumerate(results[:5]):
        print(f"#{i+1} PF: {r['pf']:.4f} (Top {100*(1-r['quantile']):.1f}%) | Trades: {r['trades']} | ER: {r['er']:.4f}")
        print(f"   MM: DCA {r['mm']['dca_pump_pct']*100}% / TP {r['mm']['tp_pct']*100}% / SL {r['mm']['sl_pct']*100}%")

if __name__ == '__main__':
    main()
