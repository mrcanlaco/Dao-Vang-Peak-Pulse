import logging
from datetime import datetime, timedelta, timezone

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector

logging.basicConfig(level=logging.INFO)


def run_tests():
    print("Testing M1 Collectors...")

    settings = AppSettings()
    # Override data dir for testing if you want, 
    # or just let it write to the default data dir.

    client = BinanceClient()

    end_time = datetime.now(timezone.utc)
    # Collect 1 hour of data
    start_time = end_time - timedelta(hours=1)

    run_id = f"test-m1-{int(end_time.timestamp())}"

    collectors = [
        ("Klines", KlinesCollector(client, settings)),
        ("Funding", FundingCollector(client, settings)),
        ("Open Interest", OpenInterestCollector(client, settings)),
        ("Taker Ratio", TakerRatioCollector(client, settings)),
        ("Global Ratio", GlobalRatioCollector(client, settings)),
        ("Top Ratio", TopRatioCollector(client, settings)),
    ]

    for name, collector in collectors:
        print(f"\n--- Running {name} Collector ---")
        manifest = collector.collect(start_time, end_time, run_id)
        print(f"Status: {manifest.status}")
        print(f"Raw rows: {manifest.rows_raw}")
        print(f"Errors: {manifest.error_count}")


if __name__ == "__main__":
    run_tests()
