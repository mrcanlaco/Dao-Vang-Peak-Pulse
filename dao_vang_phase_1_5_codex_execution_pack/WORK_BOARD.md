# ACTIVE WORK BOARD

## Sprint M0 — Foundation

Goal: Dựng repository Python có quality gates và module boundaries theo Documentation v1.0.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M0-FOUND-001 | Scaffold Python project | Codex-Integrator | ready | root, pyproject, src/tests skeleton | full | - | 651d17453a7ae9f6287cd9ca86594015ff176af3 |
| M0-DOMAIN-001 | Domain types/errors | Codex-Agent-A | waiting | src/dao_vang/domain/*, tests/unit/domain/* | unit+type | M0-FOUND-001 | - |
| M0-CONFIG-001 | Typed config | Codex-Agent-B | waiting | src/dao_vang/config/*, tests/unit/config/* | unit+type | M0-FOUND-001 | - |
| M0-LOG-001 | Structured logging | Codex-Agent-C | waiting | src/dao_vang/logging/*, tests/unit/logging/* | unit | M0-FOUND-001 | - |
| M0-CI-001 | CI workflow | Codex-Agent-D | waiting | .github/workflows/* | CI | M0-FOUND-001 | - |
| M0-CLI-001 | CLI skeleton | Codex-Agent-A | waiting | src/dao_vang/cli/*, tests/unit/cli/* | unit | M0-CONFIG-001 | - |

## Ownership rule

Mỗi file chỉ một owner trong cùng wave.

## Status values

`waiting`, `ready`, `in_progress`, `ready_for_review`, `changes_requested`, `merged`, `blocked`.
