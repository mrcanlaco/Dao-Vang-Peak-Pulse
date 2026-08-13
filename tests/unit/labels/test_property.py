import duckdb
import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from dao_vang.labels.specs.distribution_short_v1 import DistributionShortV1Spec
from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.events import group_events, create_event_summary_table

@pytest.fixture
def db():
    return duckdb.connect(':memory:')

def make_candle(symbol, ts, o, h, l, c):
    return {
        'symbol': symbol,
        'timestamp': ts,
        'open': o,
        'high': h,
        'low': l,
        'close': c,
        'volume': 100
    }

def test_property_deterministic(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    data = []
    # Generate 2 days of random-ish 5m candles
    np.random.seed(42)
    price = 100.0
    for i in range(0, 288*2):
        ts = base_time + timedelta(minutes=i*5)
        move = np.random.normal(0, 1)
        h = price + abs(np.random.normal(0, 1))
        l = price - abs(np.random.normal(0, 1))
        c = price + move
        data.append(make_candle("BTC", ts, price, max(h, price, c), min(l, price, c), c))
        price = c
        
    df = pd.DataFrame(data)
    db.register('candles', df)
    
    spec = DistributionShortV1Spec(horizon_hours=12)
    engine = DistributionLabelEngineV1(spec)
    
    # Run 1
    engine.compute_all_to_table(db, 'candles', 'run1')
    
    # Run 2
    engine.compute_all_to_table(db, 'candles', 'run2')
    
    # Compare
    diff = db.execute("SELECT * FROM run1 EXCEPT SELECT * FROM run2").df()
    assert len(diff) == 0

def test_leakage_future_doesnt_change_past(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    # Target signal at 00:00
    # Horizon is 6h (until 06:00)
    # Include the close at exactly +6h so the label is materialized rather
    # than (correctly) excluded as missing future data.
    data = [
        make_candle(
            "BTC", base_time + timedelta(minutes=i * 5), 100, 101, 99, 100
        )
        for i in range(73)
    ]
    # Make it positive
    data[10] = make_candle("BTC", base_time + timedelta(minutes=50), 100, 101, 90, 95)
    
    df1 = pd.DataFrame(data)
    db.register('candles1', df1)
    
    spec = DistributionShortV1Spec(horizon_hours=6)
    engine = DistributionLabelEngineV1(spec)
    engine.compute_all_to_table(db, 'candles1', 'run1')
    r1 = db.execute("SELECT * FROM run1 WHERE signal_time = '2024-01-01 00:00:00'").df().iloc[0]
    
    # Now add data way past horizon
    data.append(make_candle("BTC", base_time + timedelta(hours=10), 100, 200, 10, 150)) # Massive move
    df2 = pd.DataFrame(data)
    db.register('candles2', df2)
    engine.compute_all_to_table(db, 'candles2', 'run2')
    r2 = db.execute("SELECT * FROM run2 WHERE signal_time = '2024-01-01 00:00:00'").df().iloc[0]
    
    assert r1['label_value'] == r2['label_value']
    assert r1['max_adverse_excursion'] == r2['max_adverse_excursion']
