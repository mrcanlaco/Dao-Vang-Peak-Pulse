Task: M0-FOUND-001
Branch: task/M0-FOUND-001
Base SHA: abc123
Head SHA: def456
Files changed:
  - pyproject.toml
  - src/dao_vang/__init__.py
Gate:
  - uv run ruff check . → PASS
  - uv run pytest → PASS
Acceptance: yes
Docs changed: none
Residual risks: none
Point-in-time impact: none
