from datetime import datetime

from dao_vang.validation.metrics import calculate_event_metrics, calculate_row_metrics


def test_row_metrics_happy_path():
    y_true = [True, True, False, False]
    y_pred = [True, False, True, False]

    metrics = calculate_row_metrics(y_true, y_pred)

    assert metrics.true_positives == 1
    assert metrics.false_negatives == 1
    assert metrics.false_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.support_positive == 2
    assert metrics.support_negative == 2

    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.fpr == 0.5
    assert metrics.f1_score == 0.5


def test_row_metrics_zero_division():
    y_true = [False, False]
    y_pred = [False, False]

    metrics = calculate_row_metrics(y_true, y_pred)

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.fpr == 0.0
    assert metrics.f1_score == 0.0


def test_event_metrics_cooldown():
    timestamps = [
        datetime(2023, 1, 1, 0, 0),
        datetime(2023, 1, 1, 1, 0),  # +1h
        datetime(2023, 1, 1, 2, 0),  # +2h
        datetime(2023, 1, 2, 0, 0),  # +24h
    ]

    y_true = [True, True, True, False]
    y_pred = [True, True, True, True]

    # Cooldown 24h: only the first and last signals will be registered
    metrics = calculate_event_metrics(timestamps, y_true, y_pred, cooldown_minutes=1440)

    # Signals:
    # idx 0: ts=Jan 1 0:00 -> NOT in cooldown. Signal fired. yp=T, yt=T -> True Signal.
    # idx 1: ts=Jan 1 1:00 -> IN cooldown. Ignored.
    # idx 2: ts=Jan 1 2:00 -> IN cooldown. Ignored.
    # idx 3: ts=Jan 2 0:00 -> NOT in cooldown. Signal fired. yp=T, yt=F -> False Signal.

    assert metrics.total_signals == 2
    assert metrics.false_signals == 1
    assert metrics.true_events == 1
    assert metrics.caught_events == 1

    assert metrics.precision == 0.5
    assert metrics.recall == 1.0


def test_event_metrics_multiple_events():
    timestamps = [
        datetime(2023, 1, 1, 0, 0),
        datetime(2023, 1, 2, 0, 0),
        datetime(2023, 1, 3, 0, 0),
        datetime(2023, 1, 4, 0, 0),
    ]

    y_true = [True, False, True, False]
    y_pred = [False, False, True, False]

    metrics = calculate_event_metrics(timestamps, y_true, y_pred, cooldown_minutes=1440)

    assert metrics.true_events == 2
    assert metrics.caught_events == 1  # Second event caught
    assert metrics.total_signals == 1  # Only one signal fired at idx 2
    assert metrics.false_signals == 0

    assert metrics.precision == 1.0
    assert metrics.recall == 0.5
