import math
from typing import List


class StandardScaler:
    """Standardize features by removing the mean and scaling to unit variance."""

    def __init__(self):
        self.means: List[float] = []
        self.stds: List[float] = []
        self._is_fitted = False

    def fit(self, X: List[List[float]]) -> None:
        """Compute the mean and std to be used for later scaling."""
        if not X:
            raise ValueError("Cannot fit on an empty dataset.")

        n_samples = len(X)
        n_features = len(X[0])

        self.means = [0.0] * n_features
        for row in X:
            for j in range(n_features):
                self.means[j] += row[j]

        for j in range(n_features):
            self.means[j] /= n_samples

        variances = [0.0] * n_features
        for row in X:
            for j in range(n_features):
                diff = row[j] - self.means[j]
                variances[j] += diff * diff

        self.stds = [math.sqrt(v / n_samples) for v in variances]

        # Prevent division by zero for constant features
        for j in range(n_features):
            if self.stds[j] == 0.0:
                self.stds[j] = 1.0

        self._is_fitted = True

    def transform(self, X: List[List[float]]) -> List[List[float]]:
        """Perform standardization by centering and scaling."""
        if not self._is_fitted:
            raise RuntimeError("Scaler has not been fitted yet.")

        n_features = len(self.means)
        result: List[List[float]] = []
        for row in X:
            if len(row) != n_features:
                raise ValueError("Mismatch in number of features.")

            scaled_row = [
                (row[j] - self.means[j]) / self.stds[j] for j in range(n_features)
            ]
            result.append(scaled_row)

        return result


def sigmoid(z: float) -> float:
    # Cap z to avoid math range error (overflow)
    z = max(min(z, 20.0), -20.0)
    return 1.0 / (1.0 + math.exp(-z))


class LogisticRegressionSGD:
    """Logistic Regression trained via Stochastic Gradient Descent."""

    def __init__(
        self, learning_rate: float = 0.01, epochs: int = 100, l2_lambda: float = 0.0
    ):
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2_lambda = l2_lambda
        self.weights: List[float] = []
        self.bias: float = 0.0
        self._is_fitted = False

    def fit(self, X: List[List[float]], y: List[bool]) -> None:
        """Fit the model according to the given training data."""
        if not X or not y:
            raise ValueError("Empty training data.")
        if len(X) != len(y):
            raise ValueError("X and y must have the same length.")

        n_samples = len(X)
        n_features = len(X[0])

        self.weights = [0.0] * n_features
        self.bias = 0.0

        for _ in range(self.epochs):
            for i in range(n_samples):
                row = X[i]
                target = 1.0 if y[i] else 0.0

                # Compute prediction
                z = self.bias
                for j in range(n_features):
                    z += self.weights[j] * row[j]

                prediction = sigmoid(z)
                error = prediction - target

                # Update weights and bias
                for j in range(n_features):
                    grad = error * row[j] + self.l2_lambda * self.weights[j]
                    self.weights[j] -= self.learning_rate * grad

                self.bias -= self.learning_rate * error

        self._is_fitted = True

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        """Probability estimates."""
        if not self._is_fitted:
            raise RuntimeError("Model has not been fitted yet.")

        n_features = len(self.weights)
        probas: List[float] = []
        for row in X:
            if len(row) != n_features:
                raise ValueError("Mismatch in number of features.")

            z = self.bias
            for j in range(n_features):
                z += self.weights[j] * row[j]

            probas.append(sigmoid(z))

        return probas
