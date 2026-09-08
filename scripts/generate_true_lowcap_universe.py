import json
import urllib.request
import time

def fetch_coingecko_market_caps(pages=4):
    """Lấy dữ liệu Market Cap của 1000 coin lớn nhất từ CoinGecko."""
    print("Đang lấy Market Cap từ CoinGecko...")
    mc_map = {}
    for i in range(1, pages + 1):
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={i}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                for coin in data:
                    base = coin["symbol"].upper()
                    mc_map[base] = coin.get("market_cap") or 0
        except Exception as e:
            print(f"Lỗi khi gọi CoinGecko trang {i}: {e}")
        time.sleep(2)  # Tránh Rate Limit của CoinGecko
    return mc_map

def generate_true_lowcap_universe(min_vol_usd=5_000_000, max_mc_usd=1_000_000_000, min_mc_usd=10_000_000):
    cg_mc_map = fetch_coingecko_market_caps()

    print("Đang lấy danh sách USD-M Futures từ Binance...")
    req = urllib.request.Request("https://fapi.binance.com/fapi/v1/exchangeInfo")
    with urllib.request.urlopen(req) as resp:
        info = json.loads(resp.read().decode())

    active_symbols = [
        s["symbol"] for s in info["symbols"]
        if s["status"] == "TRADING" 
        and s["contractType"] == "PERPETUAL" 
        and s["quoteAsset"] == "USDT"
    ]

    print("Đang lấy Volume 24h từ Binance Futures...")
    req_vol = urllib.request.Request("https://fapi.binance.com/fapi/v1/ticker/24hr")
    with urllib.request.urlopen(req_vol) as resp_vol:
        tickers = json.loads(resp_vol.read().decode())

    volume_map = {t["symbol"]: float(t["quoteVolume"]) for t in tickers if t["symbol"] in active_symbols}

    stablecoins = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT"]
    
    final_list = []
    excluded_large_cap = []
    excluded_micro_cap = []
    excluded_low_vol = []
    missing_mc = []

    for sym in active_symbols:
        if sym in stablecoins:
            continue
            
        vol = volume_map.get(sym, 0)
        
        # Bóc tách tên base coin (Xóa đuôi USDT và tiền tố 1000, ví dụ 1000PEPEUSDT -> PEPE)
        base = sym.replace('USDT', '')
        if base.startswith('1000'):
            base = base[4:]
        if base.startswith('10000'): # Ví dụ 10000SATS
            base = base[5:]
            
        mc = cg_mc_map.get(base, None)
        
        # Nếu không tìm thấy Market Cap hợp lệ, thẳng tay loại bỏ để tuân thủ quy định $10M-$1B
        if mc is None:
            missing_mc.append(sym)
            continue

        if mc > max_mc_usd:
            excluded_large_cap.append(sym)
        elif mc < min_mc_usd:
            excluded_micro_cap.append(sym)
        elif vol < min_vol_usd:
            excluded_low_vol.append(sym)
        else:
            final_list.append(sym)

    out_file = "data/true_lowcap_universe.json"
    with open(out_file, "w") as f:
        json.dump(final_list, f, indent=2)
        
    print("\n" + "="*50)
    print("🏆 KẾT QUẢ LỌC VŨ TRỤ COIN ĐẢO VÀNG")
    print("="*50)
    print(f"Tổng số hợp đồng USDT Perpetual: {len(active_symbols)}")
    print(f"❌ Bị loại do Vốn hóa quá to (> 1 Tỷ USD): {len(excluded_large_cap)} coins (Ví dụ: {', '.join(excluded_large_cap[:5])}...)")
    print(f"❌ Bị loại do Vốn hóa quá bé (< 10 Triệu USD): {len(excluded_micro_cap)} coins")
    print(f"❌ Bị loại do Volume 24h quá bé (< $5M): {len(excluded_low_vol)} coins")
    print(f"❌ Bị loại do không tìm thấy MarketCap (Drop hoàn toàn): {len(missing_mc)} coins")
    print(f"✅ CHUẨN LOW/MID-CAP ĐƯỢC GIỮ LẠI: {len(final_list)} coins")
    print(f"Đã lưu danh sách vào: {out_file}")

if __name__ == "__main__":
    generate_true_lowcap_universe()
