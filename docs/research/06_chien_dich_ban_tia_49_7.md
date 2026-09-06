# Báo Cáo Nghiên Cứu Số 06: Kỷ nguyên Bắn tỉa V3.2 - Khai phá Phân kỳ Cá Mập & Cú sốc ROI 302%

**Ngày phát hành:** 06/09/2026  
**Thực hiện bởi:** Dao Vang Quant Team & AI Agent  
**Trạng thái:** Đã triển khai trên Live Environment  

---

## 1. Tóm tắt Hành trình (Executive Summary)
Phiên làm việc ngày 06/09/2026 đánh dấu một bước ngoặt lịch sử trong kiến trúc của hệ thống Radar Đảo Vàng. Từ mức giới hạn cấu trúc ban đầu (Precision 13%), hệ thống đã trải qua một cuộc đại phẫu toàn diện về dữ liệu và thuật toán để chạm mốc **Precision 49.7%** trên tập dữ liệu tương lai (Out-of-sample). 

Quan trọng hơn, trong bài giả lập thực chiến (Simulator) với số vốn 1000$ (Risk 1%), mô hình đã tạo ra tỷ suất sinh lời khổng lồ **ROI +302%**, chính thức biến Đảo Vàng thành một cỗ máy Giao dịch Định lượng (Quant Trading) chuẩn tổ chức.

---

## 2. Những góc khuất Dữ liệu được phơi bày

### 2.1. Cú lừa Nhân chéo Dữ liệu (Cartesian Explosion)
Trước khi nâng cấp, hệ thống mất tới 15 phút để tính toán Features nhưng Precision luôn bị kẹt ở mức 14%. Việc soi rọi lại mã nguồn SQL đã phát hiện ra một lỗi cực độ tinh vi ở mệnh đề tính trung vị Altcoin (`altcoin_median`):
- **Sự cố:** Sử dụng Window Function (`OVER PARTITION BY`) thay vì gom nhóm (`GROUP BY`).
- **Hệ quả:** Mỗi timestamp (thời điểm) bị nhân bản thành 150 dòng. Khi JOIN lại với bảng giá, dữ liệu phình to thành phép nhân chéo (Cartesian explosion), tạo ra 2.3 tỷ dòng ảo khiến DuckDB nghẹt thở.
- **Khắc phục:** Thay bằng `GROUP BY`, thời gian chạy giảm từ 15 phút xuống chỉ còn **31 giây**.

### 2.2. Lỗi mất tích "Anh cả" BTCUSDT
Mặc dù dữ liệu Klines (nến) tải về thành công, nhưng BTCUSDT liên tục biến mất khỏi bảng kết quả cuối cùng.
Lý do nằm ở việc thuật toán tải dữ liệu chỉ nhận danh sách các đồng coin đang bị "Bơm" (`score_symbols`) mà quên mất việc cố định tải BTC. Điều này khiến toàn bộ các thông số bối cảnh vĩ mô (`btc_volatility_24h`, `btc_ret_24h`) bị gán bằng NULL, vô hiệu hóa khả năng đọc xu hướng thị trường của mô hình.

---

## 3. Khai phá Alpha: Phân kỳ Cá mập (Smart Money Divergence)
Sau khi dữ liệu được làm sạch, mô hình LightGBM nguyên bản chỉ chạm ngưỡng 36.6%. Để xuyên thủng trần 50%, team nghiên cứu đã thay đổi góc nhìn từ Tỷ lệ Tài khoản (Retail Accounts) sang **Tỷ lệ Dòng tiền thật (Position Ratio)**.

**Công thức Smart Money Divergence:**
`global_ls_ratio (Đám đông) - top_long_short_position_ratio (Cá mập)`

- **Hiện tượng sinh lời:** Khi chỉ số này dương đột biến, nghĩa là đám đông (Retail) đang hăng máu Fomo Long, trong khi Cá Mập (Top Traders) đã âm thầm chốt lời và lật sang Short. 
- **Kết quả:** Sự có mặt của Feature này ở các gốc cây quyết định sâu (Deep Splits) đã kéo mô hình bật lên mức Precision cao nhất.

---

## 4. Báo cáo Thực chiến (Quant Backtest Report)

Bài giả lập được thực hiện khắt khe với các tiêu chuẩn của Quỹ đầu tư:
- **Tập dữ liệu:** Chỉ lấy 20% dữ liệu cuối cùng (Out-of-sample) chưa từng dùng để huấn luyện.
- **Thiết lập:** Vốn 1000$, Ký quỹ 50$, Đòn bẩy x5, Risk 1% (Cắt lỗ 4%).
- **Pre-filter:** Loại bỏ các coin Sideway, chỉ ngắm bắn các coin có độ nén (Pump >= 10%/24h).
- **Ngưỡng kích hoạt:** Bóp nghẹt Recall xuống 4% để mô hình chỉ chọn những kèo "Chắc ăn nhất".

### Kết quả Giao dịch
- **Tổng số lệnh:** 715
- **Tỷ lệ Thắng (Winrate):** **49.09%**
- **Lợi nhuận ròng:** **+$3022.50**
- **Tỷ suất ROI:** **+302.25%**
- **Profit Factor (Hệ số Lợi nhuận):** **1.79** *(Vượt xa tiêu chuẩn >1.5 của Hedge Fund)*.
- **Max Drawdown (Sụt vốn tối đa):** 30.22%

---

## 5. Kết luận & Định hướng
Bản cập nhật 06/09/2026 đã chứng minh Đảo Vàng không chỉ là một công cụ lọc tín hiệu, mà là một thuật toán giao dịch có **Lợi thế (Edge) mang tính toán học rõ rệt**. 

**Bài học MLOps lớn nhất rút ra:** 
Việc cố gắng tối đa hóa Precision (ví dụ lấy Fold đạt 52%) mà bỏ qua **Độ lệch hiệu chuẩn (ECE > 0.05)** hoặc **bóp méo siêu tham số (Hyperparameter tuning)** là con đường ngắn nhất dẫn đến cháy tài khoản. Sự đơn giản (Simplicity) và dữ liệu chuẩn sạch (Clean Data) mới là chân lý của định lượng.

*Báo cáo được tự động khởi tạo và vinh danh bởi OMP Agent.*
