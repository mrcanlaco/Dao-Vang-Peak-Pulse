# ACTIVE WORK BOARD

## Sprint M0 — Foundation

Goal: Dựng repository Python có quality gates và module boundaries theo Documentation v1.0.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M0-FOUND-001 | Scaffold Python project | Codex-Integrator | merged | root, pyproject, src/tests skeleton | full | - | 651d174 |
| M0-DOMAIN-001 | Domain types/errors | Codex-Agent-A | merged | src/dao_vang/domain/*, tests/unit/domain/* | unit+type | M0-FOUND-001 | e2c3058 |
| M0-CONFIG-001 | Typed config | Codex-Agent-B | merged | src/dao_vang/config/*, tests/unit/config/* | unit+type | M0-FOUND-001 | 29deab1 |
| M0-LOG-001 | Structured logging | Codex-Agent-C | merged | src/dao_vang/logging/*, tests/unit/logging/* | unit | M0-FOUND-001 | f3fd9a7 |
| M0-CI-001 | CI workflow | Codex-Agent-D | merged | .github/workflows/* | CI | M0-FOUND-001 | 5b24b42 |
| M0-CLI-001 | CLI skeleton | Codex-Agent-A | merged | src/dao_vang/cli/*, tests/unit/cli/* | unit | M0-CONFIG-001 | ddedb7d |

## Sprint M1 — Raw Data

Goal: Xây dựng layer collection cho Binance USD-M, raw storage atomic, checksum, path policy.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M1-STORAGE-001 | Atomic storage/checksum | Codex-Integrator | merged | src/dao_vang/data/storage/* | unit | M0-DOMAIN-001 | 77d4baf |
| M1-BINANCE-001 | Binance HTTP client | Codex-Integrator | merged | src/dao_vang/data/collectors/binance_client.py | unit | M0-CONFIG-001 | 77d4baf |
| M1-MANIFEST-001 | Manifest models | Codex-Integrator | merged | src/dao_vang/data/manifest.py | unit | M1-STORAGE-001 | 9ef2c0f |
| M1-KLINES-001 | Klines collector | Codex-Integrator | merged | src/dao_vang/data/collectors/klines.py | unit | M1-BINANCE-001 | e7da9b0 |
| M1-FUNDING-001 | Funding collector | Codex-Integrator | merged | src/dao_vang/data/collectors/funding.py | unit | M1-BINANCE-001 | 5045288 |
| M1-OI-001 | Open interest collector | Codex-Integrator | merged | src/dao_vang/data/collectors/open_interest.py | unit | M1-BINANCE-001 | 0da2203 |
| M1-TAKER-001 | Taker ratio collector | Codex-Integrator | merged | src/dao_vang/data/collectors/taker.py | unit | M1-BINANCE-001 | 669f9ee |
| M1-RATIOS-001 | Global/top trader ratio collectors | Codex-Integrator | merged | src/dao_vang/data/collectors/ratios.py | unit | M1-BINANCE-001 | 92adb94 |

## Sprint M2 — Normalize, Quality and Alignment

Goal: Normalize raw JSON to typed models, apply quality filters, and store as canonical dataset.

| ID | Task | Owner | Status | Scope | Gate | Depends | Base SHA |
|---|---|---|---|---|---|---|---|
| M2-SCHEMA-001 | Pydantic normalized schemas | Codex-Integrator | merged | src/dao_vang/data/schemas.py | unit | M0-DOMAIN-001 | cb92482 |
| M2-NORM-001 | Normalizers for all MVP data | Codex-Integrator | merged | src/dao_vang/data/normalization/normalizers.py | unit | M2-SCHEMA-001 | 6a92dd4 |
| M2-QUALITY-001 | Data quality engine | Codex-Integrator | merged | src/dao_vang/data/quality.py | unit | M2-NORM-001 | 6038bc5 |
| M2-PARQUET-001 | Normalized Parquet writer | Codex-Integrator | ready | src/dao_vang/data/storage/parquet.py | unit | M2-NORM-001, M1-STORAGE-001 | 6038bc5 |

## Ownership rule

Mỗi file chỉ một owner trong cùng wave.

## Status values

`waiting`, `ready`, `in_progress`, `ready_for_review`, `changes_requested`, `merged`, `blocked`.
