# LEAKAGE THREAT MODEL

| Risk | Prevention | Test |
|---|---|---|
| Nến chưa đóng | close-time gate | unfinished candle rejected |
| Future as-of join | backward-only | future insertion invariance |
| Rolling center | prohibit | static scan/unit test |
| Scaler toàn dataset | pipeline fit train | transformed train/test audit |
| Percentile toàn lịch sử | rolling past-only | prefix equality |
| Label trong feature | schema separation | forbidden column test |
| Random split | validation contract | split monotonicity |
| Threshold sau test | artifact freeze | config provenance |
| Revised API data | source snapshot/version | fingerprint |
| Overlap horizon | embargo | interval overlap test |

Mọi `PointInTimeViolation` phải fail closed.
