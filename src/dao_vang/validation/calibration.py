from typing import List, Tuple


def brier_score(y_true: List[bool], y_prob: List[float]) -> float:
    """
    Calculate the Brier Score (mean squared error of probability predictions).
    """
    if not y_true or not y_prob:
        raise ValueError("Inputs cannot be empty")
    if len(y_true) != len(y_prob):
        raise ValueError("y_true and y_prob must have the same length")

    n = len(y_true)
    score = 0.0
    for i in range(n):
        true_val = 1.0 if y_true[i] else 0.0
        diff = y_prob[i] - true_val
        score += diff * diff

    return score / n


def calibration_curve(
    y_true: List[bool], y_prob: List[float], n_bins: int = 10
) -> Tuple[List[float], List[float], List[int]]:
    """
    Compute true fraction and mean predicted probability for calibration curve.
    Uses uniform bins over the range [0, 1].

    Returns:
        mean_predicted_probs: The mean predicted probability in each bin.
        true_fractions: The fraction of positive labels in each bin.
        counts: The number of samples in each bin.
    """
    if not y_true or not y_prob:
        raise ValueError("Inputs cannot be empty")
    if len(y_true) != len(y_prob):
        raise ValueError("y_true and y_prob must have the same length")
    if n_bins <= 0:
        raise ValueError("n_bins must be greater than 0")

    bin_sums = [0.0] * n_bins
    bin_true_counts = [0] * n_bins
    bin_totals = [0] * n_bins

    for i in range(len(y_true)):
        prob = y_prob[i]

        if prob < 0.0 or prob > 1.0:
            raise ValueError("y_prob must be between 0 and 1")

        # Determine bin index [0, n_bins-1]
        bin_idx = int(prob * n_bins)
        # Handle the edge case where prob == 1.0
        if bin_idx == n_bins:
            bin_idx = n_bins - 1

        bin_totals[bin_idx] += 1
        bin_sums[bin_idx] += prob
        if y_true[i]:
            bin_true_counts[bin_idx] += 1

    mean_predicted_probs: List[float] = []
    true_fractions: List[float] = []
    counts: List[int] = []

    for i in range(n_bins):
        if bin_totals[i] > 0:
            mean_predicted_probs.append(bin_sums[i] / bin_totals[i])
            true_fractions.append(bin_true_counts[i] / bin_totals[i])
            counts.append(bin_totals[i])

    return mean_predicted_probs, true_fractions, counts


def expected_calibration_error(
    y_true: List[bool], y_prob: List[float], n_bins: int = 10
) -> float:
    """
    Calculate Expected Calibration Error (ECE) using uniform bins.
    """
    mean_predicted_probs, true_fractions, counts = calibration_curve(
        y_true, y_prob, n_bins
    )

    total_samples = sum(counts)
    if total_samples == 0:
        return 0.0

    ece = 0.0
    for i in range(len(counts)):
        weight = counts[i] / total_samples
        diff = abs(mean_predicted_probs[i] - true_fractions[i])
        ece += weight * diff

    return ece
