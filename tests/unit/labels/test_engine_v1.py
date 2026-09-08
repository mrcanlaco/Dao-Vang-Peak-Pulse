import duckdb
import pandas as pd

from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.specs.distribution_short_v1 import specs


def test_distribution_label_engine_5_cases():
    """Test the 5 distinct edge cases defined in the label contract."""
    conn = duckdb.connect(":memory:")
    
    # Base signal price: 100
    # Target: 8% drop (92)
    # MAE: 4% spike (104)
    # Horizon: 24h
    
    # We will simulate 5 different symbols, each representing a case.
    # To keep it simple, we just create a few rows per symbol.
    
    data = []
    
    base_time = pd.Timestamp("2026-01-01 00:00:00")
    
    # Case 1: Invalid quality -> null
    data.append({"symbol": "C1_INVALID", "close_time": base_time, "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "invalid"})
    for i in range(1, 289):
        data.append({"symbol": "C1_INVALID", "close_time": base_time + pd.Timedelta(minutes=5*i), "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})

    # Case 2: Data gap -> null (missing data for > gap_tol)
    data.append({"symbol": "C2_GAP", "close_time": base_time, "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})
    # Jump 3 hours (180 mins) which exceeds the default gap_tol
    data.append({"symbol": "C2_GAP", "close_time": base_time + pd.Timedelta(minutes=180), "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})
    for i in range(37, 289):
        data.append({"symbol": "C2_GAP", "close_time": base_time + pd.Timedelta(minutes=5*i), "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})

    # Case 3: Insufficient future horizon -> null
    data.append({"symbol": "C3_SHORT", "close_time": base_time, "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})
    for i in range(1, 100): # Only 100 bars < 288 bars
        data.append({"symbol": "C3_SHORT", "close_time": base_time + pd.Timedelta(minutes=5*i), "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})

    # Case 4: TP and MAE hit in the exact same candle -> null
    data.append({"symbol": "C4_SAME_CANDLE", "close_time": base_time, "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})
    for i in range(1, 288):
        data.append({"symbol": "C4_SAME_CANDLE", "close_time": base_time + pd.Timedelta(minutes=5*i), "open": 100, "high": 105, "low": 90, "close": 100, "quality_status": "valid"})
    # The very next candle hits 105 (MAE hit) and 90 (TP hit) simultaneously

    # Case 5: Sufficient horizon, but neither TP nor MAE hit -> 0 (Negative)
    data.append({"symbol": "C5_NO_HIT", "close_time": base_time, "open": 100, "high": 100, "low": 100, "close": 100, "quality_status": "valid"})
    for i in range(1, 289):
        data.append({"symbol": "C5_NO_HIT", "close_time": base_time + pd.Timedelta(minutes=5*i), "open": 100, "high": 102, "low": 98, "close": 100, "quality_status": "valid"})
        
    df = pd.DataFrame(data)
    conn.register("source_table", df)
    
    engine = DistributionLabelEngineV1(specs[24])
    engine.compute_all_to_table(conn, "source_table", "output_labels")
    
    # We only care about the labels for the base_time signal (the first row of each symbol)
    res = conn.execute("SELECT symbol, label_value, exclusion_reason FROM output_labels WHERE signal_time = ?", [base_time]).df()
    
    res_dict = res.set_index("symbol").to_dict("index")
    
    # Asserts based on contract
    assert pd.isna(res_dict["C1_INVALID"]["label_value"])
    assert res_dict["C1_INVALID"]["exclusion_reason"] == "invalid_quality"
    
    assert pd.isna(res_dict["C2_GAP"]["label_value"])
    assert res_dict["C2_GAP"]["exclusion_reason"] == "data_gap"
    
    assert pd.isna(res_dict["C3_SHORT"]["label_value"])
    assert res_dict["C3_SHORT"]["exclusion_reason"] == "missing_future_data"
    
    assert pd.isna(res_dict["C4_SAME_CANDLE"]["label_value"])
    assert res_dict["C4_SAME_CANDLE"]["exclusion_reason"] == "ambiguous_intrabar"
    
    assert res_dict["C5_NO_HIT"]["label_value"] == 0.0
    assert pd.isna(res_dict["C5_NO_HIT"]["exclusion_reason"])
    
    print("All 5 Engine V1 Label Contract cases passed successfully!")
