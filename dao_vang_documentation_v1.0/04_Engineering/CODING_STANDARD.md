# CODING STANDARD

- Python 3.12.
- Type hints bắt buộc cho public APIs.
- Pydantic v2 cho config/schema boundaries.
- Dataclass/frozen model cho domain khi phù hợp.
- UTC-aware datetime.
- Không bare except.
- Không `print` trong core.
- Logging structured.
- Pure functions cho label/feature.
- Decimal tại boundary tài chính, float64 cho analytics có kiểm soát.
- Docstring cho public APIs và invariant khó.
- Ruff format/lint.
- Pyright strict dần theo module.
- Không premature abstraction.
