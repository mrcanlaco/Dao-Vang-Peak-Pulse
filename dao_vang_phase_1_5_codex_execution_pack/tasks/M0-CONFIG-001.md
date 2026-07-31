# M0-CONFIG-001 — Typed configuration system

## Goal
Tạo Pydantic config cho paths, Binance source, lags và collection policy.

## Required Reading
- 00_Governance/CONSTITUTION.md
- 01_Product/MVP_SCOPE.md
- 04_Engineering/ARCHITECTURE.md
- 04_Engineering/CODING_STANDARD.md
- 04_Engineering/TESTING.md
- 05_AI/AGENTS.md
- 02_Data/DATA_SOURCE_SPEC.md
- 02_Data/TIME_ALIGNMENT.md

## Dependencies
M0-FOUND-001

## Allowed Files
- `src/dao_vang/config/**`
- `tests/unit/config/**`
- `configs/*.example.yaml`

## Forbidden Files
- `src/dao_vang/data/**`
- `03_Research/LABEL_SPEC.md`

## Implementation Requirements
- Thực hiện tối thiểu, rõ ràng, typed và deterministic.

## Acceptance Criteria
- Config load từ YAML/env
- Defaults khớp docs
- Validation từ chối interval/source sai
- Không chứa secret trade key

## Required Tests
- valid config
- invalid lag
- invalid interval
- env override

## Gate
```bash
uv run ruff check src/dao_vang/config tests/unit/config
uv run pyright
uv run pytest tests/unit/config
```

## Handoff
Dùng `templates/HANDOFF_TEMPLATE.md`. Không merge và không push sau handoff.
