# 📊 Khảo sát & Đánh giá Nguồn Dữ liệu Lịch sử cho Backtest

> **Ngày khảo sát:** 2026-09-07
> **Mục tiêu:** Đánh giá tính khả thi của việc tải dữ liệu lịch sử số lượng lớn (Backtest 1 năm+, 150+ coins, nến 5m) trực tiếp từ Binance Agent OS, Binance REST API, hoặc MCP.

---

## 1. Kết luận nhanh (Executive Summary)
- ❌ **Binance Agent OS:** KHÔNG KHẢ THI. Chỉ phù hợp để truy vấn thông tin live dạng point-in-time (ví dụ: Market Cap hiện tại). Không hỗ trợ tải bulk time-series.
- ❌ **MCP (Model Context Protocol):** KHÔNG KHẢ THI. MCP được thiết kế để cấp context cho AI, việc truyền tải hàng chục GB dữ liệu time-series qua bridge MCP sẽ tạo nút thắt cổ chai cực lớn.
- ❌ **Binance REST API (fapi):** KHÔNG KHẢ THI cho backtest sâu. Dù klines lấy được dài hạn, nhưng các endpoint quan trọng của hệ thống Đảo Vàng như **Open Interest Hist, Taker Buy/Sell Volume, Top Trader Ratios** bị Binance **giới hạn cứng tối đa 30 ngày trong quá khứ**.
- ✅ **GIẢI PHÁP TỐI ƯU CHỈ ĐỊNH:** Sử dụng **Binance Public Data Archive (data.binance.vision)**.

---

## 2. Phân tích chi tiết các nguồn

### 2.1. Binance Agent OS (`bapi/defi/.../search/ai`)
- **Bản chất:** Là endpoint nội bộ phục vụ Web3 Wallet / AI Agent của Binance để hỏi đáp thông tin (ví dụ file `binance_agent_os.py` đang dùng để lấy Market Cap).
- **Hạn chế:** 
  - Không có endpoint cho dữ liệu nến (OHLCV) hay phái sinh quá khứ dạng chuỗi thời gian.
  - Rate limit ngầm từ Cloudflare (Web Application Firewall) rất gắt, tải bulk sẽ bị ban IP ngay lập tức.

### 2.2. MCP (Model Context Protocol)
- **Bản chất:** Giao thức kết nối tool nội bộ cho các LLM.
- **Hạn chế:** Không sinh ra để làm Data Pipeline. Việc nhồi hàng triệu dòng Klines/OI qua JSON-RPC của MCP để nạp vào DuckDB là một anti-pattern về kiến trúc phần mềm, gây tràn RAM và timeout.

### 2.3. Binance USD-M Futures REST API (`fapi.binance.com`)
- **Bản chất:** API giao dịch và dữ liệu thời gian thực.
- **Hạn chế:** 
  - Điểm chết của API này nằm ở **Dữ liệu thống kê phái sinh**. Các endpoint như `/fapi/v1/openInterestHist`, `/fapi/v1/takerlongshortRatio`, `/fapi/v1/topLongShortAccountRatio` bị giới hạn [StartTime, EndTime] không được vượt quá 30 ngày tính từ hiện tại.
  - Giới hạn request (Weight limit): 1200-2400 weight/phút. Quét 1 năm cho 150+ symbol sẽ ngốn hàng chục nghìn request, dễ bị khóa API 24h.

---

## 3. Hướng triển khai tiêu chuẩn (System Standard Protocol)

Để tải dữ liệu backtest từ 1-5 năm trước cho hệ thống Đảo Vàng, **bắt buộc sử dụng Binance Vision Archive**.

**Quy trình triển khai (Dành cho lần cập nhật sau):**
1. **Nguồn:** `https://data.binance.vision/`
2. **Cấu trúc URL tải Klines:** 
   `https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/5m/{symbol}-5m-{YYYY}-{MM}.zip`
3. **Cấu trúc URL tải Metrics (Bao gồm OI, Taker Buy/Sell, Ratios):**
   `https://data.binance.vision/data/futures/um/monthly/metrics/{symbol}/{symbol}-metrics-{YYYY}-{MM}.zip`
4. **Cơ chế Pipeline:**
   - Viết một script độc lập (`scripts/download_vision_archive.py`).
   - Tải các file ZIP hàng tháng, giải nén ra CSV.
   - Dùng DuckDB đọc trực tiếp CSV (`read_csv_auto`) và chuyển đổi thẳng sang định dạng `.parquet` lưu vào `data/raw/` để tiết kiệm dung lượng.
   - Bỏ qua Rate Limit, chỉ phụ thuộc vào băng thông mạng.

> **Lưu ý cho Dev:** Mọi nỗ lực dùng API hay MCP để bypass quy trình này cho backtest sâu đều sẽ lãng phí thời gian và vi phạm giới hạn 30 ngày của Binance. Cứ bám sát Binance Vision.