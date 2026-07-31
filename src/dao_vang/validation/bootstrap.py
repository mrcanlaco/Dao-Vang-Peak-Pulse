import random
from typing import Any, Callable, List, Tuple


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

    random.seed(seed)
    n = len(y_true)
    stats: List[float] = []

    for _ in range(n_iterations):
        # Sample with replacement
        indices = [random.randint(0, n - 1) for _ in range(n)]

        sample_true = [y_true[i] for i in indices]
        sample_pred = [y_pred[i] for i in indices]

        stat = metric_fn(sample_true, sample_pred)
        stats.append(stat)

    stats.sort()

    alpha = (1.0 - confidence_level) / 2.0
    lower_idx = max(0, int(alpha * n_iterations))
    upper_idx = min(n_iterations - 1, int((1.0 - alpha) * n_iterations))

    return stats[lower_idx], stats[upper_idx]
