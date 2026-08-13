import duckdb
import pytest
from datetime import datetime, timedelta
import pandas as pd
from decimal import Decimal

from dao_vang.labels.specs.distribution_short_v1 import DistributionShortV1Spec
from dao_vang.labels.engine_v1 import DistributionLabelEngineV1

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

def test_label_computation_basic(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    data = [
        make_candle("BTC", base_time, 100, 101, 99, 100),
        # Hit -8% without hitting +4%
        make_candle("BTC", base_time + timedelta(minutes=5), 100, 101, 92, 92),
        make_candle("BTC", base_time + timedelta(minutes=10), 92, 95, 90, 91),
    ]
    # Fill remaining 6h to avoid missing_future_data
    for i in range(15, 365, 5):
        data.append(make_candle("BTC", base_time + timedelta(minutes=i), 91, 92, 90, 91))
        
    df = pd.DataFrame(data)
    db.register('candles', df)
    
    spec = DistributionShortV1Spec(horizon_hours=6)
    engine = DistributionLabelEngineV1(spec)
    engine.compute_all_to_table(db, 'candles', 'labels_out')
    
    res = db.execute("SELECT * FROM labels_out WHERE signal_time = '2024-01-01 00:00:00'").df()
    
    assert len(res) == 1
    row = res.iloc[0]
    assert row['label_value'] == 1
    assert row['target_reached'] == True
    assert row['exclusion_reason'] is None
    assert row['ambiguous_intrabar'] == False

def test_ambiguous_intrabar(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    data = [
        make_candle("BTC", base_time, 100, 101, 99, 100),
        # Candle high hits +4% (104) and low hits -8% (92) simultaneously
        make_candle("BTC", base_time + timedelta(minutes=5), 100, 105, 90, 95),
    ]
    # Fill remaining 6h
    for i in range(10, 365, 5):
        data.append(make_candle("BTC", base_time + timedelta(minutes=i), 95, 96, 94, 95))
        
    df = pd.DataFrame(data)
    db.register('candles', df)
    
    spec = DistributionShortV1Spec(horizon_hours=6)
    engine = DistributionLabelEngineV1(spec)
    engine.compute_all_to_table(db, 'candles', 'labels_out')
    
    res = db.execute("SELECT * FROM labels_out WHERE signal_time = '2024-01-01 00:00:00'").df()
    row = res.iloc[0]
    assert pd.isna(row['label_value'])
    assert row['ambiguous_intrabar'] == True

def test_missing_future_data(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    data = [
        make_candle("BTC", base_time, 100, 101, 99, 100),
        make_candle("BTC", base_time + timedelta(minutes=5), 100, 101, 99, 100),
    ]
    # Only 5 minutes of future data provided for a 6h horizon
    df = pd.DataFrame(data)
    db.register('candles', df)
    
    spec = DistributionShortV1Spec(horizon_hours=6)
    engine = DistributionLabelEngineV1(spec)
    engine.compute_all_to_table(db, 'candles', 'labels_out')
    
    res = db.execute("SELECT * FROM labels_out WHERE signal_time = '2024-01-01 00:00:00'").df()
    row = res.iloc[0]
    assert row['exclusion_reason'] == 'missing_future_data'

def test_data_gap(db):
    base_time = datetime(2024, 1, 1, 0, 0)
    data = [
        make_candle("BTC", base_time, 100, 101, 99, 100),
        make_candle("BTC", base_time + timedelta(minutes=5), 100, 101, 99, 100),
        # Gap of 20 minutes (exceeds 15)
        make_candle("BTC", base_time + timedelta(minutes=25), 100, 101, 99, 100),
    ]
    # Fill remaining
    for i in range(30, 365, 5):
        data.append(make_candle("BTC", base_time + timedelta(minutes=i), 100, 101, 99, 100))
        
    df = pd.DataFrame(data)
    db.register('candles', df)
    
    spec = DistributionShortV1Spec(horizon_hours=6)
    engine = DistributionLabelEngineV1(spec)
    engine.compute_all_to_table(db, 'candles', 'labels_out')
    
    res = db.execute("SELECT * FROM labels_out WHERE signal_time = '2024-01-01 00:00:00'").df()
    row = res.iloc[0]
    assert row['exclusion_reason'] == 'data_gap'
