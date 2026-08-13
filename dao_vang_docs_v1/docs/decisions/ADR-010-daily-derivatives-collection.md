---
document_id: ADR-010
status: accepted
decision_date: 2026-08-10
author: Integrator
related: DATA_SOURCE_SPECIFICATION.md, LABEL_SPECIFICATION_v0.2.md, LABEL_SPECIFICATION_v0.3.md
---

# ADR-010: Daily collection cho derivative metrics (OI, taker, ratios, funding)

## Status

Accepted — chạy bằng cron/Task Scheduler.

## Context

Experiment Label v0.2/v0.3 cho thấy các feature OI/taker/ratio bị **~98% null** trong dữ liệu hiện tại vì Binance chỉ trả ~500 bản ghi gần nhất cho các endpoint derivative. Các feature này có tiềm năng cải thiện model nếu được tích lũy đều đặn theo thời gian. Do đó cần một quy trình thu thập hàng ngày (daily cron) cho funding, open interest, taker ratio, global ratio, top trader ratio trên danh sách coin volatile.

## Decision

1. Triển khai hàm `collect_derivatives(symbols, settings, hours_back=24, run_id=None)` trong `src/dao_vang/data/daily_collection.py`.
2. Lặp qua từng symbol trong whitelist, thu thập 5 loại dữ liệu:
   - `/fapi/v1/fundingRate` — FundingCollector
   - `/futures/data/openInterestHist` — OpenInterestCollector
   - `/futures/data/takerlongshortRatio` — TakerRatioCollector
   - `/futures/data/globalLongShortAccountRatio` — GlobalRatioCollector
   - `/futures/data/topLongShortAccountRatio` — TopRatioCollector
3. Xuất CLI command: `dao-vang data collect-derivatives BTCUSDT,ETHUSDT,... --hours-back 24`.
4. Chạy 1 lần mỗi ngày qua cron/Task Scheduler, ghi raw JSONL vào `data/raw/<data_type>/date=YYYY-MM-DD/`.
5. Sau đó pipeline `process_raw_to_parquet` sẽ normalize thành Parquet và DB ingest.

## Alternatives considered

1. **Thu thập OI/taker cùng lúc klines realtime**: tăng độ phức tạp scanner, không cần thiết cho MVP.
2. **Dùng dữ liệu 1 request lúc train**: dữ liệu quá mỏng (~500 record), không giải quyết null features.
3. **Chỉ thu thập BTC/ETH**: whitelist volatile altcoin mới có đủ positive label; cần data cho các coin đó.

## Consequences

- Sau 30–90 ngày chạy daily, các feature `oi_zscore_7d`, `taker_buy_ratio_trend_1h`, `price_oi_divergence_1h` sẽ có đủ lookback, giảm null rate đáng kể.
- Có thể chạy lại label/feature pipeline khi đủ dữ liệu để đánh giá lại v0.2/v0.3.
- Tăng chi phí lưu trữ raw nhưng không tăng độ phức tạp logic.
- Cần giám sát cron và API rate-limit.

## Operational notes

- Whitelist hiện tại (15 coin volatile) có thể thay đổi; command nhận symbols động.
- `hours_back=24` phù hợp cho daily cron; lần đầu có thể dùng `hours_back=720` (30 ngày) để backfill nếu API cho phép.
- Mỗi collector tự xử lý pagination và lưu theo `run_id`.
