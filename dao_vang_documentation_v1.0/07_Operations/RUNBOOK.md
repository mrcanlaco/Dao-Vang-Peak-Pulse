# RUNBOOK

## Collector fail

1. Kiểm tra HTTP/status/rate limit.
2. Không sửa watermark thành công.
3. Retry theo policy.
4. Nếu schema drift: quarantine và dừng parser.

## Gap dữ liệu

1. Xác định nguồn và thời gian.
2. Thử backfill nếu endpoint cho phép.
3. Nếu không: ghi metadata, không nội suy.
4. Rebuild dataset version nếu input đổi.

## Leakage test fail

Dừng release. Đánh dấu experiment affected là invalidated.
