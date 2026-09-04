import duckdb
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import datetime, timedelta
from sklearn.impute import SimpleImputer
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

FEATURE_COLS = [
    "return_5m", "volatility_5m", "volatility_24h", "return_1h", "return_4h",
    "return_24h", "funding_rate_raw", "taker_ratio", "vol_surge_24h",
    "oi_change_1h", "oi_change_4h", "top_acct_ratio", "global_ls_ratio", "taker_bs_ratio"
]

def simulate_trade_strategy(
    highs, lows, closes, entry_price, fee=0.0020,
    dca_pump_pct=0.12, sl_pct=0.15, tp_pct=0.35, time_limit_bars=288, is_time_stop=True
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
                return -(sl_price_full - avg_entry) / avg_entry - fee
            if curr_low <= target_price_full: return tp_pct - fee
                
        if is_time_stop and b == time_limit_bars - 1:
            current_drop = (avg_entry - closes[b]) / avg_entry if dca_filled else (entry_price - closes[b]) / entry_price
            if current_drop < 0.02:
                return ((avg_entry - closes[b]) / avg_entry - fee) if dca_filled else (0.5 * ((entry_price - closes[b]) / entry_price) - fee)

    # FIXED: using closes[-1] instead of hardcoded 863
    return ((avg_entry - closes[-1]) / avg_entry - fee) if dca_filled else (0.5 * ((entry_price - closes[-1]) / entry_price) - fee)

global_sym_klines = None
global_sig_dfs = None

def init_worker(klines_dict, dfs_dict):
    global global_sym_klines
    global global_sig_dfs
    global_sym_klines = klines_dict
    global_sig_dfs = dfs_dict

def evaluate_single_config(task):
    q, mm = task
    df_signals = global_sig_dfs[q]
    
    total_profit = 0.0
    total_loss = 0.0
    for row in df_signals.itertuples():
        sym = row.symbol
        t_sig = row.feature_time.to_datetime64()
        entry = row.close
        k = global_sym_klines.get(sym)
        if not k: continue
        times = k["times"]
        idx = np.searchsorted(times, t_sig)
        if idx >= len(times) - 1: continue
        idx += 1
        pnl = simulate_trade_strategy(
            k["high"][idx:idx+864], k["low"][idx:idx+864], k["close"][idx:idx+864], entry, 
            dca_pump_pct=mm['dca_pump_pct'], sl_pct=mm['sl_pct'], tp_pct=mm['tp_pct'], 
            time_limit_bars=mm.get('time_limit_bars', 864), is_time_stop=mm.get('is_time_stop', False)
        )
        if pnl > 0: total_profit += pnl
        else: total_loss += abs(pnl)
    pf = total_profit / total_loss if total_loss > 0 else 999.0
    er = (total_profit - total_loss) / len(df_signals) if len(df_signals) else 0
    return {'quantile': q, 'trades': len(df_signals), 'pf': pf, 'er': er, 'mm': mm}

def main():
    print("1. Training honest ML models across 10 folds...")
    df = pd.read_parquet('artifacts/lowcap_dual_features_cache.parquet')
    window_start, as_of = df["feature_time"].min(), df["feature_time"].max()
    n_folds = 10
    total_duration = (as_of - pd.Timedelta(hours=72)) - window_start
    fold_duration = total_duration / n_folds
    boundaries = [{"test_start": window_start + i * fold_duration, "test_end": (as_of - pd.Timedelta(hours=72)) if i == n_folds - 1 else window_start + (i + 1) * fold_duration} for i in range(n_folds)]
    
    quantiles = [0.98, 0.985, 0.99, 0.995]
    all_oos = {q: [] for q in quantiles}
    
    for fold_idx, b in enumerate(boundaries, start=1):
        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < (b["test_start"] - timedelta(hours=48)))].copy()
        test = df[(df["feature_time"] >= b["test_start"]) & (df["feature_time"] < b["test_end"])].copy()
        if len(train) < 200 or len(test) == 0: continue
        
        n_fit = int(len(train) * 0.8)
        fit, cal = train.iloc[:n_fit], train.iloc[n_fit:]
        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(fit[FEATURE_COLS])
        x_cal = imputer.transform(cal[FEATURE_COLS])
        x_test = imputer.transform(test[FEATURE_COLS])
        
        lgb_model = lgb.LGBMClassifier(random_state=42+fold_idx, n_estimators=200, learning_rate=0.05, max_depth=5, num_leaves=31, subsample=0.8, colsample_bytree=0.8, deterministic=True, force_col_wise=True, verbosity=-1, n_jobs=2)
        lgb_model.fit(x_fit, fit["label_20_10"].astype(int).to_numpy())
        
        cal_probs = lgb_model.predict_proba(x_cal)[:, 1]
        test["prob"] = lgb_model.predict_proba(x_test)[:, 1]
        
        for q in quantiles:
            passed = test[test["prob"] >= np.quantile(cal_probs, q)][["symbol", "feature_time", "close"]]
            all_oos[q].append(passed)
            
    print("2. Loading duckdb price data...")
    conn = duckdb.connect(str(r"D:\Quant-trading\data_lake\quant_master.duckdb"), read_only=True)
    conn.register("sym_df", pd.DataFrame({"symbol": df['symbol'].unique().tolist()}))
    klines_df = conn.execute("SELECT k.symbol, k.close_time, k.high, k.low, k.close FROM klines_5m k INNER JOIN sym_df s ON k.symbol = s.symbol WHERE k.close_time >= '2025-08-25' AND k.close_time <= '2026-09-01' ORDER BY k.symbol, k.close_time ASC").fetchdf()
    conn.close()
    
    sym_klines = {sym: {"times": g["close_time"].dt.tz_convert("UTC").values, "high": g["high"].values.astype(np.float32), "low": g["low"].values.astype(np.float32), "close": g["close"].values.astype(np.float32)} for sym, g in klines_df.groupby("symbol")}
    
    sig_dfs = {}
    for q in quantiles:
        if all_oos[q]:
            sig_df = pd.concat(all_oos[q], ignore_index=True)
            sig_df["feature_time"] = pd.to_datetime(sig_df["feature_time"], utc=True)
            sig_dfs[q] = sig_df
        
    print("3. Generating extensive grid (144 configurations)...")
    mm_configs = []
    for dca in [0.08, 0.10, 0.12, 0.15]:
        for tp in [0.30, 0.35, 0.40]:
            for sl in [0.12, 0.15, 0.18]:
                for ts in [144, 288, 432]: mm_configs.append({'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'time_limit_bars': ts, 'is_time_stop': True})
                mm_configs.append({'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'is_time_stop': False})
    
    tasks = [(q, mm) for q in quantiles for mm in mm_configs if q in sig_dfs]
    print(f"Total combinations to evaluate: {len(tasks)}")
    
    results = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, multiprocessing.cpu_count() - 2), initializer=init_worker, initargs=(sym_klines, sig_dfs)) as executor:
        for res in executor.map(evaluate_single_config, tasks):
            results.append(res)
            
    print(f"Sweep completed in {time.time() - t0:.1f}s")
    results.sort(key=lambda x: x['pf'], reverse=True)
    
    print("\n--- ULTIMATE HONEST OPTIMIZATION RANKING ---")
    for i, r in enumerate(results[:15]):
        print(f"#{i+1} PF: {r['pf']:.4f} | Quantile: Top {100*(1-r['quantile']):.1f}% | Trades: {r['trades']} | ER: {r['er']:.4f}")
        print(f"   Config: DCA {r['mm']['dca_pump_pct']} / TP {r['mm']['tp_pct']} / SL {r['mm']['sl_pct']} / TimeStop: {r['mm'].get('time_limit_bars', 'None')}")

if __name__ == '__main__':
    main()
