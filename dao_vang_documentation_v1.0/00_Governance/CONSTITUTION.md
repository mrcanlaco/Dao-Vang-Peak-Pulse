---
document_id: DAO_VANG_CONSTITUTION
version: 1.0.0
status: approved
authority: highest
effective_date: 2026-07-31
---

# HIẾN PHÁP ĐẢO VÀNG

## 1. Mục tiêu tối cao

Đảo Vàng không cố dự đoán chính xác giá sẽ tăng hay giảm đến mức nào.

Đảo Vàng chỉ tập trung vào một nhiệm vụ:

> Phát hiện sớm những đồng coin có xác suất cao chuyển từ giai đoạn tăng giá sang giai đoạn phân phối và có nguy cơ xuất hiện một nhịp xả đáng kể.

Mọi dữ liệu, chỉ số, thuật toán, mô hình AI và tính năng phải phục vụ trực tiếp mục tiêu này.

Một thành phần chỉ được đưa vào hệ thống khi giúp cải thiện ít nhất một trong các yếu tố:

- phát hiện Distribution sớm hơn;
- tăng precision hoặc recall;
- giảm false positive;
- cải thiện calibration;
- tăng stability;
- tăng explainability;
- tăng data quality.

Đảo Vàng không được phát triển thành hệ thống “biết mọi thứ”. Hệ thống phải chuyên biệt, có kỷ luật, có thể kiểm chứng và ngày càng tốt hơn ở một nhiệm vụ duy nhất.

## 2. Nguyên tắc phương pháp luận

### 2.1. Không có dữ liệu trước khi có định nghĩa mục tiêu

Trước khi thu thập dữ liệu hoặc xây dựng mô hình, hệ thống phải định nghĩa rõ:

- Distribution là gì;
- tín hiệu đúng và sai;
- prediction horizon;
- mức giảm mục tiêu;
- mức tăng bất lợi tối đa;
- thời gian tối đa để sự kiện xảy ra;
- điều kiện loại trừ.

Không sử dụng khái niệm mơ hồ nếu không có tiêu chí định lượng.

### 2.2. Không tin nguồn dữ liệu; chỉ tin kết quả đã kiểm chứng

Không mặc định tin Binance, API, website, browser, OCR, AI, công thức bên thứ ba hoặc nhận định trader.

Mọi nguồn dữ liệu phải được kiểm tra:

- tính ổn định;
- tính nhất quán;
- độ trễ;
- tỷ lệ thiếu;
- khả năng thu thập lịch sử;
- schema;
- giá trị thực tế đối với Distribution.

### 2.3. Internet và AI chỉ dùng để tạo giả thuyết

Internet, AI, tài liệu và kinh nghiệm chỉ được dùng để:

- tạo giả thuyết;
- gợi ý dữ liệu;
- phát hiện điểm mù;
- đề xuất cách kiểm chứng;
- tìm lỗi phương pháp.

Vòng đời bắt buộc:

```text
Hypothesis → Experimental → Validated → Production → Retired
```

Không đưa giả thuyết vào production chỉ vì nghe hợp lý.

### 2.4. Không sử dụng dữ liệu tương lai

Tại thời điểm `T`, hệ thống chỉ được dùng dữ liệu có `available_time <= T`.

Mỗi record tối thiểu phải có:

- `event_time`: thời điểm sự kiện xảy ra tại nguồn;
- `available_time`: thời điểm sớm nhất hệ thống có thể biết dữ liệu;
- `collected_at`: thời điểm hệ thống ghi nhận dữ liệu.

Nghiêm cấm:

- dùng nến chưa đóng;
- dùng future high/low trong feature;
- dùng dữ liệu cập nhật sau thời điểm tín hiệu;
- fit scaler trên toàn dataset;
- random split;
- nearest join lấy record tương lai;
- để label hoặc thông tin tương lai rò vào feature.

### 2.5. Không đánh giá trên dữ liệu dùng để tạo chiến thuật

Dữ liệu phải được tách theo thời gian thành:

- Discovery;
- Validation;
- Test;
- Forward Test.

Ưu tiên walk-forward validation. Test set không được dùng để tiếp tục chỉnh tham số.

## 3. Định nghĩa Distribution

Distribution phải được biểu diễn bằng label định lượng, có version và tái tạo được bằng code.

Khung v0.1:

- symbol: BTCUSDT;
- market: Binance USD-M Futures;
- interval: 5 phút;
- signal price: close của nến đã đóng;
- prediction horizon: tối đa 24 giờ;
- target drawdown: 8%;
- max adverse excursion trước target: 4%.

Các giá trị trên là khởi điểm nghiên cứu, không phải chân lý. Mọi thay đổi phải tạo Label Version mới.

## 4. Chín khối chính thức

### Khối -1 — Mục tiêu và nhãn
Xác định chính xác hệ thống dự đoán điều gì.

### Khối 0 — Tri thức và giả thuyết
Lưu vòng đời đầy đủ của mọi giả thuyết, kể cả giả thuyết thất bại.

### Khối 1 — Thu thập dữ liệu
Lấy đúng, lưu đúng, gắn thời gian đúng, kiểm tra chất lượng. Không diễn giải và không phát tín hiệu.

### Khối 2 — Chuẩn hóa và feature
Tạo feature từ dữ liệu point-in-time. Không xóa dữ liệu gốc.

### Khối 3 — Pattern
Nhận diện tổ hợp điều kiện có cơ chế hành vi hợp lý. Không cộng điểm cơ học vô căn cứ.

### Khối 4 — Xác suất và giải thích
Xuất probability, confidence interval, sample size, evidence quality và điều kiện vô hiệu.

### Khối 5 — Watchlist
Chỉ hỗ trợ quyết định. Không tự Buy, Sell, Short, TP, SL hoặc quản lý vốn.

### Khối 6 — Ghi nhận kết quả
Phân biệt Model Outcome và Trading Outcome. Ghi mọi tín hiệu, không chỉ giao dịch thực tế.

### Khối 7 — Kiểm chứng
So sánh baseline, đo precision, recall, false positive, lead time, stability và calibration.

### Khối 8 — Học lại và versioning
Mọi thay đổi phải qua backtest, validation, out-of-sample, walk-forward, forward test và phê duyệt con người.

## 5. Nguyên tắc bất biến

1. Chỉ thêm thứ làm tăng giá trị dự báo hoặc chất lượng hệ thống.
2. Mọi thay đổi phải thuộc đúng khối.
3. Chỉ giữ feature/pattern sống sót qua kiểm chứng.
4. Không tối ưu theo vài lệnh gần đây.
5. Đơn giản là mặc định.
6. Không che giấu bất định.
7. Mọi kết quả phải tái tạo được.
8. Mọi thay đổi phải rollback được.
9. Không tự động giao dịch trong phạm vi Đảo Vàng Core.
10. AI không được thay thế kiểm chứng thống kê.

## 6. Phạm vi MVP

MVP chỉ trả lời:

> Bộ dữ liệu tối thiểu có tạo ra lợi thế thống kê trong phát hiện Distribution hay không?

MVP dùng:

- BTCUSDT;
- Binance USD-M Futures;
- 5 phút;
- OHLCV;
- Funding Rate;
- Open Interest;
- Taker Buy/Sell Volume;
- Global Long/Short Account Ratio;
- Top Trader Long/Short Account Ratio.

MVP không dùng AI, OCR, browser automation, whale data, social/news, dashboard lớn, alert real-time, auto trade hoặc database phân tán.

## 7. Tiêu chuẩn thành công

MVP chỉ thành công khi:

- dữ liệu đủ sạch;
- nhãn tái tạo được;
- không có leakage nghiêm trọng;
- có baseline rõ;
- có ít nhất một pattern/model vượt baseline;
- hiệu suất giữ được ngoài mẫu;
- forward test không sụp đổ;
- kết quả giải thích được;
- lợi thế đủ lớn để đáng tiếp tục.

## 8. Câu hỏi bắt buộc trước mọi thay đổi

1. Thuộc khối nào?
2. Cơ chế giúp phát hiện Distribution là gì?
3. Có dữ liệu lịch sử không?
4. Có nguy cơ leakage không?
5. Baseline là gì?
6. Điều kiện chứng minh hiệu quả?
7. Điều kiện loại bỏ?
8. Có làm hệ thống khó bảo trì hơn không?
9. Có cách đơn giản hơn không?
10. Có rollback được không?

## 9. Thứ tự ưu tiên tài liệu

Khi tài liệu mâu thuẫn:

1. `CONSTITUTION.md`
2. `MVP_SCOPE.md`
3. Specification chuyên ngành
4. `ARCHITECTURE.md`
5. `AGENTS.md`
6. Code hiện hành

Code không phải nguồn chân lý nếu trái specification.
