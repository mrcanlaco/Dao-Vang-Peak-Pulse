import random
from collections.abc import Callable, Sequence
from typing import Any, List, Tuple


def calculate_bootstrap_ci(
    y_true: List[bool],
    y_pred: List[Any],
    metric_fn: Callable[[List[bool], List[Any]], float],
    n_iterations: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float]:
    """
    Calculate confidence intervals using bootstrap resampling.

    Args:
        y_true: List of ground truth boolean labels.
        y_pred: List of predictions (can be bools or floats depending on the metric).
        metric_fn: A function that takes (y_true, y_pred) and returns a float metric.
        n_iterations: Number of bootstrap samples to draw.
        confidence_level: Desired confidence level (e.g., 0.95 for 95% CI).
        seed: Random seed for reproducibility.

    Returns:
        A tuple (lower_bound, upper_bound) representing the confidence interval.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        raise ValueError("Inputs cannot be empty")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be between 0 and 1")
    if n_iterations <= 0:
        raise ValueError("n_iterations must be positive")

    rng = random.Random(seed)
    n = len(y_true)
    stats: List[float] = []

    for _ in range(n_iterations):
        # Sample with replacement
        indices = [rng.randrange(n) for _ in range(n)]

        sample_true = [y_true[i] for i in indices]
        sample_pred = [y_pred[i] for i in indices]

        stat = metric_fn(sample_true, sample_pred)
        stats.append(stat)

    stats.sort()

    alpha = (1.0 - confidence_level) / 2.0
    lower_idx = max(0, int(alpha * n_iterations))
    upper_idx = min(n_iterations - 1, int((1.0 - alpha) * n_iterations))

    return float(stats[lower_idx]), float(stats[upper_idx])


def calculate_group_bootstrap_ci(
    groups: Sequence[Any],
    metric_fn: Callable[[list[Any]], float],
    *,
    n_iterations: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float]:
    """Bootstrap whole groups (events or contiguous time blocks).

    ``groups`` contains already-aggregated event/block observations.  Sampling
    this sequence, rather than individual rows, prevents duplicate candles
    from narrowing the confidence interval artificially.
    """

    values = list(groups)
    if not values:
        raise ValueError("groups cannot be empty")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be between 0 and 1")
    if n_iterations <= 0:
        raise ValueError("n_iterations must be positive")
    rng = random.Random(seed)
    n = len(values)
    statistics = [
        float(metric_fn([values[rng.randrange(n)] for _ in range(n)]))
        for _ in range(n_iterations)
    ]
    statistics.sort()
    alpha = (1.0 - confidence_level) / 2.0
    lower = statistics[max(0, int(alpha * n_iterations))]
    upper = statistics[min(n_iterations - 1, int((1.0 - alpha) * n_iterations))]
    return lower, upper


def calculate_event_bootstrap_ci(
    event_values: Sequence[Any],
    metric_fn: Callable[[list[Any]], float],
    **kwargs: Any,
) -> Tuple[float, float]:
    """Named convenience wrapper for event-level confidence intervals."""

    return calculate_group_bootstrap_ci(event_values, metric_fn, **kwargs)


def calculate_block_bootstrap_ci(
    blocks: Sequence[Any],
    metric_fn: Callable[[list[Any]], float],
    **kwargs: Any,
) -> Tuple[float, float]:
    """Named convenience wrapper for contiguous time-block confidence intervals."""

    return calculate_group_bootstrap_ci(blocks, metric_fn, **kwargs)
