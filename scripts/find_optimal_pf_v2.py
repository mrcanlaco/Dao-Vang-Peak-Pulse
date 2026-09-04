from typing import Any
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path

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
        return {"pnl": -fee}

    pump_pct = (highs - entry_price) / entry_price
    drop_pct = (entry_price - lows) / entry_price
    
    if strategy_name == "scale_in_dca":
        dca_pump_pct = kwargs.get("dca_pump_pct", 0.10)
        sl_pct = kwargs.get("sl_pct", 0.15)
        tp_pct = kwargs.get("tp_pct", 0.30)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        dca_filled = False
        p_dca = entry_price * (1.0 + dca_pump_pct)

        for b in range(max_bars):
            curr_high = highs[b]
            curr_low = lows[b]

            if not dca_filled:
                if curr_high >= entry_price * (1.0 + sl_pct):
                    return {"pnl": 0.5 * (-sl_pct) - fee}
                if curr_low <= entry_price * (1.0 - tp_pct):
                    return {"pnl": 0.5 * tp_pct - fee}
                if curr_high >= p_dca:
                    dca_filled = True
                    avg_entry = (entry_price + p_dca) / 2.0
                    target_price_full = avg_entry * (1.0 - tp_pct)
                    sl_price_full = entry_price * (1.0 + sl_pct)
            else:
                if curr_high >= sl_price_full:
                    loss_pct = (sl_price_full - avg_entry) / avg_entry
                    return {"pnl": -loss_pct - fee}
                if curr_low <= target_price_full:
                    return {"pnl": tp_pct - fee}

        if dca_filled:
            final_pnl = (avg_entry - closes[max_bars - 1]) / avg_entry - fee
            return {"pnl": final_pnl}
        else:
            final_pnl = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price) - fee
            return {"pnl": final_pnl}
            
    elif strategy_name == "scale_in_dca_time_stop":
        dca_pump_pct = kwargs.get("dca_pump_pct", 0.10)
        sl_pct = kwargs.get("sl_pct", 0.15)
        tp_pct = kwargs.get("tp_pct", 0.30)
        time_limit_bars = min(kwargs.get("time_limit_bars", 288), n_bars) # Default 24h
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        dca_filled = False
        p_dca = entry_price * (1.0 + dca_pump_pct)

        for b in range(max_bars):
            curr_high = highs[b]
            curr_low = lows[b]

            if not dca_filled:
                if curr_high >= entry_price * (1.0 + sl_pct):
                    return {"pnl": 0.5 * (-sl_pct) - fee}
                if curr_low <= entry_price * (1.0 - tp_pct):
                    return {"pnl": 0.5 * tp_pct - fee}
                if curr_high >= p_dca:
                    dca_filled = True
                    avg_entry = (entry_price + p_dca) / 2.0
                    target_price_full = avg_entry * (1.0 - tp_pct)
                    sl_price_full = entry_price * (1.0 + sl_pct)
            else:
                if curr_high >= sl_price_full:
                    loss_pct = (sl_price_full - avg_entry) / avg_entry
                    return {"pnl": -loss_pct - fee}
                if curr_low <= target_price_full:
                    return {"pnl": tp_pct - fee}
                    
            # Time-stop check
            if b == time_limit_bars - 1:
                if dca_filled:
                    current_drop = (avg_entry - closes[b]) / avg_entry
                else:
                    current_drop = (entry_price - closes[b]) / entry_price
                
                # If trade is not in profit by at least 2% at the time limit, kill it.
                if current_drop < 0.02:
                    if dca_filled:
                        exit_pnl = (avg_entry - closes[b]) / avg_entry - fee
                    else:
                        exit_pnl = 0.5 * ((entry_price - closes[b]) / entry_price) - fee
                    return {"pnl": exit_pnl}

        if dca_filled:
            final_pnl = (avg_entry - closes[max_bars - 1]) / avg_entry - fee
            return {"pnl": final_pnl}
        else:
            final_pnl = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price) - fee
            return {"pnl": final_pnl}

    return {"pnl": 0}

def evaluate_params(params, df_v2, sym_klines):
    strat_name = params['strat_name']
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    
    for row in df_v2.itertuples():
        sym = row.symbol
        t_sig = row.feature_time.to_datetime64()
        entry = row.close
        
        k = sym_klines.get(sym)
        if not k:
            continue
            
        times = k["times"]
        idx = np.searchsorted(times, t_sig)
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
        "expected_return": expected_return
    }

def main():
    print("Loading signals...")
    df = pd.read_parquet('artifacts/oos_optimal_signals.parquet')
    df['feature_time'] = pd.to_datetime(df['feature_time'], utc=True)
    df_v2 = df[df['V2_sig'] == True].copy()
    symbols = df_v2['symbol'].unique().tolist()
    
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
    
    # Aggressive Sweep for standard DCA
    for dca in [0.05, 0.08, 0.10, 0.12]:
        for tp in [0.25, 0.30, 0.35, 0.40]:
            for sl in [0.10, 0.12, 0.15, 0.18]:
                param_grid.append({'strat_name': 'scale_in_dca', 'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 'max_bars': 864})

    # Sweep for DCA + Time-Stop
    for dca in [0.08, 0.10, 0.12]:
        for tp in [0.30, 0.35]:
            for sl in [0.12, 0.15, 0.18]:
                for time_limit in [144, 288, 432]: # 12h, 24h, 36h
                    param_grid.append({
                        'strat_name': 'scale_in_dca_time_stop', 
                        'dca_pump_pct': dca, 'tp_pct': tp, 'sl_pct': sl, 
                        'time_limit_bars': time_limit, 'max_bars': 864
                    })
                
    print(f"Testing {len(param_grid)} configurations...")
    
    results = []
    for p in param_grid:
        res = evaluate_params(p, df_v2, sym_klines)
        results.append(res)
        
    print("\n--- TOP 10 OVERALL RESULTS ---")
    results.sort(key=lambda x: x['pf'], reverse=True)
    for i, r in enumerate(results[:10]):
        print(f"#{i+1} PF: {r['pf']:.4f} | ER: {r['expected_return']:.4f} | Params: {r['params']}")

if __name__ == '__main__':
    main()
