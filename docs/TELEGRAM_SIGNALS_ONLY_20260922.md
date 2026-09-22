# Telegram chỉ báo tín hiệu phân phối — 22/09/2026

Theo yêu cầu người dùng, coin thuộc WATCH/ARMED/WAIT vẫn được theo dõi trong
ứng dụng nhưng không gửi Telegram. Cấu hình live chỉ chọn HIGH_CONFIDENCE,
bỏ mục tiêu tối thiểu số thông báo mỗi ngày; hạn mức tối đa và cooldown giữ nguyên.

Cổng gửi của scanner, kể cả shadow, từ chối WATCH ngay cả khi cấu hình cũ còn
cho phép. Episode dùng ngưỡng model, không hạ ngưỡng để lấy thêm coin WATCH.
Bộ xếp hạng và thông báo đơn/tổng hợp đều lọc trạng thái trước khi gửi;
điểm số hoặc xác suất cao không tự nâng WATCH thành tín hiệu phân phối.
Bản tổng hợp không còn mục “canh đỉnh quá mua”; nếu không có tín hiệu hợp lệ
thì không gửi thông báo. Luồng hai tầng chỉ gửi FIRED.

V3 tiếp tục chỉ gửi khi đã qua điều kiện Timing và Champion, gồm xác nhận
đảo chiều và funding. Coin mới phát hiện hoặc Scout chưa đạt Champion không
gửi Telegram. Các cập nhật kết quả của tín hiệu đã xác nhận vẫn giữ nguyên.

Kiểm thử dùng bộ gửi giả lập, không gửi tin thử tới Telegram thật. Bao phủ
WATCH có điểm/xác suất cao, cấu hình cũ còn WATCH, quota chưa đủ, bản tổng hợp
rỗng/hỗn hợp trong cả tiếng Việt và tiếng Anh, ARMED, cùng V3 chưa xác nhận.
