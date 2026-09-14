# Báo cáo backtest Execution Policy — 13/09/2026

## Kết luận

Chưa có policy hoặc AI challenger nào đủ điều kiện promotion. Hệ thống tiếp
tục ở chế độ `research/advisory`; model v1 không được phép phát lệnh cho
contract `distribution_short_v2`.

## Dữ liệu

- Nguồn: `data_live/live.duckdb`.
- Frozen model: `frozen_20260811_082824_96df7ec9`.
- Train cutoff: 10/08/2026 15:09:59 +07.
- Tín hiệu OOS: 13/08/2026–25/08/2026.
- Ngưỡng frozen: 0,60.
- 569 episode sau khi khử lặp theo rising edge/gap quan sát.
- Hai fold thời gian: 399 episode train/research, 170 episode holdout.
- Mục tiêu: giảm 20% từ giá vào trung bình trong 24 giờ.
- Chi phí: 5 bps phí + 5 bps slippage mỗi chiều; cộng funding thực tế.
- Nếu cùng nến chạm stop và target: tính stop trước.

Không có market cap point-in-time trong dataset. Báo cáo chỉ dùng trailing
quote volume để phân tầng thanh khoản và không coi đó là market cap.

## So sánh ba policy trên toàn bộ 569 episode

| Policy | Hit −20% | Stop | E2 fill | E3 fill | Net return/signal |
|---|---:|---:|---:|---:|---:|
| Compact | 8,08% | 49,21% | 72,23% | 50,26% | −1,801% |
| Balanced | 9,49% | 38,14% | 55,36% | 34,09% | −1,272% |
| Deep Squeeze | 9,67% | 38,14% | 58,35% | 36,91% | −0,401% |

Deep Squeeze ít xấu nhất và ổn định hơn giữa hai fold:

- Fold 1: −0,426%/signal.
- Fold 2: −0,342%/signal.

Tuy vậy expected return vẫn âm, nên không được promotion. Kết quả tốt hơn một
phần đến từ risk multiplier 0,5 và tỷ lệ vốn thực sự khớp thấp hơn; không được
diễn giải là tín hiệu chính xác hơn.

Rule router chọn Compact 22 lần, Balanced 547 lần và Deep Squeeze 0 lần. Sau
guardrail label-version, số signal đủ điều kiện thực thi là 0/569 vì toàn bộ
signal đến từ `distribution_short_v1`.

## AI challenger

Random Forest challenger học trên fold 1, dự đoán một trong bốn hành động:
`SKIP`, Compact, Balanced hoặc Deep Squeeze. Chỉ fold 2 được dùng để đánh giá.

| Selector | Holdout net return/signal | Max drawdown tuần tự |
|---|---:|---:|
| Rule router | −1,252% | 91,40% |
| AI challenger | −0,549% | 80,28% |
| Deep tĩnh, chọn từ train fold | −0,342% | 48,25% |
| Oracle biết trước tương lai | +1,915% | 0% |

AI tốt hơn rule router nhưng vẫn âm và kém Deep tĩnh. Promotion bị từ chối vì:

- chỉ có 2 fold, yêu cầu tối thiểu 3;
- holdout có 170 episode, yêu cầu tối thiểu 200;
- expected return của challenger âm;
- không thắng best static policy;
- drawdown xấu hơn best static policy.

Không có model runtime nào được ghi và cấu hình live không thay đổi sang
`shadow_model` hoặc `model`.

## Quyết định tiếp theo

1. Huấn luyện signal model mới trực tiếp trên label `distribution_short_v2`
   (−20%/24h, MAE +16%), không tái sử dụng calibration của v1.
2. Thu thập tối thiểu thêm một fold OOS và đạt ít nhất 200 episode holdout.
3. Bổ sung market cap point-in-time nếu muốn kết luận theo low/mid-cap.
4. Sau khi baseline signal v2 có expected return không âm, chạy lại ba policy
   và challenger có lớp SKIP.
5. Chỉ chuyển sang shadow khi toàn bộ promotion gate đạt; live vẫn advisory.

## Artifacts

- `artifacts/execution_policy_backtest_20260913.json`
- `artifacts/execution_policy_backtest_events_20260913.csv`
- `artifacts/execution_policy_ai_challenger_20260913.json`
