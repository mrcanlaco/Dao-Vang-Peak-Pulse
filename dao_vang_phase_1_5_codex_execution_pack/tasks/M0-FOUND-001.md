# M0-FOUND-001 — Scaffold Python project

## Goal
Tạo skeleton repository Python 3.12 dùng uv, src layout, pytest, Ruff và Pyright.

## Required Reading
- 00_Governance/CONSTITUTION.md
- 01_Product/MVP_SCOPE.md
- 04_Engineering/ARCHITECTURE.md
- 04_Engineering/CODING_STANDARD.md
- 04_Engineering/TESTING.md
- 05_AI/AGENTS.md
- 04_Engineering/REPOSITORY.md
- 04_Engineering/DEPENDENCIES.md

## Dependencies
-

## Allowed Files
- `pyproject.toml`
- `README.md`
- `src/dao_vang/__init__.py`
- `tests/__init__.py`
- `.gitignore`

## Forbidden Files
- `00_Governance/**`
- `01_Product/**`
- `02_Data/**`
- `03_Research/**`

## Implementation Requirements
- Dùng package metadata tối thiểu.
- Không tạo business modules giả.
- Tạo test placeholder có giá trị, không test `assert True`.

## Acceptance Criteria
- `uv sync` thành công
- import `dao_vang` thành công
- Ruff/Pyright/Pytest chạy được
- Không thêm dependency ngoài approved list

## Required Tests
- smoke import test
- pytest discovers tests

## Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

## Handoff
Dùng `templates/HANDOFF_TEMPLATE.md`. Không merge và không push sau handoff.
