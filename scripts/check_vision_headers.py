import urllib.request
import zipfile
import io
import pandas as pd

def check_zip(url):
    try:
        resp = urllib.request.urlopen(url)
        with zipfile.ZipFile(io.BytesIO(resp.read())) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, nrows=2)
                print(f"{url.split('/')[-1]}: {df.columns.tolist()}")
    except Exception as e:
        print(f"Error for {url}: {e}")

check_zip("https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-09.zip")
check_zip("https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2024-09.zip")
check_zip("https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-09-01.zip")
