# CONTRACT — Experiment Runner

## Responsibility
Thực hiện đúng một vai trò theo Architecture.

## Input
Experiment config

## Output
Predictions, metrics, report artifacts

## Side Effects
Artifact registry

## Invariants
- Deterministic với cùng input/config.
- Version và provenance đầy đủ.
- Không vượt module boundary.
- Không dùng dữ liệu tương lai.
- Fail closed khi integrity vi phạm.

## Errors
Dùng taxonomy trong `04_Engineering/ERROR_HANDLING.md`.

## Tests
- happy path;
- invalid input;
- boundary;
- idempotency nếu có IO;
- point-in-time/leakage khi áp dụng.
