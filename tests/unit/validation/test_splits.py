from datetime import datetime, timedelta

from dao_vang.validation.splits import generate_walk_forward_splits


def test_happy_path_walk_forward():
    start = datetime(2023, 1, 1)
    # 90d train + 24h embargo + 30d val + 24h embargo + 30d test 
    # = 152 days for first fold
    end = start + timedelta(days=200)

    folds = generate_walk_forward_splits(
        dataset_start=start,
        dataset_end=end,
        train_days=90,
        val_days=30,
        test_days=30,
        step_days=30,
        embargo_hours=24,
    )

    assert len(folds) >= 1
    f0 = folds[0]
    assert f0.fold_idx == 0

    # Check boundaries of first fold
    assert f0.train.start_time == start
    assert f0.train.end_time == start + timedelta(days=90)

    # Check embargo 1
    assert f0.validation.start_time == f0.train.end_time + timedelta(hours=24)
    assert f0.validation.end_time == f0.validation.start_time + timedelta(days=30)

    # Check embargo 2
    assert f0.test.start_time == f0.validation.end_time + timedelta(hours=24)
    assert f0.test.end_time == f0.test.start_time + timedelta(days=30)

    # Step forward is 30 days, so fold 1 train should start 30 days after fold 0
    if len(folds) > 1:
        f1 = folds[1]
        assert f1.train.start_time == f0.train.start_time + timedelta(days=30)


def test_boundary_not_enough_data():
    start = datetime(2023, 1, 1)
    end = start + timedelta(days=100)  # Not enough for 152 days fold

    folds = generate_walk_forward_splits(
        dataset_start=start,
        dataset_end=end,
        train_days=90,
        val_days=30,
        test_days=30,
        step_days=30,
        embargo_hours=24,
    )

    assert len(folds) == 0


def test_leakage_and_embargo():
    start = datetime(2023, 1, 1)
    end = start + timedelta(days=500)

    folds = generate_walk_forward_splits(
        dataset_start=start,
        dataset_end=end,
        train_days=90,
        val_days=30,
        test_days=30,
        step_days=30,
        embargo_hours=48,  # Testing 48h embargo
    )

    for f in folds:
        # Train and Val must not overlap, and must have exact embargo gap
        val_train_gap = f.validation.start_time - f.train.end_time
        assert val_train_gap == timedelta(hours=48), (
            "Leakage detected between train and val"
        )

        # Val and Test must not overlap, and must have exact embargo gap
        test_val_gap = f.test.start_time - f.validation.end_time
        assert test_val_gap == timedelta(hours=48), (
            "Leakage detected between val and test"
        )

        # Sanity check chronological order
        assert f.train.start_time < f.train.end_time
        assert f.train.end_time < f.validation.start_time
        assert f.validation.start_time < f.validation.end_time
        assert f.validation.end_time < f.test.start_time
        assert f.test.start_time < f.test.end_time


def test_deterministic_behavior():
    start = datetime(2023, 1, 1)
    end = start + timedelta(days=365)

    folds1 = generate_walk_forward_splits(start, end)
    folds2 = generate_walk_forward_splits(start, end)

    assert folds1 == folds2
