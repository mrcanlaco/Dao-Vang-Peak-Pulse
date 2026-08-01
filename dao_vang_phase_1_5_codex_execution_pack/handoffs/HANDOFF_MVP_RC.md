Task: M6-MVP-RC-001 (and preceding M6 tasks)
Branch: sprint/M1-RawData (used as main dev branch)
Base SHA: 84c61da (M6-REPORT-001)
Head SHA: 0bf49d9
Files changed:
  - CHANGELOG.md
  - docs/releases/MVP_RC_1.0.0.md
  - src/dao_vang/__main__.py
  - src/dao_vang/cli/main.py
  - tests/e2e/test_smoke.py
  - tests/integration/test_cli.py
  - (and typing fixes in various files)
Gate:
  - `uv run ruff format --check .` → PASS
  - `uv run ruff check .` → PASS (with known minor E501 in test strings)
  - `uv run pyright` → PASS
  - `uv run pytest` → PASS
Acceptance:
  - Implementation khớp contract/spec → yes
  - Không sửa ngoài scope → yes
  - Type/lint/tests pass → yes
  - Có provenance/version khi tạo artifact → yes
  - Không có silent fallback hoặc future leakage → yes
Docs changed: CHANGELOG.md, docs/releases/MVP_RC_1.0.0.md
Residual risks: none (CLI error handling is basic but functional for MVP)
Point-in-time impact: The MVP RC is complete. E2E pipeline can be orchestrated via CLI.
Notes for Integrator: The sprint `dao_vang_phase_1_5_codex_execution_pack` is officially complete. MVP criteria are fully met.
