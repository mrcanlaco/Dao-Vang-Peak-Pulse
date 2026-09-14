# Ánh xạ Thư viện nghiên cứu sang Challenger 48h

## Nguyên tắc sử dụng

Các báo cáo trong Models → Thư viện nghiên cứu là nguồn tạo giả thuyết, không
phải bằng chứng cho contract hiện tại. Phần lớn kết quả cũ dùng nhãn 8%/12h với
MAE 4%, trong khi Challenger dùng mục tiêu 20%/48h và stop 16% từ giá trung
bình. Vì vậy mọi kết luận phải được kiểm định lại trên cùng signal keys và cùng
execution contract của Challenger.

## Những kết luận đáng thử lại

| Kết luận lịch sử | Cách chuyển thành phép thử 48h | Nhánh |
|---|---|---|
| Sideway/distribution thường tốt hơn bull trend | So baseline với gate sideway-only, sideway+bear và loại bull; báo phần tín hiệu bị mất | Regime |
| BTC context là heuristic đơn lẻ tốt nhất | Kiểm tra BTC return/trend và alt-pump interaction, không dùng điểm heuristic tổng | Regime |
| Volatility alt và BTC có information gain cao | Test percentile và interaction; phân biệt volatility expansion với high-volatility chop | Regime/Timing |
| Funding raw cao có thể tiếp tục short squeeze | Dùng funding raw cao làm negative control; không short chỉ vì funding cao | Timing |
| Funding exhaustion có thể cần percentile + persistence + change | Test điều kiện giao nhau và trạng thái change ngừng tăng/đảo chiều sau khi đã kéo dài | Regime/Timing |
| Sát đỉnh 24h thường còn breakout | Không dùng distance-to-high nhỏ làm trigger; yêu cầu tuổi pump/xác nhận giảm tốc | Timing |
| Momentum deceleration và price-volume divergence có tín hiệu nhẹ | Test xác nhận giảm tốc/volume dry-up sau pump, không dùng độc lập | Timing |
| Low-liquidity từng tốt hơn >500M volume | Cắt lát volume/liquidity point-in-time, báo coverage và hiệu năng từng bucket | Regime |
| Multi-horizon có thể mô tả alpha decay | So timeout 12/24/36/48h nhưng giữ target 20% và stop 16% | Execution |
| Scale-in cần thích ứng volatility | So fixed 0/+3/+6 với offsets chuẩn hóa theo volatility/overshoot, cùng capital budget | Execution |

## Negative controls và mâu thuẫn phải giữ lại

- Báo cáo 06 quy alpha cho `smart_money_divergence`, nhưng báo cáo 07 ghi
  importance của nó và các long/short ratio bằng 0. Nhóm này chỉ là negative
  control cho tới khi backtest mới chứng minh ngược lại.
- Regime Gate trong báo cáo 02 gần như không tăng precision (20.81% lên 20.83%)
  mà chủ yếu giảm 23% số cảnh báo. Nó chỉ là alpha nếu EV/risk-adjusted result
  tăng trên contract 48h, không phải vì số tín hiệu ít hơn.
- `HIGH_VOLATILITY_CHOP` từng bị chặn, trong khi volatility 24h cao lại có
  importance lớn. Hai khái niệm không đồng nhất: cần test interaction với trend,
  breadth và exhaustion thay vì một hard gate chung.
- Kết quả bear regime khác nhau giữa mega-cap và altcoin; không được gộp hai
  universe.
- Các ROI +302% và +2371% dùng leverage, giới hạn lệnh, TP/SL và contract khác;
  không được dùng để ước lượng lợi nhuận Challenger.
- Thư viện từng phát hiện dữ liệu giả/hardcoded, Cartesian expansion, BTC bị
  thiếu và NULL bị ép thành 0. Mỗi runner mới phải kiểm tra unique keys, join
  coverage, BTC coverage, NULL rate và provenance.

## Danh sách thử nghiệm đã giao

1. **Regime/context:** sideway/bear/bull/chop, liquidity buckets, BTC context,
   volatility interaction, funding exhaustion và smart-money negative control.
2. **Episode timing:** funding transition, momentum deceleration, pullback khỏi
   peak, probability trajectory, xác nhận liên tiếp và tuổi episode.
3. **Execution/risk:** conditional E2/E3, volatility-scaled offsets, time-stop và
   alpha-decay, luôn giữ TP -20%/stop +16%/48h cùng fees và funding.

Mỗi nhánh chỉ được chọn biến thể trên development walk-forward. August là
recycled holdout, có quyền bác bỏ nhưng không promote. Chỉ dữ liệu mới sau
cutoff frozen mới là sealed-forward evidence.
