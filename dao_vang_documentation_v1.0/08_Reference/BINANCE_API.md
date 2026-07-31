# BINANCE API REFERENCE NOTES

## MVP endpoints

- USD-M Futures klines.
- Funding rate history.
- Open interest statistics.
- Taker buy/sell ratio.
- Global long/short account ratio.
- Top trader long/short account ratio.

## Cảnh báo

- Một số statistics endpoints chỉ giữ lịch sử ngắn.
- Timestamps có thể đại diện period start.
- Numeric values thường là strings.
- Account ratio khác position ratio.
- API contract có thể đổi.

Official docs là nguồn xác minh; code phải có contract tests.
