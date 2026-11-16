"""Point-in-time price features, with distinct forward **training** labels.

The returned feature for t uses only bars at or before t. Labels require a
fully observed future interval; don't use labels for online predictions.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class Bar:
    asof: datetime
    close: float
    volume: float | None

    def __post_init__(self) -> None:
        if self.asof.tzinfo is None or self.asof.utcoffset() is None:
            raise ValueError("bar timestamp must be timezone-aware")
        if not isfinite(self.close) or self.close <= 0:
            raise ValueError("close must be finite and positive")
        if self.volume is not None and (not isfinite(self.volume) or self.volume < 0):
            raise ValueError("volume must be nonnegative or explicitly missing")


@dataclass(frozen=True)
class Example:
    feature_time: datetime
    label_end_time: datetime
    features: tuple[float, ...]
    label_net_return: float


def examples(bars: Sequence[Bar], lookback: int = 3, horizon: int = 1,
             costs_bps: float = 2.0) -> list[Example]:
    if lookback < 2 or horizon < 1 or costs_bps < 0:
        raise ValueError("invalid lookback, horizon or costs")
    if any(a.asof >= b.asof for a, b in zip(bars, bars[1:])):
        raise ValueError("timestamps must be strictly increasing")
    result: list[Example] = []
    # The last horizon bars cannot be labeled: their future is not known.
    for t in range(lookback, len(bars) - horizon):
        now = bars[t]
        previous = bars[t - 1]
        oldest = bars[t - lookback]
        past_volumes = [b.volume for b in bars[t - lookback:t]]
        has_volume = now.volume is not None and all(v is not None for v in past_volumes)
        mean_past_vol = sum(v for v in past_volumes if v is not None) / lookback if has_volume else 0.0
        volume_ratio = (now.volume / mean_past_vol if mean_past_vol > 0 and now.volume is not None else 0.0)
        feat = (
            now.close / previous.close - 1.0,
            now.close / oldest.close - 1.0,
            volume_ratio if has_volume else 0.0,
            0.0 if has_volume and mean_past_vol > 0 else 1.0,  # missing/invalid measurement flag
        )
        future = bars[t + horizon]
        target = future.close / now.close - 1.0 - costs_bps / 10000.0
        result.append(Example(now.asof, future.asof, feat, target))
    return result
