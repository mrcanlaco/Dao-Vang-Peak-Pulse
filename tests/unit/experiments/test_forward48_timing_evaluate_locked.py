import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from forward48_timing_evaluate_locked import _promotion_gate  # noqa: E402


def test_promotion_gate_fails_when_wilson_lower_is_below_break_even() -> None:
    gate = _promotion_gate(
        {
            "evaluable_signals": 120,
            "precision": 0.55,
            "precision_wilson95_lower": 0.44,
        }
    )

    assert gate["wilson_lower_above_break_even"] is False
    assert gate["passed"] is False


def test_promotion_gate_passes_only_when_every_invariant_passes() -> None:
    gate = _promotion_gate(
        {
            "evaluable_signals": 120,
            "precision": 0.55,
            "precision_wilson95_lower": 0.46,
        }
    )

    assert gate["wilson_lower_above_break_even"] is True
    assert gate["passed"] is True
