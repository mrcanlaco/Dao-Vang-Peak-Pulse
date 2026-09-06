import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timezone
import sys
import joblib

from dao_vang.config.settings import AppSettings
from dao_vang.experiments.forward_test import load_frozen_model
from dao_vang.experiments.walk_forward import embargo_split

def run_simulation():
    # Cấu hình giả lập
    CAPITAL = 1000.0
    LEVERAGE = 5.0
    MARGIN_PER_ORDER = 50.0
    FEE_BPS = 0.001 * 2  # 0.1% vào + 0.1% ra
    SL_PCT = 0.04  # 4% giá trị thực = 20% vốn ký quỹ
    TP_PCT = 0.08  # 8% giá trị thực = 40% vốn ký quỹ
    
    settings = AppSettings()
    # Lấy model chuẩn Quant (Không Leakage, ECE < 0.05)
    MODEL_ID = "frozen_20260906_105716_bc3c369b"
    
    print(f"=== KHỞI ĐỘNG SIMULATOR V3 (QUỸ LƯỢNG HÓA) ===")
    print(f"Model ID: {MODEL_ID}")
    print(f"Vốn: ${CAPITAL} | Đòn bẩy: x{LEVERAGE} | Ký quỹ/Lệnh: ${MARGIN_PER_ORDER}")
    print(f"Chốt lời (TP): {TP_PCT*100}% | Cắt lỗ (SL): {SL_PCT*100}%")
    
    model_dir = Path(settings.scanner.artifact_dir) / "frozen_models" / MODEL_ID
    frozen_info = load_frozen_model(MODEL_ID, Path(settings.scanner.artifact_dir))
    threshold = frozen_info.threshold
    print(f"Ngưỡng kích hoạt (Threshold): {threshold:.4f}")
    
    conn = duckdb.connect(str(settings.scanner.db_path), read_only=True)
    
    print("Đang nạp dữ liệu từ DuckDB...")
    df = conn.execute(
        """
        SELECT f.*, 
               l.label_value AS is_distribution,
               l.signal_price,
               l.max_adverse_excursion,
               l.max_favorable_excursion
        FROM feature_results f
        INNER JOIN labels l
            ON f.feature_time = l.signal_time
            AND f.symbol = l.symbol
        WHERE l.horizon_hours = 24
        """
    ).df()
    
    df = df.dropna(subset=['is_distribution'])
    df = df.sort_values(by="feature_time").reset_index(drop=True)
    
    # Lấy tập Test của Fold 5 (Out-of-sample)
    min_time = df['feature_time'].min()
    max_time = df['feature_time'].max()
    test_start = min_time + (max_time - min_time) * 0.8
    test_end = max_time
    
    _, test_df = embargo_split(
        df,
        train_start=pd.Timestamp(min_time),
        train_end=pd.Timestamp(test_start),
        test_start=pd.Timestamp(test_start),
        test_end=pd.Timestamp(test_end),
        embargo_minutes=24*60
    )
    
    print(f"Tập dữ liệu Out-of-sample (Tương lai chưa biết): {len(test_df)} nến")
    
    # Pre-filter (Giống Live)
    ret = pd.to_numeric(test_df['price_ret_24h'], errors='coerce')
    test_df = test_df[ret >= 0.10].reset_index(drop=True)
    print(f"Sau khi qua bộ lọc Gác cổng (Pump >= 10%): {len(test_df)} nến")
    
    # Tải mô hình
    pipeline = joblib.load(model_dir / "model.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib") if (model_dir / "calibrator.joblib").exists() else None
    
    X_test = test_df[list(frozen_info.feature_cols)]
    
    y_prob_raw = pipeline.predict_proba(X_test)[:, 1] if hasattr(pipeline, "predict_proba") else pipeline.predict(X_test)
    y_prob = calibrator.predict(y_prob_raw) if calibrator else y_prob_raw
    
    # Tìm lệnh cắn
    signals = test_df[y_prob >= threshold].copy()
    print(f"\nMô hình đã hú còi {len(signals)} lần trên tập Test.")
    
    if len(signals) == 0:
        print("Không có tín hiệu nào thỏa mãn ngưỡng an toàn khắt khe của mô hình!")
        sys.exit(0)
    
    # Các biến đánh giá rủi ro Quant
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    
    equity = CAPITAL
    peak_equity = CAPITAL
    max_drawdown = 0.0
    
    current_win_streak = 0
    current_loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    
    notional = MARGIN_PER_ORDER * LEVERAGE
    fee_cost = notional * FEE_BPS
    
    # Giả lập lệnh theo thứ tự thời gian
    signals = signals.sort_values(by="feature_time")
    
    for _, row in signals.iterrows():
        is_win = row['is_distribution'] == 1
        mae = row['max_adverse_excursion']
        mfe = row['max_favorable_excursion']
        
        if is_win:
            pnl = (MARGIN_PER_ORDER * (TP_PCT * LEVERAGE)) - fee_cost
            wins += 1
            gross_profit += pnl
            current_win_streak += 1
            current_loss_streak = 0
            if current_win_streak > max_win_streak: max_win_streak = current_win_streak
        else:
            if mae >= SL_PCT:
                # Bị cắn Stoploss
                pnl = -(MARGIN_PER_ORDER * (SL_PCT * LEVERAGE)) - fee_cost
            else:
                # Hết hạn 24h nhưng không chạm SL/TP, giả sử cắt lệnh ở mức MFE/2
                pnl = (MARGIN_PER_ORDER * (-mfe / 2 * LEVERAGE)) - fee_cost
            
            losses += 1
            gross_loss += abs(pnl)
            current_loss_streak += 1
            current_win_streak = 0
            if current_loss_streak > max_loss_streak: max_loss_streak = current_loss_streak
                
        equity += pnl
        
        # Cập nhật Max Drawdown
        if equity > peak_equity:
            peak_equity = equity
        drawdown = (peak_equity - equity) / peak_equity * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            
    total_pnl = equity - CAPITAL
    win_rate = wins / len(signals) * 100
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    roi = total_pnl / CAPITAL * 100
    
    print("\n" + "="*50)
    print("📊 BÁO CÁO THẨM ĐỊNH LÕI (QUANT REPORT)")
    print("="*50)
    print(f"Tổng số lệnh (Trades)  : {len(signals)}")
    print(f"Lệnh Thắng (Win)       : {wins}")
    print(f"Lệnh Thua (Loss)       : {losses}")
    print(f"Tỷ lệ thắng (Winrate)  : {win_rate:.2f}%")
    print("-" * 50)
    print(f"Tổng tiền Thắng        : ${gross_profit:.2f}")
    print(f"Tổng tiền Thua         : ${gross_loss:.2f}")
    print(f"Lợi nhuận ròng (Net)   : ${total_pnl:.2f}")
    print(f"Tỷ suất sinh lời (ROI) : {roi:.2f}%")
    print("-" * 50)
    print("⚠️ CHỈ SỐ RỦI RO CHUYÊN SÂU (RISK METRICS)")
    print(f"Profit Factor (Hệ số LN): {profit_factor:.2f} (Đạt >1.5 là Tuyệt vời)")
    print(f"Max Drawdown (Sụt vốn)  : {max_drawdown:.2f}% (Rủi ro cháy tài khoản)")
    print(f"Chuỗi Thắng liên tiếp   : {max_win_streak} lệnh")
    print(f"Chuỗi Thua liên tiếp    : {max_loss_streak} lệnh")
    print("="*50)

if __name__ == "__main__":
    run_simulation()
