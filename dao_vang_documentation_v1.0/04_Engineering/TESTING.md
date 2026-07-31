# TESTING STRATEGY

## Layers

- Unit.
- Integration.
- Contract.
- Leakage.
- Regression.
- Smoke.

## Nguyên tắc

- Test behavior, không test implementation detail vô ích.
- Fixture nhỏ và deterministic.
- Golden files có version.
- External API contract tests tách khỏi unit.
- Network bị mock trong unit.
- Leakage tests là release blocker.
- Bug fix phải có regression test.

## Gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```
