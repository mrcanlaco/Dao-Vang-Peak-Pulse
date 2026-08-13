# DAO VANG — Telegram Bot Setup Guide

Configure real-time Telegram alerts for the DAO VANG (PeakPulse AI) distribution radar.

---

## 1. Create a Bot via @BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`.
3. Enter a display name (e.g. `PeakPulse Radar Alerts`).
4. Enter a bot username (e.g. `peakpulse_radar_bot` — must end with `bot`).
5. BotFather will reply with your **Bot Token** formatted like `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`.
   → This is your `DAO_VANG_TELEGRAM__BOT_TOKEN`.

---

## 2. Obtain Your Chat ID

1. Open Telegram and search for **@userinfobot** or **@getmyid_bot**.
2. Send `/start`.
3. The bot will return **Your ID: 123456789**.
   → This is your `DAO_VANG_TELEGRAM__CHAT_ID` (for private direct messages).

### For Telegram Groups / Channels

1. Create a group, add your bot into the group.
2. Send any text message in the group.
3. Open browser: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for `"chat":{"id":-1001234567890,...}` — negative numbers represent group/supergroup chat IDs.

---

## 3. Configure DAO VANG

Create a `.env` file in the project root (already ignored by `.gitignore`):

```env
DAO_VANG_TELEGRAM__BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
DAO_VANG_TELEGRAM__CHAT_ID=123456789
DAO_VANG_TELEGRAM__LANGUAGE=en
```

Or set environment variables directly:

```powershell
# PowerShell
$env:DAO_VANG_TELEGRAM__BOT_TOKEN = "123456789:ABCdef..."
$env:DAO_VANG_TELEGRAM__CHAT_ID = "123456789"
$env:DAO_VANG_TELEGRAM__LANGUAGE = "en"
```

---

## 4. Test Bot Connection

```bash
dao-vang scanner test-telegram
```

If successful, you will receive a test notification from the bot in your selected language.

---

## 5. Alert Mechanism & Operating Modes

- **Reference Reporting:** Telegram alerts are designed for decision support and analysis. **No automated order placement is performed.**
- **Deep Linking:** Every alert includes a direct deep-link `[🔗 Open SYMBOL Analysis Dashboard]` which opens the web app directly focused on that coin.
- **Language Customization:** Set `language: en` in `configs/live.yaml` or `DAO_VANG_TELEGRAM__LANGUAGE=en` for English notifications.

---

## 6. Security

- **Never commit bot tokens to Git** (enforced via `.gitignore`).
- **Log Masking:** Logs only record the first 4 characters followed by `***` (`1234***`).
- **Revocation:** Send `/revoke` to @BotFather at any time to regenerate a new token if compromised.
