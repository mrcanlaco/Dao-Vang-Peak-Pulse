import random
from typing import List


def b0_random(prevalence: float, size: int, seed: int = 42) -> List[bool]:
    """
    B0: prevalence/random calibrated.
    Generates a boolean list of length `size` where True is predicted
    with a probability equal to `prevalence`.
    """
    random.seed(seed)
    return [random.random() < prevalence for _ in range(size)]


def b1_price_return(price_return_24h: List[float], threshold: float) -> List[bool]:
    """
    B1: price return 24h cao.
    Predicts True if the 24h price return exceeds the given threshold.
    """
    return [val > threshold for val in price_return_24h]


def b2_funding(funding_percentile: List[float], threshold: float) -> List[bool]:
    """
    B2: funding percentile cao.
    Predicts True if the funding percentile exceeds the given threshold.
    """
    return [val > threshold for val in funding_percentile]


def b3_oi_change(oi_change_4h: List[float], threshold: float) -> List[bool]:
    """
    B3: OI change 4h cao.
    Predicts True if the 4h Open Interest change exceeds the given threshold.
    """
    return [val > threshold for val in oi_change_4h]


def b4_funding_and_oi(
    funding_percentile: List[float],
    oi_change_4h: List[float],
    funding_threshold: float,
    oi_threshold: float,
) -> List[bool]:
    """
    B4: funding cao + OI tăng.
    Predicts True if both funding percentile and OI change exceed their thresholds.
    """
    if len(funding_percentile) != len(oi_change_4h):
        raise ValueError(
            "Inputs funding_percentile and oi_change_4h must have the same length"
        )

    return [
        (f > funding_threshold) and (o > oi_threshold)
        for f, o in zip(funding_percentile, oi_change_4h)
    ]
