"""Reverse-line-movement-inspired *research observation* for equities.

No brokerage action and no claim to detect insider or institutional activity.
Requires observed positioning; not inferred from price or text alone.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class PositioningObservation:
    timestamp: datetime
    symbol: str
    reference_price: float
    last_price: float
    retail_long_fraction: float | None
    relative_volume: float | None
    independent_venue_confirms: bool | None


@dataclass(frozen=True)
class Divergence:
    flagged: bool
    direction: str
    reasons: tuple[str, ...]


def observe_divergence(obs: PositioningObservation,
                       min_move_pct: float = 0.3,
                       min_relative_volume: float = 1.5) -> Divergence:
    if obs.timestamp.tzinfo is None or obs.timestamp.utcoffset() is None:
        return Divergence(False, 'none', ('timestamp_missing_timezone',))
    if (not isfinite(obs.reference_price) or obs.reference_price <= 0
        or not isfinite(obs.last_price) or obs.last_price <= 0):
        return Divergence(False, 'none', ('invalid_price',))
    if (obs.retail_long_fraction is None or obs.relative_volume is None
        or obs.independent_venue_confirms is None):
        return Divergence(False, 'none', ('required_data_missing',))
    if (not 0 <= obs.retail_long_fraction <= 1 or not isfinite(obs.relative_volume)
        or obs.relative_volume < 0):
        return Divergence(False, 'none', ('invalid_positioning_or_volume',))
    move_pct = (obs.last_price / obs.reference_price - 1) * 100
    contra_bearish = obs.retail_long_fraction >= 0.60 and move_pct <= -min_move_pct
    contra_bullish = obs.retail_long_fraction <= 0.40 and move_pct >= min_move_pct
    if not (contra_bearish or contra_bullish):
        return Divergence(False, 'none', ('no_counter_positioning_move',))
    if obs.relative_volume < min_relative_volume or not obs.independent_venue_confirms:
        return Divergence(False, 'none', ('insufficient_independent_confirmation',))
    direction = 'bearish_divergence' if contra_bearish else 'bullish_divergence'
    return Divergence(True, direction,
                      ('observed_positioning_opposed_price', 'relative_volume_confirmed',
                       'independent_market_confirmation'))
