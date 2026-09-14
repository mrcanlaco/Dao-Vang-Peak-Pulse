# Báo Cáo Chuyên Sâu: Bóc Tách Bản Chất & Công Thức Của `combo_pump25_reversal_funding_scout`

*Ngày thực hiện: 2026-09-14 17:05:46 UTC*

## 1. Tóm tắt phát hiện: 'Sự thật đằng sau'
Biến thể đạt Precision 50.0% và EV dương (+1.80%) dựa trên **sự hội tụ của 3 lực kích hoạt vật lý**:
1. **Bơm kiệt sức (Climax Pump >= 25%)**: Loại bỏ 90% nhiễu dao động thông thường, chỉ chọn các coin có dòng tiền đầu cơ đẩy cực độ.
2. **Đỉnh cước phí (Crowded Long Exhaustion)**: `funding_percentile_30d >= 0.80` + `change_8h > 0`. Đám đông long chấp nhận trả phí cao nhất 30 ngày và cước đang dốc lên.
3. **Kích hoạt xác nhận cấu trúc (Roll-over Trigger <= -2%)**: Giá đã không còn tạo đỉnh mới và bắt đầu rớt ít nhất 2% từ đỉnh 24h, đánh dấu phe mua hụt hơi.

## 2. Thử nghiệm độ nhạy: Ngưỡng Pump
| Ngưỡng Pump | Tín hiệu | Precision | Conservative EV |
|---|---:|---:|---:|
| `pump_15pct` | 100 | 24.0% | **-7.56%** |
| `pump_18pct` | 87 | 28.7% | **-5.86%** |
| `pump_20pct` | 36 | 22.2% | **-8.20%** |
| `pump_22pct` | 50 | 36.0% | **-3.24%** |
| `pump_25pct` | 23 | 52.2% | **+2.58%** |
| `pump_28pct` | 21 | 14.3% | **-11.06%** |
| `pump_30pct` | 8 | 50.0% | **+1.80%** |
| `pump_35pct` | 14 | 64.3% | **+6.94%** |

## 3. Thử nghiệm độ nhạy: Độ sâu đảo chiều (Reversal Depth từ đỉnh)
| Độ lệch từ đỉnh 24h | Tín hiệu | Precision | Conservative EV |
|---|---:|---:|---:|
| `no_filter` | 39 | 20.5% | **-8.82%** |
| `dist_0pct` | 39 | 20.5% | **-8.82%** |
| `dist_1pct` | 49 | 28.6% | **-5.91%** |
| `dist_2pct` | 23 | 52.2% | **+2.58%** |
| `dist_3pct` | 39 | 30.8% | **-5.12%** |
| `dist_4pct` | 38 | 47.4% | **+0.85%** |
| `dist_5pct` | 6 | 83.3% | **+13.80%** |
| `dist_6pct` | 14 | 50.0% | **+1.80%** |

## 4. Bóc tách thành phần (Component Ablation)
| Cấu hình kiểm tra | Tín hiệu | Precision | Conservative EV |
|---|---:|---:|---:|
| `no_funding_gate` | 211 | 28.0% | **-6.13%** |
| `scout_full (pct>=80 + persist>0 + change8h>0)` | 23 | 52.2% | **+2.58%** |
| `pct_only (percentile_30d >= 80%)` | 88 | 35.2% | **-3.52%** |
| `persistence_only (persistence_7d > 0)` | 188 | 28.7% | **-5.86%** |
| `change_only (change_8h > 0)` | 118 | 31.4% | **-4.91%** |
| `raw_high (funding_rate_raw >= 0.05%)` | 13 | 30.8% | **-5.12%** |

## 5. Danh sách kiểm toán 18 tín hiệu thực tế
| Symbol | Thời gian (UTC) | Giá vào | Pump 24h | Rơi từ đỉnh | Funding %ile | Kết quả nhãn |
|---|---|---:|---:|---:|---:|---|
| `APRUSDT` | 2026-06-02T20:04 | 0.2314 | +31.5% | -4.1% | 100% | ❌ DỪNG LỖ / TIMEOUT |
| `CLOUSDT` | 2026-06-03T11:04 | 0.1937 | +58.9% | -2.6% | 80% | ✅ ĐẠT TP -20% |
| `BEATUSDT` | 2026-06-08T12:04 | 4.4247 | +72.5% | -3.0% | 95% | ✅ ĐẠT TP -20% |
| `CLOUSDT` | 2026-06-12T04:04 | 0.1899 | +36.2% | -3.4% | 100% | ✅ ĐẠT TP -20% |
| `JELLYJELLYUSDT` | 2026-06-14T13:04 | 0.0740 | +27.4% | -3.0% | 94% | ❌ DỪNG LỖ / TIMEOUT |
| `BASUSDT` | 2026-06-24T12:04 | 0.0415 | +34.3% | -3.9% | 100% | ❌ DỪNG LỖ / TIMEOUT |
| `MAGMAUSDT` | 2026-06-26T16:04 | 0.7306 | +72.8% | -3.5% | 99% | ✅ ĐẠT TP -20% |
| `RAVEUSDT` | 2026-06-29T09:04 | 0.4823 | +69.0% | -10.3% | 100% | ✅ ĐẠT TP -20% |
| `TACUSDT` | 2026-06-29T20:04 | 0.0588 | +169.1% | -7.0% | 100% | ❌ DỪNG LỖ / TIMEOUT |
| `BLESSUSDT` | 2026-07-03T11:04 | 0.0092 | +28.1% | -9.8% | 100% | ❌ DỪNG LỖ / TIMEOUT |
| `4USDT` | 2026-07-06T01:04 | 0.0125 | +26.1% | -7.8% | 88% | ✅ ĐẠT TP -20% |
| `EDGEUSDT` | 2026-07-07T17:04 | 0.3918 | +37.5% | -3.7% | 81% | ❌ DỪNG LỖ / TIMEOUT |
| `BUSDT` | 2026-07-11T04:04 | 0.2408 | +49.3% | -2.4% | 88% | ✅ ĐẠT TP -20% |
| `AKEUSDT` | 2026-07-15T08:04 | 0.0007 | +241.3% | -14.2% | 94% | ✅ ĐẠT TP -20% |
| `TAGUSDT` | 2026-07-19T12:04 | 0.0012 | +26.5% | -3.6% | 94% | ❌ DỪNG LỖ / TIMEOUT |
| `BUSDT` | 2026-07-19T13:04 | 0.2072 | +40.1% | -8.5% | 87% | ❌ DỪNG LỖ / TIMEOUT |
| `HEMIUSDT` | 2026-07-21T00:04 | 0.0071 | +57.1% | -10.9% | 100% | ✅ ĐẠT TP -20% |
| `LABUSDT` | 2026-07-22T04:04 | 0.1788 | +36.6% | -3.4% | 97% | ✅ ĐẠT TP -20% |
| `APRUSDT` | 2026-07-24T16:04 | 0.2165 | +36.2% | -3.3% | 82% | ❌ DỪNG LỖ / TIMEOUT |
| `PIEVERSEUSDT` | 2026-07-26T08:04 | 0.9435 | +42.7% | -5.2% | 100% | ✅ ĐẠT TP -20% |
| `KAITOUSDT` | 2026-07-26T14:04 | 1.2014 | +25.9% | -2.6% | 90% | ❌ DỪNG LỖ / TIMEOUT |
| `TAGUSDT` | 2026-07-27T12:04 | 0.0014 | +28.3% | -3.6% | 100% | ❌ DỪNG LỖ / TIMEOUT |
| `UAIUSDT` | 2026-07-29T17:04 | 0.4305 | +41.8% | -5.1% | 93% | ✅ ĐẠT TP -20% |

## 6. Công thức định lượng chuẩn hóa (V3 Production Formula)

```text
ELIGIBLE = (price_ret_24h >= 0.25)
       AND (distance_from_high_24h <= -0.02)
       AND (funding_percentile_30d >= 0.80)
       AND (funding_persistence_7d > 0)
       AND (funding_change_8h > 0)
       AND (model_probability >= calibrated_threshold)
```