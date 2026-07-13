from __future__ import annotations

from typing import Any, Protocol

import numpy as np


class FeatureBuilder(Protocol):
    def build(self, samples: list[Any], feature_names: list[str]) -> np.ndarray: ...


class ObjectiveBuilder(Protocol):
    def build(self, samples: list[Any], target_metric: str) -> np.ndarray: ...


class SurrogateModelFactory(Protocol):
    def create(self, dimensions: int, *, random_seed: int, noise: float | None = None) -> Any: ...


class AcquisitionStrategy(Protocol):
    version: str
    def score(self, mean: np.ndarray, std: np.ndarray) -> np.ndarray: ...


class CandidateGenerator(Protocol):
    def generate(self, bounds: dict[str, list[float]], *, count: int, random_seed: int) -> np.ndarray: ...


class RecommendationRecorder(Protocol):
    def record_run(self, run: dict[str, Any]) -> None: ...


class UCBStrategy:
    version = "ucb-1.0"

    def __init__(self, beta: float = 1.5):
        self.beta = float(beta)

    def score(self, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
        return mean + self.beta * std


class ModelEvaluator:
    """Leakage-aware metric helpers; split generation stays explicit at the caller."""

    @staticmethod
    def metrics(y_true: np.ndarray, mean: np.ndarray, std: np.ndarray) -> dict[str, float]:
        y_true = np.asarray(y_true, dtype=float)
        mean = np.asarray(mean, dtype=float)
        std = np.maximum(np.asarray(std, dtype=float), 1e-9)
        errors = y_true - mean
        lower = mean - 1.96 * std
        upper = mean + 1.96 * std
        coverage = np.mean((y_true >= lower) & (y_true <= upper))
        nlpd = np.mean(0.5 * np.log(2 * np.pi * std**2) + 0.5 * (errors / std) ** 2)
        return {
            "mae": float(np.mean(np.abs(errors))),
            "rmse": float(np.sqrt(np.mean(errors**2))),
            "negative_log_predictive_density": float(nlpd),
            "prediction_interval_coverage": float(coverage),
            "uncertainty_calibration_error": float(abs(0.95 - coverage)),
            "mean_baseline_rmse": float(np.sqrt(np.mean((y_true - np.mean(y_true)) ** 2))),
        }

    @staticmethod
    def group_splits(groups: list[str], folds: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
        unique = list(dict.fromkeys(groups))
        if len(unique) < 2:
            return []
        fold_count = max(2, min(folds, len(unique)))
        result = []
        group_array = np.asarray(groups)
        for test_groups in np.array_split(np.asarray(unique, dtype=object), fold_count):
            test = np.flatnonzero(np.isin(group_array, test_groups))
            train = np.flatnonzero(~np.isin(group_array, test_groups))
            result.append((train, test))
        return result

