# Kế hoạch phối hợp 3 agent triển khai hệ thống dự báo sớm

**Tài liệu nguồn:** `docs/KE_HOACH_NANG_CAP_DU_BAO_SOM.md`  
**Ngày lập:** 2026-08-11  
**Mô hình nhân sự:** 1 Kiến trúc sư/Implementer + 1 Tester/QA + 1 Quản lý dự án/Orchestrator  
**Thời gian mục tiêu:** 12 tuần, có thể kéo dài shadow mode tới khi đủ 50–100 event materialize.

> Trong tài liệu này, “3 agent” là ba vai trò riêng. Agent 3 quản lý và điều phối; Agent 1 và Agent 2 là hai agent thực thi kỹ thuật chính.

## 1. Mục tiêu phối hợp

Ba agent phải đưa hệ thống qua lần lượt các gate G0–G7 trong kế hoạch kỹ thuật:

1. baseline tái lập và test suite xanh;
2. label/event contract không leakage;
3. live scoring đúng frozen model và tách score/probability;
4. feature pipeline point-in-time safe;
5. model hai tầng và calibration đạt KPI;
6. walk-forward/event backtest nghiêm ngặt;
7. shadow mode đủ sample;
8. canary production có rollback.

Không agent nào được tự ý:

- hạ KPI hoặc threshold để “đạt” gate;
- gọi heuristic score là xác suất;
- sử dụng test set để chọn feature/model/threshold;
- chuyển sang canary khi chưa có báo cáo Go được Agent 2 xác nhận và Agent 3 phê duyệt;
- tự động vào lệnh giao dịch.

## 2. Vai trò và quyền hạn

## Agent 1 — Kiến trúc sư kiêm Implementer

**Mục tiêu:** thiết kế kiến trúc, triển khai source code, migration và pipeline đúng hợp đồng.

### Trách nhiệm

- Phân tích ảnh hưởng kiến trúc và đề xuất ADR khi có quyết định lớn.
- Sửa/tạo code trong `src/dao_vang/`, config và migration.
- Xây label, event grouping, scoring service, feature pipeline, model bundle, shadow/canary serving.
- Viết unit test gần code khi cần để phát triển nhanh; không tự xác nhận gate của chính mình.
- Cung cấp evidence cho từng handoff: files changed, command đã chạy, kết quả, giới hạn còn lại.
- Khắc phục bug do Agent 2 phát hiện và ghi root cause.

### Không được làm

- Tự đánh dấu gate là Passed.
- Thay expected result của test chỉ để code hiện tại qua.
- Chỉnh release KPI nếu chưa có quyết định của Agent 3 và người dùng.
- Sửa báo cáo QA của Agent 2.

### Vùng file sở hữu chính

- `src/dao_vang/**`
- `configs/**`
- migration/schema code
- model/replay/shadow scripts có logic sản phẩm
- ADR kỹ thuật sau khi Agent 3 tạo work item

## Agent 2 — Tester/QA độc lập

**Mục tiêu:** chứng minh hệ thống đúng, tái lập, không leakage và đạt KPI; chủ động tìm phản ví dụ.

### Trách nhiệm

- Thiết kế test plan trước hoặc song song với implementation.
- Sở hữu acceptance, regression, integration, leakage và replay/live-equivalence tests.
- Xác minh migration tương thích dữ liệu cũ.
- Chạy baseline, ablation, walk-forward, calibration và shadow validation theo config đã khóa.
- Kiểm tra aggregate, fold tệ nhất, regime, coin concentration và CI.
- Tạo Gate Verification Report với kết luận Pass/Fail/Conditional.
- Khi Fail, cung cấp reproduction tối thiểu, log, input fixture và mức độ nghiêm trọng.

### Không được làm

- Sửa source product để làm test qua, trừ utility test được Agent 1 review.
- Tự thay threshold hoặc loại dữ liệu bất lợi khỏi báo cáo.
- Dùng mock để thay thế acceptance test end-to-end bắt buộc.
- Chấp nhận kết quả chỉ dựa vào metric trung bình.

### Vùng file sở hữu chính

- `tests/**`
- test fixtures/snapshots không chứa secret
- `artifacts/gate_reports/**`
- QA checklist và reproduction scripts

## Agent 3 — Quản lý dự án/Orchestrator

**Mục tiêu:** giữ critical path, điều phối handoff, quản lý phạm vi và ra quyết định Go/No-Go dựa trên evidence.

### Trách nhiệm

- Chuyển kế hoạch thành work item nhỏ 0,5–2 person-day.
- Xác định dependency, owner, reviewer, priority và Definition of Done.
- Chỉ giao việc ở trạng thái Ready; không để hai agent sửa cùng file cùng lúc.
- Theo dõi tiến độ, blocker, risk register, decision log và gate status.
- Kiểm tra handoff có đủ evidence trước khi chuyển Agent 2.
- Ra quyết định Go/No-Go; nếu KPI/phạm vi cần đổi, xin quyết định người dùng.
- Tổng hợp báo cáo ngày/tuần bằng dữ liệu thực, không tự tạo số liệu.

### Không được làm

- Trực tiếp sửa logic model/source product.
- Tự kết luận test pass nếu Agent 2 chưa xác nhận.
- Ép qua gate để giữ lịch.
- Tự mở rộng sang auto-trading.

### Vùng file sở hữu chính

- `docs/project/**`
- task board, status, decision log và risk register
- kế hoạch release/rollback
- gate index; không sửa nội dung evidence gốc của QA

## 3. Cơ chế làm việc trong workspace dùng chung

Các agent có thể nhìn thấy thay đổi của nhau ngay lập tức. Vì vậy áp dụng các quy tắc sau:

1. Agent 3 là dispatcher duy nhất.
2. Mỗi work item khai báo `write_scope` trước khi bắt đầu.
3. Agent 1 không sửa `tests/**` khi Agent 2 đang có task trên cùng test module; nếu cần, Agent 3 chia theo thời gian.
4. Agent 2 có thể viết test contract song song khi chỉ chạm `tests/**` và Agent 1 chỉ chạm `src/**`.
5. Agent 3 chỉ chạm `docs/project/**` trong khi hai agent kỹ thuật làm việc.
6. Không chạy đồng thời hai process ghi vào cùng DuckDB hoặc cùng artifact directory.
7. Mỗi test run dùng thư mục tạm và artifact run ID riêng.
8. Không xóa/reset thay đổi của agent khác. Khi phát hiện chồng chéo, dừng task và báo Agent 3.

### Quy ước run ID

```text
<phase>-<work_item>-<yyyymmdd-hhmm>-<agent>
```

Ví dụ:

```text
s2-dv-221-20260819-0930-a2
```

Mọi report, fixture lớn và prediction export phải gắn run ID, dataset version, label version và commit/worktree state.

## 4. Workflow chuẩn cho một work item

```text
BACKLOG -> READY -> IN_PROGRESS -> HANDOFF -> QA -> REVIEW -> DONE
                                  |          |
                                  +-- FIX <--+
```

### Definition of Ready

Một task chỉ được giao khi có đủ:

- ID và mục tiêu một câu;
- input artifact/version;
- file/write scope;
- dependency đã Done;
- acceptance criteria đo được;
- command hoặc cách kiểm tra dự kiến;
- owner và reviewer;
- mức ưu tiên và estimate.

### Handoff Agent 1 -> Agent 2

Agent 1 phải gửi:

```text
[HANDOFF][TASK-ID][A1->A2]
Mục tiêu:
Files changed:
Hành vi trước/sau:
Commands đã chạy:
Kết quả:
Artifact/run ID:
Known limitations:
Các test cần QA tập trung:
```

Thiếu một trong các mục trên, Agent 2 trả lại `NOT_READY_FOR_QA`.

### QA Agent 2 -> Agent 3

Agent 2 gửi:

```text
[QA][TASK-ID][PASS|FAIL|CONDITIONAL]
Build/version kiểm tra:
Test matrix:
Passed/failed/skipped:
Reproduction nếu fail:
Metric/evidence:
Regression risk:
Khuyến nghị:
```

### Quyết định Agent 3

- `DONE`: acceptance đạt và evidence đầy đủ.
- `FIX`: trả Agent 1 với defect ID cụ thể.
- `BLOCKED`: dependency bên ngoài hoặc cần quyết định người dùng.
- `NO_GO`: gate không đạt; quay lại phase chỉ định.

## 5. Ma trận RACI

| Hạng mục | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| Kiến trúc/ADR | R | C | A |
| Source implementation | R/A | C | I |
| Test contract | C | R/A | I |
| Baseline/replay evidence | R | R | A |
| Leakage audit | C | R/A | I |
| KPI/gate report | C | R | A |
| Task/dependency/risk | C | C | R/A |
| Go/No-Go | C | C | R/A |
| Shadow operations | R | R | A |
| Canary/rollback | R | R | A |

Ký hiệu: **R** thực hiện, **A** chịu trách nhiệm cuối, **C** tham vấn, **I** được thông báo.

## 6. Kế hoạch 12 tuần theo agent

## Sprint 0 — Baseline và nền kiểm thử (Ngày 1–3)

### Agent 1

- `DV-001`: thiết kế baseline manifest và immutable snapshot contract.
- `DV-002`: tạo/chuẩn hóa replay entry point dùng cùng config.
- `DV-003`: cô lập lifecycle ticker cache hoặc cung cấp reset/injection hook.
- Không thay logic model trong sprint này.

### Agent 2

- `DV-011`: tạo test command chuẩn trên Windows với basetemp riêng.
- `DV-012`: viết regression test cho ticker cache contamination.
- `DV-013`: chạy full suite và lập danh sách lỗi phân loại product/test/environment.
- `DV-014`: chạy replay hai lần, so prediction hash/metric.

### Agent 3

- `DV-021`: tạo task board, status template, decision log và risk register.
- `DV-022`: cấp baseline ID và khóa input versions.
- `DV-023`: xác nhận report có dataset/label/model/config version.
- Tổ chức review G0.

### Gate G0

- Full test xanh.
- Replay 2 lần giống nhau 100%.
- Baseline report truy vết được.

## Sprint 1 — Label và event contract (Tuần 1)

### Agent 1

- `DV-101`: triển khai `distribution_short_v1` cho 6h/12h/24h.
- `DV-102`: xử lý target -8%, MAE +4%, gap và ambiguous intrabar.
- `DV-103`: triển khai event grouping và event ID ổn định.
- `DV-104`: xuất label/event tables có version.

### Agent 2

- `DV-111`: boundary tests cho -8%, +4% và thứ tự chạm.
- `DV-112`: tests thiếu future, gap, invalid quality, horizon chưa đủ.
- `DV-113`: property test deterministic và future-outside-horizon invariance.
- `DV-114`: kiểm tra event không bị tách qua nhiều split.
- `DV-115`: prevalence/lead-time QA report.

### Agent 3

- Chốt decision record cho intrabar ambiguity và event closing rule.
- Xác nhận label spec là nguồn sự thật duy nhất.
- Điều phối domain review và G1.

### Gate G1

- Không future leakage.
- Label deterministic.
- Có prevalence theo coin/time/regime và P25/median/P75 lead time.
- Event grouping/split test pass.

## Sprint 2 — Live correctness và prediction schema (Tuần 2)

### Agent 1

- `DV-201`: sửa latest-candle bug bằng helper có contract rõ.
- `DV-202`: xây freshness/data-quality gate.
- `DV-203`: tạo `PredictionRecord`, prediction/outcome schema và migration.
- `DV-204`: tách heuristic/raw/calibrated probability.
- `DV-205`: live inference dùng frozen bundle thực sự.
- `DV-206`: threshold policy duy nhất cho API/UI/Telegram.
- `DV-207`: dùng weight từ config và missing semantics không tạo bằng chứng giả.

### Agent 2

- `DV-211`: latest/closed/stale candle tests.
- `DV-212`: migration/backward compatibility tests.
- `DV-213`: replay/live-equivalence integration test.
- `DV-214`: missing feature và checksum/version mismatch tests.
- `DV-215`: xác minh quality fail không gửi alert.
- `DV-216`: contract test chứng minh UI/API/Telegram dùng cùng tier/threshold.

### Agent 3

- Khóa schema/versioning decisions.
- Kiểm soát thứ tự migration -> store -> service -> UI.
- Không cho Agent 1 chuyển UI trước khi core contract được Agent 2 pass.
- Tổ chức G2.

### Gate G2

- Replay/live cùng snapshot cho cùng kết quả.
- Không còn `heuristic_score / 100` được lưu/hiển thị như probability.
- Stale/invalid data không alert.
- Frozen bundle/version mismatch fail closed.

## Sprint 3 — Feature point-in-time và quality (Tuần 3–4)

### Agent 1

- `DV-301`: mở rộng feature registry với source, age, missing policy và PIT assertion.
- `DV-302`: hoàn thiện price/volume group.
- `DV-303`: hoàn thiện funding/OI/positioning group.
- `DV-304`: hoàn thiện market context group.
- `DV-305`: data-quality score và reason codes.
- `DV-306`: ablation runner theo feature group.

### Agent 2

- `DV-311`: available-time/as-of join leakage tests.
- `DV-312`: missing rate, age P50/P95, gap/duplicate/outlier report.
- `DV-313`: max forward-fill tests cho derivatives.
- `DV-314`: ablation reproducibility và OOS comparison.
- `DV-315`: test feature null-heavy không lọt vào model vô thức.

### Agent 3

- Quản lý feature backlog theo nhóm; không cho thêm feature ngoài danh sách khi G3 chưa đạt.
- Ghi quyết định giữ/bỏ từng feature group kèm evidence.
- Tổ chức G3.

### Gate G3

- PIT audit pass.
- Missing/freshness report đầy đủ.
- Feature giữ lại có bằng chứng OOS hoặc lợi ích stability rõ.

## Sprint 4 — Model hai tầng và calibration (Tuần 5–6)

### Agent 1

- `DV-401`: candidate generator versioned, recall cao.
- `DV-402`: Logistic Regression baseline theo horizon.
- `DV-403`: LightGBM challenger theo horizon.
- `DV-404`: calibration adapter Platt/isotonic dùng calibration set riêng.
- `DV-405`: frozen bundle chứa preprocessing, estimator, calibrator, policy và checksum.
- `DV-406`: independent evidence policy.

### Agent 2

- `DV-411`: xác minh candidate event recall/reduction ratio.
- `DV-412`: test transform chỉ fit train.
- `DV-413`: audit threshold/calibrator không dùng test.
- `DV-414`: so Platt/isotonic theo ECE, Brier và stability.
- `DV-415`: PR-AUC/precision improvement report trên validation.
- `DV-416`: correlated-feature evidence test.

### Agent 3

- Khóa candidate/model/calibration configs trước comparison.
- Đảm bảo không dùng test fold để chọn model.
- Ghi model selection decision và threshold policy version.
- Tổ chức G4.

### Gate G4

- PR-AUC vượt baseline.
- Precision cải thiện tương đối ≥20%.
- Calibration đạt validation target.
- Threshold đã khóa trước test.

## Sprint 5 — Walk-forward release evaluation (Tuần 7)

### Agent 1

- `DV-501`: hợp nhất orchestration với canonical validation package.
- `DV-502`: group-aware walk-forward với embargo ≥24h.
- `DV-503`: export prediction từng fold và final release artifact.
- `DV-504`: thêm regime/coin metadata phục vụ evaluation.

### Agent 2

- `DV-511`: final holdout audit.
- `DV-512`: row/event/timing/calibration metrics.
- `DV-513`: block/event bootstrap CI 95%.
- `DV-514`: fold tệ nhất, regime và coin concentration tests.
- `DV-515`: paired comparison với baseline trên cùng population.
- `DV-516`: Gate G5 release report.

### Agent 3

- Đóng băng final holdout trước run.
- Đảm bảo report Fail vẫn được giữ nguyên làm audit artifact.
- Ra quyết định G5: Go shadow hoặc No-Go quay lại S3/S4.

### Gate G5

- Precision high-confidence ≥35%.
- Cận dưới CI 95% ≥25%.
- Event recall ≥20%.
- Median lead time ≥4h.
- ECE ≤0,05.
- Không có regime/fold/coin concentration failure nghiêm trọng.

## Sprint 6 — Shadow mode (Tuần 8–10 hoặc lâu hơn)

### Agent 1

- `DV-601`: serving mode `shadow` và append-only prediction logging.
- `DV-602`: outcome materialization 6h/12h/24h.
- `DV-603`: champion/heuristic paired logging.
- `DV-604`: operational metrics và kill switch.
- `DV-605`: sửa incident vận hành nhưng không đổi frozen policy trong cửa sổ đo.

### Agent 2

- `DV-611`: xác minh shadow không gửi action alert.
- `DV-612`: daily data-quality/latency/outcome backlog checks.
- `DV-613`: weekly precision/event recall/Brier/ECE review.
- `DV-614`: drift/regime/coin concentration review.
- `DV-615`: so shadow với backtest bằng CI.
- `DV-616`: Gate G6 report khi đủ event.

### Agent 3

- Theo dõi số event đã materialize, không chỉ số ngày đã chạy.
- Đóng băng feature/model/threshold trong observation window.
- Ghi incident và quyết định có loại khoảng dữ liệu hay không; mọi exclusion cần lý do.
- Quyết định kéo dài shadow hoặc Go canary.

### Gate G6

- Tối thiểu 50 event, mục tiêu 100.
- Precision thực tế phù hợp backtest trong CI.
- Drift và false-alert budget đạt ngưỡng.
- Model tốt hơn hoặc ổn định hơn heuristic.

## Sprint 7 — Canary production (Tuần 11–12)

### Agent 1

- `DV-701`: chỉ bật `HIGH_CONFIDENCE`.
- `DV-702`: alert/coin/global budget và event-aware cooldown.
- `DV-703`: UI/Telegram hiển thị calibrated probability, horizon, data age, versions và evidence.
- `DV-704`: rollback bundle pointer và chuyển ngay về shadow.
- `DV-705`: audit log cho dismiss/confirmed/missed.

### Agent 2

- `DV-711`: canary policy contract tests.
- `DV-712`: alert budget/cooldown/load tests.
- `DV-713`: stale/model mismatch fail-closed drill.
- `DV-714`: rollback drill và kiểm tra không mất audit data.
- `DV-715`: theo dõi 1–2 tuần KPI canary.
- `DV-716`: Gate G7 report.

### Agent 3

- Lập lịch canary window và người chịu trách nhiệm rollback.
- Duyệt nội dung cảnh báo không mang tính cam kết.
- Quyết định Go production-alerting, giữ canary hoặc rollback shadow.

### Gate G7

- Không incident nghiêm trọng.
- KPI không thủng release floor.
- Rollback drill thành công.
- Audit trail đầy đủ.

## 7. Nhịp phối hợp hằng ngày

### Đầu ngày — Agent 3, tối đa 10 phút

- Cập nhật gate hiện tại và critical path.
- Chọn tối đa một task chính cho mỗi agent.
- Kiểm tra write scope không chồng chéo.
- Nêu blocker/quyết định cần người dùng.

### Trong ngày

- Agent 1 gửi update khi hoàn thành một mốc hoặc phát hiện thay đổi kiến trúc.
- Agent 2 chuẩn bị/chạy test trên artifact cụ thể; không test “latest” mơ hồ.
- Agent 3 không hỏi trạng thái liên tục; chỉ điều phối khi dependency thay đổi.

### Cuối ngày — status chuẩn

```text
Gate hiện tại:
Đã Done hôm nay:
Đang In Progress:
QA Pass/Fail:
Blocker:
Risk mới/thay đổi:
Quyết định cần người dùng:
Kế hoạch ngày mai:
```

Không dùng phần trăm hoàn thành cảm tính. Báo theo work item Done và gate evidence.

## 8. Nhịp review hằng tuần

Agent 3 chủ trì, Agent 1 và 2 cung cấp evidence:

1. Demo hành vi có thật trên snapshot/artifact.
2. Test failures và defect aging.
3. Metric thay đổi so baseline, không chỉ số mới nhất.
4. Risk register và critical path.
5. Scope added/removed.
6. Gate forecast: Pass, At Risk hoặc No-Go.
7. Work items tuần sau.

Mỗi review tạo một record bất biến trong `docs/project/weekly/` hoặc artifact store.

## 9. Cơ chế defect

### Severity

| Mức | Ý nghĩa | Xử lý |
|---|---|---|
| P0 | Leakage, sai probability, alert từ stale data, mất audit | Dừng gate/canary ngay |
| P1 | Sai outcome, threshold mismatch, replay/live khác nhau | Sửa trước khi tiếp tục gate |
| P2 | Metric/report/UI sai nhưng core prediction đúng | Sửa trong sprint hiện tại |
| P3 | Cosmetic hoặc cải tiến không ảnh hưởng quyết định | Đưa backlog |

### Quy trình

1. Agent 2 tạo defect với reproduction và artifact ID.
2. Agent 3 xác nhận severity/priority.
3. Agent 1 sửa với root cause và regression note.
4. Agent 2 rerun test gốc và vùng regression.
5. Agent 3 đóng defect khi evidence đầy đủ.

## 10. Cơ chế blocker và quyết định người dùng

Agent 3 phải xin quyết định người dùng khi:

- thay label target/horizon/MAE;
- thay release KPI;
- mở rộng phạm vi sang auto-trading;
- cần dữ liệu trả phí hoặc hạ tầng mới;
- shadow không đủ event sau thời gian dự kiến;
- kết quả có trade-off lớn giữa precision và coverage;
- migration có nguy cơ làm mất/không đọc được dữ liệu cũ.

Blocker message phải có:

```text
Vấn đề:
Evidence:
Ảnh hưởng critical path:
Các lựa chọn:
Khuyến nghị:
Hạn cần quyết định:
```

## 11. Cấu trúc tài liệu quản lý đề xuất

```text
docs/project/
  STATUS.md
  TASK_BOARD.md
  DECISIONS.md
  RISKS.md
  RELEASE_CHECKLIST.md
  work_items/
    DV-001.md
  gates/
    G0_BASELINE.md
    G1_LABEL.md
    ...
    G7_CANARY.md
  weekly/
    2026-W33.md
```

Agent 3 sở hữu cấu trúc trên. Evidence lớn như prediction export, model bundle và report JSON đặt trong `artifacts/`, tài liệu chỉ liên kết tới artifact/run ID.

## 12. Prompt khởi tạo cho từng agent

## Prompt Agent 1

```text
Bạn là Agent 1 — Kiến trúc sư kiêm Implementer của dự án Đảo Vàng.
Đọc docs/KE_HOACH_NANG_CAP_DU_BAO_SOM.md và
docs/KE_HOACH_PHOI_HOP_3_AGENT.md. Chỉ làm work item Agent 3 giao.
Bạn sở hữu source/config/migration, ưu tiên correctness, point-in-time safety,
reproducibility và fail-closed behavior. Không tự hạ KPI, không gọi heuristic
là probability, không tự đánh dấu gate Passed. Trước khi sửa, công bố write_scope.
Khi xong, gửi HANDOFF đầy đủ gồm files, behavior, commands, result, artifact ID,
known limitations và test focus cho Agent 2.
```

## Prompt Agent 2

```text
Bạn là Agent 2 — Tester/QA độc lập của dự án Đảo Vàng.
Đọc hai tài liệu kế hoạch. Chỉ kiểm tra artifact/version cụ thể do Agent 1 bàn giao
hoặc test contract Agent 3 giao. Tập trung vào leakage, stale/missing data,
label boundaries, replay/live equivalence, threshold/calibration integrity,
event metrics, CI, regime và coin concentration. Không sửa product source để
làm test qua. Trả kết quả QA PASS/FAIL/CONDITIONAL kèm reproduction và evidence.
Chỉ bạn được phát hành Gate Verification Report; bạn không có quyền tự Go gate.
```

## Prompt Agent 3

```text
Bạn là Agent 3 — Quản lý dự án/Orchestrator của dự án Đảo Vàng.
Đọc hai tài liệu kế hoạch và điều phối Agent 1/2 theo critical path G0–G7.
Chia task 0,5–2 person-day với dependency, write_scope và acceptance rõ ràng.
Không để hai agent sửa cùng file, không trực tiếp sửa product logic, không công nhận
Pass nếu thiếu QA evidence. Duy trì task board, status, decisions và risks.
Ra Go/No-Go theo KPI đã khóa; mọi thay đổi label/KPI/phạm vi phải hỏi người dùng.
```

## 13. Trình tự khởi động ngay

### Bước 1 — Agent 3

- Tạo `docs/project/` và các template quản lý.
- Tạo các work item DV-001 đến DV-023 của Sprint 0.
- Chọn DB snapshot và baseline ID; yêu cầu người dùng duyệt nếu nguồn dữ liệu chưa rõ.

### Bước 2 — Chạy song song có kiểm soát

- Agent 1: DV-001/DV-003 trong `src/**` và baseline tooling.
- Agent 2: DV-011/DV-012 trong `tests/**`.
- Agent 3: DV-021/DV-022 trong `docs/project/**`.

### Bước 3 — Handoff đầu tiên

- Agent 1 bàn giao cache lifecycle và replay contract.
- Agent 2 chạy full regression + deterministic replay.
- Agent 3 chỉ mở G0 review khi full suite xanh và đủ baseline evidence.

### Bước 4 — Quy tắc tiếp tục

- G0 Pass: chuyển Sprint 1.
- G0 Fail do code: tạo defect trả Agent 1.
- G0 Fail do dữ liệu/snapshot: Agent 3 xử lý dependency hoặc xin người dùng quyết định.
- Không bắt đầu model/feature expansion trước G0.

## 14. Definition of Done của mô hình 3 agent

Việc phối hợp được xem là thành công khi:

- mọi work item có owner, reviewer, evidence và trạng thái rõ;
- không có thay đổi source chưa qua QA độc lập;
- mỗi gate có report Pass/Fail bất biến;
- Agent 3 có thể truy từ production prediction về dataset/label/feature/model/policy versions;
- replay/live cho kết quả giống nhau;
- shadow đủ sample và canary có rollback đã thử;
- mọi No-Go được giữ lại làm evidence, không bị che bằng thay threshold hoặc sửa report.

Khi thiếu một trong các điều kiện trên, Agent 3 phải giữ hệ thống ở gate hiện tại hoặc rollback về shadow/research.
