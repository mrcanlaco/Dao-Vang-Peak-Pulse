# Hướng dẫn tạo Telegram bot cho Đảo Vàng

## 1. Tạo bot qua @BotFather

1. Mở Telegram, tìm **@BotFather**.
2. Gửi `/newbot`.
3. Đặt tên bot (VD: `Đảo Vàng Alerts`).
4. Đặt username (VD: `dao_vang_alerts_bot` — phải kết thúc bằng `bot`).
5. BotFather trả về **bot token** dạng `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`.
   → Đây là `TELEGRAM_BOT_TOKEN`.

## 2. Lấy chat ID của bạn

1. Mở Telegram, tìm **@userinfobot** (hoặc **@getmyid_bot**).
2. Gõ `/start`.
3. Bot trả về **Your ID: 123456789**.
   → Đây là `TELEGRAM_CHAT_ID` (chat cá nhân).

### Nếu dùng group chat

1. Tạo group, thêm bot vào group.
2. Gửi 1 tin nhắn bất kỳ trong group.
3. Mở URL: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Tìm `"chat":{"id":-1001234567890,...}` — số âm là group chat ID.

## 3. Cấu hình Đảo Vàng

Tạo file `.env` ở thư mục gốc (đã trong `.gitignore`):

```env
DAO_VANG_TELEGRAM__BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
DAO_VANG_TELEGRAM__CHAT_ID=123456789
```

Hoặc set env var trực tiếp (PowerShell):

```powershell
$env:DAO_VANG_TELEGRAM__BOT_TOKEN = "123456789:ABCdef..."
$env:DAO_VANG_TELEGRAM__CHAT_ID = "123456789"
```

## 4. Test bot

```bash
dao-vang scanner test-telegram
```

Nếu thành công, bạn nhận được tin nhắn test từ bot.

## 5. Live reference reporting

The live service now uses `production_alerting` for Telegram reference reports.
Only signals that pass the quality gate, model threshold, cooldown, and daily
budget are sent. Telegram is for evaluation/reference only; this application
has no auto-trading or order execution.

Tin nhắn được Việt hóa để đọc nhanh và có dòng **Mở trang phân tích SYMBOL**.
Liên kết này mở thẳng dashboard tại đúng coin được báo cáo. Live đang dùng:
`https://trade.comaygiauco.com/#coin=SYMBOL`. Nếu chạy domain khác, đặt
`web.public_url` trong YAML hoặc `DAO_VANG_WEB__PUBLIC_URL` trong môi trường.

To verify delivery:

```bash
dao-vang scanner test-telegram --config configs/live.yaml
```

## 5b. Telegram trong shadow mode

Live scanner có thể gửi các tín hiệu `HIGH_CONFIDENCE` đã qua quality gate để
quan sát, nhưng tin nhắn sẽ ghi rõ `SHADOW / OBSERVATION`. Đây không phải là
production alert và không thay thế cổng canary.

Trong `run_scanner_live.bat`:

```bat
set DAO_VANG_SCANNER__OPERATING_MODE=shadow
set DAO_VANG_SCANNER__SHADOW_TELEGRAM_ENABLED=true
```

`research` vẫn không gửi Telegram. Canary/production vẫn fail-closed khi dữ
liệu không hợp lệ, model bundle sai, kill switch bật, hết cooldown hoặc vượt
ngân sách alert.

## 6. Bảo mật

- **Không commit token vào git** — `.env` đã trong `.gitignore`.
- **Không log token** — code chỉ log 4 ký tự đầu + `***`.
- **Revoke bất kỳ lúc nào** — gửi `/revoke` cho @BotFather để tạo token mới.
- Bot chỉ cần `sendMessage` permission — không cần admin group.
