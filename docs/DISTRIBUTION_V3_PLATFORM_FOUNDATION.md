# Nền tảng v3 cho mục tiêu giảm 20% trong 48 giờ

## Quyết định

Lấy `distribution_short_v3_policy_48h` làm tiêu chuẩn nghiên cứu mới. Không sửa
ngược v1 hoặc v2: v1 là nhãn giảm 8%/24h, còn code v2 hiện cố định ở 20%/24h.
Giữ nguyên chúng để các báo cáo cũ vẫn tái tạo được.

V3 đo đúng kết quả người dùng cần: sau các Entry đã khớp, giá phải giảm 20% từ
giá trung bình trước khi tăng 16% từ cùng giá trung bình, trong tối đa 48 giờ.
Phí, trượt giá và funding là một phần bắt buộc của kết quả.

## Vì sao cần contract mới

Hệ thống hiện tại có ba ngôn ngữ không khớp nhau:

1. Model production học nhãn 8%/24h với MAE 4%.
2. Candidate comparison ghi mục tiêu 20%/24h.
3. Execution router đặt target từ giá trung bình nhưng stop từ giá tín hiệu,
   và từ chối eligibility khi model vẫn mang label v1.

Chỉ đổi con số trên giao diện sẽ tạo một xác suất sai nghĩa. V3 phải thống nhất
label, timing, execution, outcome ledger và forward evidence dưới cùng một
version.

## Kiến trúc đề xuất

```text
Point-in-time market data
          |
          v
Candidate universe (pump >=15%)
          |
          v
Opportunity model P(outcome under compact policy)
          |
          v
Timing state machine (peak >=30%, age >=4h, 2 confirmations)
          |
          +------------------------------+
          |                              |
          v                              v
Parent Challenger                 Funding Scout
all eligible events               3 funding feature predicates
          |                              |
          +--------------+---------------+
                         v
Compact execution 0/+3/+6, 20/30/50
                         |
                         v
Fill ledger -> weighted average revisions -> TP/stop/timeout
                         |
                         v
Identical-row forward evaluator and promotion gates
```

### 1. Data and event ledger

Mỗi candidate, kể cả bị gate chặn, phải có event key ổn định và lưu model ID,
feature schema, label contract, timing version và policy version. Fill ledger
lưu từng Entry, thời gian khớp, vốn, giá trung bình sau khớp, target/stop mới,
funding và exit. Điều này cho phép phân biệt model sai với execution sai.

### 2. Opportunity model

Primary label không còn chỉ hỏi “giá có giảm 20% từ Entry 1 không?”. Nó hỏi
“compact policy có đạt target trước stop trong 48h không?”. Policy là xác định
trước nên label vẫn hợp lệ cho supervised learning. Entry-1 price-path label
được giữ làm diagnostic để đo riêng chất lượng tín hiệu.

### 3. Timing engine

Timing là state machine riêng, không nhét vào threshold model. Baseline đã khóa:
pump peak >=30% kể từ lúc armed, tuổi episode >=4h, hai xác nhận với điểm >=0.39
cách nhau tối đa 90 phút. Xác nhận được giữ trong episode; sau đó Entry 1 cho phép
điểm >=0.29 (tolerance 0.10 của bản Challenger đã khóa). Một Entry 1 mỗi episode,
cooldown 24h; Entry đủ điều kiện nhưng bị cooldown cũng tiêu thụ episode.
Mỗi thay đổi timing có version và backtest riêng. Ngưỡng này chỉ phục vụ đối chiếu
model nghiên cứu cũ, chưa phải xác suất calibrated của model policy-aware v3.

### 4. Strategy lanes

- `v3_parent_challenger`: mọi tín hiệu đạt timing baseline.
- `v3_funding_exhaustion_scout`: cùng tín hiệu nhưng thêm funding percentile
  >=80%, persistence >0 và funding change 8h >0.
- Model production v1 chỉ làm comparator; không trộn xác suất v1 với v3.

Hai lane chạy trên cùng snapshot và cùng evaluator. Scout không được âm thầm
thay baseline hoặc làm biến mất denominator.

### 5. Execution and risk

Compact `0/+3/+6`, vốn `20/30/50`, cửa sổ 6h là champion nghiên cứu. Target và
stop đều rebase từ giá trung bình sau mỗi fill. Evaluator dùng stop-first khi
một bar chạm cả hai, mark-to-market ở 48h, tính phí/slippage/funding và báo vốn
thực tế đã triển khai.

### 6. Evidence and promotion

Development, recycled holdout và future sealed forward phải được gắn nhãn rõ.
Chỉ dữ liệu mới sau khi toàn bộ candidate đã khóa mới có quyền promotion. Gate
tối thiểu: 100 event mới, ba cửa sổ thời gian, target rate >=50%, episode recall
>=10%, Wilson lower >45%, actual và conservative EV dương, paired EV lower bound
dương và ECE <=0.05.

## Trình tự build an toàn

1. Thêm label spec/engine v3 policy-aware và golden path tests.
2. Thêm fill/outcome ledger có version, uniqueness và provenance constraints.
3. Cho scanner ghi song song parent/scout ở research mode, kể cả suppressed
   events; tuyệt đối chưa gửi lệnh hoặc đổi Telegram production.
4. Huấn luyện/calibrate bundle v3, khóa checksum và protocol forward mới.
5. Thêm API/UI hiển thị rõ lane, contract, Entry đã khớp, giá trung bình,
   target/stop hiện hành và evidence status.
6. Chỉ sau khi promotion gates đạt mới đề xuất thay `scanner.frozen_model_id`.

## Phần có thể tái sử dụng

Feature pipeline, frozen bundle/checksum, episode tracker, policy router,
price-path evaluator, prediction store và forward evidence framework đều có
thể tái sử dụng. Cần mở rộng thay vì viết lại toàn bộ ứng dụng.

Các phần không nên tái sử dụng nguyên trạng là label v1/v2, forward protocol
v1, stop cố định theo signal price, và các metric UI không gắn label/policy
version.

Research standard machine-readable nằm tại
`configs/distribution_v3_research_standard.yaml`. Production config chưa đổi.

## Đã triển khai — 2026-09-14

Đợt này đã có lõi chạy được, chưa nối scanner hoặc thay model đang phục vụ:

- Contract bất biến và checksum: `src/dao_vang/labels/specs/distribution_short_v3.py`.
- Evaluator policy-aware 48h và diagnostic Entry1 riêng: `src/dao_vang/labels/engine_v3.py`.
- Timing Challenger, Funding Scout cùng Entry1, offline replay và SQLite evidence
  ledger: `src/dao_vang/experiments/distribution_v3.py`.
- CLI `dao-vang experiment replay-v3` và fixture kiểm thử có nhãn `synthetic`.
- Lưu mọi snapshot, quyết định chọn/loại, từng fill, giá trung bình/TP/stop sau fill,
  funding, chi phí và kết quả. Replay giống hệt không nhân đôi dữ liệu. Path được
  bổ sung/sửa tạo run mới; không ghi đè kết quả cũ, không cộng các run thành mẫu độc lập.

### Các quy ước tính toán đã khóa

`20/30/50` là tỷ trọng **notional** trên một đơn vị vốn kế hoạch, không phải tỷ
trọng số coin. Với mỗi leg, `quantity = notional / fill_price`, rồi
`average = sum(notional) / sum(quantity)`. Lợi nhuận báo trên vốn kế hoạch và vốn
đã triển khai; không phải ROE có đòn bẩy. Entry1 diagnostic dùng 100% một lệnh để
tách chất lượng điểm vào khỏi hiệu ứng tăng vị thế.

Bars là OHLC 5 phút, `close_time` ở cuối nến. Entry1 khớp giả định tại signal close;
không dùng lại high/low của nến tín hiệu. Cửa sổ 6h và hạn 48h tính từ Entry1,
không đặt lại đồng hồ khi thêm lệnh. Phải đủ đường giá liên tục tới exit hoặc 48h.

Trong nến, open đã biết được xử lý trước: gap vượt stop thoát ở open xấu hơn,
gap qua target chỉ được hưởng giá target. Nếu chưa thoát tại open, thứ tự bảo thủ
là **stop đang có → target đang có → thêm lệnh → kiểm tra close với target mới**.
Chạm stop và target tính stop. Không nâng stop để cứu vị thế đã vi phạm stop cũ;
không dùng low có thể xảy ra trước fill để nhận TP mới. Đây là mô phỏng nến có
quy ước bảo thủ, không tái dựng chính xác tick hay queue khớp lệnh. Timestamp của
fill/exit trong nến là giới hạn ở cuối nến, không phải giờ khớp chính xác.

Phí + trượt giá hiện là **giả định 0.1% mỗi chiều** trên notional thực giao dịch,
không phải dữ liệu phí tài khoản. Funding dùng rate và mark price từng settlement:
`cash_flow_short = quantity * mark_price * rate`. Settlement đầu nến áp dụng cho
vị thế trước thao tác nến; loại settlement đúng lúc Entry1, tính settlement cuối
48h nếu timeout. Provider phải xác nhận danh sách funding đầy đủ từ Entry1 tới
`funding_coverage_through`; danh sách trống không kèm xác nhận không có nghĩa là 0.

Thiếu đường giá hoặc funding: label/net EV bị loại có lý do, vẫn giữ kết quả quan
sát được để audit. Mỗi lane báo số snapshot, số Entry1, độ phủ đường giá, độ phủ đủ
chi phí/funding và denominator hợp lệ. Scout chỉ là tập con Entry1 của Parent,
không được đợi một tín hiệu muộn hơn riêng cho mình.

### Chạy kiểm thử và replay

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/execution tests/unit/labels tests/unit/experiments -q
.venv\Scripts\dao-vang.exe experiment replay-v3 tests/fixtures/distribution_v3_replay.json --ledger-path data/research/v3_synthetic_demo.sqlite
```

Fixture chỉ kiểm tra phần mềm, **không phải backtest thị trường hoặc bằng chứng
tăng tỷ lệ thắng**. Chạy lại lệnh thứ hai phải trả `inserted: false`.

Input JSON mẫu mô tả đủ schema. `provenance` bắt buộc có dataset/model ID, SHA-256
model, feature schema, nhãn mà score đã học và nguồn dữ liệu. Mọi feature phải có
`features_available_at <= feature_time`. Snapshot phải theo thời gian, không trùng
symbol/time, và khai báo stablecoin rõ ràng. `path` chỉ dùng sau khi chọn Entry1;
không cung cấp path vẫn lưu quyết định và ghi outcome thiếu dữ liệu.

Replay phải bắt đầu từ đầu cửa sổ candidate đã khóa, có đủ warm-up episode và
cooldown. Không chạy chỉ các entry đã chọn rồi diễn giải như backtest toàn universe.
Bản này là API/CLI offline; chưa phải bộ xử lý incremental có state khôi phục scanner.

### Các bước còn lại trước production

1. Adapter xuất snapshot point-in-time và path/funding thật từ kho dữ liệu hiện có;
   chạy lại cùng các event cũ để đo ảnh hưởng của sửa weighted average/intrabar/cost.
2. Materialize dataset nhãn policy-aware đầy đủ (cả universe, không chỉ Entry được
   chọn), kiểm tra temporal split/embargo, train/calibrate model v3.
3. Nối shadow scanner và API/UI; không gửi lệnh, không đổi cảnh báo production.
4. Khóa bundle, thời điểm freeze và tập forward thật sự mới; tính đủ recall,
   calibration, CI theo episode, paired EV và các gate trước khi xin đổi live.

Hiện `promotion_eligible=false` với mọi replay, chỉ nhận `synthetic` hoặc
`retrospective`; không tự chứng nhận `sealed_forward` từ một file JSON. Chưa có
gate tự động đủ điều kiện promotion. Mốc Wilson 45% chỉ là một điều kiện sàng lọc,
không phải điểm hòa vốn chắc chắn của scale-in với vốn triển khai thay đổi.
Funding persistence >0 là predicate chính xác của feature, không chứng minh
funding duy trì cao liên tục bảy ngày. Chưa thêm phân loại market-cap point-in-time.

## Cập nhật: adapter thị trường và đối chiếu cùng Entry1

Đã thêm `experiment audit-v3-market` và chạy trên 40 Entry1 tháng 8 đã khóa.
Đối chiếu trên 36 lệnh chung: Challenger vẫn 20/36 TP; Scout vẫn 8/10. Adapter
đọc nguồn chỉ đọc, chuẩn hóa ranh giới nến, ổn định chọn phiên bản trùng và lưu
snapshot đường giá/funding. Đây chưa phải replay toàn 5.703 candidate.

Funding thiếu xác nhận độ phủ và có timestamp lệch ranh giới mà engine v3.1
chưa mô phỏng; net EV chính thức vẫn để trống. Không huấn luyện/thay model live.
Chi tiết và run ID chuẩn nằm trong `docs/DISTRIBUTION_V3_MARKET_AUDIT_20260914.md`.
