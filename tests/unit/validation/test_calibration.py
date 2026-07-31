import pytest

from dao_vang.validation.calibration import (
    brier_score,
    calibration_curve,
    expected_calibration_error,
)


def test_brier_score():
    # Perfect prediction
    y_true = [True, False, True]
    y_prob = [1.0, 0.0, 1.0]
    assert brier_score(y_true, y_prob) == 0.0

    # Completely wrong prediction
    y_prob_wrong = [0.0, 1.0, 0.0]
    assert brier_score(y_true, y_prob_wrong) == 1.0

    # Random guess (0.5 everywhere) -> Brier should be 0.25
    y_prob_random = [0.5, 0.5, 0.5]
    assert brier_score(y_true, y_prob_random) == 0.25

    # Mismatch length
    with pytest.raises(ValueError):
        brier_score([True], [1.0, 0.5])

    # Empty
    with pytest.raises(ValueError):
        brier_score([], [])


def test_calibration_curve():
    y_true = [False, False, True, True, True]
    # Bins for n=2 (0-0.5, 0.5-1.0):
    # Bin 0: 0.1 (F), 0.4 (F) -> true_fraction = 0/2 = 0.0, mean_prob = 0.25
    # Bin 1: 0.6 (T), 0.9 (T), 1.0 (T) -> true_fraction = 3/3 = 1.0, mean_prob = 0.8333
    y_prob = [0.1, 0.4, 0.6, 0.9, 1.0]

    mean_probs, true_fracs, counts = calibration_curve(y_true, y_prob, n_bins=2)

    assert counts == [2, 3]
    assert true_fracs == [0.0, 1.0]
    assert abs(mean_probs[0] - 0.25) < 1e-6
    assert abs(mean_probs[1] - (0.6 + 0.9 + 1.0) / 3) < 1e-6

    # Out of bounds prob
    with pytest.raises(ValueError):
        calibration_curve([True], [1.1])


def test_expected_calibration_error():
    y_true = [False, False, True, True, True]
    y_prob = [0.1, 0.4, 0.6, 0.9, 1.0]

    # Bin 0: diff = abs(0.25 - 0.0) = 0.25, weight = 2/5
    # Bin 1: diff = abs(0.8333 - 1.0) = 0.1666, weight = 3/5
    # ECE = (2/5) * 0.25 + (3/5) * 0.16666 = 0.1 + 0.1 = 0.2

    ece = expected_calibration_error(y_true, y_prob, n_bins=2)
    assert abs(ece - 0.2) < 1e-5
