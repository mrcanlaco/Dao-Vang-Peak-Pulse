# COLLECTION POLICY

## Nguyên tắc

- Idempotent.
- Raw write trước normalize.
- Explicit time ranges.
- Retry có giới hạn.
- Respect rate limits.
- Không fallback âm thầm.
- Ghi collection run metadata.

## Chế độ

### Backfill
Tải dữ liệu lịch sử trong khả năng endpoint, chia window nhỏ, có checkpoint.

### Incremental
Bắt đầu từ watermark kế tiếp, overlap một period để chống mất dữ liệu rồi deduplicate.

### Forward snapshot
Chạy định kỳ để tích lũy endpoint có lịch sử ngắn.

## Failure policy

- HTTP 429/5xx: retry exponential backoff.
- 4xx semantic: fail task, không retry vô hạn.
- Schema drift: quarantine.
- Empty response trong kỳ vọng: warning hoặc fail theo config.
- Clock drift lớn: fail closed.
