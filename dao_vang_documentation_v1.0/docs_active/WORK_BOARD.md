# ACTIVE WORK BOARD

## Current phase

Phase 2 MVP Research Release — in progress.

## Multi-coin volatile scan — kết quả (2026-08-03)

### Phát hiện chính

Quét top 20 coin volatile nhất (24h ticker, min $10M volume) + BTC:
- Thu thập 90 ngày klines + funding cho 21 coins
- Chạy labels v0.1 (8% drawdown/24h, MAE ≤4%)
- Chạy experiment walk-forward cho coins có ≥50 events

| Coin | Events | Prevalence | Model P | Baseline P | CI 95% | Folds | Leakage | Status |
|------|--------|-----------|---------|-----------|--------|-------|---------|--------|
| COTIUSDT | 475 | 20.5% | 0.3481 | 0.3162 | [0.264, 0.506] | 3 | passed | 🟢 Edge |
| EULUSDT | 2,606 | 10.0% | 0.1572 | 0.2297 | [0.006, 0.392] | 3 | passed | 🟡 No edge |
| BTCUSDT | 127 | 0.49% | — | — | — | 0 | passed | ⚪ Skip (1 event cluster) |

### Insight

1. **Altcoin có nhiều distribution events hơn BTC** — COTIUSDT 20.5%, EULUSDT 10% (vs BTC 0.49%)
2. **COTIUSDT = edge sạch đầu tiên** — P=0.35 > baseline 0.32, CI [0.26, 0.51], leakage passed, 3 folds
3. **Nhưng chỉ 8 ngày data** — edge cần validate thêm khi tích lũy data
4. **EULUSDT: nhiều events nhưng model kém baseline** — khi 8% drop xảy ra 10% thời gian, nó là "normal" không phải anomaly
5. **Leakage fix quan trọng** — pre-joining labels vào feature_results tạo `is_distribution_1` column → P=1.0000 fake edge. Fixed: runner joins labels itself.

### UI

Tab "🔍 Quét Multi-Coin" đã thêm vào app.py:
- Slider số coin (5-30), số ngày (30/60/90), min events (30/50/100)
- Hiển thị events per coin + experiment results table
- Nút "Chạy quét" thu thập + chạy pipeline E2E

## MVP Research Release — kết luận formal (BTC-only)

### Trạng thái: 🟡 REVISE (sửa giả thuyết)

**Ngày đánh giá:** 2026-08-03
**Artifact cuối:** `exp_20260803_012158_699aaf0d` (90 ngày BTCUSDT)

### Gate check (SUCCESS_METRICS + RELEASE_CRITERIA)

| # | Tiêu chí | Trạng thái | Ghi chú |
|---|----------|-----------|---------|
| 1 | Không leakage nghiêm trọng | ✅ PASSED | future_data_check passed |
| 2 | Model vượt baseline ngoài mẫu | ❌ FAIL | P=0.22 ≤ baseline 0.24 (B1_price_ret_0.05) |
| 3 | Uplift không chỉ ở 1 cửa sổ | ❌ FAIL | Chỉ 1 fold valid (2/3 skipped) |
| 4 | Sample size đủ | ❌ FAIL | 127 positive rows = 1 event (June 3) |
| 5 | Calibration + CI báo cáo | ✅ DONE | Bootstrap CI + regime breakdown |
| 6 | Cơ chế giải thích | ✅ DONE | Feature importance + regime analysis |
| 7 | Forward test | ❌ N/A | Không khả thi với 1 event |
| 8 | Kết luận continue/revise/stop | ✅ DONE | REVISE |

### Phát hiện chính

1. **Label spec v0.1 quá khắt khe:** 8% drawdown trong 24h + MAE ≤4% → chỉ 1 event trong 90 ngày (June 2-3 crash, BTC 71,568→65,359). Không đủ data cho statistical validation.

2. **Binance API giới hạn lịch sử:** `/futures/data/*` (OI, taker, ratios) chỉ trả ~500 record gần nhất (~2 ngày). Không thể backfill lịch sử. 4/6 loại dữ liệu MVP (OI, taker, global ratio, top ratio) chỉ có 3 ngày data.

3. **Funding normalizer bug (đã fix):** `available_time = max(event_time, collected_at)` → historical backfill set available_time = collection time, breaking ASOF join. Fixed: `available_time = event_time + 1s`.

4. **Regime breakdown:** Distribution events cluster trong bull/bear regimes (prevalence 4.6-5.5%), gần không có trong sideways (0.1%). Đây là insight hữu ích cho v0.2.

5. **Edge không stable:** Với 31 ngày, model P=0.28 > baseline 0.23 (có vẻ có edge). Với 90 ngày, model P=0.22 < baseline 0.24 (edge biến mất). Edge trước đó là overfitting.

### Quyết định: REVISE

Per CONSTITUTION §7: MVP chỉ thành công khi "có ít nhất một pattern/model vượt baseline" và "hiệu suất giữ được ngoài mẫu". Chưa đạt.

### Hướng revise (Phase 2 tiếp)

| Ưu tiên | Task | Lý do |
|---------|------|-------|
| 1 | **Label v0.2: giảm target drawdown** | 8% → 5% hoặc 6% → nhiều event hơn |
| 2 | **Label v0.2: kéo dài horizon** | 24h → 48h hoặc 72h → bắt event kéo dài |
| 3 | **Daily collection OI/taker/ratio** | Tích lũy dần khi Binance API không cho history |
| 4 | **Thêm features từ klines** | ATR, volume profile, candle patterns — klines có full history |
| 5 | **Forward test infra** | Scheduler thu thập daily + đánh giá stability |

### Không làm (per NON_GOALS)

- Không thêm AI/LLM trước khi predictive core có edge stable
- Không mở rộng multi-coin trước khi BTC edge được validate
- Không auto trading

## Sprint log

| Date | Phase | Artifact | Kết luận |
|------|-------|----------|----------|
| 2026-08-01 | MVP Alpha | exp_20260801_* | Pipeline E2E chạy, chưa có edge |
| 2026-08-02 | MVP Research (31d) | exp_20260802_125940 | P=0.28 > baseline 0.23 (overfit) |
| 2026-08-03 | MVP Research (90d) | exp_20260803_012158 | P=0.22 < baseline 0.24 → REVISE |
