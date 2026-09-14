# V3: đối chiếu lại với dữ liệu thị trường thật

## Kết luận

Trên đúng tập Entry1 cũ đã khóa, bộ chấm v3 **không làm thay đổi kết quả TP/stop/
timeout** ở 36 lệnh có thể đối chiếu. Challenger vẫn đạt TP 20/36; Funding Scout
vẫn đạt 8/10. Điều này xác nhận kết quả đường giá trong mẫu đã mở vẫn tồn tại sau
khi đổi cách tính giá trung bình, stop/intrabar và chi phí. Nó không chứng minh
khả năng sinh lời tương lai hoặc đủ điều kiện chạy thật.

| Nhánh | Lệnh ghép cặp | TP trước | TP theo v3 | Lãi/lỗ giá sau phí giả định, trước funding: cũ → v3 |
|---|---:|---:|---:|---:|
| Challenger + Compact | 36 | 20/36 = 55,56% | 20/36 = 55,56% | +0,6394% → +0,6401% |
| Funding Scout + Compact | 10 | 8/10 = 80% | 8/10 = 80% | +6,8580% → +6,8650% |

Lãi/lỗ là trung bình mỗi lệnh trên **notional kế hoạch**, không phải lợi nhuận
tài khoản/ROE có đòn bẩy. Funding Scout là tập con của Challenger, không phải
hai mẫu độc lập. Không cộng số lệnh của hai nhánh. Mẫu Scout chỉ có 10 lệnh.

Các tỷ lệ TP trên là diagnostic của đường giá; nhãn chính thức yêu cầu đủ
funding vẫn bị loại (`label=null`). Không gọi đây là tỷ lệ chính xác hoàn chỉnh
của model v3 và không so lợi nhuận trước funding với số net EV cũ sau funding.

## Phạm vi và độ phủ

- Khóa nguyên 40 Entry1 trong đợt tháng 8 đã nghiên cứu; kiểm tra SHA-256 model,
  file khóa Entry1 và khớp chính xác symbol/thời gian. Không tối ưu lại ngưỡng.
- 40/40 giá Entry1 khớp đúng nến nguồn; 21.899 lượt nến tương lai gắn với đường lệnh.
- 39/40 đường giá được chấm tới kết thúc: 22 target, 15 stop, 2 timeout; 1 thiếu
  đường giá (`SPORTFUNUSDT`).
- Báo cáo cũ có 36 lệnh đủ điều kiện. Ba lệnh `BLUAIUSDT`, `AIOUSDT`, `BEATUSDT`
  có kết thúc trước khi dữ liệu bị thiếu được v3 chấm thêm, nhưng **không thêm ba
  lệnh này vào mẫu 36 lệnh ghép cặp**. Đây là đổi quy tắc độ phủ, không phải cải thiện
  tín hiệu mới.
- 5.703 candidate của nghiên cứu cũ không được chạy lại timing trong đợt này.
  Adapter này chỉ cô lập thay đổi execution trên cùng Entry1; không tính recall,
  hiệu chỉnh xác suất hoặc tái xác nhận độ phủ universe.

## Vấn đề dữ liệu đã phát hiện và cách xử lý

### 1. Nến có nhiều phiên bản và kết quả đọc không ổn định

View `kline` cũ chọn bản ghi bằng `available_time DESC` nhưng không phân xử khi
trùng thời điểm. Hai lần đọc cùng kho đã trả về OHLC khác nhau cho hai nến trong
cửa sổ nghiên cứu. Trong lát dữ liệu liên quan, có 21.547 bản ghi thô và 21.372
nến sau chọn phiên bản, tức 175 bản ghi cũ/trùng.

Adapter v1.2 đọc parquet chuẩn hóa, chọn `available_time DESC` rồi
`collected_at DESC`. Nếu cùng cả hai thời điểm mà nội dung khác nhau, dừng và báo
xung đột, không chọn tùy ý. Bản trùng hoàn toàn được gộp. Quy tắc chỉ áp dụng
trong adapter nghiên cứu, **không sửa view hoặc dữ liệu live**.

Hai lần chạy lại v1.2 trả cùng checksum nguồn và cùng run ID. Những artifact
v1/v1.1 trước đó chỉ lưu diễn biến điều tra; không gộp chúng thành bằng chứng mới.

Đây là chọn phiên bản mới nhất cho đánh giá hồi cứu, không khẳng định phiên bản
thu thập muộn đã có sẵn khi Entry1 phát sinh.

### 2. Đồng hồ nến và funding

Nến nguồn đóng tại `xx:04:59.999`; adapter đổi chính xác **+1 ms** thành ranh giới
`xx:05:00`, không dùng lại nến tín hiệu. Giá Entry1 không đổi.

Có 498 lượt bản ghi funding gắn với các đường lệnh (487 bản ghi trong lát nguồn;
các đường cùng coin có thể dùng chung settlement). 205 lượt nằm lệch ranh giới
5 phút, có độ lệch tới 11 ms trong mẫu. Lõi v3.1 chỉ chấp nhận settlement đúng
ranh giới nến; adapter giữ các bản ghi lệch giờ trong audit và không tự làm tròn
sang trước/sau một lần fill. Phần funding đã mô phỏng vì vậy chỉ là quan sát
chưa đầy đủ, không được xuất thành net EV chính thức.

Kho có rate và mark price, nhưng chưa tìm thấy manifest xác nhận đầy đủ các lần
thu thập funding cho các đường này; cột interval không cung cấp lịch settlement
để chứng minh không thiếu bản ghi. Manifest tải được tìm thấy là lỗi 404 cho
dữ liệu khác, không đáp ứng xác nhận độ phủ.

Do đó hiện **0 lệnh có lợi nhuận sau funding được chứng nhận đầy đủ**.
`verified_net_ev=null`, `promotion_eligible=false`; tuyệt đối không đổi thành 0.

### 3. Point-in-time chưa được chứng nhận

Feature export không có bằng chứng đầy đủ về thời điểm sẵn có thực tế; nến cũng
có cả available time và thời điểm thu thập hồi cứu. Adapter lưu provenance và
đánh dấu `pit_verified=false`. Không bịa `features_available_at=feature_time`
để vượt kiểm tra của replay toàn universe.

## Triển khai và tái tạo

- Adapter: `src/dao_vang/experiments/distribution_v3_market.py`.
- CLI: `dao-vang experiment audit-v3-market`.
- SQLite ledger và JSON theo hash: `artifacts/distribution_v3_market_audit/`.
- JSON lưu cả đường nến/funding đầu vào để replay không phụ thuộc vào lần đọc
  nguồn mới; các phiên bản dữ liệu khác nhau tạo run khác nhau.
- Test mới kiểm tra khớp khóa, nguồn chỉ đọc, trùng Entry1, nến invalid, funding
  lệch giờ, tách market/interval, chọn revision, xung đột revision và idempotence.

```powershell
.venv\Scripts\dao-vang.exe experiment audit-v3-market
.venv\Scripts\python.exe -m pytest tests/unit/execution tests/unit/labels tests/unit/experiments -q
```

Run v1.2 dùng cho bảng kết quả này:
`4bf8d9ac07779ee4fba2257c015ccf30628b0c4360d11e5f399508ad53a4a981`.

SHA-256 lát nguồn:
`50cdc99518404c4b44267976ac0af9cab3261f41c66d8d2808d7ecab29c44f6f`.

## Bước tiếp theo

1. Mở rộng quy ước settlement funding cho timestamp thực, đặc biệt khi gần fill/
   exit; giữ nguyên timestamp gốc và biểu diễn bất định trong nến, không âm thầm
   làm tròn. Thay đổi evaluator phải tăng version và có golden tests.
2. Xác minh/bổ sung lịch settlement cùng manifest thu thập đầy đủ; sau đó mới tính
   lại net EV có funding trên cùng keys.
3. Hoàn thiện adapter toàn candidate universe, dữ liệu as-of và warm-up timing;
   materialize nhãn v3 để train/calibrate. Chưa thay model hoặc scanner production.
