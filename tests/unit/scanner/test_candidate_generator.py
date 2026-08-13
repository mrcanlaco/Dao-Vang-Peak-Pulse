import duckdb
import pandas as pd
from datetime import datetime
from dao_vang.scanner.candidate_generator import generate_candidates
from dao_vang.config.settings import ScoringConfig

def test_generate_candidates():
    db = duckdb.connect(':memory:')
    data = [
        {"symbol": "BTC", "feature_time": datetime(2024, 1, 1), "price_ret_24h": 0.10, "volume_percentile_24h": 0.1, "funding_zscore_30d": 3.0, "distance_from_high_24h": 0.0, "momentum_deceleration_4h": -0.05, "taker_buy_ratio": 0.3},
        {"symbol": "ETH", "feature_time": datetime(2024, 1, 1), "price_ret_24h": 0.02, "volume_percentile_24h": 0.9, "funding_zscore_30d": 0.0, "distance_from_high_24h": -0.1, "momentum_deceleration_4h": 0.0, "taker_buy_ratio": 0.5},
    ]
    df = pd.DataFrame(data)
    db.register('timeline', df)
    
    config = ScoringConfig()
    candidates = generate_candidates(db, 'timeline', config, min_score=35.0)
    
    assert "BTC" in candidates
    assert "ETH" not in candidates
