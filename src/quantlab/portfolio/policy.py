"""Profit harvest and trailing-exit policy evaluated on broker-reconciled positions.

Decisions are candidates only; execution controller must check current broker
state and trading session. A 30% trailing stop is NOT a 30% guaranteed max loss.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum

D=lambda v: Decimal(str(v))

class Decision(StrEnum):
    HOLD='HOLD'
    TRIM='TRIM'
    EXIT='EXIT'

@dataclass(frozen=True)
class Position:
    symbol:str
    quantity:Decimal
    avg_cost:Decimal
    high_water:Decimal
    last_harvest_peak:Decimal|None=None
    initial_core_qty:Decimal|None=None

@dataclass(frozen=True)
class HarvestPolicy:
    take_profit_fraction:Decimal=D('0.20')
    trim_position_fraction:Decimal=D('0.25')
    trailing_drawdown_fraction:Decimal=D('0.30')
    preserve_core_fraction:Decimal=D('0.50')
    precision:Decimal=D('0.000001')

    def __post_init__(self):
        for x in (self.take_profit_fraction,self.trim_position_fraction,self.trailing_drawdown_fraction):
            if not (D('0')<x<D('1')):raise ValueError('percent fractions must be strictly between 0 and 1')
        if not(D('0')<=self.preserve_core_fraction<D('1')):raise ValueError('core fraction invalid')

@dataclass(frozen=True)
class PositionDecision:
    action:Decision
    shares:Decimal
    reason:str
    reference_price:Decimal


def evaluate_position(pos:Position,last_price:Decimal,policy:HarvestPolicy=HarvestPolicy())->PositionDecision:
    price=D(last_price)
    if min(price,pos.quantity,pos.avg_cost,pos.high_water)<=0:raise ValueError('nonpositive position/quote')
    peak=max(pos.high_water,price)
    if price <= peak*(D('1')-policy.trailing_drawdown_fraction):
        core_start=pos.initial_core_qty if pos.initial_core_qty is not None else D('0')
        core_qty=min(pos.quantity,core_start*policy.preserve_core_fraction)
        exit_qty=max(D('0'),pos.quantity-core_qty).quantize(policy.precision,rounding=ROUND_DOWN)
        if exit_qty<=0:
            return PositionDecision(Decision.HOLD,D('0'),'Preserved separately designated core position',price)
        return PositionDecision(Decision.EXIT,exit_qty,'Trailing decline from observed high water; execution not guaranteed',price)
    target=pos.avg_cost*(D('1')+policy.take_profit_fraction)
    if price<target:return PositionDecision(Decision.HOLD,D('0'),'Profit threshold not met',price)
    if price < peak*D('0.98'):
        return PositionDecision(Decision.HOLD,D('0'),'Not within 2% of previous observed peak',price)
    if pos.last_harvest_peak is not None and peak<=pos.last_harvest_peak:
        return PositionDecision(Decision.HOLD,D('0'),'Already harvested at this high-water level',price)
    core_start=pos.initial_core_qty if pos.initial_core_qty is not None else pos.quantity
    minimum_core=core_start*policy.preserve_core_fraction
    available=max(D('0'),pos.quantity-minimum_core)
    shares=min(pos.quantity*policy.trim_position_fraction,available)
    shares=shares.quantize(policy.precision,rounding=ROUND_DOWN)
    if shares<=0:return PositionDecision(Decision.HOLD,D('0'),'Core position floor',price)
    return PositionDecision(Decision.TRIM,shares,'Candidate partial profit harvest; taxable disposition',price)
