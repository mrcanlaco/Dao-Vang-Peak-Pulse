---
adr_id: 0001
title: Telegram alerts + 24/7 scanner (post-MVP expansion)
status: proposed
date: 2026-08-03
deciders: [Boss, Integrator]
---

# ADR 0001 — Telegram alerts + 24/7 scanner

## Bối cảnh

MVP_SCOPE.md mục 7 "Ngoài phạm vi" liệt kê rõ:

- `real-time signals`
- `Telegram/Discord alerts`
- `auto trading`

AGENTS.md mục 4 cấm thêm tính năng ngoài MVP scope. Tuy nhiên, MVP
pipeline (collect → normalize → labels → features → train → freeze) đã
ổn định và có frozen model. Boss yêu cầu mở rộng post-MVP để:

1. Cắm daemon 24/7 quét danh sách coin tiềm năng (auto từ top gainers).
2. Phát hiện Distribution bằng frozen model đã đóng băng.
3. Bắn alert qua Telegram khi risk level CAO hoặc TRUNG BÌNH.
4. User nhận Telegram → mở web app check kỹ → tự quyết định vào lệnh.

**Không auto trade** — chỉ alert + hỗ trợ ra quyết định.

## Quyết định

Mở rộng post-MVP với scope giới hạn sau:

### Thêm

- `src/dao_vang/alerts/` — Telegram client + alert store (DuckDB).
- `src/dao_vang/scanner/` — daemon 24/7 dùng frozen model, không retrain.
- `alert_history` table trong DuckDB — lưu mọi tín hiệu đã phát.
- CLI `dao-vang scanner start|status|test-telegram`.
- Web tab "🚨 Alert Inbox" — xem + deep-dive + dismiss/confirm alert.
- `scripts/run_scanner.ps1` — launcher Windows.
- Config `telegram` + `scanner` trong `configs/default.yaml`.

### Không thêm (vẫn nằm ngoài scope)

- Auto trade / order execution.
- TP/SL tự động.
- Real-time streaming (vẫn batch 5 phút/lần, polling).
- Dashboard production phức tạp (web app vẫn Streamlit local).
- LLM / agent runtime / MCP.

## Ràng buộc

1. **Frozen model only** — daemon chỉ dùng model đã `freeze_model`, không
   retrain trong loop. Tránh drift + đảm bảo reproducibility.
2. **Point-in-time correct** — feature tại T chỉ dùng record có
   `available_time <= T`. Vi phạm = fail closed.
3. **Cooldown + dedup** — sau khi alert 1 coin, chờ `cooldown_minutes`
   (mặc định 60) mới alert lại. Tránh spam.
4. **No silent fallback** — nếu Telegram fail, log + retry theo tenacity,
   không bỏ qua âm thầm.
5. **Secrets từ env** — `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` từ env
   var hoặc `.env`, không hard-code.
6. **Watchlist auto + manual** — top gainers 24h (auto) + watchlist.json
   (manual), de-dup. Số coin quét giới hạn `max_coins` (mặc định 20) để
   tránh rate limit.
7. **Rate limit Binance** — polling 5 phút/lần, max_concurrency=2 (đã có
   trong config). Nếu hit rate limit → backoff, không spam.
8. **Auditability** — mọi alert ghi vào `alert_history` với model_id,
   feature_time, probability, risk_level, threshold. Sau 24h tính
   hit/miss từ label materialized.

## Hậu quả

- Tăng 1 dependency: `httpx` (đã có cho collector, dùng lại cho Telegram).
- Tăng 2 module mới: `alerts/`, `scanner/`.
- Tăng 1 table DuckDB: `alert_history`.
- Web app thêm 1 tab.
- Không phá vỡ MVP pipeline hiện có — scanner dùng lại `score_frozen`,
  `build_features`, collectors đã có.

## Liên quan

- `docs/product/MVP_SCOPE.md` mục 7 — cần ghi chú "mở rộng bởi ADR 0001".
- `docs/engineering/ARCHITECTURE.md` mục 12 — "MCP, dashboard, agent hoặc
  cloud chỉ được thêm khi core pipeline ổn định và ADR được phê duyệt" —
  ADR này thoả điều kiện.
- `AGENTS.md` mục 6 — thay đổi production/release cần ADR — ADR này.
