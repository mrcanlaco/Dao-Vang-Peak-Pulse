# Mô hình production và mức độ bằng chứng

`configs/live.yaml` là cấu hình production không chứa bí mật và được quản lý
phiên bản trong Git. Đây là nguồn duy nhất chọn bundle mà scanner live sử dụng;
bí mật vận hành chỉ nằm trong `.env.docker`. `metadata.json` trong bundle là
nguồn sự thật cho cutoff, threshold, feature schema và checksum.

## Phiên bản đang phục vụ

| Trường | Giá trị |
|---|---|
| Model ID | frozen_20260906_105716_bc3c369b |
| Freeze time | 2026-09-06T10:57:16.293277+07:00 |
| Train cutoff | 2026-07-28T19:05:39.999000+07:00 |
| Frozen threshold | 0.4100000000000001 |
| Calibration | isotonic_v1 |
| Model SHA-256 | 27961bc6c9a24e52136d00f208258343e8d5b75980fe156dbfba699264f51a12 |
| Calibrator SHA-256 | 0e425413f24a3a96ece91d1e201f0be4dd3709526733d19a19d649871b3c72db |

CI chạy tests/qa/test_live_release_contract.py để bảo đảm config live trỏ
đúng bundle, model/calibrator tồn tại, checksum khớp và estimator có thể nạp.
Serving path cũng kiểm tra checksum và fail closed trước khi phát xác suất.

## Số liệu hiện có và giới hạn diễn giải

Metadata của bundle lưu các training_stats sau:

| Metric | Giá trị |
|---|---:|
| Precision | 0.3895582329 |
| Brier score | 0.1859139683 |
| ECE | 0.0261074685 |

Đây là số liệu đi kèm quá trình tạo bundle, không phải bằng chứng forward-test
độc lập và không chứng minh lợi nhuận giao dịch. Bundle hiện chưa kèm một báo
cáo out-of-sample sau cutoff có đủ model ID, checksum, cửa sổ dữ liệu, số mẫu,
số event và phân rã regime. Vì vậy:

- Không dùng các con số ROI, win rate, lead time hoặc event recall trong tài
  liệu nghiên cứu lịch sử để mô tả hiệu năng live hiện tại.
- Không tự động thăng hạng challenger. Mọi thay đổi champion phải qua review và
  đổi scanner.frozen_model_id bằng commit rõ ràng.
- Scanner chỉ phát cảnh báo human-in-the-loop; không được xem xác suất hoặc
  anomaly score là lệnh giao dịch.

## Điều kiện để công bố hiệu năng production

Một báo cáo đủ điều kiện phải:

1. Chỉ dùng dữ liệu có feature_time sau train cutoff và label đã materialize.
2. Gắn model ID, hai checksum, phiên bản label/feature và thời gian dữ liệu.
3. Công bố sample size, event count, precision, recall, Brier/ECE và khoảng tin
   cậy; báo rõ mọi nhóm regime không đủ mẫu.
4. So sánh với champion/baseline trên cùng các event và cùng cửa sổ thời gian.
5. Qua quality gate, review thủ công và một giai đoạn shadow trước khi đổi live
   config.

Các báo cáo không đáp ứng đủ năm điều kiện trên chỉ có giá trị nghiên cứu.
