"""Lightweight observed Markov regime baseline, not an HMM or oracle.

The states are determined from lagged closes and fixed, declared thresholds;
transition probabilities are estimated from past states only. This does NOT
predict price direction. It describes whether today's conditions resemble a
quiet, directional, or volatile regime, with substantial model uncertainty.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence
import numpy as np

REGIMES = ('QUIET', 'TRENDING', 'STRESS')


def observed_regime(closes: Sequence[float], *, lookback: int = 20,
                    stress_vol_per_bar: float = 0.025,
                    trend_mean_per_bar: float = 0.003) -> str:
    if lookback < 3 or len(closes) < lookback + 1:
        raise ValueError('more historical closes are needed')
    p = np.asarray(closes[-(lookback + 1):], dtype=float)
    if not np.all(np.isfinite(p)) or np.any(p <= 0):
        raise ValueError('valid positive prices required')
    if not (isfinite(stress_vol_per_bar) and isfinite(trend_mean_per_bar)) or stress_vol_per_bar <= 0 or trend_mean_per_bar <= 0:
        raise ValueError('positive regime thresholds required')
    r = np.diff(np.log(p))
    if np.std(r, ddof=1) >= stress_vol_per_bar:
        return 'STRESS'
    if abs(np.mean(r)) >= trend_mean_per_bar:
        return 'TRENDING'
    return 'QUIET'


@dataclass(frozen=True)
class RegimeSnapshot:
    asof_index: int
    current_regime: str
    next_regime_probabilities: dict[str, float]
    transition_counts: tuple[tuple[int, ...], ...]
    training_observations: int
    research_only: bool = True


def estimate_regime_transitions(closes: Sequence[float], *, lookback: int = 20,
                                laplace_alpha: float = 1.0,
                                stress_vol_per_bar: float = 0.025,
                                trend_mean_per_bar: float = 0.003) -> RegimeSnapshot:
    """Fit on the supplied historical close prefix, including no future bars.

    To evaluate a past decision at index t, call with closes[:t+1].
    Smoothing avoids absolute certainty when observations are scarce.
    """
    if len(closes) < lookback + 3 or not isfinite(laplace_alpha) or laplace_alpha <= 0:
        raise ValueError('insufficient history or nonpositive smoothing')
    labels = [observed_regime(closes[:i + 1], lookback=lookback,
                  stress_vol_per_bar=stress_vol_per_bar,
                  trend_mean_per_bar=trend_mean_per_bar)
              for i in range(lookback, len(closes))]
    counts = np.zeros((3,3), dtype=int)
    for a,b in zip(labels, labels[1:]):
        counts[REGIMES.index(a),REGIMES.index(b)] += 1
    current = labels[-1]
    row = counts[REGIMES.index(current)].astype(float) + laplace_alpha
    probs = row / row.sum()
    return RegimeSnapshot(
        asof_index=len(closes)-1,
        current_regime=current,
        next_regime_probabilities={name:float(x) for name,x in zip(REGIMES,probs)},
        transition_counts=tuple(tuple(int(x) for x in row) for row in counts),
        training_observations=len(labels),
    )
