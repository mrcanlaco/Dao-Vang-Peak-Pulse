# CODEX OPERATING RULES

## Vai trò của Codex

Codex là implementation engine, không phải chủ sở hữu phương pháp luận.

Codex được phép:

- scaffold repository;
- viết collector, parser, storage, quality checks;
- viết label/feature theo specification;
- viết baseline, validation, report;
- viết tests, CI, docs kỹ thuật liên quan implementation;
- refactor trong scope đã giao.

Codex không được:

- tự đổi Constitution;
- tự đổi MVP scope;
- tự đổi Label v0.1;
- tự đổi endpoint hoặc source semantic;
- tự đổi available_time rule;
- tự thêm AI, dashboard, MCP, auto trade;
- tự thêm dữ liệu ngoài MVP;
- tự merge;
- tự bỏ qua test/gate;
- tự sửa file ngoài scope.

## Cách chia phiên Codex

- 1 Integrator session.
- 1 Contract/Domain session.
- 1–2 Implementation sessions.
- 1 QA session.
- Không cần nhiều hơn 4 agent đồng thời trong dự án một người.

## Kích thước task

Task lý tưởng:

- 1 mục tiêu;
- 1–5 file production;
- 1–3 file test;
- tối đa khoảng 300–600 dòng thay đổi;
- hoàn thành trong một context tương đối độc lập.

Nếu task vượt mức này, Integrator phải tách.

## Human stop

Bắt buộc dừng để chủ dự án duyệt khi:

- đổi schema semantic;
- đổi label;
- đổi source;
- thêm dependency kiến trúc;
- data migration phá tương thích;
- release;
- production scheduling;
- secret/API key;
- kết luận research edge.
