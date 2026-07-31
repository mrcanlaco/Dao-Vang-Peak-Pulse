# PERFORMANCE

## Ưu tiên

Correctness > reproducibility > maintainability > performance.

## Targets MVP

- Chạy trên laptop cá nhân.
- Incremental collector không tải lại toàn bộ.
- Parquet partition pruning.
- DuckDB query theo time range.
- Feature vectorization hợp lý.
- Không tối ưu trước khi đo.

## Profiling gate

Chỉ thay pandas/pipeline khi benchmark chứng minh bottleneck và có ADR.
