# ADR 011: Refactor Decision Center UI

## Vấn đề
Trang Decision Center (`MainWorkspace.tsx`) hiện tại quá tải thông tin. Biểu đồ, chỉ số (Metrics), phân tích chuyên sâu (Deep Analysis), và SHAP drivers hiển thị cùng lúc, khiến người dùng khó tập trung vào hành động cốt lõi (Action).

## Giải pháp
1. **Phân cấp thông tin (Progressive Disclosure):**
   - Rút gọn "Hero Card": Chỉ hiển thị Tên Coin, Giá, AI Score, Risk Level và các nút hành động (Telegram, Hide, Watchlist).
   - Đưa SHAP Drivers, 8-Component Breakdown, và Validation Integrity vào chế độ "Advanced View" (ẩn mặc định).
2. **Gộp nhóm Metrics:**
   - Đưa các chỉ số phụ (RSI, Vol Δ, Target) vào dưới biểu đồ hoặc trong một tab con.
3. **Làm gọn Biểu đồ:**
   - Mặc định ẩn sub-chart OI/Funding, có nút toggle để xem.

## Trạng thái
Đề xuất (Proposed)
