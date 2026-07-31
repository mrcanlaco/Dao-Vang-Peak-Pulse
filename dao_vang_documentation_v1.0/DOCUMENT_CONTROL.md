# DOCUMENT CONTROL

## Version hiện hành

```yaml
documentation_version: 1.0.0
status: approved_baseline
effective_date: 2026-07-31
owner: project_owner
```

## Quy tắc thay đổi

- Sửa lỗi chính tả, làm rõ câu không đổi semantic: patch.
- Thêm quy tắc tương thích ngược: minor.
- Đổi label, schema semantic, time alignment hoặc kiến trúc: major.
- Không sửa âm thầm tài liệu đã dùng để tạo dataset/experiment.
- Mọi thay đổi semantic phải có ADR hoặc decision log.
- Code và config phải ghi version tài liệu liên quan.

## Trạng thái tài liệu

- `draft`
- `experimental`
- `approved`
- `deprecated`
- `retired`

## Review bắt buộc

Các tài liệu sau phải được chủ dự án phê duyệt khi đổi semantic:

- Constitution
- MVP Scope
- Label Spec
- Data Schema
- Time Alignment
- Validation Protocol
- Architecture
- Agent Guardrails
