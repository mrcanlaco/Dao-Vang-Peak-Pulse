# AI AGENT ENTRYPOINT — ĐẢO VÀNG

## 1. Nhiệm vụ

Xây dựng Đảo Vàng theo `docs/constitution/CONSTITUTION.md`.

Mục tiêu duy nhất của MVP là kiểm tra liệu dữ liệu tối thiểu có tạo lợi thế thống kê trong phát hiện Distribution hay không.

## 2. Thứ tự ưu tiên tài liệu

1. `docs/constitution/CONSTITUTION.md`
2. `docs/product/MVP_SCOPE.md`
3. `docs/specifications/LABEL_SPECIFICATION.md`
4. `docs/specifications/DATA_SOURCE_SPECIFICATION.md`
5. `docs/specifications/DATA_SCHEMA.md`
6. `docs/specifications/TIME_ALIGNMENT_SPEC.md`
7. `docs/engineering/ARCHITECTURE.md`
8. File task/WORK_BOARD hiện hành
9. Code hiện hành

Nếu code trái tài liệu, không tự sửa specification để hợp code. Báo Integrator.

## 3. Cách nhận việc

Khi nhận `Nhận <TASK-ID>.`:

1. Đọc file này.
2. Đọc `docs/active/WORK_BOARD.md`.
3. Tìm đúng task ID.
4. Đọc toàn bộ Required Reading của task.
5. Tạo branch `task/<TASK-ID>` từ Base SHA.
6. Chỉ sửa file trong Scope.
7. Chạy Gate.
8. Push branch.
9. Bàn giao bằng template.
10. Không tự merge và không push sau bàn giao.

## 4. Guardrails bắt buộc

- Không tự thêm tính năng ngoài MVP scope.
- Không thêm AI, LLM, LangGraph, agent runtime, MCP, dashboard hoặc auto trade.
- Không đổi schema, label semantic hoặc availability rule nếu task không cho phép.
- Không dùng random train/test split.
- Không dùng dữ liệu tương lai.
- Không dùng nến chưa đóng.
- Không dùng nearest join hai phía.
- Không fit scaler trên toàn dataset.
- Không hard-code secrets.
- Không sửa raw data.
- Không fallback nguồn âm thầm.
- Không tạo `utils.py` tổng hợp.
- Không đặt business logic trong notebook hoặc CLI.
- Mọi public function có type hints.
- Mọi feature/label mới có unit test và leakage test.
- Mọi lỗi point-in-time phải fail closed.

## 5. Quy tắc phạm vi

Mỗi file chỉ có một owner trong một wave.

Nếu cần sửa ngoài scope:

1. dừng;
2. ghi rõ file cần sửa và lý do;
3. báo Integrator;
4. không tự mở rộng task.

## 6. Quy tắc thay đổi tài liệu

Thay đổi các nội dung sau cần phê duyệt:

- Label threshold/horizon;
- source endpoint;
- schema semantic;
- available_time rule;
- architecture boundary;
- dependency lớn;
- storage format;
- production/release.

Thay đổi phải tạo version hoặc ADR phù hợp.

## 7. Gate mặc định

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Task có thể quy định gate hẹp hơn, nhưng final integration phải chạy toàn bộ.

## 8. Test bắt buộc theo loại task

### Collector

- contract test;
- pagination;
- retry;
- idempotency;
- raw-before-normalize.

### Alignment

- backward-only as-of;
- available_time enforcement;
- future insertion invariance.

### Label

- edge cases;
- missing future;
- ambiguous intrabar;
- deterministic output.

### Feature

- formula;
- minimum lookback;
- missing policy;
- future data invariance.

### Validation

- chronological split;
- no overlap;
- train-only fitting;
- deterministic seed.

## 9. Khi nào phải dừng

- yêu cầu mơ hồ ảnh hưởng semantic;
- task cần đổi scope;
- phát hiện tài liệu mâu thuẫn;
- chạm production data;
- chạm secret/trade permission;
- cần migration phá tương thích;
- test leakage fail;
- source schema thay đổi.

## 10. Handoff template

```text
Task: <TASK-ID>
Branch: task/<TASK-ID>
Base SHA: <sha>
Head SHA: <sha>
Files changed:
  - ...
Gate:
  - <command> → PASS/FAIL
Acceptance: yes/no
Docs changed: none/list
Residual risks: none/list
Point-in-time impact: none/description
```

## 11. Multi-agent workflow

Tuân thủ:

- không tự nhận việc;
- không tự merge;
- không đánh dấu done;
- branch đóng băng sau handoff;
- mỗi file một owner;
- Integrator review diff, gate, acceptance;
- Boss phê duyệt release.

## 12. Definition of good change

Một thay đổi tốt:

- nhỏ;
- đúng một mục tiêu;
- có test;
- deterministic;
- point-in-time correct;
- dễ rollback;
- không tăng complexity nếu không cần;
- cập nhật tài liệu khi semantic thay đổi.
