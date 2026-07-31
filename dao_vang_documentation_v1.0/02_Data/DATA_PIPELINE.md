# DATA PIPELINE

```text
Request Plan
→ Fetch
→ Raw Persist
→ Normalize
→ Contract Validate
→ Quality Check
→ Partition Persist
→ Watermark Update
→ Align
→ Dataset Manifest
```

## Invariants

- Fetch không tạo feature.
- Normalize không quyết định business meaning ngoài mapping đã spec.
- Quality không xóa raw.
- Align chỉ dùng available_time hợp lệ.
- Manifest được ghi sau khi toàn bộ output thành công.
- Partial run không được đánh dấu succeeded.

## Re-run

Mọi bước phải có thể chạy lại mà không tạo duplicate logic.
