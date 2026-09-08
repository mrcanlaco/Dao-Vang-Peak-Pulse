import json
import urllib.request
import time
from datetime import datetime

def fetch_coingecko():
    print("Fetching CoinGecko Market Caps (Pages 1-3)...")
    mc_map = {}
    for i in range(1, 4):
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={i}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                for coin in data:
                    base = coin["symbol"].upper()
                    mc_map[base] = coin.get("market_cap") or 0
        except Exception as e:
            pass
        time.sleep(1)
    return mc_map

def get_active_binance():
    req = urllib.request.Request("https://fapi.binance.com/fapi/v1/exchangeInfo")
    with urllib.request.urlopen(req) as resp:
        info = json.loads(resp.read().decode())
    return [s["symbol"] for s in info["symbols"] if s["status"] == "TRADING" and s["quoteAsset"] == "USDT" and s["contractType"] == "PERPETUAL"]

def check_pump(symbol):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1d&limit=90"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            klines = json.loads(resp.read().decode())
            
        # kline format: [open_time, open, high, low, close, volume, close_time, ...]
        pumped = False
        max_pump = 0
        pump_date = ""
        
        for i in range(len(klines) - 2):
            # Rolling 3-day window
            window = klines[i:i+3]
            low = min(float(k[3]) for k in window)
            high = max(float(k[2]) for k in window)
            
            pump_pct = (high / low - 1) * 100
            if pump_pct > max_pump:
                max_pump = pump_pct
                pump_date = datetime.fromtimestamp(window[0][0]/1000).strftime('%Y-%m-%d')
                
            if pump_pct >= 100:
                pumped = True
                
        return pumped, max_pump, pump_date
    except Exception:
        return False, 0, ""

def run_survey():
    cg_map = fetch_coingecko()
    symbols = get_active_binance()
    
    target_coins = []
    for sym in symbols:
        base = sym.replace('USDT', '')
        if base.startswith('1000'): base = base[4:]
        if base.startswith('10000'): base = base[5:]
        
        mc = cg_map.get(base)
        if mc and 200_000_000 <= mc <= 1_000_000_000:
            target_coins.append((sym, mc))
            
    print(f"\nPhát hiện {len(target_coins)} coin có Market Cap từ $200M - $1B.")
    print("Đang quét lịch sử 90 ngày (Khung 1D) tìm Pump >= 100% trong 3 ngày...\n")
    
    found = []
    for sym, mc in target_coins:
        is_pump, max_pct, date = check_pump(sym)
        if is_pump:
            found.append((sym, mc, max_pct, date))
            print(f"🚀 {sym}: +{max_pct:.1f}% (Bắt đầu từ {date}) | MC: ${mc/1_000_000:.1f}M")
            
    print("\n" + "="*50)
    print(f"Tổng kết: Có {len(found)}/{len(target_coins)} coin ($200M-$1B) pump x2 trong 3 ngày (90 ngày qua).")

if __name__ == "__main__":
    run_survey()
