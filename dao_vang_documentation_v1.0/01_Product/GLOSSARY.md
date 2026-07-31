---
document_id: DAO_VANG_GLOSSARY
version: 1.0.0
status: approved
---

# TỪ ĐIỂN ĐẢO VÀNG

## Available Time

Thời điểm sớm nhất mà Đảo Vàng được phép sử dụng record trong mô phỏng point-in-time.

Điều kiện bắt buộc:

```text
record.available_time <= feature_time
```

## Baseline

Phương pháp đơn giản dùng làm mốc so sánh. Mô hình phức tạp không vượt baseline thì không được triển khai.

## Calibration

Mức độ phù hợp giữa xác suất dự báo và tần suất xảy ra thực tế. Nhóm tín hiệu được dự báo 70% phải xảy ra xấp xỉ 70% trong đủ mẫu.

## Canonical Timeline

Chuỗi timestamp 5 phút chuẩn dùng để align mọi nguồn dữ liệu.

## Collected At

Thời điểm collector ghi nhận response vào hệ thống.

## Confidence Interval

Khoảng bất định thống kê quanh metric hoặc probability estimate.

## Data Leakage

Bất kỳ cơ chế nào làm feature, model selection hoặc evaluation sử dụng thông tin không hợp pháp tại thời điểm dự báo.

## Dataset Fingerprint

Hash của manifest, schema, source files và config nhằm nhận diện chính xác dataset.

## Distribution

Trạng thái chuyển tiếp có dấu hiệu tài sản mất động lượng tăng và có xác suất cao xuất hiện nhịp giảm đạt điều kiện Label Specification.

Distribution không phải nhận định bằng mắt; nó chỉ có ý nghĩa trong hệ thống khi gắn với một label version.

## Event Time

Thời điểm sự kiện xảy ra tại nguồn, không nhất thiết là thời điểm hệ thống biết sự kiện.

## Evidence Quality

Đánh giá chất lượng bằng chứng dựa trên data quality, completeness, sample size, regime fit và stability. Không đồng nghĩa probability.

## False Negative

Sự kiện Distribution thực sự xảy ra nhưng hệ thống không phát tín hiệu.

## False Positive

Hệ thống phát tín hiệu Distribution nhưng sự kiện không đạt định nghĩa label.

## Feature Time

Timestamp mà feature vector đại diện. Với MVP, feature time là close time đã chuẩn hóa của nến 5 phút.

## Forward Test

Đánh giá trên dữ liệu phát sinh sau khi phương pháp đã bị đóng băng.

## Horizon

Khoảng thời gian tương lai dùng để xác định outcome của tín hiệu.

## Label

Kết quả mục tiêu được tạo bằng thuật toán định lượng từ dữ liệu tương lai, chỉ dùng cho training/evaluation, không được dùng làm feature.

## Label Version

Phiên bản bất biến của định nghĩa label. Thay đổi ngưỡng, horizon, signal price hoặc exclusion rule phải tăng version.

## Lead Time

Khoảng thời gian từ signal time đến khi target event xảy ra.

## Max Adverse Excursion (MAE)

Mức tăng bất lợi lớn nhất so với signal price trước khi target giảm được đạt.

Với bài toán Short:

```text
MAE = max(future_high / signal_price - 1)
```

trong giai đoạn trước target.

## Max Favorable Excursion (MFE)

Mức giảm thuận lợi lớn nhất so với signal price trong horizon.

## Market Regime

Trạng thái thị trường dùng để phân nhóm đánh giá, ví dụ trend, sideway, volatility cao/thấp. Regime không được tính bằng dữ liệu tương lai.

## Model Outcome

Kết quả mô hình dự báo đúng hay sai theo label. Không đồng nghĩa Trading Outcome.

## Pattern

Tổ hợp điều kiện feature có mô tả hành vi, điều kiện xác nhận, vô hiệu, regime và kết quả kiểm chứng.

## Point-in-Time Correctness

Tính đúng đắn khi mọi dữ liệu dùng tại thời điểm T thực sự có thể biết tại hoặc trước T.

## Precision

Trong số tín hiệu dương đã phát, tỷ lệ đạt label dương.

## Recall

Trong số label dương thực tế, tỷ lệ được hệ thống phát hiện.

## Signal

Một prediction record được tạo tại signal time, có model/pattern version, probability hoặc score và evidence metadata.

## Signal Price

Giá tham chiếu tại thời điểm tín hiệu. MVP v0.1 dùng close của nến futures 5 phút đã đóng.

## Stability

Mức độ duy trì hiệu suất qua các cửa sổ thời gian và regime.

## Target Drawdown

Mức giảm tối thiểu từ signal price cần đạt trong horizon để label dương.

## Trading Outcome

Kết quả lời/lỗ của giao dịch do con người thực hiện. Phải tách biệt Model Outcome.

## Walk-Forward Validation

Quy trình train/validate/test theo thời gian, sau mỗi vòng cửa sổ được tiến về phía trước. Không shuffle.

## Watermark

Thời điểm dữ liệu mới nhất đã được collector xác nhận hoàn tất và đủ điều kiện sử dụng.
