from datetime import datetime, timedelta
from typing import List, Tuple

from pydantic import BaseModel


class RowMetrics(BaseModel):
    """Metrics calculated at the row (point-in-time) level."""

    precision: float
    recall: float
    fpr: float
    f1_score: float
    support_positive: int
    support_negative: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int


class EventMetrics(BaseModel):
    """Metrics calculated at the event level with signal cooldown."""

    precision: float  # True Signals / Total Signals
    recall: float  # Caught Events / True Events
    f1_score: float
    total_signals: int
    false_signals: int
    true_events: int
    caught_events: int


def calculate_row_metrics(y_true: List[bool], y_pred: List[bool]) -> RowMetrics:
    """Calculates standard classification metrics without any temporal awareness."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt and yp)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and yp)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt and not yp)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and not yp)

    pos = tp + fn
    neg = tn + fp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / pos if pos > 0 else 0.0
    fpr = fp / neg if neg > 0 else 0.0

    f1 = 0.0
    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)

    return RowMetrics(
        precision=precision,
        recall=recall,
        fpr=fpr,
        f1_score=f1,
        support_positive=pos,
        support_negative=neg,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
    )


def calculate_event_metrics(
    timestamps: List[datetime],
    y_true: List[bool],
    y_pred: List[bool],
    cooldown_minutes: int = 1440,
) -> EventMetrics:
    """
    Calculates event-level metrics.
    A signal is emitted when y_pred=True and no cooldown is active.
    A true event is defined as a contiguous block of y_true=True.
    """
    if not (len(timestamps) == len(y_true) == len(y_pred)):
        raise ValueError("Inputs must have the same length")

    # 1. Identify True Events (contiguous blocks of y_true=True)
    true_events: List[Tuple[int, int]] = []
    in_event = False
    event_start = 0
    for i, yt in enumerate(y_true):
        if yt and not in_event:
            in_event = True
            event_start = i
        elif not yt and in_event:
            in_event = False
            true_events.append((event_start, i - 1))

    if in_event:
        true_events.append((event_start, len(y_true) - 1))

    num_true_events = len(true_events)
    events_caught: set[int] = set()

    # 2. Iterate through predictions and apply cooldown
    cooldown_until = None
    total_signals = 0
    true_signals = 0
    false_signals = 0

    cooldown_delta = timedelta(minutes=cooldown_minutes)

    for i, (ts, yt, yp) in enumerate(zip(timestamps, y_true, y_pred)):
        if yp:
            if cooldown_until is not None and ts < cooldown_until:
                continue  # In cooldown, ignore signal

            # Valid signal
            total_signals += 1
            cooldown_until = ts + cooldown_delta

            if yt:
                # True signal
                true_signals += 1
                # Mark the event as caught
                for e_idx, (start_idx, end_idx) in enumerate(true_events):
                    if start_idx <= i <= end_idx:
                        events_caught.add(e_idx)
                        break
            else:
                # False signal
                false_signals += 1

    caught_events_count = len(events_caught)

    precision = true_signals / total_signals if total_signals > 0 else 0.0
    recall = caught_events_count / num_true_events if num_true_events > 0 else 0.0

    f1 = 0.0
    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)

    return EventMetrics(
        precision=precision,
        recall=recall,
        f1_score=f1,
        total_signals=total_signals,
        false_signals=false_signals,
        true_events=num_true_events,
        caught_events=caught_events_count,
    )
