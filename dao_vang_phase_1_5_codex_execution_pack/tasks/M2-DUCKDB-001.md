# M2-DUCKDB-001 — DuckDB layer

## Goal
Query partitions theo time range.

## Required Reading
- 00_Governance/CONSTITUTION.md
- 01_Product/MVP_SCOPE.md
- 04_Engineering/ARCHITECTURE.md
- 04_Engineering/CODING_STANDARD.md
- 04_Engineering/TESTING.md
- 05_AI/AGENTS.md
- 02_Data/STORAGE.md

## Dependencies
-

## Allowed Files
- `src/dao_vang/data/query/**`
- `tests/unit/data/query/**`

## Forbidden Files
- `00_Governance/**`
- `01_Product/MVP_SCOPE.md`
- `03_Research/LABEL_SPEC.md (trừ task label nếu được phép)`

## Implementation Requirements
- Tối thiểu hóa abstraction.
- Dùng fixture nhỏ, không phụ thuộc network trong unit test.

## Acceptance Criteria
- Implementation khớp contract/spec
- Không sửa ngoài scope
- Type/lint/tests pass
- Có provenance/version khi tạo artifact
- Không có silent fallback hoặc future leakage

## Required Tests
- Happy path
- Boundary/invalid input
- Deterministic behavior
- Leakage/idempotency test nếu áp dụng

## Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

## Handoff
Dùng `templates/HANDOFF_TEMPLATE.md`. Không merge và không push sau handoff.
