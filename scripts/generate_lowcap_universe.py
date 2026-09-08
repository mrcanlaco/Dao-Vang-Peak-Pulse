import json
import urllib.request

def generate_lowcap_universe(min_vol_usd=500_000, exclude_top_n=30):
    print("Fetching USD-M Futures Exchange Info...")
    req = urllib.request.Request("https://fapi.binance.com/fapi/v1/exchangeInfo")
    with urllib.request.urlopen(req) as resp:
        info = json.loads(resp.read().decode())

    active_symbols = [
        s["symbol"] for s in info["symbols"]
        if s["status"] == "TRADING" 
        and s["contractType"] == "PERPETUAL" 
        and s["quoteAsset"] == "USDT"
    ]

    print("Fetching 24h Ticker Volume...")
    req_vol = urllib.request.Request("https://fapi.binance.com/fapi/v1/ticker/24hr")
    with urllib.request.urlopen(req_vol) as resp_vol:
        tickers = json.loads(resp_vol.read().decode())

    volume_map = {t["symbol"]: float(t["quoteVolume"]) for t in tickers if t["symbol"] in active_symbols}

    stablecoins = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT"]
    
    # Lọc ban đầu: bỏ stablecoin & vol quá bé (< 500k)
    filtered = []
    for sym in active_symbols:
        if sym in stablecoins:
            continue
        vol = volume_map.get(sym, 0)
        if vol >= min_vol_usd:
            filtered.append((sym, vol))

    # Sắp xếp theo volume giảm dần
    filtered.sort(key=lambda x: x[1], reverse=True)
    
    # Bỏ top coin (những con volume cao nhất thường là BTC, ETH, SOL, XRP... vốn hóa quá to, khó pump láo)
    lowcap_list = [x[0] for x in filtered[exclude_top_n:]]
    
    out_file = "data/universe_lowcap.json"
    with open(out_file, "w") as f:
        json.dump(lowcap_list, f, indent=2)
        
    print(f"✅ Đã lưu {len(lowcap_list)} low-cap/mid-cap coins vào {out_file}.")
    print(f"Bị loại (Top {exclude_top_n} volume): {', '.join([x[0] for x in filtered[:5]])}...")
    print(f"Mẫu Low-cap giữ lại: {', '.join(lowcap_list[:5])}...")

if __name__ == "__main__":
    generate_lowcap_universe()