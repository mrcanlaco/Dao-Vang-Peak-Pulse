# 🧪 Báo Cáo Nghiên Cứu #02: Thí Nghiệm 8 Chiến Lược Giao Dịch Phân Phối Đỉnh

> **Mã nghiên cứu:** `RES-2026-0830-02`  
> **Ngày công bố:** 30/08/2026  
> **Tác giả:** Đội ngũ Nghiên cứu & Định lượng Đảo Vàng (`dao_vang Quant Lab`)  
> **Quy mô mẫu:** 209 Altcoins vốn hóa vừa và nhỏ (\$10M–\$500M)  
> **Dữ liệu:** 1 năm (08/2025 → 08/2026, 1,350,576 hàng điều kiện xả)  
> **Phương pháp:** 8-Fold Walk-Forward Cross-Validation, Embargo 48h

---

## 1. Tóm Tắt Nghiên Cứu (Abstract)

Sau khi xác lập ưu thế của mô hình Machine Learning trên tập Altcoin, câu hỏi đặt ra là:
1. *Tăng ngưỡng xác suất (Percentile 98% $\rightarrow$ 99% $\rightarrow$ 99.5%) có giúp đạt mục tiêu Precision $\ge 35\%$ không?*
2. *Mô hình Ensemble (kết hợp đồng thuận giữa Logistic Regression và LightGBM) có tạo ra bộ lọc an toàn hơn không?*
3. *Bộ lọc chế độ thị trường (Regime Gate) cải thiện độ chính xác và mức độ an toàn như thế nào?*

Nghiên cứu tiến hành thử nghiệm song song 8 biến thể chiến lược trên cùng một tập dữ liệu và chu kỳ Walk-Forward đồng nhất.

---

## 2. Danh Mục 8 Chiến Lược Thử Nghiệm

| ID | Tên Chiến Lược | Nguyên Lý & Cấu Trúc |
| :---: | :---|---|
| **A** | **LGB p98 (Baseline)** | LightGBM kết hợp Isotonic Calibration, lấy top 2% điểm số tin cậy nhất (`percentile 98`). |
| **B** | **LGB p99** | Nâng ngưỡng lọc lên top 1% tự tin nhất (`percentile 99`). |
| **C** | **LGB p99.5** | Nâng ngưỡng cực hạn lên top 0.5% tự tin nhất (`percentile 99.5`). |
| **D** | **LogReg p98** | Mô hình tuyến tính Champion hiện tại, ngưỡng p98. |
| **E** | **Ensemble p98** | Kích hoạt tín hiệu khi và chỉ khi CẢ HAI mô hình (LightGBM VÀ Logistic Regression) cùng đồng thuận. |
| **F** | **Regime + LGB p98** | LightGBM p98 kết hợp bộ lọc chỉ cho phép phát tín hiệu trong `SIDEWAY_DISTRIBUTION` và `TRENDING_BEAR`. |
| **G** | **Regime + Ensemble p98** | Kết hợp bộ lọc Regime Gate VÀ sự đồng thuận của cả 2 mô hình. |
| **H** | **Regime + LGB p99** | Kết hợp bộ lọc Regime Gate VÀ ngưỡng p99 cực hạn. |

---

## 3. Bảng Xếp Hạng Hiệu Năng 8 Chiến Lược

| Xếp hạng | Chiến lược | Actual Precision | 95% Confidence Interval | Recall | Tổng số tín hiệu | Lệnh đúng (TP) | Số tín hiệu / Fold |
| :---: | :---| :---: | :---: | :---: | :---: | :---: | :---: |
| 🥇 | **F: Regime + LGB p98** | **20.83%** 🏆 | **[19.55% – 22.46%]** | **6.94%** | **45,217** | **9,419** | **5,652** |
| 🥈 | **H: Regime + LGB p99** | **20.83%** | [19.29% – 22.44%] | 6.54% | 42,548 | 8,864 | 5,318 |
| 🥉 | **A: LGB p98 (Baseline)** | **20.81%** | [20.09% – 22.18%] | 9.09% | 59,030 | 12,286 | 7,379 |
| 4 | **B: LGB p99** | **20.73%** | [19.98% – 22.15%] | 8.54% | 55,603 | 11,527 | 6,950 |
| 5 | **C: LGB p99.5** | **20.56%** | [20.01% – 22.06%] | 7.56% | 48,760 | 10,024 | 6,095 |
| 6 | **G: Regime + Ensemble** | **17.08%** ⚠️ | [13.81% – 23.44%] | 0.58% | 4,555 | 778 | 569 |
| 7 | **E: Ensemble p98** | **16.93%** ⚠️ | [14.33% – 24.27%] | 0.73% | 5,658 | 958 | 707 |
| 8 | **D: LogReg p98** | **14.03%** ⚠️ | [12.50% – 17.82%] | 2.94% | 27,151 | 3,809 | 3,394 |

---

## 4. Các Phát Hiện Định Lượng Quan Trọng

### 🔍 1. Tăng Threshold Không Cải Thiện Độ Chính Xác
- **p98 $\rightarrow$ p99 $\rightarrow$ p99.5:** Độ chính xác dao động quanh mức **$20.8\%$** mà không tăng thêm, nhưng số lượng tín hiệu bị cắt giảm từ $59,030 \rightarrow 48,760$ (mất $17\%$ cơ hội).
- **Lý do kỹ thuật:** Mô hình sau khi hiệu chuẩn Isotonic đã đạt sai số hiệu chuẩn tối ưu ($ECE = 0.0249$). Khi xác suất đã phản ánh trung thực phân phối thực tế, việc co hẹp ngưỡng ở đuôi phân phối không làm thay đổi tỷ lệ đúng/sai bản chất.

### 🔍 2. Ensemble Gây Tổn Hại Hiệu Năng (Thất Bại Của LogReg Trên Altcoin)
- Kết hợp **Ensemble (LGB + LogReg)** làm Precision sụt giảm mạnh từ **$20.81\% \rightarrow 16.93\%$** (giảm $-3.88\%$).
- Đồng thời, số lượng tín hiệu bị triệt tiêu tới **$90\%$** (chỉ còn ~700 tín hiệu/fold).
- **Nguyên nhân:** Mô hình Logistic Regression quá tuyến tính và hoạt động kém trên Altcoin (chỉ đạt 14.03%). Khi bắt buộc cả 2 mô hình cùng đồng thuận, LogReg trở thành "nút thắt cổ chai" loại bỏ các cơ hội thắng đúng của LightGBM.

### 🔍 3. Giá Trị Của Regime Gate: Triệt Tiêu 23% Nhiễu
- **Regime Gate** giữ nguyên tỷ lệ chính xác cao nhất (**$20.83\%$**) trong khi **loại bỏ 13,813 tín hiệu nhiễu** phát ra trong giai đoạn thị trường tăng nóng (`TRENDING_BULL`) hoặc biến động hỗn loạn (`HIGH_VOLATILITY_CHOP`).
- **Ý nghĩa thực tế:** Giúp người giao dịch tránh bị quá tải thông báo (Alert Fatigue) và tập trung vào các giai đoạn thị trường có xác suất phân phối cao nhất.

---

## 5. Quyết Định Kiến Trúc Được Phê Duyệt

1. **Chọn Chiến Lược F (Regime + LightGBM p98)** làm tiêu chuẩn vận hành chính thức cho phân khúc Altcoin.
2. **Từ chối cơ chế Ensemble đa mô hình** trên nhóm Altcoin vốn hóa vừa/nhỏ.
3. **Kích hoạt mặc định Regime Gate** trong `configs/live.yaml` và quy trình quét 24/7 của Daemon.
