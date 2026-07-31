# REPOSITORY STRUCTURE

```text
src/dao_vang/
  domain/
  data/
  labels/
  features/
  baselines/
  validation/
  experiments/
  reports/
  cli/
tests/
  unit/
  integration/
  contracts/
  leakage/
  regression/
configs/
docs/
```

## Quy tắc

- Một file một trách nhiệm.
- Tránh file > 400 dòng nếu không có lý do.
- Không `utils.py` đa mục đích.
- Public interface rõ.
- Config ngoài code.
- Notebook chỉ exploratory.
- Dependency đi một chiều theo Architecture.
