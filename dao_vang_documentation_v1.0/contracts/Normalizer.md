# CONTRACT — Normalizer

## Responsibility
Thực hiện đúng một vai trò theo Architecture.

## Input
Raw envelope

## Output
Typed normalized records

## Side Effects
Normalized writes

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
