# Báo Cáo Nghiên Cứu Số 07: Bóc trần Cơ chế V3.2 - Sự sụp đổ của "Phân kỳ Cá Mập" và Quyền lực của Funding Exhaustion

**Ngày phát hành:** 06/09/2026  
**Thực hiện bởi:** Dao Vang Quant Team & AI Agent  
**Mô hình đánh giá:** `frozen_20260906_105716_bc3c369b` (Challenger LightGBM)

---

## 1. Cú lừa từ "Phân kỳ Cá Mập" (The Illusion of Smart Money Divergence)

Trong Báo cáo 06, giả thuyết cốt lõi đằng sau sự đột phá của thuật toán được quy cho chỉ báo `smart_money_divergence` (Sự khác biệt vị thế giữa Đám đông và Cá mập). Tuy nhiên, việc trích xuất và đo lường trực tiếp Thông tin thu được (Information Gain) từ lõi thuật toán LightGBM đã phơi bày một sự thật trái ngược:

- Trọng số của `smart_money_divergence`: **0.00%**
- Trọng số của các chỉ báo vị thế khác (`top_ls_ratio`, `global_ls_ratio`): **0.00%**

Mô hình đã **tự động phớt lờ hoàn toàn** nhóm chỉ báo này trong quá trình huấn luyện. Nguyên nhân gốc rễ là do dữ liệu vị thế từ sàn giao dịch có độ trễ lớn và dễ bị nhiễu, không cung cấp đủ giá trị dự báo tuyến tính hoặc phi tuyến tính trong những pha đảo chiều cực ngắn của thị trường.

---

## 2. Cội nguồn Lợi nhuận thực sự (The True Source of Edge)

Sự thành công của mô hình V3.2 không đến từ việc đọc vị dòng tiền thông minh, mà đến từ việc **nhận diện chính xác trạng thái cực đoan của đám đông fomo (Long Squeeze)**. Mô hình dồn toàn bộ trọng số vào 2 trụ cột chính:

### Trụ cột 1: Bối cảnh Biến động (Volatility & Macro) - Chiếm ~28%
- **`price_volatility_24h` (12.13%)** và **`btc_volatility_24h` (10.42%)**: Mô hình kích hoạt mạnh nhất khi cả Altcoin mục tiêu và BTC đều dao động với biên độ hoảng loạn. 
- **`btc_dominance_slope_24h` (5.92%)**: Nếu BTC hút máu (Dominance tăng) trong khi Altcoin đang bay, mô hình xác định đây là một cái bẫy thanh khoản (Bull-trap).

### Trụ cột 2: Vắt kiệt Dòng tiền (Funding Exhaustion) - Chiếm ~42%
- **`funding_change_8h` (9.20%)**, **`funding_percentile_30d` (8.01%)**, và **`funding_persistence_7d` (7.81%)**: Đây là bộ ba sát thủ. 
- **Cơ chế hoạt động:** Khi một đồng coin bị đẩy giá lên (Pump), phe Long phải trả phí Funding cực cao để duy trì vị thế. Nếu mức phí này duy trì liên tục ở mức đỉnh điểm trong 7 ngày (`persistence_7d`) và tiếp tục gia tốc trong 8 giờ qua (`change_8h`), phe Long chính thức cạn kiệt tài chính (Funding Exhaustion). Lực xả bắt buộc (Liquidation/Chốt lời) sẽ tạo ra pha đảo chiều (Reversal) chết chóc mà thuật toán nhắm tới.

---

## 3. Lãnh địa Độc tôn: Ranh giới Low-Cap

Việc hiểu đúng cơ chế giải thích lý do tại sao mô hình có hành vi hoàn toàn khác biệt trên các không gian thanh khoản khác nhau:

- **Thất bại tại Top/Mid-Cap (Volume > 500M):** Ở những thị trường thanh khoản sâu (BTC, ETH, SOL), sự mất cân bằng Funding Rate không đủ sức làm sập giá vì lực hấp thụ của các quỹ (Institutions) là quá lớn. Mô hình sụp đổ hoàn toàn với Winrate **14.58%** và đe dọa **cháy tài khoản chỉ sau 187 lệnh**.
- **Thống trị tại Low-Cap (Volume 10M - 500M):** Tại vùng thanh khoản mỏng, hiệu ứng "Funding Exhaustion" phát huy tối đa sức mạnh. Chỉ một lượng xả hàng nhỏ từ phe Long cạn vốn cũng đủ gây ra hiệu ứng hòn tuyết lăn (Cascade Liquidation). Kết quả: Winrate đạt **57.27%** và mô phỏng Portfolio tạo ra **ROI +2371%** (Max Drawdown chỉ 4.39%).

---

## 4. Quyết định Vận hành (MLOps Directives)

1. **Loại bỏ vĩnh viễn các tín hiệu thuộc nhóm Top-Cap / Mid-Cap** (Lọc Volume > 500M USDT/24h). Lợi thế (Edge) của hệ thống là độc tôn ở phân khúc Low-Cap.
2. Dừng việc theo đuổi và tốn tài nguyên tính toán cho nhóm dữ liệu `Position Ratio` (Smart Money), loại bỏ khỏi 파i-pê-line (Pipeline) dữ liệu ở các bản cập nhật sau để tối ưu tốc độ quét (Scan latency).

*Báo cáo được tự động phân tích và kết xuất từ Dữ liệu cây quyết định của Mô hình - OMP Quant Agent.*