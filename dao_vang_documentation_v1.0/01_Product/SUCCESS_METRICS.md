# SUCCESS METRICS

## Mục tiêu MVP

Chứng minh hoặc bác bỏ việc bộ dữ liệu tối thiểu tạo lợi thế thống kê trong phát hiện Distribution.

## Metrics chính

- Precision.
- Recall.
- False positive rate.
- Median lead time.
- Calibration error.
- Stability qua walk-forward windows.
- Sample size.
- Data completeness.

## Không dùng làm metric chính

- Accuracy tổng thể.
- Profit của vài giao dịch.
- Sharpe từ chiến thuật chưa tách execution.
- “AI score”.
- Số lượng feature hoặc model.

## Success gate sơ bộ

MVP đáng tiếp tục khi:

- không có leakage nghiêm trọng;
- có tối thiểu một baseline/model vượt baseline đơn giản ngoài mẫu;
- uplift không chỉ xuất hiện ở một cửa sổ duy nhất;
- sample size đủ để không kết luận từ vài sự kiện;
- calibration và confidence interval được báo cáo;
- kết quả có cơ chế giải thích hợp lý.

Ngưỡng số cụ thể phải được khóa trong Validation Protocol trước final test.
