"""Optional challenger primitives for point-in-time NLP and model tournaments.

The default path is dependency-light and fit-only: no online weight mutation,
no model downloads, and no broker authority. Heavy transformer/XGBoost adapters
belong behind the optional ``ml`` extra and must be benchmarked against these
baselines before promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import exp, isfinite
from typing import Callable, Iterable, Mapping, Protocol, Sequence

import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class TextScorer(Protocol):
    def __call__(self, texts: Sequence[str], source_type: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class ReceiptEvent:
    text: str
    source_type: str
    receipt_timestamp: datetime
    verified: bool = True

    def __post_init__(self) -> None:
        if self.receipt_timestamp.tzinfo is None or self.receipt_timestamp.utcoffset() is None:
            raise ValueError("receipt_timestamp must be timezone aware")
        if not self.text.strip():
            raise ValueError("event text is required")


@dataclass(frozen=True)
class NLPFeatureRow:
    formal_mean: float
    formal_count: float
    social_mean: float
    social_std: float
    social_velocity: float
    missing_flag: float


FORMAL = frozenset({"SEC_EDGAR", "RSS_OFFICIAL"})
SOCIAL = frozenset({"X_GROK", "TELEGRAM", "DEX_SOCIAL"})


def receipt_time_features(
    bar_times: Iterable[datetime],
    events: Iterable[ReceiptEvent],
    scorer: TextScorer | None = None,
    lookback: timedelta = timedelta(minutes=30),
) -> list[NLPFeatureRow]:
    """Aggregate only events received before each bar timestamp.

    ``scorer`` is injected so the default system can use rules or a local model;
    it is never called for future events. Scores are expected in [-1, 1].
    """
    if lookback <= timedelta(0):
        raise ValueError("lookback must be positive")
    normalized_times = []
    for value in bar_times:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bar times must be timezone aware")
        normalized_times.append(value.astimezone(timezone.utc))
    normalized_events = sorted(events, key=lambda event: event.receipt_timestamp)
    scored: list[tuple[ReceiptEvent, float]] = []
    for event in normalized_events:
        score = 0.0 if scorer is None else float(scorer([event.text], event.source_type)[0])
        if not isfinite(score) or not -1.0 <= score <= 1.0:
            raise ValueError("event scores must be finite and in [-1, 1]")
        scored.append((event, score))
    rows = []
    for end in normalized_times:
        window = [(event, score) for event, score in scored
                  if end - lookback < event.receipt_timestamp.astimezone(timezone.utc) <= end
                  and event.verified]
        formal = [score for event, score in window if event.source_type in FORMAL]
        social = [score for event, score in window if event.source_type in SOCIAL]
        rows.append(NLPFeatureRow(
            formal_mean=float(np.mean(formal)) if formal else 0.0,
            formal_count=float(len(formal)),
            social_mean=float(np.mean(social)) if social else 0.0,
            social_std=float(np.std(social)) if social else 0.0,
            social_velocity=float(len(social)),
            missing_flag=0.0 if window else 1.0,
        ))
    return rows


def fit_sgd_challenger(X_train: Sequence[Sequence[float]], y_train: Sequence[int], *, alpha: float = 1e-4,
                       random_state: int = 42) -> Pipeline:
    """Fit an SGD logistic challenger on one chronological training fold."""
    if alpha <= 0 or len(X_train) != len(y_train) or len(set(y_train)) < 2:
        raise ValueError("training data needs matching rows, both classes, and positive alpha")
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("sgd", SGDClassifier(loss="log_loss", alpha=alpha, max_iter=1000,
                              tol=1e-3, random_state=random_state)),
    ])
    model.fit(np.asarray(X_train, dtype=float), np.asarray(y_train, dtype=int))
    return model


@dataclass(frozen=True)
class ModelWeightLedger:
    """Delayed credibility weights updated only after realized outcomes exist."""
    weights: Mapping[str, float]
    observations: Mapping[str, int]

    @classmethod
    def equal(cls, model_names: Iterable[str]) -> "ModelWeightLedger":
        names = tuple(dict.fromkeys(model_names))
        if not names:
            raise ValueError("at least one model is required")
        equal = 1.0 / len(names)
        return cls({name: equal for name in names}, {name: 0 for name in names})

    def update(self, realized_returns: Mapping[str, float], *, learning_rate: float = 0.05) -> "ModelWeightLedger":
        """Reward/penalize models after outcomes are known; never use future outcomes online."""
        if not 0 < learning_rate <= 1:
            raise ValueError("learning_rate must be in (0, 1]")
        scores = dict(self.weights)
        counts = dict(self.observations)
        for name, result in realized_returns.items():
            if name not in scores or not isfinite(float(result)):
                raise ValueError("unknown model or non-finite realized return")
            scores[name] = scores[name] * exp(learning_rate * float(result))
            counts[name] += 1
        total = sum(scores.values())
        if not isfinite(total) or total <= 0:
            raise ValueError("invalid model weight state")
        return ModelWeightLedger({name: value / total for name, value in scores.items()}, counts)

    def blend(self, probabilities: Mapping[str, float]) -> float:
        if set(probabilities) != set(self.weights):
            raise ValueError("probability models must match ledger models")
        if any(not 0 <= float(value) <= 1 for value in probabilities.values()):
            raise ValueError("probabilities must be in [0, 1]")
        return sum(self.weights[name] * float(probabilities[name]) for name in self.weights)
