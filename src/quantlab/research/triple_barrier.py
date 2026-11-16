"""Outcome labels for meta-classification: target first, stop first, or timeout.

Conservative when both barriers are crossed in one OHLC bar: STOP wins.
Without ticks, we cannot know the intra-bar order. Labels are for historical
supervised training; they must NEVER be used as an online feature.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class OHLC:
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self):
        p=(self.open,self.high,self.low,self.close)
        if any(not isfinite(x) or x<=0 for x in p) or self.low>min(self.open,self.close) or self.high<max(self.open,self.close):
            raise ValueError('malformed OHLC bar')


@dataclass(frozen=True)
class Outcome:
    label: str  # TARGET, STOP, TIMEOUT
    bars_to_exit: int
    realized_net_return: float
    intrabar_ambiguous: bool
    exit_price: float


def label_trade(*, entry: float, stop: float, target: float, bars: Sequence[OHLC],
                direction: str='LONG', round_trip_cost_bps: float=5) -> Outcome:
    if direction not in ('LONG','SHORT') or not all(isfinite(v) for v in (entry,stop,target,round_trip_cost_bps)):
        raise ValueError('invalid trade parameters')
    if round_trip_cost_bps<0 or not bars:
        raise ValueError('costs must be nonnegative and future bars nonempty')
    if direction == 'LONG' and not (0<stop<entry<target):
        raise ValueError('LONG needs stop < entry < target')
    if direction == 'SHORT' and not (0<target<entry<stop):
        raise ValueError('SHORT needs target < entry < stop')
    sign=1 if direction=='LONG' else -1
    for i,bar in enumerate(bars,1):
        hit_stop=bar.low<=stop if direction=='LONG' else bar.high>=stop
        hit_target=bar.high>=target if direction=='LONG' else bar.low<=target
        if hit_stop:
            # Stop order can fill worse than stop if market opens through it.
            price=min(stop,bar.open) if direction=='LONG' else max(stop,bar.open)
            return Outcome('STOP',i,sign*(price/entry-1)-round_trip_cost_bps/10000,hit_target,price)
        if hit_target:
            return Outcome('TARGET',i,sign*(target/entry-1)-round_trip_cost_bps/10000,False,target)
    price=bars[-1].close
    return Outcome('TIMEOUT',len(bars),sign*(price/entry-1)-round_trip_cost_bps/10000,False,price)
