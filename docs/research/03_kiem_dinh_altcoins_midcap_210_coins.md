# 📈 Báo Cáo Nghiên Cứu #03: Kiểm Định Mở Rộng Altcoins Vốn Hóa Vừa & Nhỏ (210 Coins × 1 Năm)

> **Mã nghiên cứu:** `RES-2026-0830-03`  
> **Ngày công bố:** 30/08/2026  
> **Tác giả:** Đội ngũ Nghiên cứu & Định lượng Đảo Vàng (`dao_vang Quant Lab`)  
> **Quy mô mẫu:** 210 Altcoins (Khối lượng 24h từ \$1,000,000 đến \$100,000,000)  
> **Khoảng thời gian:** 1 năm (08/2025 → 08/2026, 19,371,492 nến thô)  
> **Phương pháp:** 8-Fold Walk-Forward Cross-Validation, Isotonic Calibration

---

## 1. Mục Tiêu & Động Lực Nghiên Cứu

Trước đây, hệ thống chỉ được kiểm định trên **30 coin có thanh khoản lớn nhất (Mega-Cap)**. Điều này tạo ra câu hỏi lớn về tính tổng quát (Generalizability):
- *Liệu mô hình có hoạt động hiệu quả trên hàng trăm Altcoins vốn hóa \$10M–\$500M — nơi các đợt pump & dump diễn ra thường xuyên nhất?*
- *Các tính năng phái sinh (Funding Rate, Open Interest, Top Trader Account Ratio từ Binance Vision) có duy trì được giá trị dự báo trên diện rộng không?*

---

## 2. Kết Quả Tổng Quan & So Sánh Mô Hình

| Tiêu chí | LightGBM (Challenger) | Logistic Regression (Champion) | Đánh giá |
|---|:---:|:---:|---|
| **Precision trung bình** | **21.23%** 🏆 | **14.87%** | **LightGBM thắng áp đảo (+6.36%)** |
| **Khoảng tin cậy 95% (CI)** | **[20.06% – 22.17%]** | — | Biên độ rất hẹp ($\pm 1\%$), độ ổn định cao |
| **Sai số hiệu chuẩn (ECE)** | **0.0249** | — | Đạt chuẩn an toàn ($ECE \le 0.05$) |
| **Số Fold vượt trội** | **8 / 8 Folds** | 0 / 8 Folds | Thắng tuyệt đối trên mọi chu kỳ kiểm tra |

### So Sánh Bước Ngoặt: Mega-Cap (Top 30) vs Mid-Cap (210 Coins)

| Hạng mục kiểm định | Top 30 Mega-Cap (2.6 Năm) | 210 Mid-Cap Altcoins (1 Năm) | Giải thích quy luật |
|---|:---:|:---:|---|
| **LightGBM Precision** | $16.22\%$ | **$21.23\%$** 🟢 | Mid-cap có nhiều cấu trúc phi tuyến mà cây quyết định khai thác tốt |
| **LogReg Precision** | **$27.84\%$** 🟢 | $14.87\%$ 🔴 | LogReg hoạt động tốt trên coin lớn, nhưng gãy trên altcoins nhỏ |
| **Mô hình tối ưu** | **Logistic Regression** | **LightGBM** | **Cần chiến lược phân khúc mô hình theo vốn hóa** |
| **Quality Gates** | 1 / 5 Gates PASS | **3 / 5 Gates PASS** | Mức độ tin cậy được nâng cấp rõ rệt |

---

## 3. Độ Quan Trọng Của Các Nhóm Đặc Trưng (Feature Importance)

Bảng xếp hạng Information Gain của LightGBM trên 210 coins:

| Hạng | Đặc trưng (Feature) | Information Gain | Nhóm dữ liệu | Ý nghĩa thị trường |
| :---: | :---| :---: | :---: |---|
| **1** | `volatility_24h` | **536,619** | Biến động giá | Mức độ mở rộng biên độ nến 24h là tiền đề của xả hàng |
| **2** | `funding_rate_raw` | **296,223** | Phái sinh (Binance) | Đã sửa lỗi ASOF JOIN: trở thành biến phân loại top 2 |
| **3** | `top_acct_ratio` | **234,819** | Phái sinh (Binance Vision) | Tỷ lệ Long/Short của Top Trader phản ánh hành vi tay to |
| **4** | `global_ls_ratio` | **217,652** | Phái sinh (Binance Vision) | Tỷ lệ Long/Short toàn sàn đo lường mức độ FOMO đám đông |
| **5** | `return_24h` | **133,879** | Giá | Biên độ tăng giá trong 24 giờ qua |
| **6** | `oi_change_4h` | **112,450** | Phái sinh (Binance Vision) | Tốc độ thay đổi Open Interest trong 4 giờ |

> **Phát hiện quan trọng:** Các dữ liệu phái sinh lịch sử (Derivatives Data) thu thập từ kho lưu trữ Binance Vision chiếm **3 trong top 4 đặc trưng quan trọng nhất**, khẳng định giá trị vượt trội so với chỉ sử dụng nến OHLCV đơn thuần.

---

## 4. Hiệu Quả Theo Chế Độ Thị Trường (Market Regimes)

| Chế độ thị trường | Precision | Số lượng mẫu kiểm định | Tỷ lệ phân bổ mẫu |
|---|:---:|:---:|:---:|
| **`SIDEWAY_DISTRIBUTION`** | **23.75%** 🏆 | **237,812** | **88.2%** |
| **`TRENDING_BEAR`** | **16.30%** | **31,728** | **11.8%** |
| **`TRENDING_BULL`** | $0.00\%$ | $0$ | $0.0\%$ |
| **`HIGH_VOLATILITY_CHOP`** | $0.00\%$ | $0$ | $0.0\%$ |

---

## 5. Kết Luận
Nghiên cứu chứng minh rằng trên không gian 210 Altcoins, **LightGBM kết hợp dữ liệu phái sinh chuyên sâu và bộ lọc Regime Gate** mang lại hiệu quả vượt trội, là cơ sở dữ liệu nền tảng cho việc nâng cấp hệ thống Đảo Vàng 2026.
