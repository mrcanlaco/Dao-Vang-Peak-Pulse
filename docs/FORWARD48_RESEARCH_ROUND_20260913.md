# Vòng nghiên cứu forward 48h — 2026-09-13

## Kết luận

Chưa có cấu hình nào đủ điều kiện triển khai live. Kết quả tháng 8 bác bỏ việc
promote model mới, xác nhận timing trưởng thành là một cải tiến có hướng nhưng
chưa hòa vốn, và cho thấy scale-in sâu không tự động cải thiện lợi nhuận.

Challenger tiếp theo được đóng băng cho dữ liệu tương lai là:

- pump 24h đã đạt ít nhất 30%;
- tuổi episode ít nhất 4 giờ và có 2 xác nhận liên tiếp;
- model threshold 0.39;
- Entry 1 / 2 / 3 tại 0% / +3% / +6%, phân bổ 20% / 30% / 50% trong 6 giờ;
- TP -20% và hard stop +16% từ giá vào trung bình động.

Việc ghép timing với compact được quyết định sau khi đã mở kết quả tháng 8.
Do đó tháng 8 chỉ chứng minh khả năng tương thích, không phải sealed-forward
evidence. Cấu hình chỉ được chấm promotion trên dữ liệu mới sau thời điểm khóa.

## Kết quả các nhánh

| Nhánh | Mẫu forward | Precision / hit | Recall | EV | Quyết định |
|---|---:|---:|---:|---:|---|
| Model augmented 48h | 187 signals | 27.81% | 4.75% | -6.19% bảo thủ | Loại khỏi promotion |
| Timing locked | 36 evaluable | 38.89% | 7.33% episode | -2.20% bảo thủ | Giữ nghiên cứu |
| Timing baseline | 61 evaluable | 32.79% | 10.47% episode | -4.40% bảo thủ | Kém champion |
| Timing + single entry | 36 | 38.89% target | — | +1.32% actual path | Reference |
| Timing + compact 0/+3/+6 | 36 | 55.56% target | — | +0.46% actual path | Future challenger |
| Timing + optimized 0/+10/+18 | 36 | 47.22% target | — | -1.08% actual path | Không giữ |

Model augmented có khả năng xếp hạng tốt hơn ngẫu nhiên (ROC-AUC 0.6244, AP
0.2962 so với prevalence 0.2173), nhưng ngưỡng quyết định tạo 0/4 tuần EV
dương. Không nên chữa kết quả này bằng cách chọn lại threshold trên tháng 8.

Timing champion cải thiện 6.10 điểm phần trăm precision và 2.20 điểm phần
trăm EV so với first-crossing, nhưng cận dưới Wilson chỉ 24.78%, thấp hơn điểm
hòa vốn 45%. Hai tuần cuối dương không bù được tuần lớn nhất âm.

Trong compatibility test, compact nâng target-hit từ 38.89% lên 55.56% nhưng
EV actual-path giảm từ +1.32% xuống +0.46%. Template 0/+10/+18 giảm MDD tuần tự
từ 81.19% xuống 52.96%, song EV chuyển âm. Vì vậy scale-in là công cụ đổi phân
bố rủi ro và hit rate, không phải lợi thế độc lập.

## Audit dữ liệu

Lần chạy đầu dùng `quant_master` chỉ exact-match 1.98%–2.19% ứng viên tháng 8.
Các kết quả dựa trên denominator lệch này đã bị hủy. Kết quả cuối dùng
`data_live/live.duckdb::kline`, đạt 100% exact entry coverage; bundle/model và
policy lock không đổi, không retune theo nhãn tháng 8.

Timing có 5,703 candidate rows, trong đó 5,074 (88.97%) đủ đường giá 48h và 629
incomplete. Model augmented có 5,038 rows đã resolve trong universe pump >=15%,
176 symbols.

## Protocol cho vòng kế tiếp

Chỉ dùng challenger đã khóa trong
`configs/distribution_v2_3_research_48h_timing_compact.yaml`. Không thay model,
threshold, timing, offsets hoặc weights cho tới khi có ít nhất 100 episode độc
lập đã resolve và phân bố trong ít nhất 3 cửa sổ thời gian.

Promotion yêu cầu đồng thời precision >=50%, episode recall >=10%, cận dưới
Wilson 95% vượt 45%, actual-path EV dương và ít nhất 3 cửa sổ EV dương. Mọi thay
đổi live vẫn cần một quyết định riêng.

## Artifacts chính

- `docs/forward48_aug_model_report.md`
- `docs/forward48_timing_20260913.md`
- `artifacts/forward48_scalein_report_20260913.md`
- `artifacts/forward48_scalein_timing_compatibility_report_20260913.md`
- `artifacts/forward48_aug_model_report.json`
- `artifacts/forward48_timing_20260913/forward48_timing_locked_forward_report.json`
- `artifacts/forward48_scalein_timing_compatibility_20260913.json`
