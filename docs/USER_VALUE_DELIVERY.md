# Hoàn thiện trải nghiệm theo dõi Đào Vàng

## Phạm vi đã thống nhất

1. Theo dõi coin cá nhân, thông báo thay đổi đáng kể và mở đúng phần giải thích.
2. Giải thích cảnh báo: lý do, thời điểm dữ liệu, điều kiện hết hiệu lực, mức kiểm chứng.
3. Lịch sử giữ nguyên tín hiệu gốc; kết quả sau 24/48 giờ gồm đúng, sai, hết hạn và thiếu dữ liệu.
4. Nhật ký vốn giả lập, tính phí và funding, phân biệt với giao dịch thật.
5. Kiểm thử luồng người dùng mới, chống thông báo trùng, minh bạch dữ liệu cũ; chuẩn bị đo hữu ích/phiền/quay lại cho thử nghiệm nhóm nhỏ.
6. Người dùng đã yêu cầu cập nhật lên GCP. Sau khi hoàn tất và kiểm thử, triển khai bản chứa các thay đổi này lên môi trường GCP hiện có, xác nhận web/scanner và domain sau rollout.

## Tiến độ

- Đã sửa bước nền: giá thiếu không được thay bằng giá tín hiệu; giá lưu cache giữ thời điểm gốc; không tính lãi/lỗ hiện tại từ giá cũ.
- Giữ mục tiêu, điểm và giá gốc của mục theo dõi, không diễn giải lại theo mô hình hiện tại.
- Phân biệt không đạt mục tiêu với hết hạn chưa xác minh; hiển thị giải thích trên danh sách theo dõi.
- Đã thêm lưu trữ mềm khi bỏ theo dõi, nhật ký cập nhật và tab toàn bộ lịch sử. Mục mới lưu ID dự báo để lấy đúng kết quả; API kiểm tra ID thuộc đúng coin. Bản ghi cũ chưa có ID vẫn dùng đối chiếu cảnh báo lịch sử.
- Đã thêm worker trong dịch vụ web theo dõi khi trang đóng, kết quả giá 24/48 giờ, thông báo có giãn cách và trạng thái đã đọc/tắt.
- Đã thêm nhật ký giả lập lấy giá mới tại thời điểm thao tác, khóa giả định chi phí khi mở; đối chiếu funding settlement khi đóng. Funding thiếu giữ net P&L rỗng và có cơ chế thử lại.
- Đã thêm phản hồi hữu ích/gây phiền/khó hiểu và đếm thiết bị hoạt động/quay lại trong 7 ngày bằng ID băm lưu cục bộ.
- Bộ backend đầy đủ trước các kiểm thử HTTP bổ sung: 717 đạt, 3 bỏ qua. Luồng trình duyệt desktop/mobile và hồi quy: 9 đạt. Build, giới hạn bundle, Ruff và kiểm tra kiểu các phần thay đổi đạt; đã xem ảnh giao diện điện thoại.
- Đang thực hiện: kiểm tra CI trên bản phát hành, triển khai GCP và kiểm chứng sau rollout. Hướng dẫn dùng thử thật tại `docs/USER_VALUE_ACCEPTANCE.md`; chưa có kết quả người tham gia thật.

## Điều kiện hoàn tất

Cần bằng chứng kiểm thử API, dữ liệu và giao diện cho cả bốn luồng trên. Build thành công hoặc các kiểm thử nền riêng lẻ không chứng minh toàn bộ trải nghiệm đã hoàn tất. Thử nghiệm người dùng thật cần người tham gia; không tự gửi lời mời.

## GCP

- Đã kiểm tra kết nối ngày 18/09/2026: host truy cập được; scanner và web healthy; API health trả ok; checkout server sạch.
- Server tại `ff51d4f`, local HEAD lúc kiểm tra là `68a965b`: cần đối chiếu và tích hợp thay đổi mới trên remote trước khi chốt bản phát hành, không đưa server lùi về HEAD cũ.
- Quy trình hiện có yêu cầu bản commit qua CI; giữ image/SHA cũ để phục hồi và kiểm tra readiness, scanner, API có xác thực và domain sau triển khai.
