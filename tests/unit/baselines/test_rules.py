import pytest

from dao_vang.baselines.rules import (
    b0_random,
    b1_price_return,
    b2_funding,
    b3_oi_change,
    b4_funding_and_oi,
)


def test_b0_random():
    size = 10000
    prevalence = 0.05

    # Deterministic behavior
    res1 = b0_random(prevalence, size, seed=42)
    res2 = b0_random(prevalence, size, seed=42)
    assert res1 == res2

    # Check prevalence approximation
    true_count = sum(res1)
    actual_prevalence = true_count / size
    # Should be close to 0.05
    assert 0.04 <= actual_prevalence <= 0.06

    # Boundary: size 0
    assert b0_random(prevalence, 0) == []


def test_b1_price_return():
    data = [0.01, 0.05, -0.02, 0.10, 0.0]
    res = b1_price_return(data, threshold=0.04)
    assert res == [False, True, False, True, False]

    assert b1_price_return([], 0.04) == []


def test_b2_funding():
    data = [0.5, 0.8, 0.95, 0.1, 0.99]
    res = b2_funding(data, threshold=0.90)
    assert res == [False, False, True, False, True]


def test_b3_oi_change():
    data = [100.0, -50.0, 500.0, 0.0]
    res = b3_oi_change(data, threshold=200.0)
    assert res == [False, False, True, False]


def test_b4_funding_and_oi():
    funding = [0.5, 0.95, 0.95, 0.1]
    oi = [500.0, 100.0, 500.0, -50.0]

    # Both must be > threshold
    res = b4_funding_and_oi(funding, oi, funding_threshold=0.90, oi_threshold=200.0)
    # 0.5 > 0.9 (F) and 500 > 200 (T) -> F
    # 0.95 > 0.9 (T) and 100 > 200 (F) -> F
    # 0.95 > 0.9 (T) and 500 > 200 (T) -> T
    # 0.1 > 0.9 (F) and -50 > 200 (F) -> F
    assert res == [False, False, True, False]

    # Boundary: mismatch length
    with pytest.raises(ValueError):
        b4_funding_and_oi([0.5, 0.95], [500.0], 0.90, 200.0)
