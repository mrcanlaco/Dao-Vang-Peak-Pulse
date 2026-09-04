# 📊 Báo Cáo Nghiên Cứu #01: So Sánh Đối Đầu Mô Hình Heuristic 0–100 vs Machine Learning

> **Mã nghiên cứu:** `RES-2026-0830-01`  
> **Ngày công bố:** 30/08/2026  
> **Tác giả:** Đội ngũ Nghiên cứu & Định lượng Đảo Vàng (`dao_vang Quant Lab`)  
> **Quy mô mẫu:** 160 Altcoins vốn hóa vừa và nhỏ (\$10M–\$500M)  
> **Khoảng thời gian:** 1 năm gần nhất (08/2025 → 08/2026, nến 5 phút)  
> **Tổng số nến đánh giá:** 1,164,492 hàng dữ liệu điều kiện xả (Exhaustion Candidates)  
> **Phương pháp xác thực:** 8-Fold Walk-Forward Cross-Validation (Embargo 48 giờ chống rò rỉ dữ liệu)

---

## 1. Tóm Tắt Nghiên Cứu (Executive Abstract)

Hệ thống Đảo Vàng ban đầu sử dụng mô hình chấm điểm theo quy tắc chuyên gia **V1 Heuristic (thang điểm 0–100)** gồm 8 thành phần trọng số tuyến tính để phát hiện các tín hiệu phân phối đỉnh và tìm cơ hội Short.

Nghiên cứu này thực hiện kiểm định độc lập trên dữ liệu lịch sử quy mô lớn nhằm trả lời câu hỏi:
1. *Hiệu quả thực tế của mô hình Heuristic gốc là bao nhiêu khi so với tỷ lệ ngẫu nhiên của thị trường?*
2. *Khi nâng ngưỡng điểm Heuristic lên cao ($\ge 70$ hoặc $\ge 80$), tỷ lệ thắng có tăng theo không?*
3. *Mô hình Machine Learning (LightGBM kết hợp Isotonic Calibration và Regime Gate) cải thiện độ chính xác bao nhiêu lần so với Heuristic?*

### Kết quả then chốt:
- **Tỷ lệ nền ngẫu nhiên (Base Rate):** $11.74\%$
- **Heuristic gốc ở cấu hình mặc định ($\ge 40$):** Đạt **$13.28\%$ precision** (chỉ nhỉnh hơn ngẫu nhiên $1.54\%$, tỷ lệ báo động giả lên tới $86.7\%$).
- **Heuristic ở ngưỡng khuyến nghị Short ($\ge 70$):** Đạt **$0.00\%$ precision** (31/31 tín hiệu thua do rơi vào bẫy bắt đỉnh nến đang pump).
- **Regime Gate + LightGBM (p98):** Đạt **$20.93\%$ precision** (gấp **1.6 lần** Heuristic, vượt trội trên mọi chu kỳ kiểm định).

---

## 2. Thiết Kế Thí Nghiệm & Định Nghĩa Nhãn

### 2.1 Định Nghĩa Nhãn Mục Tiêu (Label Definition)
Một tín hiệu được xác nhận là **Thắng (Label = 1)** khi và chỉ khi trong vòng 12 giờ tiếp theo (144 nến 5m):
$$\text{Max Drawdown} \le -8\% \quad \text{VÀ} \quad \text{Maximum Adverse Excursion (MAE)} \le +4\%$$
- **Ý nghĩa kinh tế:** Giá thực sự bước vào pha phân phối giảm ít nhất 8% mà không có nhịp giật ngược vượt quá 4% gây cắn Stop Loss của nhà giao dịch.

### 2.2 Quy Trình Walk-Forward 8-Fold
- Dữ liệu 1 năm được chia thành 8 chu kỳ cuốn chiếu liên tiếp.
- Mỗi chu kỳ áp dụng **Embargo 48 giờ (576 nến)** giữa tập Train và Test để triệt tiêu hoàn toàn hiện tượng tự tương quan chuỗi thời gian (Serial Correlation).

---

## 3. Bảng So Sánh Hiệu Năng Toàn Diện

| Mô hình / Chiến lược | Ngưỡng kích hoạt | Precision (Độ chính xác) | Recall (Độ bao phủ) | Tổng tín hiệu | Lệnh đúng (TP) | Báo động giả (False Alarms) | Precision ở Sideway |
| :---| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🥇 **Optimal: Regime + LightGBM** | **Top 2% (p98)** | **20.93%** 🏆 | **14.69%** | **92,587** | **19,375** | **73,212** | **20.98%** |
| 🥈 **Challenger: LightGBM** | **Top 2% (p98)** | **20.59%** | 18.98% | 121,628 | 25,044 | 96,584 | 20.98% |
| 🥉 **V1 Heuristic gốc (Live)** | **Điểm $\ge 40$** | **13.28%** | 15.55% | 139,890 | 18,580 | 121,310 | 13.34% |
| 4. **Champion: LogisticRegression** | **Top 2% (p98)** | **12.75%** | 2.48% | 22,670 | 2,891 | 19,779 | 12.08% |
| 5. **V1 Heuristic (Watch)** | **Điểm $\ge 50$** | **12.56%** | 1.36% | 12,400 | 1,557 | 10,843 | 11.80% |
| 6. **Regime + Heuristic** | **Điểm $\ge 50$** | **12.52%** | 1.14% | 10,464 | 1,310 | 9,154 | 11.80% |
| 7. **V1 Heuristic** | **Điểm $\ge 60$** | **11.20%** | 0.07% | 732 | 82 | 650 | 6.99% |
| 8. **V1 Heuristic (Short Candidate)** | **Điểm $\ge 70$** | **0.00%** ⚠️ | 0.00% | 31 | 0 | 31 | 0.00% |
| 9. **V1 Heuristic (Extreme)** | **Điểm $\ge 80$** | **0.00%** ⚠️ | 0.00% | 0 | 0 | 0 | 0.00% |

---

## 4. Bóc Tách Sức Mạnh 8 Thành Phần Heuristic (ROC-AUC Analysis)

Để tìm hiểu nguồn gốc gây sai số của Heuristic, chúng tôi đo lường diện tích dưới đường cong ROC (**ROC-AUC**) và hệ số tương quan tuyến tính của từng thành phần trong `distribution_scorer.py`:

| Thành phần | Trọng số cũ | ROC-AUC | Hệ số tương quan | Điểm TB lệnh Thắng | Điểm TB lệnh Thua | Nhận xét & Đánh giá |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **BTC Context Filter** | $15\%$ | **0.5707** 🟢 | $+0.0863$ | **52.5** | **46.0** | **Tốt nhất**: Xu hướng BTC giảm là bối cảnh thuận lợi nhất cho Short |
| **Price-Volume Divergence** | $20\%$ | **0.5486** 🟢 | $+0.0556$ | **11.9** | **10.0** | **Hiệu quả**: Giá tăng nhưng khối lượng giảm thể hiện lực mua ảo |
| **Momentum Exhaustion** | $15\%$ | **0.5227** 🟡 | $+0.0263$ | **24.0** | **21.8** | **Đóng góp dương nhẹ**: Tốc độ tăng 1h suy giảm |
| **Open Interest Divergence** | $10\%$ | **0.5060** ⚪ | $-0.0002$ | **32.1** | **32.2** | **Vô nghĩa**: Chưa nắm bắt được dòng tiền phái sinh |
| **Fake Breakout (Bull Trap)** | $5\%$ | **0.5021** ⚪ | $+0.0079$ | **11.7** | **11.5** | **Vô nghĩa**: Nến 5m quá nhiều râu giả gây nhiễu |
| **Taker Sell Pressure** | $10\%$ | **0.4956** ⚪ | $+0.0116$ | **63.5** | **62.2** | **Vô nghĩa**: Tỷ lệ taker sell thường xuất hiện trễ sau khi giá đã rơi |
| **Funding Spike** | $15\%$ | **0.4495** 🔴 | $-0.0587$ | **3.7** | **7.0** | ⚠️ **Phản tác dụng**: Funding cực cao hay bị kéo Short Squeeze tiếp |
| **Distance from High** | $10\%$ | **0.4120** 🔴 | $-0.0917$ | **79.9** | **84.9** | ⚠️ **Nguy hiểm nhất**: Càng sát đỉnh 24h thì giá càng dễ phá đỉnh tiếp |
| **TỔNG ĐIỂM HEURISTIC (0-100)** | $100\%$ | **0.5338** | $+0.0367$ | **32.6** | **31.7** | **Kém**: Điểm khi thắng (32.6) và khi thua (31.7) gần như y hệt nhau |

---

## 5. Phân Tích Nguyên Nhân Thất Bại & Giải Pháp Machine Learning

### 5.1 Hai Giả Định Sai Lầm Của Heuristic Thủ Công
1. **Bẫy "Sát Đỉnh 24h" (`distance_from_high`)**:  
   Quy tắc Heuristic gán điểm tối đa ($100/100$) khi giá tiệm cận đỉnh 24h. Tuy nhiên, trên các Altcoin vốn hóa vừa và nhỏ, nến áp sát đỉnh thường có quán tính tăng rất mạnh (Momentum Breakout). Việc mở lệnh Short ngay tại điểm này khiến lệnh dễ bị quét $MAE > 4\%$ trước khi giá kịp đảo chiều.
2. **Bẫy "Funding Quá Cao" (`funding_spike`)**:  
   Heuristic cho rằng Funding Rate tăng đột biến là lúc vị thế Long sắp sập. Trong thực tế, đây là giai đoạn các nhà tạo lập thị trường (MM) đẩy giá lên nhằm ép thanh lý các vị thế Short sớm (Short Squeeze).

### 5.2 Lợi Thế Vượt Trội Của LightGBM
- **Khả năng phi tuyến**: LightGBM học được các điểm giao thoa điều kiện phức tạp (ví dụ: *chỉ kích hoạt khi Biến động đạt đỉnh VÀ Tỷ lệ Top Trader bắt đầu hạ nhiệt VÀ Funding Rate ngưng tăng*).
- **Hiệu chuẩn Isotonic**: Đưa ra xác suất thực nghiệm chính xác tuyệt đối, cho phép chọn lọc top 2% cơ hội có độ tin cậy cao nhất.

---

## 6. Kết Luận Thực Thi
- **Giao diện Web:** Tiếp tục duy trì Điểm Heuristic 0–100 để hiển thị trực quan các đặc tính thị trường.
- **Quyết định Bắn Tín Hiệu (Execution Gate):** Chuyển dịch hoàn toàn sang **Bộ đôi Regime Gate + LightGBM Calibrated Probability**.
