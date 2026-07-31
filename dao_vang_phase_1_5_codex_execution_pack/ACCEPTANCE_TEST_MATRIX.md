# ACCEPTANCE TEST MATRIX

| Capability | Required evidence | Blocking |
|---|---|---|
| Project scaffold | full gate pass | Yes |
| Collector pagination | no missing/duplicate across pages | Yes |
| Raw immutability | same raw file never overwritten | Yes |
| Retry/rate limit | bounded retry and metadata | Yes |
| Schema parsing | contract fixtures pass | Yes |
| Kline closed-only | unfinished candle rejected | Yes |
| Time alignment | exact/bwd-only joins | Yes |
| Available time | future record excluded | Yes |
| Funding age | stale funding becomes null | Yes |
| Dataset fingerprint | same input same hash | Yes |
| Label target/MAE | all edge cases | Yes |
| Intrabar ambiguity | label null | Yes |
| Feature rolling | prefix/future invariance | Yes |
| Split | chronological, no overlap | Yes |
| Preprocessing | train-only fit | Yes |
| Walk-forward | per-window artifacts | Yes |
| Calibration | bins and error metrics | No for alpha, Yes for research release |
| Leakage audit | all tests pass | Yes |
| E2E | raw fixture to report | Yes |
| Provenance | commit/config/dataset/seed | Yes |
| Documentation sync | v1.1 audit completed | Yes for Phase 3 |
