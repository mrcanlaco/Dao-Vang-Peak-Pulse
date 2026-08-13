# Kế hoạch triển khai hệ thống cảnh báo phân phối sớm Đảo Vàng

**Phiên bản kế hoạch:** 1.0  
**Ngày lập:** 2026-08-11  
**Phạm vi:** Nâng hệ thống hiện tại từ heuristic scanner thành hệ thống cảnh báo xác suất có kiểm định, chạy shadow trước khi canary production.  
**Mục tiêu thời gian:** 10–12 tuần cho đội 2 kỹ sư; 14–18 tuần nếu chỉ có 1 kỹ sư. Shadow mode phải kéo dài thêm nếu chưa đủ 50–100 event đã materialize.

> Đây là hệ thống hỗ trợ ra quyết định, không phải cam kết lợi nhuận hay cơ chế tự động vào lệnh. Không vượt cổng kiểm định thì giữ ở research/shadow mode.

## 1. Kết quả cần đạt

Sau kế hoạch này, hệ thống phải trả lời được một câu hỏi rõ ràng:

> Tại thời điểm đóng nến 5 phút, xác suất coin giảm ít nhất 8% trong 6h, 12h hoặc 24h tới là bao nhiêu, với điều kiện giá không tăng quá 4% trước khi chạm mục tiêu?

Mỗi prediction phải có:

- `heuristic_score`: điểm luật 0–100, không được gọi là xác suất;
- `model_probability`: xác suất thô của model;
- `calibrated_probability`: xác suất sau calibration;
- `data_quality_score` và `quality_status`;
- horizon 6h/12h/24h;
- label, feature set, model và threshold version;
- feature time, feature freshness và snapshot ID;
- trạng thái `early_watch`, `confirmed_distribution` hoặc `invalidated`;
- reason codes và các nhóm bằng chứng độc lập;
- outcome sau khi horizon hoàn tất.

### KPI phát hành bắt buộc

| KPI | Ngưỡng Go | Điều kiện đo |
|---|---:|---|
| Precision tier high-confidence | ≥ 35% | Walk-forward và shadow |
| Cận dưới CI 95% của precision | ≥ 25% | Bootstrap theo event, không chỉ theo row |
| Event recall | ≥ 20% | Event đã gộp, tránh đếm nhiều nến của một lần xả |
| Median lead time | ≥ 4 giờ | Từ signal tới lần đầu chạm -8% |
| ECE | ≤ 0,05 | Trên prediction out-of-sample |
| Cải thiện precision tương đối | ≥ 20% | So với baseline tốt nhất đã khóa trước test |
| Data freshness | ≤ 10 phút | Không alert nếu vượt ngưỡng |
| Shadow sample | ≥ 50 event, mục tiêu 100 | Event đã materialize hoàn toàn |

KPI phụ bắt buộc báo cáo: PR-AUC, Brier score, alert/ngày, duplicate alert, missing rate, stale-data rate, precision/recall theo regime, coin concentration, MFE, MAE, fee và slippage giả lập.

## 2. Hiện trạng repo và khoảng trống

### Thành phần đã có, nên tái sử dụng

- Label engine tại `src/dao_vang/labels/` đã hỗ trợ target -8%, MAE +4% và horizon cấu hình được.
- Feature pipeline và metadata point-in-time đã có nền tảng tại `src/dao_vang/data/` và `src/dao_vang/features/`.
- Logistic Regression, LightGBM, isotonic calibration và frozen model đã có trong `src/dao_vang/experiments/`.
- Bộ validation đã có embargo, leakage audit, row/event metrics, ECE và bootstrap trong `src/dao_vang/validation/`.
- Alert history, outcome resolution, Telegram, UI/API và full scan result đã có nền tảng.

### Lỗi/gap phải xử lý trước khi huấn luyện thêm

1. Live scanner truy vấn `ORDER BY ... DESC LIMIT 12` nhưng lấy `df.iloc[-1]`, tức lấy nến cũ nhất trong 12 nến.
2. Scanner chỉ kiểm tra frozen model tồn tại; luồng score/alert thực tế vẫn gọi composite heuristic.
3. Heuristic `score / 100` đang được lưu vào cột `probability` và UI hiển thị như xác suất.
4. Scanner dùng threshold heuristic trong settings, trong khi frozen model có threshold riêng.
5. Weight tồn tại trong `ScoringConfig`, nhưng các hàm scorer vẫn hard-code weight.
6. Missing feature đang bị thay bằng giá trị có ý nghĩa rủi ro (`0`, `0.5`) ở nhiều chỗ.
7. Label hiện mặc định 24h và version `0.1.0`; chưa có contract duy nhất cho 6h/12h/24h và event grouping.
8. Có hai nhánh walk-forward (`experiments/` và `validation/`) với hành vi khác nhau; một nhánh còn tối ưu threshold trên test fold.
9. Schema alert chưa tách heuristic/raw/calibrated probability/data quality/label version/horizon.
10. Test hiện trạng: **251 passed, 4 failed**. Bốn lỗi do `_TICKERS_CACHE` toàn cục làm dữ liệu cache lọt giữa các test watchlist.

### Quyết định kỹ thuật cần khóa ngay

- `validation/` là nguồn sự thật cho split, leakage và metrics; `experiments/` chỉ orchestration/model adapter.
- Không tối ưu threshold trên test. Threshold chỉ học từ validation, sau đó khóa trước test/shadow.
- Một prediction là một bản ghi bất biến. Outcome được ghi riêng hoặc cập nhật bằng audit trail.
- Không dùng `fillna(0)` chung cho mọi feature. Mỗi feature có missing policy và missing indicator riêng.
- Không tự động giao dịch trong phạm vi kế hoạch này.

## 3. Kiến trúc đích

```text
Collectors -> normalized point-in-time data -> feature snapshot + quality gate
                                                |
                                                v
                                     Candidate generator (recall cao)
                                                |
                                                v
                            Confirmation model 6h / 12h / 24h
                                                |
                                                v
                                  Probability calibration
                                                |
                                                v
                           Policy gate + independent evidence rule
                                                |
                         +----------------------+-------------------+
                         |                                          |
                    Shadow store                         Canary alert/UI
                         |                                          |
                         +---------------- outcome resolver --------+
                                                |
                                                v
                              Monitoring, drift, retrain proposal
```

### Hợp đồng prediction đề xuất

Tạo model/domain object `PredictionRecord` và bảng `predictions` với tối thiểu:

| Nhóm | Trường |
|---|---|
| Định danh | `prediction_id`, `symbol`, `signal_time`, `created_at` |
| Mục tiêu | `horizon_hours`, `target_drawdown`, `max_adverse_excursion`, `label_version` |
| Điểm số | `heuristic_score`, `model_probability`, `calibrated_probability` |
| Chất lượng | `data_quality_score`, `quality_status`, `max_feature_age_minutes`, `missing_features_json` |
| Phiên bản | `dataset_version`, `feature_set_version`, `model_id`, `calibrator_id`, `threshold_policy_version` |
| Quyết định | `candidate_passed`, `state`, `tier`, `threshold`, `reason_codes_json`, `evidence_groups_json` |
| Vận hành | `shadow_mode`, `telegram_sent`, `cooldown_key`, `invalidation_time` |

Tạo bảng `prediction_outcomes`:

- `prediction_id`, `label_value`, `target_time`, `lead_time_minutes`;
- `mae`, `mfe`, `outcome_status`, `exclusion_reason`;
- `materialized_at`, `outcome_engine_version`.

Giữ `alert_history` để tương thích UI trong giai đoạn chuyển đổi, nhưng dừng dùng nó làm nguồn dữ liệu huấn luyện sau khi bảng mới ổn định.

## 4. Kế hoạch theo sprint và gói công việc

Ước lượng dùng đơn vị **person-day (PD)**. Một PD là một ngày làm việc tập trung của một kỹ sư.

## Sprint 0 — Đóng băng hiện trạng và làm xanh nền kiểm thử

**Thời gian:** 2–3 ngày, 4–6 PD  
**Mục tiêu:** Có baseline tái lập được trước khi thay đổi logic.

### S0.1 — Snapshot bất biến

- Xuất manifest gồm commit SHA, config đã loại secret, dataset paths/checksum, label version, feature set, model artifact và Python lockfile.
- Chọn một database snapshot read-only làm mốc; không dùng live DB đang tiếp tục ghi.
- Ghi seed, timezone UTC, symbol universe và khoảng thời gian đo.
- Tạo `artifacts/baselines/<baseline_id>/manifest.json`.

**Đầu ra:** manifest + snapshot reference + checksum report.  
**Nghiệm thu:** chạy replay hai lần cho hash prediction và metric giống nhau 100%.

### S0.2 — Baseline report

- Chạy lại heuristic score ≥40, ≥50, rule “giá tăng >5%”, Logistic Regression và LightGBM hiện tại trên cùng snapshot.
- Báo cáo row metrics, event metrics, lead time, regime, coin concentration, alert/ngày, data missing/stale.
- Không dùng số liệu cũ trong bản thông tin làm kết quả chính thức nếu không truy ngược được artifact.

**Đầu ra:** `baseline_report.json` và `baseline_report.md`.  
**Nghiệm thu:** mọi metric trỏ được về dataset/label/model version.

### S0.3 — Ổn định test suite

- Reset/inject ticker cache trong fixture hoặc đưa cache vào object có lifecycle rõ ràng.
- Thêm test ngăn cache fallback che mất lỗi HTTP khi test yêu cầu kết quả rỗng.
- Chuẩn hóa lệnh test có `--basetemp` trong workspace cho Windows.

**Nghiệm thu:** toàn bộ test hiện hữu xanh; không chấp nhận xfail cho 4 lỗi cache.

**Gate G0:** replay deterministic, baseline report bất biến, test suite xanh. Không đạt G0 thì chưa sửa model.

## Sprint 1 — Label contract và event semantics

**Thời gian:** Tuần 1, 7–10 PD  
**Phụ thuộc:** G0.

### S1.1 — Định nghĩa `distribution_short_v1`

- Signal time là close time của nến 5m đã đóng và đã available.
- Tạo ba label spec độc lập: 6h, 12h, 24h.
- Positive khi low chạm -8% trước khi high chạm +4%.
- Quy định intrabar ambiguity: nếu cùng một nến chạm cả hai mức mà không có dữ liệu nhỏ hơn, gắn `ambiguous_intrabar`, không ép thành 0/1.
- Exclude khi thiếu tương lai, gap >15 phút, quality invalid hoặc horizon chưa hoàn tất.

### S1.2 — Event grouping

- Gộp các positive row liên tiếp cùng coin thành một event.
- Chọn quy tắc đóng event: hết chuỗi positive và có ít nhất 60 phút không positive; con số này phải nằm trong label spec, không hard-code rải rác.
- Mỗi event có `event_id`, start, target time, peak drawdown và member rows.
- Khi split, toàn bộ row của cùng `event_id` phải nằm trong một split.

### S1.3 — Test và báo cáo label

- Unit test biên chính xác -8%, +4%, thứ tự target/MAE, thiếu tương lai, gap, ambiguous candle.
- Property test: cùng snapshot/spec cho kết quả giống nhau; thay dữ liệu sau horizon không đổi label.
- Báo cáo prevalence theo horizon, coin, tháng, BTC regime và volatility regime.

**Đầu ra:** label spec JSON/YAML, label table, event table, prevalence/lead-time report.  
**Gate G1:** leakage audit pass; deterministic; P25/median/P75 lead time có đủ; event không bị chia split.

## Sprint 2 — Correctness của live scoring và schema

**Thời gian:** Tuần 2, 8–12 PD  
**Phụ thuộc:** G1.

### S2.1 — Sửa chọn nến và freshness gate

- Với query `DESC LIMIT`, lấy `iloc[0]` hoặc sort tăng dần trước khi lấy `iloc[-1]`; ưu tiên helper `get_latest_feature_snapshot()` có test.
- So sánh `feature_time`, `available_time` và clock UTC hiện tại.
- Chặn prediction nếu nến chưa đóng, age >10 phút, quality invalid hoặc feature bắt buộc quá cũ.

### S2.2 — Tách các loại điểm

- Đổi schema để không còn ánh xạ `heuristic_score / 100 -> probability`.
- Tách raw probability và calibrated probability; chỉ trường calibrated mới được UI gọi là xác suất.
- Thêm migration idempotent và test đọc dữ liệu schema cũ.

### S2.3 — Live inference bằng frozen bundle

- Frozen bundle phải chứa estimator, ordered feature list, imputer/preprocessor, calibrator, thresholds theo horizon, label spec và checksums.
- Scanner load bundle một lần khi start; fail closed nếu thiếu artifact hoặc checksum sai.
- Dùng chính một hàm `score_snapshot()` cho replay, integration test và live.
- Heuristic tiếp tục chạy song song để candidate generation và so sánh, không quyết định probability.

### S2.4 — Threshold policy duy nhất

- Tạo `ThresholdPolicy` với các tier: `WATCH`, `HIGH_CONFIDENCE`, `AVOID`.
- Telegram, API và UI đọc cùng policy/version từ frozen bundle.
- High-confidence cần calibrated probability vượt threshold và ít nhất hai nhóm bằng chứng độc lập.

### S2.5 — Weight và missing semantics

- Truyền weight từ `ScoringConfig` vào scorer; validator kiểm tra tổng weight bằng 1 trong tolerance.
- Missing không được biến thành bằng chứng. Component thiếu dữ liệu có `available=false`, contribution 0 và quality penalty riêng.
- Với model, missing policy nằm trong pipeline đã fit trên train; thêm missing flag nếu được chứng minh qua ablation.

**Đầu ra:** prediction schema, migration, scoring service, threshold policy, freshness/data-quality gate.  
**Gate G2:** cùng snapshot cho replay/live cùng kết quả; test stale/missing/version/threshold pass; không alert khi quality fail.

## Sprint 3 — Pipeline feature point-in-time và data quality

**Thời gian:** Tuần 3–4, 12–18 PD  
**Phụ thuộc:** G2.

### S3.1 — Feature contract

Mỗi feature phải khai báo:

- business meaning, dtype, unit và range;
- lookback và source;
- `feature_available_time`;
- max allowed age;
- missing policy;
- source/feature version;
- point-in-time assertion.

### S3.2 — Hoàn thiện nhóm feature

- Price/volume: return 5m/15m/1h/4h/24h, volatility, volume z-score, volume delta, divergence, distance high nhiều khung, confirmed fake breakout.
- Funding/leverage: raw, z-score, percentile, change 8h/24h, persistence và age.
- OI/positioning: change 1h/4h/24h, acceleration, price/OI divergence, global/top trader ratios và spread.
- Market context: BTC 1h/4h/24h, ETH/BTC, breadth, advance/decline, market volatility/funding.

### S3.3 — Data quality report và gate

- Missing rate theo feature/coin/ngày/source.
- P50/P95 feature age và collector latency.
- Duplicate, gap, outlier và invalid range rate.
- Không forward-fill derivatives vượt max age trong registry.
- Quality score phải giải thích được bằng reason codes.

### S3.4 — Ablation matrix

Chạy tối thiểu:

1. price only;
2. price + volume;
3. price + derivatives;
4. full;
5. full bỏ lần lượt từng nhóm.

Chỉ giữ feature/group nếu cải thiện out-of-sample hoặc có vai trò rõ trong ổn định regime/calibration. Không chọn theo train score.

**Gate G3:** point-in-time audit pass; missing report đầy đủ; feature mới có bằng chứng OOS; không có feature null-heavy lọt vào model vô thức.

## Sprint 4 — Mô hình hai tầng và calibration

**Thời gian:** Tuần 5–6, 12–18 PD  
**Phụ thuộc:** G3.

### S4.1 — Candidate generator

- Mục tiêu recall cao, tạo watchlist chứ không gửi action alert.
- Bắt đầu bằng luật versioned, dễ audit: pump/near-high + momentum suy yếu hoặc derivatives bất thường.
- Đo candidate event recall và reduction ratio. Mục tiêu nội bộ: giữ ≥80% event nhưng giảm đáng kể số row cần model chấm.

### S4.2 — Confirmation model theo horizon

- Baseline bắt buộc: Logistic Regression.
- Challenger: LightGBM.
- Huấn luyện model riêng 6h/12h/24h trước; chỉ dùng multi-output nếu chứng minh tốt và vận hành đơn giản hơn.
- Model selection dựa trên validation folds, không test folds.

### S4.3 — Calibration

- Dành calibration set riêng nằm sau train và trước test, có embargo.
- So sánh Platt và isotonic; chọn theo ECE/Brier và độ ổn định, không chỉ precision.
- Lưu calibrator trong frozen bundle; reliability curve theo horizon/tier/regime.

### S4.4 — Evidence policy

Chuẩn hóa ba nhóm bằng chứng:

1. price/volume weakening;
2. funding/OI/positioning abnormality;
3. sell pressure/fake breakout.

`HIGH_CONFIDENCE` cần ít nhất hai nhóm có reason code hợp lệ và data fresh. Các feature tương quan trong cùng nhóm không được tính như bằng chứng độc lập.

**Gate G4:** PR-AUC vượt mọi baseline; precision tăng ≥20% tương đối; ECE đạt mục tiêu validation; threshold khóa và có version.

## Sprint 5 — Walk-forward và event backtest chuẩn phát hành

**Thời gian:** Tuần 7, 8–12 PD  
**Phụ thuộc:** G4.

### S5.1 — Split chuẩn

- Train -> embargo 24h -> validation -> embargo 24h -> calibration nếu tách riêng -> embargo -> test tương lai.
- Không shuffle.
- Group theo event ID để event không đi qua nhiều split.
- Giữ một final holdout chưa từng dùng cho feature/model/threshold decisions.

### S5.2 — Metric chuẩn

- Row: precision, recall, F1, PR-AUC.
- Event: precision, recall, false alerts/event và duplicate ratio.
- Timing: P25/median/P75 lead time.
- Calibration: Brier, ECE, reliability table/curve.
- Stability: bull/bear/sideways, volatility high/low, từng tháng, top coin vs long tail.
- Trading simulation chỉ là phụ trợ: MFE, MAE, drawdown, fee và slippage.

### S5.3 — Release report bất biến

- Ghi predictions của từng fold thay vì chỉ aggregate metric.
- Bootstrap CI theo event hoặc block thời gian; không bootstrap row độc lập trong cùng event.
- Báo cáo fold tệ nhất và coin concentration.
- So baseline trên chính các test rows giống nhau.

**Gate G5 — Research release:** đạt toàn bộ KPI phát hành. Nếu fail, quay lại S3/S4; không hạ threshold chỉ để tăng alert.

## Sprint 6 — Shadow mode và forward test

**Thời gian:** Tuần 8–10, tối thiểu 2 tuần; kéo dài tới khi đủ event  
**Phụ thuộc:** G5.

### S6.1 — Vận hành shadow

- Model mới score toàn bộ cycle nhưng không gửi Telegram action alert và không thay model cũ.
- Không retrain, không đổi threshold, không đổi feature logic trong cửa sổ đo.
- Ghi prediction, snapshot/checksum, bundle version, latency, quality và outcome.
- Chạy heuristic bên cạnh để so sánh paired performance.

### S6.2 — Giám sát hằng ngày

- Scanner heartbeat, cycle latency, collector failure, stale/missing rate.
- Prediction count và distribution theo horizon/tier.
- Duplicate/cooldown behavior.
- Materialization queue và outcome resolver lag.

### S6.3 — Review hằng tuần

- Precision/recall/event recall đã materialize.
- Brier/ECE và reliability drift.
- Feature/prediction drift so train/reference.
- Regime và coin concentration.
- Incident/data exclusion log.

**Gate G6 — Shadow pass:** ≥50 event (mục tiêu 100), precision gần backtest trong CI, không có drift lớn liên tục, false alert/day trong ngân sách, tốt hơn hoặc ổn định hơn heuristic.

## Sprint 7 — Canary production

**Thời gian:** Tuần 11–12, 6–10 PD  
**Phụ thuộc:** G6.

- Chỉ gửi tier `HIGH_CONFIDENCE`.
- Không tự động vào lệnh.
- Giới hạn alert/coin/ngày và toàn hệ thống/ngày; cooldown dựa trên event/state.
- Fail closed khi data/model/calibrator/threshold version không khớp.
- UI hiển thị calibrated probability, heuristic score, target/horizon, model/label version, data age, historical evidence count và CI nếu có.
- Có `dismiss`, `confirmed`, `missed`, nhưng feedback người dùng không tự động sửa label.
- Giữ kill switch chuyển tức thì về shadow mode.

**Gate G7 — Production pass:** 1–2 tuần không incident nghiêm trọng, KPI không thủng ngưỡng, rollback drill thành công.

## 5. Lịch tuần đề xuất

| Tuần | Trọng tâm | Mốc cuối tuần |
|---:|---|---|
| 0 | Snapshot, baseline, sửa test cache | G0 |
| 1 | Label 6h/12h/24h, event grouping | G1 |
| 2 | Latest candle, schema, frozen inference, threshold | G2 |
| 3 | Feature contracts, freshness/missing | G3 phần 1 |
| 4 | Feature groups và ablation | G3 |
| 5 | Candidate generator + baselines | Model candidates |
| 6 | LightGBM + calibration + evidence policy | G4 |
| 7 | Strict walk-forward, final report | G5 |
| 8–10 | Shadow/forward test | G6 khi đủ sample |
| 11–12 | Canary high-confidence | G7 |

Hai kỹ sư có thể chạy song song data/label và schema/UI trong tuần 1–3. Một kỹ sư nên giữ đúng thứ tự phụ thuộc, không ép lịch 12 tuần bằng cách bỏ gate.

## 6. Phân công vai trò

| Vai trò | Trách nhiệm chính | Tải dự kiến |
|---|---|---:|
| ML/Data engineer | Label, feature, model, calibration, backtest | 55–70 PD |
| Backend/MLOps engineer | Live scoring, schema, shadow, monitoring, rollout | 40–55 PD |
| Reviewer/domain owner | Duyệt label, alert budget, Go/No-Go | 0,5–1 ngày/tuần |

Nếu chỉ một người thực hiện, làm theo thứ tự S0 -> S1 -> S2 -> S3 -> S4 -> S5 -> S6 -> S7 và ước lượng 14–18 tuần.

## 7. Kế hoạch kiểm thử

### Unit tests bắt buộc

- latest candle và candle closed;
- feature freshness, missing, invalid/outlier;
- label boundaries và ambiguous intrabar;
- event grouping;
- weight config và independent evidence count;
- threshold tier/horizon;
- model/calibrator/version mismatch;
- prediction serialization và migration;
- ticker cache isolation.

### Integration tests bắt buộc

- raw snapshot -> normalize -> timeline -> features -> label;
- snapshot -> candidate -> model -> calibrator -> policy -> prediction store;
- cùng snapshot replay/live cho prediction giống nhau;
- outcome materialization cho 6h/12h/24h;
- UI/API/Telegram dùng cùng threshold policy;
- shadow mode không gửi action alert;
- data-quality fail không tạo alert.

### Leakage/reproducibility tests

- feature available time không vượt decision time;
- fit transform chỉ fit trên train;
- threshold/calibrator không dùng test;
- cùng event không nằm ở hai split;
- thay future data ngoài horizon không đổi feature/label;
- frozen bundle + snapshot cho hash prediction giống nhau.

### Lệnh kiểm tra chuẩn

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp pytest-run
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pyright src
```

Sau Sprint 2, thêm smoke command cho replay và live-equivalence; sau Sprint 5, thêm command tạo release report từ một config duy nhất.

## 8. Go/No-Go checklist

Chỉ chuyển giai đoạn khi tất cả ô của gate hiện tại đạt:

- [ ] Test suite xanh.
- [ ] Dataset/label/feature/model/threshold version đầy đủ.
- [ ] Không leakage và replay deterministic.
- [ ] Data quality/freshness đạt ngưỡng.
- [ ] Baseline chạy trên cùng test population.
- [ ] Threshold khóa trước test/shadow.
- [ ] KPI đạt cả aggregate, fold tệ nhất và regime chính.
- [ ] CI đủ tốt, không chỉ point estimate.
- [ ] Không phụ thuộc quá mức vào vài coin.
- [ ] Rollback/kill switch đã thử.
- [ ] Reviewer ký Go; nếu No-Go có ticket quay về sprint tương ứng.

## 9. Rollout và rollback

### Rollout

1. `research`: chạy offline, không live output.
2. `shadow`: live score và lưu, không alert hành động.
3. `canary`: chỉ high-confidence, alert budget thấp.
4. `production_alerting`: mở rộng tier chỉ khi có review riêng.

### Điều kiện rollback ngay về shadow

- stale/invalid data vẫn tạo alert;
- model/calibrator/threshold checksum mismatch;
- prediction latency vượt một scan cycle liên tục;
- false alerts/day vượt 2 lần ngân sách trong 2 ngày;
- precision rolling xuống dưới ngưỡng đã định khi đủ sample;
- ECE hoặc drift vượt ngưỡng cảnh báo hai kỳ liên tiếp;
- schema/outcome resolver mất dữ liệu audit.

Rollback chỉ đổi serving mode/bundle pointer; không xóa prediction đã ghi. Sau rollback, lập incident record và không đổi threshold nóng để che lỗi.

## 10. Monitoring và retraining

### Dashboard hằng ngày

- service health, last successful cycle, latency P50/P95;
- stale/missing/invalid rate theo source;
- predictions và alerts theo horizon/tier;
- duplicate/cooldown/Telegram delivery;
- materialization backlog.

### Dashboard chất lượng model

- rolling precision/event recall/lead time;
- Brier/ECE/reliability;
- feature/prediction drift;
- regime và coin concentration;
- champion vs heuristic/challenger paired results.

### Trigger retrain

- thêm 50–100 event mới; hoặc
- lịch hằng tháng; hoặc
- drift vượt ngưỡng; hoặc
- rolling precision xuống dưới release floor.

Retrain chỉ tạo challenger. Challenger phải đi lại G5 và G6; không tự động promote sau vài prediction sai/đúng.

## 11. Risk register

| Rủi ro | Khả năng/Tác động | Biện pháp |
|---|---|---|
| Event hiếm, shadow kéo dài | Cao/Cao | Dùng nhiều coin và lịch sử hơn nhưng không hạ label; báo thời gian theo sample, không chỉ theo tuần |
| Leakage do as-of join/split | Trung bình/Cao | available-time audit, embargo, event grouping, final holdout |
| Calibration kém khi regime đổi | Cao/Cao | reliability theo regime, recalibration có gate, conservative tier |
| Missing derivatives tạo tín hiệu giả | Cao/Cao | missing flag + quality gate; không fill mặc định thành risk |
| Nhiều feature tương quan | Cao/Trung bình | group evidence, ablation, regularization, importance stability |
| Alert fatigue | Trung bình/Cao | alert budget, cooldown/event state, high-confidence canary |
| Test/production khác pipeline | Trung bình/Cao | dùng chung `score_snapshot()` và frozen preprocessing bundle |
| Model tập trung vào vài coin | Trung bình/Cao | per-coin report, concentration cap, leave-group-out check |
| Live DB thay đổi làm replay không lặp | Cao/Trung bình | immutable snapshot/checksum và append-only prediction audit |

## 12. Backlog ưu tiên theo file/module

### P0 — Chặn sai correctness

1. `src/dao_vang/scanner/daemon.py`: latest-row bug, live frozen inference, freshness gate.
2. `src/dao_vang/alerts/store.py`: schema tách score/probability/quality/version/horizon.
3. `src/dao_vang/scanner/scan_results_store.py`: lưu prediction metadata thay vì chỉ composite score.
4. `src/dao_vang/config/settings.py` và scorer: threshold policy và weight từ config.
5. `src/dao_vang/scanner/watchlist.py` + tests: cô lập/reset ticker cache.

### P1 — Chuẩn hóa research

6. `src/dao_vang/labels/`: label spec đa horizon và event grouping.
7. `src/dao_vang/validation/`: canonical split/metrics/leakage/calibration.
8. `src/dao_vang/experiments/`: bỏ threshold tuning trên test, dùng canonical validation.
9. `src/dao_vang/features/`: metadata freshness/missing/quality và ablation groups.
10. `src/dao_vang/experiments/forward_test.py`: frozen pipeline bundle, không chỉ estimator.

### P2 — Serving và trải nghiệm

11. `src/dao_vang/web/api_server.py`: contract probability/score/tier/version thống nhất.
12. `src/dao_vang/web/app.py`: hiển thị xác suất calibrated và evidence rõ ràng.
13. `src/dao_vang/alerts/telegram.py`: wording không cam kết, thêm horizon/data age/model evidence.
14. Monitoring/reporting: rolling metrics, drift, alert budget, rollback state.

## 13. Việc cần làm trong 72 giờ đầu

### Ngày 1

- Khóa snapshot dữ liệu và config; tạo baseline ID.
- Chạy full test với basetemp trong workspace; sửa ticker cache isolation.
- Xác nhận DB dùng cho research khác DB live.
- Chốt owner duyệt label contract.

### Ngày 2

- Tạo baseline replay command và manifest/checksum.
- Xuất heuristic/model/baseline predictions trên cùng snapshot.
- Viết label spec `distribution_short_v1` cho 6h/12h/24h.
- Lập danh sách schema migration và backward compatibility.

### Ngày 3

- Review baseline report và prevalence.
- Chốt event grouping, intrabar ambiguity và alert budget.
- Chuyển các mục S1/S2 thành issue nhỏ 0,5–2 PD, có acceptance test.
- Chỉ bắt đầu code Sprint 1 sau khi G0 đạt.

## 14. Definition of Done cuối cùng

Kế hoạch hoàn tất khi:

1. Một command có thể tái tạo release report từ snapshot + config + frozen bundle.
2. Live và replay dùng cùng scoring pipeline và cho cùng kết quả.
3. Mọi prediction được audit đầy đủ, không gọi heuristic là probability.
4. Label/event/split không leakage và có version.
5. Model vượt baseline, calibration đạt ngưỡng và ổn định theo regime.
6. Shadow đủ sample và đạt G6.
7. Canary có kill switch, alert budget và rollback đã thử.
8. Không có tự động vào lệnh; UI/Telegram mô tả xác suất và giới hạn rõ ràng.

Nếu bất kỳ điều kiện 1–7 nào chưa đạt, trạng thái đúng của hệ thống là `research` hoặc `shadow`, không phải “dự báo sớm đáng tin cậy ở production”.
