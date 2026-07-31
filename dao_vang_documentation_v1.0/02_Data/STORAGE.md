# STORAGE

## Lựa chọn MVP

- Raw: JSONL gzip hoặc Parquet chứa raw envelope.
- Normalized: Parquet.
- Query: DuckDB.
- Metadata/artifacts: JSON/YAML/Parquet.
- Không cần database server.

## Layout

```text
data/
├── raw/{data_type}/date=YYYY-MM-DD/
├── normalized/{data_type}/interval=5m/date=YYYY-MM-DD/
├── aligned/dataset_version=.../
├── features/feature_set_version=.../
├── metadata/
└── artifacts/experiment_id=.../
```

## Quy tắc

- Atomic write qua temp file rồi rename.
- File có checksum.
- Không mutate partition cũ; tạo snapshot/version mới.
- Dataset manifest liệt kê input hashes.
- Không commit market data vào Git.
- Backup manifest và config cùng artifact.
