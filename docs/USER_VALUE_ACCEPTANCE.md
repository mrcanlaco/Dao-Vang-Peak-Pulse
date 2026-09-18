# Dùng thử Coin của tôi

Mở ứng dụng, đăng nhập và chọn **Theo Dõi** → **Coin của tôi**.

## Kịch bản khoảng 5 phút

1. Nhập BTC hoặc một coin Binance Futures đang quan tâm. Bấm **Thêm coin theo dõi**.
2. Đọc mốc giá và lý do lúc lưu. Phân biệt điểm dự báo, biến động 24/48 giờ và lãi/lỗ giả lập. Nếu thêm thủ công thì không có dự báo mô hình; không suy ra dự báo từ giá.
3. Mở **Thử bằng vốn giả lập**, chọn hướng, quy mô và chi phí. Mở rồi đóng giả lập để xem phí, funding và lãi/lỗ ròng. Đây không phải lệnh giao dịch thật.
4. Chọn **Hữu ích**, **Gây phiền** hoặc **Khó hiểu** cho từng mục. Tắt thông báo nếu không muốn theo dõi thay đổi nữa.
5. Bỏ theo dõi sau khi đóng giả lập. Vào **Toàn bộ lịch sử** để kiểm tra thông tin vẫn còn. Quay lại ngày hôm sau để xem tiến độ 24/48 giờ.

Không cần chờ 48 giờ để thử giao diện: cảnh báo cũ có mốc dữ liệu xác minh được sẽ được đối chiếu lịch sử. Mục chưa đủ thời gian vẫn phải hiển thị đang chờ. Không thêm dữ liệu giả vào hệ thống đang chạy để làm đẹp kết quả.

## Đánh giá với nhóm nhỏ

Nhóm đề xuất 3–5 người, bắt đầu bằng chủ ứng dụng nếu chưa chọn nhóm. Ghi lại mỗi người có tự thêm coin và hiểu cảnh báo đầu tiên hay không, thời gian hoàn thành và điểm vướng. Không tự gửi lời mời hay tin nhắn tới người khác.

Trên màn hình có số mục nhận phản hồi, số hữu ích/gây phiền và số thiết bị quay lại/hoạt động trong 7 ngày. Thiết bị được nhận diện bằng ID ngẫu nhiên trong trình duyệt, lưu dạng băm ở máy chủ; không gửi dịch vụ phân tích bên ngoài. Quay lại nghĩa là truy cập mục theo dõi vào ít nhất hai ngày UTC khác nhau trong cửa sổ 7 ngày; không phải số người đã xác minh.

Kết quả dùng thử thật chỉ được báo khi có người tham gia và phản hồi. Bộ kiểm thử tự động không thay thế kết quả đó.

## Giới hạn cần hiểu

- Phiên bản này kế thừa một danh sách dùng chung trong hệ thống có mật khẩu truy cập; chưa có tài khoản/danh sách riêng cho từng người.
- Thông báo nằm trong ứng dụng, có dấu chưa đọc khi quay lại. Không thêm gửi Telegram/email hoặc thông báo hệ điều hành.
- Biến động giá từ mốc thông báo trước từ 5% có giãn cách 2 giờ. Mất/phục hồi dữ liệu cũng có giãn cách theo loại 2 giờ; kết quả mỗi mốc chỉ báo một lần cho mỗi trạng thái. Theo dõi nền giới hạn 20 mục và 4 lần đối chiếu lịch sử mỗi lượt để bảo vệ dịch vụ.
- Kết quả 24/48 giờ dùng chuỗi nến 5 phút đã đóng, liên tục, không trùng xung đột. Mất nến hoặc nguồn giá gốc chưa xác minh thì không công bố số liệu. Mốc xuất phát là giá đóng nến trước thời điểm tín hiệu/lưu, được ghi ngày giờ rõ ràng.
- Nhật ký giả lập dùng quy mô cố định, không đòn bẩy; chi phí và trượt giá giả định mỗi chiều. Funding lấy từ settlement thực, theo quantity × mark price × funding rate, chỉ tính các settlement sau mở và trước đóng. Nếu nguồn thiếu/lỗi hoặc vượt giới hạn truy vấn thì giữ kết quả chưa xác minh và thử lại; không coi funding thiếu là 0.
- Chưa mô phỏng thanh lý, sổ lệnh, khả năng khớp hay cả danh mục/vốn dùng chung. Không diễn giải lãi/lỗ mô phỏng thành thành tích giao dịch thực.
