# Guarded self-learning

Đảo Vàng hiện hỗ trợ self-learning theo batch có kiểm soát:

```text
prediction → materialized outcome → challenger → holdout gate → review
```

Dataset huấn luyện dùng mô hình hybrid: label lịch sử point-in-time làm nền,
outcome live đã xác thực được gộp thêm khi có, và dữ liệu trong cửa sổ gần đây
được tăng trọng số. Dữ liệu gần đây không được dùng thay thế holdout tương lai.

Challenger không tự thay thế `scanner.frozen_model_id`. Champion đang chạy
tiếp tục phục vụ cho đến khi operator review report và chủ động promote.

## Bật trong daemon

Thêm vào file YAML đang dùng:

```yaml
self_learning:
  enabled: true
  check_interval_cycles: 12
  min_training_outcomes: 200
  min_new_outcomes: 50
  min_positive_events: 20
  min_precision_improvement: 0.01
  max_recall_regression: 0.05
  max_brier_regression: 0.01
  recent_window_days: 14
  recent_sample_weight: 2.0
  historical_max_rows: 100000
```

Daemon sẽ kiểm tra theo chu kỳ. Giai đoạn bootstrap có thể train từ lịch sử
ngay cả khi live chưa có outcome hợp lệ. Khi chưa đủ label lịch sử/live hoặc
chưa có dữ liệu mới, nó chỉ ghi trạng thái `not_ready`/`skipped`; không retrain
và không làm gián đoạn serving.

## Chạy thủ công hoặc qua Task Scheduler

```powershell
.venv\Scripts\dao-vang.exe experiment self-learn `
  --db-path data_live/live.duckdb `
  --artifact-dir artifacts `
  --champion-model-id frozen_... 
```

Với live config, kết quả được lưu tại
`artifacts/self_learning/live_runs/` và con trỏ trạng thái tại
`artifacts/self_learning/live_state.json`. Lệnh có thể chạy lặp lại; cùng một
tập dữ liệu sẽ bị bỏ qua.

## Điều kiện gate

- Label lịch sử 0/1 đã materialize và live outcome hợp lệ; không dùng
  pending/excluded hoặc prediction invalid.
- Lịch sử bị giới hạn bởi `historical_max_rows` để tránh chiếm tài nguyên.
- Mẫu trong `recent_window_days` nhận trọng số `recent_sample_weight`.
- Dedupe theo symbol, signal time và horizon.
- Chia train/validation/holdout theo thứ tự thời gian; holdout nằm sau
  `champion.train_cutoff`.
- Precision challenger phải cải thiện tối thiểu theo config.
- Recall không được giảm quá mức cho phép.
- Brier score không được xấu hơn giới hạn cho phép.

Khi gate đạt, hệ thống tạo frozen challenger và ghi model cha, fingerprint dữ
liệu, threshold và metrics vào metadata/report. Việc promote vẫn thực hiện qua
quy trình canary/rollback hiện có.
