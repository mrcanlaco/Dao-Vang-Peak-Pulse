import pytest

from dao_vang.baselines.logistic import LogisticRegressionSGD, StandardScaler, sigmoid


def test_sigmoid():
    assert sigmoid(0) == 0.5
    assert sigmoid(20) > 0.99
    assert sigmoid(-20) < 0.01
    # Check capping
    assert sigmoid(100) == sigmoid(20)
    assert sigmoid(-100) == sigmoid(-20)


def test_standard_scaler():
    scaler = StandardScaler()

    with pytest.raises(RuntimeError):
        scaler.transform([[1.0]])

    X_train = [
        [1.0, 10.0],
        [3.0, 20.0],
        [5.0, 30.0],
    ]

    scaler.fit(X_train)
    # Check that transform works (is_fitted = True)
    assert scaler.means == [3.0, 20.0]

    # stdev of [1, 3, 5] is sqrt(((1-3)^2 + (3-3)^2 + (5-3)^2) / 3)
    # = sqrt(8/3) = 1.63299
    # stdev of [10, 20, 30] is sqrt(200/3) = 8.16496

    X_transformed = scaler.transform(X_train)

    # Centered around 0
    assert abs(sum(row[0] for row in X_transformed)) < 1e-6
    assert abs(sum(row[1] for row in X_transformed)) < 1e-6

    # Check boundary (empty list)
    with pytest.raises(ValueError):
        scaler.fit([])

    # Check constant feature
    scaler2 = StandardScaler()
    scaler2.fit([[1.0], [1.0]])
    assert scaler2.means == [1.0]
    assert scaler2.stds == [1.0]  # Division by zero avoided


def test_logistic_regression():
    model = LogisticRegressionSGD(learning_rate=0.1, epochs=200, l2_lambda=0.01)

    with pytest.raises(RuntimeError):
        model.predict_proba([[1.0]])

    # Simple binary classification task
    # Feature 0: 0.1 vs 0.9
    X_train = [[0.1], [0.2], [0.8], [0.9]]
    y_train = [False, False, True, True]

    model.fit(X_train, y_train)
    # Check that model predicts without error

    probas = model.predict_proba(X_train)

    # Predictions for False class should be < 0.5, True class > 0.5
    assert probas[0] < 0.5
    assert probas[1] < 0.5
    assert probas[2] > 0.5
    assert probas[3] > 0.5

    # Mismatch checking
    with pytest.raises(ValueError):
        model.fit([[1.0]], [True, False])
    with pytest.raises(ValueError):
        model.predict_proba([[1.0, 2.0]])
