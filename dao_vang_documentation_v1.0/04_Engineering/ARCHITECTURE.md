---
document_id: DAO_VANG_ARCHITECTURE
version: 1.0.0
status: approved_for_mvp
architecture_style: modular_monolith
---

# KIẾN TRÚC ĐẢO VÀNG MVP

## 1. Nguyên tắc

- Modular monolith.
- Batch-first.
- Local-first.
- Deterministic.
- Point-in-time correct.
- Không LLM trong predictive pipeline.
- Không microservices trong MVP.
- Mỗi module có một trách nhiệm.
- Raw immutable, derived versioned.

## 2. Luồng hệ thống

```text
Binance REST
    ↓
Collector
    ↓
Raw Store
    ↓
Normalizer
    ↓
Quality Validator
    ↓
Time Aligner
    ↓
Dataset Builder
    ├── Label Engine
    └── Feature Engine
           ↓
Experiment Runner
           ↓
Validation / Walk-Forward
           ↓
Artifact Registry / Reports
```

## 3. Module boundaries

### `domain`

Chứa types, enums và business invariants. Không phụ thuộc IO, pandas hoặc API.

### `data.collectors`

Gọi Binance, pagination, retry, rate-limit và ghi raw envelope.

Không:

- tạo feature;
- gắn label;
- diễn giải dữ liệu.

### `data.normalization`

Chuyển raw response sang schema typed.

Không sửa raw và không tự repair dữ liệu.

### `data.quality`

Chạy quality checks, phát flags và report.

Không âm thầm xóa anomaly.

### `data.storage`

Quản lý Parquet, DuckDB, manifests và hashes.

### `data.alignment`

Tạo canonical timeline, exact/as-of joins, watermark và availability enforcement.

### `labels`

Tạo label từ price data theo Label Specification.

Không được import feature modules.

### `features`

Pure functions tạo feature từ aligned point-in-time data.

Không được đọc label columns.

### `baselines`

Quy tắc baseline và model đơn giản.

### `validation`

Time split, walk-forward, metrics, bootstrap, calibration và leakage checks.

### `experiments`

Điều phối config → dataset → model → validation → artifact.

### `reports`

Sinh Markdown/JSON/CSV/HTML report từ artifact, không tự tính lại logic core.

### `cli`

Typer commands mỏng, gọi application services.

## 4. Cấu trúc repo

```text
dao-vang/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── configs/
│   ├── data/
│   ├── labels/
│   ├── features/
│   └── experiments/
├── docs/
├── src/dao_vang/
│   ├── domain/
│   ├── data/
│   │   ├── collectors/
│   │   ├── normalization/
│   │   ├── quality/
│   │   ├── storage/
│   │   └── alignment/
│   ├── labels/
│   ├── features/
│   ├── baselines/
│   ├── validation/
│   ├── experiments/
│   ├── reports/
│   └── cli/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── leakage/
│   └── regression/
└── data/
    ├── raw/
    ├── normalized/
    ├── aligned/
    ├── features/
    └── artifacts/
```

## 5. Technology decisions

```yaml
python: "3.12"
package_manager: uv
dataframes: pandas_initially
columnar_storage: parquet_pyarrow
query_engine: duckdb
validation_models: pydantic_v2
http_client: httpx
retry: tenacity
cli: typer
logging: structlog_or_stdlib_json
testing: pytest
lint_format: ruff
type_check: pyright
```

Polars chỉ thêm bằng ADR nếu pandas trở thành bottleneck đo được.

## 6. Dependency direction

```text
cli → experiments → domain + data + labels + features + validation
reports → artifact models
features → domain
labels → domain
data modules → domain
domain → standard library only
```

Cấm circular dependency.

## 7. Artifact model

Mỗi experiment tạo:

```text
artifacts/{experiment_id}/
├── config.snapshot.yaml
├── environment.json
├── dataset.manifest.json
├── metrics.json
├── predictions.parquet
├── splits.json
├── report.md
└── logs.jsonl
```

Bắt buộc ghi:

- git commit;
- dirty working tree flag;
- Python/dependency versions;
- random seed;
- dataset fingerprint;
- label/feature/model versions.

## 8. CLI dự kiến

```text
dao-vang data collect
dao-vang data normalize
dao-vang data validate
dao-vang data align
dao-vang labels build
dao-vang features build
dao-vang experiment run
dao-vang experiment compare
dao-vang report build
```

## 9. Error taxonomy

- `ConfigurationError`
- `SourceAPIError`
- `RateLimitError`
- `SchemaError`
- `DataQualityError`
- `InsufficientDataError`
- `PointInTimeViolation`
- `LeakageDetected`
- `ArtifactIntegrityError`

Không dùng bare `except`. Retry chỉ cho lỗi retryable.

## 10. Security

- Public data only trong MVP.
- Không trade key.
- Không auto execution.
- Không log secrets.
- Network chỉ ở collector layer.
- Generated code execution không nằm trong MVP.

## 11. Non-functional requirements

- Idempotent collection.
- Reproducible build.
- Incremental processing.
- Auditability.
- Fail closed khi vi phạm point-in-time.
- Có thể chạy laptop cá nhân.
- Một người bảo trì được.

## 12. Điều kiện thêm layer mới

MCP, dashboard, agent hoặc cloud chỉ được thêm khi core pipeline ổn định và ADR được phê duyệt.
