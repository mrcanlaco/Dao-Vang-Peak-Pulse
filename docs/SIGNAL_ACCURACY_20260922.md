# Cải thiện độ tin cậy của tín hiệu — 22/09/2026

Đã sửa các nguồn tạo tín hiệu thiếu căn cứ và làm sai dữ liệu kiểm định trong
mã nguồn cục bộ. Kết quả chứng minh bằng kiểm thử tái hiện lỗi và kiểm tra dữ
liệu đầu vào; chưa chứng minh mức tăng precision của tín hiệu trên thị trường.

## Các lỗi đã sửa

1. **Dữ liệu tương lai lọt vào đặc trưng BTC.** Khi biến động BTC bị thiếu,
   phép điền `avg(...) OVER ()` lấy cả những thời điểm tương lai và phụ thuộc
   số lượng altcoin trong tập dữ liệu. Bây giờ giữ giá trị thiếu; các return BTC
   chưa đủ lịch sử cũng không còn bị biến thành mức biến động 0. Bộ kiểm thử
   xác nhận thêm nến tương lai không làm thay đổi đặc trưng quá khứ.
2. **Return sai khung thời gian khi thiếu nến.** Các return giá 5 phút, 15 phút,
   1 giờ, 4 giờ và 24 giờ chỉ hợp lệ khi độ dài thời gian của độ trễ khớp
   chính xác. Nếu không, trả giá trị thiếu. Chặn chia cho giá bằng 0; giới hạn
   cửa sổ giá/khối lượng theo thời gian và kiểm tra thời gian của các độ trễ
   dùng cho động lượng. Dữ liệu đều đặn vẫn dùng cùng công thức.
3. **Dữ liệu thiếu được cộng điểm và tính là bằng chứng.** Trước sửa, một bộ
   đặc trưng rỗng với BTC trung tính nhận 23,165 điểm, trạng thái WATCH và vượt
   cổng hai nhóm bằng chứng: suy yếu giá và áp lực bán. Sau sửa, chỉ còn 7,5
   điểm bối cảnh BTC, trạng thái WAIT và không có nhóm bằng chứng độc lập.
   Đây là ca kiểm thử tổng hợp, không phải một giao dịch thực tế. Chỉ báo thiếu
   đầu vào hợp lệ đóng góp 0 điểm và có giải thích; trọng số không được phân
   phối lại để nâng điểm các chỉ báo còn lại.
4. **Giá trị không hợp lệ vượt cổng chất lượng.** NaN/vô hạn không thể tạo nhóm
   bằng chứng. Đầu vào bắt buộc không phải số hữu hạn bị chặn trước khi nạp mô
   hình. Điểm chất lượng không hữu hạn hoặc ngoài [0,1] bị từ chối thay vì được
   ép về điểm đạt. Kiểm thử xác nhận không sinh xác suất hoặc tín hiệu có thể
   cảnh báo trong trường hợp bị chặn.

## Kiểm tra dữ liệu cục bộ

Đọc `data_live/live.duckdb` ở chế độ chỉ đọc: 2.078.363 dòng, 222 symbol,
từ 11/07/2026 đến 26/08/2026. Đây là bản dữ liệu lịch sử cục bộ, không phải
trạng thái máy chủ production ngày 22/09.

| Khung return giá | Dòng có độ trễ không đúng thời gian |
|---|---:|
| 5 phút | 2 |
| 15 phút | 6 |
| 1 giờ | 24 |
| 4 giờ | 96 |
| 24 giờ | 454 |

Các số trên có thể chồng lặp giữa khung thời gian; không phải số cảnh báo sai.
Điều kiện đếm là có dòng quá khứ tại độ trễ tương ứng nhưng chênh lệch timestamp
khác khung return. Chưa sửa dữ liệu lịch sử đã lưu.

So sánh thêm 58.275 dòng của năm symbol đầu theo bảng chữ cái cùng BTCUSDT,
không chọn theo kết quả dự báo. Các thay đổi chủ yếu là giữ đúng trạng thái
thiếu bối cảnh BTC và thiếu lịch sử; 579 giá trị biến động BTC trước đây được
điền không hợp lệ trở thành giá trị thiếu. Báo cáo máy đọc, mã băm đầu vào và
mã băm mã nguồn so sánh nằm tại `reports/signal_accuracy_audit_20260922.json`.

Chỉ có 9 outcome đã materialize và 1 outcome bị loại trong cơ sở dữ liệu này;
các dự báo thuộc model tháng 8, không đại diện cho model được chọn trong cấu
hình live hiện tại. Không sử dụng tỷ lệ thắng hoặc precision tính từ mẫu này
để lựa chọn ngưỡng mới hay tuyên bố cải thiện hiệu năng live.

## Phạm vi áp dụng

Các bản sửa tác động tới bộ tạo đặc trưng dùng chung và cổng chấm điểm/bằng
chứng. Luồng V3 dùng bộ tạo đặc trưng chung nhưng không sử dụng toàn bộ cổng
inference của model cố định; thiếu lịch sử funding trong V3 vẫn tuân theo quy
tắc hiện có. Chưa đổi model, ngưỡng, cấu hình live, quy tắc xác nhận V3 hay các
quan sát đã lưu. Chưa triển khai lên máy chủ.

Cửa sổ giá không còn kéo nến cũ vượt khung giờ, nhưng vẫn có thể tính thống kê
từ số nến hiện có trong khung. Đây không phải chứng nhận đủ dữ liệu cho mọi
đặc trưng. Quy tắc tính OI/funding riêng và số liệu nghiên cứu cũ không được
diễn giải lại bởi bản sửa này. Đánh giá lại mô hình cần tái tạo đặc trưng với
bản sửa, lưu dấu phiên bản mã nguồn, và dùng tập đánh giá độc lập trước khi
công bố thay đổi precision hoặc thay mô hình đang phục vụ.

## Kiểm thử

Các ca hồi quy mới đã được chạy trên mã cũ và tái hiện lỗi trước khi sửa:
18 ca về đặc trưng/cổng chất lượng và 36 ca về chấm điểm dữ liệu thiếu.
Kiểm thử sau sửa bao gồm bộ tạo đặc trưng, chấm điểm, scanner/V3, API web,
chống rò rỉ, điều kiện phát hành và tích hợp outcome/walk-forward.

Kết quả: **376 kiểm thử đạt** trong 62,25 giây. Có 4 cảnh báo deprecated của
joblib/NumPy khi nạp bundle hiện có; không có kiểm thử thất bại.

Lệnh kiểm tra:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/features tests/unit/scoring tests/unit/scanner tests/unit/web tests/leakage tests/qa tests/integration/test_prediction_outcomes.py tests/integration/test_walk_forward.py -q --tb=short
```

Ruff và Pyright đã đạt trên các module thay đổi.
