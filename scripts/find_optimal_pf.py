from typing import Any
import numpy as np
import pandas as pd
import duckdb
import time
from pathlib import Path
from multiprocessing import Pool, cpu_count
from functools import partial

def simulate_trade_strategy(
    strategy_name: str,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    entry_price: float,
    fee: float = 0.0020,
    **kwargs: Any,
):
    n_bars = len(highs)
    if n_bars == 0 or entry_price <= 0:
        return {"pnl": -fee, "hit_tp": False, "hit_sl": False}

    pump_pct = (highs - entry_price) / entry_price
    drop_pct = (entry_price - lows) / entry_price

    if strategy_name == "scale_in_dca":
        dca_pump_pct = kwargs.get("dca_pump_pct", 0.10)
        sl_pct = kwargs.get("sl_pct", 0.22)
        tp_pct = kwargs.get("tp_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        dca_filled = False
        p_dca = entry_price * (1.0 + dca_pump_pct)

        for b in range(max_bars):
            curr_high = highs[b]
            curr_low = lows[b]

            if not dca_filled:
                if curr_high >= entry_price * (1.0 + sl_pct):
                    return {"pnl": 0.5 * (-sl_pct) - fee, "hit_tp": False, "hit_sl": True}
                if curr_low <= entry_price * (1.0 - tp_pct):
                    return {"pnl": 0.5 * tp_pct - fee, "hit_tp": True, "hit_sl": False}
                if curr_high >= p_dca:
                    dca_filled = True
                    avg_entry = (entry_price + p_dca) / 2.0
                    target_price_full = avg_entry * (1.0 - tp_pct)
                    sl_price_full = entry_price * (1.0 + sl_pct)
            else:
                if curr_high >= sl_price_full:
                    loss_pct = (sl_price_full - avg_entry) / avg_entry
                    return {"pnl": -loss_pct - fee, "hit_tp": False, "hit_sl": True}
                if curr_low <= target_price_full:
                    return {"pnl": tp_pct - fee, "hit_tp": True, "hit_sl": False}

        if dca_filled:
            final_pnl = (avg_entry - closes[max_bars - 1]) / avg_entry - fee
            return {"pnl": final_pnl, "hit_tp": False, "hit_sl": False}
        else:
            final_pnl = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price) - fee
            return {"pnl": final_pnl, "hit_tp": False, "hit_sl": False}
    
    elif strategy_name == "partial_tp":
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp1_pct = kwargs.get("tp1_pct", 0.10)
        tp2_pct = kwargs.get("tp2_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        tp1_hit = False
        sl_active = sl_pct
        accumulated_pnl = 0.0

        for b in range(max_bars):
            if not tp1_hit:
                if pump_pct[b] >= sl_active:
                    return {"pnl": -sl_pct - fee, "hit_tp": False, "hit_sl": True}
                if drop_pct[b] >= tp1_pct:
                    tp1_hit = True
                    accumulated_pnl += 0.5 * tp1_pct
                    sl_active = 0.0
            else:
                if pump_pct[b] >= sl_active:
                    return {"pnl": accumulated_pnl - fee, "hit_tp": True, "hit_sl": False}
                if drop_pct[b] >= tp2_pct:
                    return {"pnl": accumulated_pnl + 0.5 * tp2_pct - fee, "hit_tp": True, "hit_sl": False}

        if tp1_hit:
            exit_pnl_remaining = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price)
            return {"pnl": accumulated_pnl + exit_pnl_remaining - fee, "hit_tp": True, "hit_sl": False}
        else:
            return {"pnl": ((entry_price - closes[max_bars - 1]) / entry_price) - fee, "hit_tp": False, "hit_sl": False}
    
    elif strategy_name == "fixed_sl":
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp_pct = kwargs.get("tp_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        for b in range(max_bars):
            if pump_pct[b] >= sl_pct:
                return {"pnl": -sl_pct - fee, "hit_tp": False, "hit_sl": True}
            if drop_pct[b] >= tp_pct:
                return {"pnl": tp_pct - fee, "hit_tp": True, "hit_sl": False}
        return {"pnl": ((entry_price - closes[max_bars - 1]) / entry_price) - fee, "hit_tp": False, "hit_sl": False}



from typing import Any

def evaluate_params(params, df_v2, sym_klines):
    strat_name = params['strat_name']
    
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    
    for row in df_v2.itertuples():
        sym = row.symbol
        t_sig = row.feature_time
        entry = row.close
        
        k = sym_klines.get(sym)
        if not k:
            continue
            
        times = k["times"]
        idx = np.searchsorted(times, t_sig.to_datetime64())
        if idx >= len(times) - 1:
            continue
            
        idx += 1
        highs = k["high"][idx:idx+864]
        lows = k["low"][idx:idx+864]
        closes = k["close"][idx:idx+864]
        
        res = simulate_trade_strategy(strat_name, highs, lows, closes, entry, **params)
        pnl = res['pnl']
        
        if pnl > 0:
            total_gross_profit += pnl
        else:
            total_gross_loss += abs(pnl)
            
    pf = total_gross_profit / total_gross_loss if total_gross_loss > 0 else 999.0
    expected_return = (total_gross_profit - total_gross_loss) / len(df_v2)
    return {
        "params": params,
        "pf": pf,
        "expected_return": expected_return,
        "total_profit": total_gross_profit,
        "total_loss": total_gross_loss
    }

def main():
    print("Loading signals...")
    df = pd.read_parquet('artifacts/oos_optimal_signals.parquet')
    df['feature_time'] = pd.to_datetime(df['feature_time'], utc=True)
    df_v2 = df[df['V2_sig'] == True].copy()
    symbols = df_v2['symbol'].unique().tolist()
    print(f"Loaded {len(df_v2)} V2 signals across {len(symbols)} symbols.")
    
    print("Loading duckdb...")
    db_path = r"D:\Quant-trading\data_lake\quant_master.duckdb"
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.register("sym_df", pd.DataFrame({"symbol": symbols}))
    klines_df = conn.execute("""
        SELECT k.symbol, k.close_time, k.open, k.high, k.low, k.close
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
    
    param_grid = []
    
    # 1. Test DCA with tighter SL and bigger TP
    for dca in [0.05, 0.10, 0.15]:
        for tp in [0.20, 0.25, 0.30]:
            for sl in [0.10, 0.15, 0.20, 0.25]:
                param_grid.append({'strat_name': 'scale_in_dca', 'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'max_bars': 864})
                
    # 2. Test Partial TP with varying targets
    for tp1 in [0.05, 0.10]:
        for tp2 in [0.15, 0.20, 0.25]:
            for sl in [0.10, 0.15, 0.20]:
                param_grid.append({'strat_name': 'partial_tp', 'tp1_pct': tp1, 'tp2_pct': tp2, 'sl_pct': sl, 'max_bars': 864})
                
    # 3. Standard Fixed SL
    for tp in [0.20, 0.30, 0.50]:
        for sl in [0.05, 0.10, 0.15]:
            param_grid.append({'strat_name': 'fixed_sl', 'tp_pct': tp, 'sl_pct': sl, 'max_bars': 864})

    print(f"Testing {len(param_grid)} configurations...")
    
    best_pf = 0
    best_res = None
    
    results = []
    for p in param_grid:
        res = evaluate_params(p, df_v2, sym_klines)
        results.append(res)
        if res['pf'] > best_pf:
            best_pf = res['pf']
            best_res = res
            print(f"New Best PF: {best_pf:.4f} | ER: {res['expected_return']:.4f} | Params: {p}")
            
    print("\n--- TOP 5 RESULTS ---")
    results.sort(key=lambda x: x['pf'], reverse=True)
    for i, r in enumerate(results[:5]):
        print(f"{i+1}. PF: {r['pf']:.4f} | ER: {r['expected_return']:.4f} | Params: {r['params']}")

if __name__ == '__main__':
    main()
