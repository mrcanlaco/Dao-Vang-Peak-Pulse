# Forward 48h August — model timing branch

## Kết luận

Nhánh feature timing giúp Logistic + Platt đứng đầu trên development lịch sử,
nhưng **không xác nhận được trên forward August**. Giữ research-only, không đổi
live và không promote bundle.

| Chỉ số forward | Kết quả |
|---|---:|
| Universe đã resolve | 5.038 rows, 176 symbols |
| Positive labels | 1.095 (21,73%) |
| Episode signals, cooldown 24h | 187 |
| True positives | 52 |
| Precision | 27,81% |
| Wilson 95% precision | 21,88%–34,63% |
| Recall | 4,75% |
| Average precision | 29,62% (1,36x prevalence) |
| ROC-AUC | 0,6244 |
| Brier | 0,16825 (null 0,17011) |
| ECE | 0,0291 |
| Conservative EV | **−6,19% / signal** |

Với target +20%, stop −16% và chi phí vòng 0,2%, precision hòa vốn là
45%. Cả estimate điểm và cận trên Wilson của nhánh này đều dưới hòa vốn.

## Protocol khóa trước forward

- Label: target −20% trong 48h phải đến trước MAE/hard stop +16%; cùng candle
  chạm cả hai bị loại.
- Universe: `price_ret_24h >= 15%`, snapshot hourly tại phút 04.
- Một tín hiệu mỗi symbol trong 24h.
- History PIT: 12.504 rows, 146 symbols, 02/12/2025–30/07/2026.
- 3 development folds, embargo 48h.
- Grid bounded: 4 model/feature variants × isotonic/Platt. Không dùng August
  để chọn model, calibration hay threshold.
- Champion khóa: `augmented_logistic__platt`, threshold 0,25.
- Bundle SHA-256 khóa trước forward:
  `1946dd9ad7492f8afcdbadff19cb15ef7b593676f29acf7698f55efa2b78d08e`.

Champion lịch sử có 308 episode signals, precision 30,19%, mean fold EV
−4,88%, chỉ 1/3 fold dương. Policy partition gần nhất có 66 signals,
precision 48,48%, EV +1,25%; forward cho thấy lát cắt này không ổn định.

Các feature bổ sung đều chỉ dùng snapshot hiện tại/quá khứ và có thể triển
khai bằng state rolling: pump-age, đỉnh return 24h trong 6 snapshot, độ rời
đỉnh run-up, thay đổi khoảng cách high, chênh momentum ngắn/dài và reversal
pressure. Không feature nào đọc future candle.

## Theo tuần

| Tuần UTC | Signals | Hits | Precision | EV |
|---|---:|---:|---:|---:|
| 27/07–02/08 (chỉ 01–02/08) | 15 | 2 | 13,33% | −11,40% |
| 03/08–09/08 | 72 | 17 | 23,61% | −7,70% |
| 10/08–16/08 | 52 | 21 | 40,38% | −1,66% |
| 17/08–23/08 | 48 | 12 | 25,00% | −7,20% |

Không tuần nào có EV dương.

## Audit coverage và provenance

`data_live/live.duckdb::feature_results` là nguồn feature forward;
`data_live/live.duckdb::kline` cung cấp giá entry và outcome. Có 9.777
candidate base pump>=10%; 8.629 đủ future 48h, 1.148 bị loại vì thiếu future.
Sau gate pump>=15% còn 5.038 labeled rows.

Một lần materialization ban đầu bằng exact join vào
`D:/Quant-trading/data_lake/quant_master.duckdb::klines_5m` chỉ match
112/5.667 candidate pump>=15% (1,98%, 19 symbols), trong khi live kline match
5.667/5.667. Kết quả 112-row đó bị **hủy vì denominator bias**; nó không được
dùng để chọn lại bundle hay threshold. Report cuối dùng live kline, và giữ
nguyên SHA-256 bundle đã khóa.

## Artifact

- `scripts/forward48_aug_model_search.py`
- `artifacts/forward48_aug_model_lock.json`
- `artifacts/forward48_aug_model_bundle.joblib`
- `artifacts/forward48_aug_model_report.json`
- `artifacts/forward48_aug_model_events.csv`
- `artifacts/forward48_aug_model_dataset.duckdb`

Promotion gate: **FAIL** (187 signals đủ sample tối thiểu, nhưng precision,
Wilson lower bound và positive-week gates đều fail).
