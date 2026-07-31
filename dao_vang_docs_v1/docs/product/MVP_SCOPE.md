---
document_id: DAO_VANG_MVP_SCOPE
version: 1.0.0
status: approved
---

# PHẠM VI MVP ĐẢO VÀNG

## 1. Mục tiêu

Xây dựng pipeline nghiên cứu point-in-time đủ để kiểm tra liệu dữ liệu derivatives tối thiểu có tạo lợi thế thống kê trong phát hiện Distribution hay không.

## 2. Câu hỏi nghiên cứu

Tại cuối mỗi nến 5 phút đã đóng của BTCUSDT, các feature từ price, funding, open interest, taker flow và trader ratios có giúp phát hiện sự kiện giảm giá theo Label v0.1 tốt hơn baseline đơn giản không?

## 3. Phạm vi cố định

```yaml
exchange: binance
market: usd_m_futures
contract_type: perpetual
symbol: BTCUSDT
canonical_interval: 5m
timezone: UTC
label_version: 0.1.0
prediction_horizon: 24h
```

## 4. Dữ liệu MVP

1. OHLCV futures.
2. Funding Rate.
3. Open Interest Statistics.
4. Taker Buy/Sell Volume.
5. Global Long/Short Account Ratio.
6. Top Trader Long/Short Account Ratio.

Top Trader Position Ratio chưa nằm trong MVP v1, trừ khi ADR mới phê duyệt.

## 5. Đầu ra bắt buộc

- raw snapshot không chỉnh sửa;
- normalized Parquet;
- metadata collection run;
- báo cáo data quality;
- bảng aligned 5 phút;
- Distribution Label v0.1;
- Feature Set v0.1;
- baseline results;
- walk-forward report;
- leakage test report;
- artifact manifest có version và hash.

## 6. Thành phần phải xây

### M0 — Nền tảng repo

- Python project;
- lint, type check, test;
- config;
- logging;
- CI;
- tài liệu.

### M1 — Collector và storage

- Binance USD-M REST client;
- pagination;
- retry/rate-limit;
- raw JSONL hoặc Parquet snapshot;
- normalized Parquet;
- DuckDB query layer;
- collection metadata.

### M2 — Data quality và alignment

- duplicate detection;
- gap detection;
- schema validation;
- timestamp normalization;
- as-of backward join;
- availability rules;
- quality flags.

### M3 — Label engine

- Distribution Label v0.1;
- edge-case tests;
- label diagnostics.

### M4 — Feature engine

- price, funding, OI, taker, ratios;
- rolling computations;
- null policy;
- leakage tests.

### M5 — Baseline và validation

- random/prevalence baseline;
- single-feature thresholds;
- logistic regression;
- time-based split;
- walk-forward;
- confidence intervals;
- calibration.

## 7. Ngoài phạm vi

- real-time signals;
- dashboard production;
- Telegram/Discord alerts;
- auto trading;
- TP/SL;
- account or API key trading permissions;
- order book;
- liquidation;
- on-chain;
- social/news;
- AI/LLM;
- LangGraph;
- multi-agent runtime;
- MCP;
- OCR/browser automation;
- nhiều coin;
- cloud microservices;
- Kubernetes;
- streaming platform;
- feature store phân tán.

## 8. Ràng buộc kỹ thuật

- UTC toàn hệ thống.
- Chỉ dùng nến đã đóng.
- Feature tại `T` chỉ dùng record có `available_time <= T`.
- Không sửa raw data.
- Không fallback nguồn âm thầm.
- Không random split.
- Không hard-code secrets.
- Không notebook-only production logic.
- Mọi dataset phải có fingerprint.
- Mọi experiment phải ghi code commit và config.

## 9. Definition of Done MVP

MVP hoàn thành khi:

- chạy end-to-end bằng một command;
- có thể tái tạo cùng kết quả từ cùng raw snapshot và config;
- test leakage bắt buộc pass;
- báo cáo baseline và walk-forward được sinh tự động;
- mọi artifact có version;
- có kết luận rõ: tiếp tục, sửa giả thuyết hoặc dừng.

## 10. Điều kiện mở rộng

Chỉ mở rộng sang ETHUSDT khi:

- pipeline BTC ổn định;
- data quality đạt ngưỡng;
- label không còn thay đổi liên tục;
- ít nhất một baseline/pattern có giá trị ngoài mẫu;
- chi phí bảo trì được chấp nhận.

Chỉ thêm AI sau khi predictive core đã có kết quả định lượng ổn định.
