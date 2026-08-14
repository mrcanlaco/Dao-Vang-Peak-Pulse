from datetime import datetime, timedelta

import duckdb
import pandas as pd
import pytest

from dao_vang.labels.events import create_event_summary_table, group_events


@pytest.fixture
def db():
    return duckdb.connect(':memory:')

def make_label(symbol, ts, val, mfe=None, target_time=None):
    return {
        'symbol': symbol,
        'signal_time': ts,
        'signal_price': 100.0,
        'label_value': val,
        'max_favorable_excursion': mfe,
        'target_time': target_time
    }

def test_group_events(db):
    base = datetime(2024, 1, 1, 0, 0)
    data = [
        # Event 1
        make_label("BTC", base, 1, -0.09, base + timedelta(minutes=10)),
        make_label("BTC", base + timedelta(minutes=5), 1, -0.085, base + timedelta(minutes=15)),
        
        # Non-event
        make_label("BTC", base + timedelta(minutes=10), 0),
        make_label("BTC", base + timedelta(minutes=15), 0),
        
        # Event 2 (Gap > 60 min from previous 1)
        make_label("BTC", base + timedelta(minutes=120), 1, -0.10, base + timedelta(minutes=130)),
    ]
    df = pd.DataFrame(data)
    db.register('labels_in', df)
    
    group_events(db, 'labels_in', 'labels_out', gap_minutes=60)
    create_event_summary_table(db, 'labels_out', 'events_summary')
    
    # Check rows
    out_df = db.execute("SELECT * FROM labels_out ORDER BY signal_time").df()
    assert pd.notna(out_df.iloc[0]['event_id'])
    assert out_df.iloc[0]['event_id'] == out_df.iloc[1]['event_id']
    assert pd.isna(out_df.iloc[2]['event_id'])
    assert pd.isna(out_df.iloc[3]['event_id'])
    assert pd.notna(out_df.iloc[4]['event_id'])
    assert out_df.iloc[0]['event_id'] != out_df.iloc[4]['event_id']
    
    # Check summary
    summ = db.execute("SELECT * FROM events_summary ORDER BY event_start_time").df()
    assert len(summ) == 2
    assert summ.iloc[0]['member_rows'] == 2
    assert summ.iloc[1]['member_rows'] == 1
    assert summ.iloc[0]['peak_favorable_excursion'] == -0.09
