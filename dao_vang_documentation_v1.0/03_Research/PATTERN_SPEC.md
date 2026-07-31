# PATTERN SPECIFICATION

## Cấu trúc

```yaml
pattern_id: DISTRIBUTION_001
version: 0.1.0
status: hypothesis
behavioral_rationale: ...
conditions: ...
confirmation: ...
invalidation: ...
applicable_regimes: ...
label_version: ...
feature_set_version: ...
```

## Yêu cầu

- Không chỉ là tổ hợp threshold tối ưu ngẫu nhiên.
- Có sample size và out-of-sample result.
- Có invalidation.
- Có regime breakdown.
- Có lifecycle status.
- Có retirement rule.

## Event overlap

Pattern evaluation phải báo cả row-level và event-level, event-level dùng cooldown versioned.
