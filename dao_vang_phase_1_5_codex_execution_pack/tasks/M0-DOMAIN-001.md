# M0-DOMAIN-001 — Core domain types and errors

## Goal
Tạo enums, value objects và error taxonomy dùng chung.

## Required Reading
- 00_Governance/CONSTITUTION.md
- 01_Product/MVP_SCOPE.md
- 04_Engineering/ARCHITECTURE.md
- 04_Engineering/CODING_STANDARD.md
- 04_Engineering/TESTING.md
- 05_AI/AGENTS.md
- 04_Engineering/ERROR_HANDLING.md
- 02_Data/DATA_SCHEMA.md

## Dependencies
M0-FOUND-001

## Allowed Files
- `src/dao_vang/domain/**`
- `tests/unit/domain/**`

## Forbidden Files
- `src/dao_vang/data/**`
- `src/dao_vang/labels/**`
- `src/dao_vang/features/**`

## Implementation Requirements
- Thực hiện tối thiểu, rõ ràng, typed và deterministic.

## Acceptance Criteria
- Có QualityStatus và run status enums
- Có exception taxonomy
- Datetime invariant UTC được kiểm tra
- Domain không phụ thuộc pandas/httpx

## Required Tests
- enum values
- exception inheritance
- UTC validation

## Gate
```bash
uv run ruff check src/dao_vang/domain tests/unit/domain
uv run pyright
uv run pytest tests/unit/domain
```

## Handoff
Dùng `templates/HANDOFF_TEMPLATE.md`. Không merge và không push sau handoff.
