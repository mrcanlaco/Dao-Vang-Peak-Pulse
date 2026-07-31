# ĐẢO VÀNG — PHASE 1.5 CODEX EXECUTION PACK

Gói điều phối để chuyển Documentation v1.0 thành repository và MVP bằng Codex.

## Mục tiêu

- Chia toàn bộ Phase 2 thành task nhỏ, kiểm soát được.
- Giữ Codex trong phạm vi tài liệu đã chốt.
- Cho phép một người vận hành qua Integrator + task agents.
- Mỗi task có scope, dependency, acceptance, gate và handoff rõ.
- Không để Codex tự thay đổi label, schema, time alignment hoặc kiến trúc.

## Thành phần

- `MASTER_BACKLOG.md`: toàn bộ backlog MVP.
- `SPRINT_PLAN.md`: các sprint và wave.
- `WORK_BOARD.md`: board khởi tạo sẵn.
- `DISPATCH_SHEETS.md`: prompt gửi từng agent.
- `ACCEPTANCE_TEST_MATRIX.md`: ma trận kiểm thử.
- `INTEGRATOR_PROMPT.md`: prompt điều phối chính.
- `CODEX_OPERATING_RULES.md`: nguyên tắc dùng Codex.
- `tasks/`: đặc tả chi tiết từng task.
- `templates/`: handoff, review, changes requested, merge report.
- `phase3/`: checklist cập nhật Documentation v1.1.

## Cách dùng

1. Giải nén Documentation v1.0 vào repo.
2. Giải nén gói này vào cùng repo dưới `docs/active/`.
3. Mở Codex Integrator tại root repo.
4. Gửi nội dung `INTEGRATOR_PROMPT.md`.
5. Integrator cập nhật Base SHA và dispatch Wave 1.
6. Mỗi agent chỉ nhận `Nhận <TASK-ID>.`
7. Sau mỗi sprint, chạy Phase 3 documentation sync checklist.

## Nguyên tắc

Không chạy toàn bộ backlog trong một prompt duy nhất.
