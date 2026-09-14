# Kết quả tìm kiếm đa biến số tối ưu hoá mô hình V3 (20% / 48h)

*Thời gian thực hiện: 2026-09-14 16:21:10 UTC*

Tổng số biến thể thử nghiệm: 31 | Thời gian chạy: 51.0s

| Hạng | Biến thể | Trục (Axis) | Signals | Precision | Conservative EV | Pos Folds | AP | ROC-AUC | ECE |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `combo_pump25_reversal_funding_scout` | Combinations | 18 | 50.0% | **+1.80%** | 1/4 | 0.399 | 0.573 | 0.253 |
| 2 | `combo_pump25_funding_scout` | Combinations | 21 | 38.1% | -2.49% | 0/4 | 0.404 | 0.630 | 0.169 |
| 3 | `universe_pump_ge_25` | Universe & Filtering | 301 | 36.0% | -3.24% | 1/4 | 0.377 | 0.580 | 0.123 |
| 4 | `universe_pump_ge_30` | Universe & Filtering | 132 | 34.7% | -3.72% | 0/4 | 0.368 | 0.550 | 0.153 |
| 5 | `combo_pump20_funding_scout` | Combinations | 51 | 34.3% | -3.84% | 0/4 | 0.277 | 0.523 | 0.130 |
| 6 | `combo_pump25_reversal3pct` | Combinations | 269 | 34.3% | -3.86% | 0/4 | 0.384 | 0.583 | 0.136 |
| 7 | `combo_pump25_shallow_sigmoid` | Combinations | 250 | 33.0% | -4.33% | 0/4 | 0.398 | 0.582 | 0.080 |
| 8 | `universe_exhaustion_momentum` | Universe & Filtering | 160 | 32.7% | -4.42% | 0/4 | 0.307 | 0.623 | 0.073 |
| 9 | `universe_funding_scout` | Universe & Filtering | 98 | 32.3% | -4.58% | 1/4 | 0.327 | 0.664 | 0.123 |
| 10 | `universe_reversal_3pct` | Universe & Filtering | 312 | 31.2% | -4.96% | 0/4 | 0.325 | 0.636 | 0.076 |
| 11 | `combo_pump20_liquidity5m` | Combinations | 269 | 31.1% | -5.00% | 0/4 | 0.330 | 0.602 | 0.076 |
| 12 | `combo_pump20_shallow_lgb` | Combinations | 319 | 30.5% | -5.22% | 0/4 | 0.326 | 0.601 | 0.070 |
| 13 | `combo_pump25_liquidity5m` | Combinations | 264 | 29.2% | -5.70% | 0/4 | 0.367 | 0.571 | 0.136 |
| 14 | `decision_cooldown_48h` | Calibration & Decision | 319 | 28.5% | -5.93% | 1/4 | 0.303 | 0.669 | 0.061 |
| 15 | `decision_strict_recall_10` | Calibration & Decision | 431 | 28.1% | -6.08% | 0/4 | 0.303 | 0.669 | 0.061 |
| 16 | `universe_min_volume_10m` | Universe & Filtering | 422 | 27.4% | -6.35% | 0/4 | 0.317 | 0.665 | 0.063 |
| 17 | `combo_clean_features_shallow_sigmoid` | Combinations | 406 | 26.7% | -6.58% | 0/4 | 0.326 | 0.675 | 0.072 |
| 18 | `baseline_default` | Baseline | 494 | 26.6% | -6.61% | 0/4 | 0.303 | 0.669 | 0.061 |
| 19 | `model_lgb_shallow_reg` | Model Architecture | 415 | 26.5% | -6.67% | 0/4 | 0.317 | 0.679 | 0.065 |
| 20 | `combo_pump20_reversal3pct` | Combinations | 330 | 26.3% | -6.74% | 0/4 | 0.345 | 0.595 | 0.090 |
| 21 | `universe_pump_ge_20` | Universe & Filtering | 342 | 25.7% | -6.95% | 0/4 | 0.317 | 0.596 | 0.074 |
| 22 | `calib_platt_sigmoid` | Calibration & Decision | 493 | 25.4% | -7.05% | 0/4 | 0.344 | 0.682 | 0.066 |
| 23 | `model_lgb_feature_subsample` | Model Architecture | 508 | 25.3% | -7.09% | 0/4 | 0.304 | 0.670 | 0.060 |
| 24 | `features_no_ls_ratios` | Feature Selection | 485 | 25.0% | -7.21% | 0/4 | 0.305 | 0.658 | 0.061 |
| 25 | `model_lgb_heavy_reg` | Model Architecture | 515 | 24.8% | -7.28% | 0/4 | 0.322 | 0.685 | 0.060 |
| 26 | `universe_min_volume_5m` | Universe & Filtering | 490 | 24.8% | -7.29% | 0/4 | 0.314 | 0.673 | 0.064 |
| 27 | `features_clean_10` | Feature Selection | 462 | 24.5% | -7.38% | 0/4 | 0.289 | 0.651 | 0.061 |
| 28 | `model_random_forest` | Model Architecture | 509 | 24.4% | -7.40% | 0/4 | 0.304 | 0.673 | 0.068 |
| 29 | `features_funding_momentum` | Feature Selection | 612 | 21.7% | -8.39% | 0/4 | 0.294 | 0.657 | 0.065 |
| 30 | `model_logistic_l2_c01` | Model Architecture | 649 | 19.7% | -9.12% | 0/4 | 0.236 | 0.560 | 0.070 |
| 31 | `model_logistic_l2_c001` | Model Architecture | 755 | 16.5% | -10.26% | 0/4 | 0.226 | 0.539 | 0.073 |

## Chi tiết các biến thể hàng đầu và phát hiện chính

### Top 1: `combo_pump25_reversal_funding_scout` (Combinations)
- **Mô tả**: Pump >= 25% + Reversal >= 2% + Funding Scout Gate
- **Hiệu năng**: Signals = 18, Precision = 50.0%, Conservative EV = +1.80%, Folds dương = 1/4
- **Đo lường xác suất**: ROC-AUC = 0.573, Average Precision = 0.399, ECE = 0.253, Brier = 0.2784

### Top 2: `combo_pump25_funding_scout` (Combinations)
- **Mô tả**: Pump >= 25% + Funding Scout Gate
- **Hiệu năng**: Signals = 21, Precision = 38.1%, Conservative EV = -2.49%, Folds dương = 0/4
- **Đo lường xác suất**: ROC-AUC = 0.630, Average Precision = 0.404, ECE = 0.169, Brier = 0.2396

### Top 3: `universe_pump_ge_25` (Universe & Filtering)
- **Mô tả**: Large pump filter: price_ret_24h >= 25%
- **Hiệu năng**: Signals = 301, Precision = 36.0%, Conservative EV = -3.24%, Folds dương = 1/4
- **Đo lường xác suất**: ROC-AUC = 0.580, Average Precision = 0.377, ECE = 0.123, Brier = 0.2285

### Top 4: `universe_pump_ge_30` (Universe & Filtering)
- **Mô tả**: Extreme pump filter: price_ret_24h >= 30%
- **Hiệu năng**: Signals = 132, Precision = 34.7%, Conservative EV = -3.72%, Folds dương = 0/4
- **Đo lường xác suất**: ROC-AUC = 0.550, Average Precision = 0.368, ECE = 0.153, Brier = 0.2525

### Top 5: `combo_pump20_funding_scout` (Combinations)
- **Mô tả**: Pump >= 20% + Funding Scout Gate (high funding exhaustion)
- **Hiệu năng**: Signals = 51, Precision = 34.3%, Conservative EV = -3.84%, Folds dương = 0/4
- **Đo lường xác suất**: ROC-AUC = 0.523, Average Precision = 0.277, ECE = 0.130, Brier = 0.2101
