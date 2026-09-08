import json
import urllib.request

def generate_universe(top_n=200, min_volume_usd=5_000_000):
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
    print(f"Found {len(active_symbols)} active USDT perpetuals.")

    print("Fetching 24h Ticker Volume...")
    req_vol = urllib.request.Request("https://fapi.binance.com/fapi/v1/ticker/24hr")
    with urllib.request.urlopen(req_vol) as resp_vol:
        tickers = json.loads(resp_vol.read().decode())

    # Map tickers
    volume_map = {}
    for t in tickers:
        if t["symbol"] in active_symbols:
            volume_map[t["symbol"]] = float(t["quoteVolume"])

    # Filter & Sort
    filtered = []
    stablecoins = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT"]
    
    for sym in active_symbols:
        if sym in stablecoins:
            continue
        vol = volume_map.get(sym, 0)
        if vol >= min_volume_usd:
            filtered.append((sym, vol))

    # Sort desc by volume
    filtered.sort(key=lambda x: x[1], reverse=True)
    
    # Take top N
    final_list = [x[0] for x in filtered[:top_n]]
    
    out_file = "data/universe.json"
    with open(out_file, "w") as f:
        json.dump(final_list, f, indent=2)
        
    print(f"✅ Saved Top {len(final_list)} highest volume coins to {out_file}.")
    print(f"Top 5: {final_list[:5]}")
    print(f"Bottom 5: {final_list[-5:]}")

if __name__ == "__main__":
    generate_universe()