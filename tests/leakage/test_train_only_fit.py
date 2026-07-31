from dao_vang.baselines.logistic import StandardScaler


def test_scaler_train_only_fit():
    """
    Ensure that StandardScaler is only fitted on the train set,
    and the exact same mean/std are applied to both train and test sets,
    preventing data leakage (e.g., using test set statistics to scale test data).
    """
    # Train set has mean 10, std > 0
    X_train = [
        [8.0],
        [10.0],
        [12.0],
    ]

    # Test set has mean 100, std > 0
    X_test = [
        [98.0],
        [100.0],
        [102.0],
    ]

    scaler = StandardScaler()
    scaler.fit(X_train)

    # Check that means and stds correspond to the train set
    assert scaler.means == [10.0]
    assert abs(scaler.stds[0] - 1.63299) < 1e-4

    # Transform test set
    X_test_scaled = scaler.transform(X_test)

    # The test set must be scaled using train mean (10), not test mean (100)
    # So the value 100 becomes (100 - 10) / 1.63299 ≈ 55.11
    # If there was a leakage (fitted on test), the mean would be 100
    # and it would become 0.

    assert X_test_scaled[1][0] > 50.0  # (100 - 10) / 1.63

    # The test set values should NOT be centered around 0!
    test_scaled_mean = sum(row[0] for row in X_test_scaled) / len(X_test_scaled)
    assert test_scaled_mean > 50.0
