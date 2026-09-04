import duckdb
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import datetime, timedelta
from sklearn.impute import SimpleImputer
import time
from itertools import product

FEATURE_COLS = [
    "return_5m", "volatility_5m", "volatility_24h", "return_1h", "return_4h",
    "return_24h", "funding_rate_raw", "taker_ratio", "vol_surge_24h",
    "oi_change_1h", "oi_change_4h", "top_acct_ratio", "global_ls_ratio", "taker_bs_ratio"
]

def _fold_boundaries(start_dt, end_dt, n_folds=10):
    total_duration = end_dt - start_dt
    fold_duration = total_duration / n_folds
    boundaries = []
    for i in range(n_folds):
        t_start = start_dt + i * fold_duration
        t_end = end_dt if i == n_folds - 1 else start_dt + (i + 1) * fold_duration
        boundaries.append({"test_start": t_start, "test_end": t_end})
    return boundaries

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
                loss_pct = (sl_price_full - avg_entry) / avg_entry
                return -loss_pct - fee
            if curr_low <= target_price_full: return tp_pct - fee
                
        if is_time_stop and b == time_limit_bars - 1:
            current_drop = (avg_entry - closes[b]) / avg_entry if dca_filled else (entry_price - closes[b]) / entry_price
            if current_drop < 0.02:
                return ((avg_entry - closes[b]) / avg_entry - fee) if dca_filled else (0.5 * ((entry_price - closes[b]) / entry_price) - fee)

    return ((avg_entry - closes[863]) / avg_entry - fee) if dca_filled else (0.5 * ((entry_price - closes[863]) / entry_price) - fee)

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
        pnl = simulate_trade_strategy(
            k["high"][idx:idx+864], k["low"][idx:idx+864], k["close"][idx:idx+864], entry, 
            dca_pump_pct=params['dca_pump_pct'], sl_pct=params['sl_pct'], tp_pct=params['tp_pct'], 
            time_limit_bars=params.get('time_limit_bars', 864), is_time_stop=params.get('is_time_stop', False)
        )
        if pnl > 0: total_profit += pnl
        else: total_loss += abs(pnl)
    pf = total_profit / total_loss if total_loss > 0 else 999.0
    return pf, (total_profit - total_loss) / len(df_signals) if len(df_signals) else 0, len(df_signals)

def main():
    print("1. Training honest ML models across 10 folds...")
    df = pd.read_parquet('artifacts/lowcap_dual_features_cache.parquet')
    as_of = df["feature_time"].max()
    window_start = df["feature_time"].min()
    boundaries = _fold_boundaries(window_start, as_of - pd.Timedelta(hours=72), n_folds=10)
    embargo = timedelta(hours=48)
    
    quantiles = [0.98, 0.99, 0.995]
    all_oos = {q: [] for q in quantiles}
    
    for fold_idx, b in enumerate(boundaries, start=1):
        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < (b["test_start"] - embargo))].copy()
        test = df[(df["feature_time"] >= b["test_start"]) & (df["feature_time"] < b["test_end"])].copy()
        if len(train) < 200 or len(test) == 0: continue
        
        n_fit = int(len(train) * 0.8)
        fit, cal = train.iloc[:n_fit], train.iloc[n_fit:]
        y_fit, y_cal = fit["label_20_10"].astype(int).to_numpy(), cal["label_20_10"].astype(int).to_numpy()
        
        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(fit[FEATURE_COLS])
        x_cal = imputer.transform(cal[FEATURE_COLS])
        x_test = imputer.transform(test[FEATURE_COLS])
        
        lgb_model = lgb.LGBMClassifier(random_state=42+fold_idx, n_estimators=200, learning_rate=0.05, max_depth=5, num_leaves=31, subsample=0.8, colsample_bytree=0.8, deterministic=True, force_col_wise=True, verbosity=-1, n_jobs=2)
        lgb_model.fit(x_fit, y_fit)
        
        cal_probs = lgb_model.predict_proba(x_cal)[:, 1]
        test_probs = lgb_model.predict_proba(x_test)[:, 1]
        test["prob"] = test_probs
        
        for q in quantiles:
            threshold = np.quantile(cal_probs, q)
            passed = test[test["prob"] >= threshold][["symbol", "feature_time", "close"]]
            all_oos[q].append(passed)
            
    print("2. Loading duckdb price data...")
    db_path = r"D:\Quant-trading\data_lake\quant_master.duckdb"
    conn = duckdb.connect(str(db_path), read_only=True)
    syms = df['symbol'].unique().tolist()
    conn.register("sym_df", pd.DataFrame({"symbol": syms}))
    klines_df = conn.execute("SELECT k.symbol, k.close_time, k.high, k.low, k.close FROM klines_5m k INNER JOIN sym_df s ON k.symbol = s.symbol WHERE k.close_time >= '2025-08-25' AND k.close_time <= '2026-09-01' ORDER BY k.symbol, k.close_time ASC").fetchdf()
    conn.close()
    
    sym_klines = {sym: {"times": g["close_time"].dt.tz_convert("UTC").values, "high": g["high"].values.astype(np.float32), "low": g["low"].values.astype(np.float32), "close": g["close"].values.astype(np.float32)} for sym, g in klines_df.groupby("symbol")}
        
    print("3. Generating extensive grid...")
    mm_configs = []
    # Grid 1: DCA + Time-Stop
    for dca in [0.08, 0.10, 0.12, 0.15]:
        for tp in [0.30, 0.35, 0.40]:
            for sl in [0.12, 0.15, 0.18]:
                for ts in [144, 288, 432]: # 12h, 24h, 36h
                    mm_configs.append({'strat_name': 'dca_time_stop', 'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'time_limit_bars': ts, 'is_time_stop': True})
    
    # Grid 2: Pure DCA (No time stop)
    for dca in [0.08, 0.10, 0.12, 0.15]:
        for tp in [0.30, 0.35, 0.40]:
            for sl in [0.12, 0.15, 0.18]:
                mm_configs.append({'strat_name': 'pure_dca', 'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'is_time_stop': False})
    
    print(f"Total configs per quantile: {len(mm_configs)}")
    
    results = []
    for q in quantiles:
        if not all_oos[q]: continue
        sig_df = pd.concat(all_oos[q], ignore_index=True)
        sig_df["feature_time"] = pd.to_datetime(sig_df["feature_time"], utc=True)
        print(f"Evaluating Quantile {q} ({len(sig_df)} signals)...")
        for mm in mm_configs:
            pf, er, trades = evaluate_signals(sig_df, sym_klines, mm)
            results.append({'quantile': q, 'trades': trades, 'pf': pf, 'er': er, 'mm': mm})
            
    results.sort(key=lambda x: x['pf'], reverse=True)
    print("\n--- ULTIMATE HONEST OPTIMIZATION RANKING ---")
    for i, r in enumerate(results[:10]):
        print(f"#{i+1} PF: {r['pf']:.4f} | Quantile: Top {100*(1-r['quantile']):.1f}% | Trades: {r['trades']} | ER: {r['er']:.4f}")
        print(f"   Config: {r['mm']}")

if __name__ == '__main__':
    main()
