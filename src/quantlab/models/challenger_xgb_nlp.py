"""Point-in-time FinBERT/FinTwitBERT features and calibrated XGBoost challenger.

This module is research-only. It never submits orders, chooses allocation, or
changes execution policy. The heavy model dependencies are project requirements,
but model downloads and inference stay out of Streamlit request handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import xgboost as xgb


@dataclass(frozen=True)
class NLPModelConfig:
    finbert_id: str = "ProsusAI/finbert"
    fintwit_id: str = "StephanAkkerman/FinTwitBERT-sentiment"
    device: Optional[str] = None
    batch_size: int = 64


class DualFinancialNLPEncoder:
    """Score verified event text using receipt-time windows only."""

    def __init__(self, config: NLPModelConfig = NLPModelConfig()) -> None:
        if config.batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.config = config
        self.device = config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.finbert_tokenizer = AutoTokenizer.from_pretrained(config.finbert_id)
        self.finbert = AutoModelForSequenceClassification.from_pretrained(config.finbert_id).to(self.device).eval()
        self.fintwit_tokenizer = AutoTokenizer.from_pretrained(config.fintwit_id)
        self.fintwit = AutoModelForSequenceClassification.from_pretrained(config.fintwit_id).to(self.device).eval()

    @torch.inference_mode()
    def _score(self, texts: Sequence[str], tokenizer, model, positive: int, negative: int) -> np.ndarray:
        text_list = list(texts)
        if not text_list:
            return np.empty(0, dtype=np.float64)
        scores = []
        for start in range(0, len(text_list), self.config.batch_size):
            batch = tokenizer(text_list[start:start + self.config.batch_size], padding=True,
                              truncation=True, max_length=256, return_tensors="pt").to(self.device)
            probabilities = softmax(model(**batch).logits.cpu().numpy(), axis=1)
            scores.append(probabilities[:, positive] - probabilities[:, negative])
        return np.concatenate(scores, axis=0)

    def extract_point_in_time_features(self, bars_df: pd.DataFrame, events_df: pd.DataFrame,
                                       lookback_window: str = "30min") -> pd.DataFrame:
        required = {"receipt_timestamp", "source_type", "text"}
        if not required.issubset(events_df.columns):
            raise ValueError(f"events_df requires {sorted(required)}")
        out = pd.DataFrame(index=bars_df.index)
        for column in ("finbert_net_mean", "finbert_event_count", "fintwit_net_mean",
                       "fintwit_net_std", "fintwit_velocity"):
            out[column] = 0.0
        out["nlp_missing_flag"] = 1.0
        if events_df.empty or bars_df.empty:
            return out
        events = events_df.copy()
        events["receipt_timestamp"] = pd.to_datetime(events["receipt_timestamp"], utc=True)
        events = events.sort_values("receipt_timestamp")
        formal = events["source_type"].isin(["SEC_EDGAR", "RSS_OFFICIAL"])
        social = events["source_type"].isin(["X_GROK", "TELEGRAM", "DEX_SOCIAL"])
        events["polarity"] = 0.0
        events.loc[formal, "polarity"] = self._score(events.loc[formal, "text"].astype(str), self.finbert_tokenizer, self.finbert, 0, 1)
        events.loc[social, "polarity"] = self._score(events.loc[social, "text"].astype(str), self.fintwit_tokenizer, self.fintwit, 2, 0)
        window = pd.Timedelta(lookback_window)
        bar_timestamps_utc = pd.to_datetime(bars_df.index, utc=True)
        receipt_ns = events["receipt_timestamp"].astype("int64").to_numpy()
        sources = events["source_type"].to_numpy()
        polarities = events["polarity"].to_numpy(dtype=np.float64)
        for original_index, timestamp in zip(bars_df.index, bar_timestamps_utc):
            left = int(np.searchsorted(receipt_ns, (timestamp - window).value, side="right"))
            right = int(np.searchsorted(receipt_ns, timestamp.value, side="right"))
            if left >= right:
                continue
            out.loc[original_index, "nlp_missing_flag"] = 0.0
            window_sources = sources[left:right]
            window_polarities = polarities[left:right]
            formal_values = window_polarities[np.isin(window_sources, ["SEC_EDGAR", "RSS_OFFICIAL"])]
            social_values = window_polarities[np.isin(window_sources, ["X_GROK", "TELEGRAM", "DEX_SOCIAL"])]
            if formal_values.size:
                out.loc[original_index, "finbert_net_mean"] = float(np.mean(formal_values))
                out.loc[original_index, "finbert_event_count"] = float(len(formal_values))
            if social_values.size:
                out.loc[original_index, "fintwit_net_mean"] = float(np.mean(social_values))
                out.loc[original_index, "fintwit_net_std"] = float(np.std(social_values, ddof=0))
                out.loc[original_index, "fintwit_velocity"] = float(len(social_values))
        return out


class CalibratedXGBChallenger:
    """Fit-only calibrated XGBoost classifier for chronological research folds."""

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = None

    def fit(self, X_train: Sequence[Sequence[float]], y_train: Sequence[int]) -> "CalibratedXGBChallenger":
        X = self.scaler.fit_transform(np.asarray(X_train, dtype=float))
        y = np.asarray(y_train, dtype=int)
        classes, counts = np.unique(y, return_counts=True)
        if len(classes) < 2:
            raise ValueError("challenger training requires both classes")
        base = xgb.XGBClassifier(n_estimators=120, max_depth=3, learning_rate=0.05,
                                 subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
                                 reg_lambda=2.0, eval_metric="logloss", n_jobs=1,
                                 random_state=self.random_state)
        if int(counts.min()) >= 3:
            self.model = CalibratedClassifierCV(estimator=base, method="sigmoid",
                                                cv=min(3, int(counts.min())))
            self.model.fit(X, y)
        else:
            base.fit(X, y)
            self.model = base
        return self

    def predict_proba(self, X: Sequence[Sequence[float]]) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("fit the challenger on a training fold first")
        return self.model.predict_proba(self.scaler.transform(np.asarray(X, dtype=float)))
