"""Deterministic trade plans with independent price, volume and news evidence.

Plans are *candidates*, not forecasts of assured profit. An LLM may explain
these objects but is never consulted to choose size, stop or order direction.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import math

class Direction(StrEnum):
    LONG = 'LONG'
    SHORT = 'SHORT'
    NONE = 'NONE'

@dataclass(frozen=True)
class Evidence:
    source: str
    kind: str
    observed_at: datetime
    published_at: datetime
    verified: bool
    strength: float
    url: str = ''
    note: str = ''

    def __post_init__(self):
        for field in (self.observed_at, self.published_at):
            if field.tzinfo is None or field.utcoffset() is None:
                raise ValueError('evidence requires timezone aware timestamps')
        if not math.isfinite(self.strength) or not -1 <= self.strength <= 1:
            raise ValueError('evidence strength must be -1..1')

@dataclass(frozen=True)
class MarketFrame:
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    atr: Decimal
    volume_ratio: Decimal
    momentum_bps: Decimal
    observed_at: datetime
    venue: str
    asset: str = 'equity'

    def __post_init__(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError('market timestamp requires timezone')
        if self.price <= 0 or self.bid <= 0 or self.ask < self.bid or self.atr <= 0:
            raise ValueError('invalid market prices / ATR')
        if self.volume_ratio < 0 or self.asset not in ('equity','crypto'):
            raise ValueError('invalid volume ratio or asset')

@dataclass(frozen=True)
class EntryPlan:
    signal_id: str
    symbol: str
    direction: Direction
    status: str
    entry: Decimal|None
    stop: Decimal|None
    take_profit: Decimal|None
    shares: Decimal
    risk_dollars: Decimal
    asof: datetime
    evidence: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self):
        out=asdict(self)
        out['direction']=self.direction.value
        out['asof']=self.asof.isoformat()
        for k in ('entry','stop','take_profit','shares','risk_dollars'):
            out[k]=str(getattr(self,k)) if getattr(self,k) is not None else None
        out['evidence']=list(self.evidence);out['reasons']=list(self.reasons)
        return out

@dataclass(frozen=True)
class SignalPolicy:
    market_freshness_seconds: int = 20
    evidence_freshness_seconds: int = 3600
    min_volume_ratio: Decimal = Decimal('1.25')
    minimum_momentum_bps: Decimal = Decimal('20')
    max_spread_bps: Decimal = Decimal('30')
    risk_budget: Decimal = Decimal('5')
    stop_atr: Decimal = Decimal('1.5')
    reward_atr: Decimal = Decimal('3')
    max_notional: Decimal = Decimal('150')
    require_confirmed_event: bool = False


def propose(frame:MarketFrame, evidence:list[Evidence], policy:SignalPolicy=SignalPolicy(), now:datetime|None=None)->EntryPlan:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('clock must be timezone aware')
    reasons=[]; accepted=[]
    if frame.observed_at > now+timedelta(seconds=2) or now-frame.observed_at>timedelta(seconds=policy.market_freshness_seconds):
        reasons.append('market feed is stale')
    spread_bps=(frame.ask-frame.bid)/frame.price*Decimal('10000')
    if spread_bps>policy.max_spread_bps:reasons.append('spread too wide')
    if frame.volume_ratio<policy.min_volume_ratio:reasons.append('insufficient relative volume')
    if abs(frame.momentum_bps)<policy.minimum_momentum_bps:reasons.append('momentum below threshold')
    if policy.require_confirmed_event:
        valid=[e for e in evidence if e.verified and e.published_at<=e.observed_at<=now and now-e.observed_at<=timedelta(seconds=policy.evidence_freshness_seconds)]
        if not valid: reasons.append('no recent independently verified public event')
        else: accepted=[f'{e.source}:{e.kind}:{e.url}' for e in valid]
    else:
        accepted=[f'{e.source}:{e.kind}:{e.url}' for e in evidence if e.verified and e.observed_at<=now and now-e.observed_at<=timedelta(seconds=policy.evidence_freshness_seconds)]
    # Rumor/unverified information never automatically supplies confirmation.
    move=Direction.LONG if frame.momentum_bps>0 else Direction.SHORT
    entry=frame.ask if move is Direction.LONG else frame.bid
    stop=(entry-policy.stop_atr*frame.atr if move is Direction.LONG else entry+policy.stop_atr*frame.atr)
    take=(entry+policy.reward_atr*frame.atr if move is Direction.LONG else entry-policy.reward_atr*frame.atr)
    if min(entry,stop,take)<=0:reasons.append('invalid calculated stop or target')
    per_unit=abs(entry-stop)
    if per_unit<=0 or policy.risk_budget<=0 or policy.max_notional<=0:
        reasons.append('invalid risk mandate');qty=Decimal('0')
    else:
        qty=min(policy.risk_budget/per_unit, policy.max_notional/entry).quantize(Decimal('0.000001'))
    if qty<=0:reasons.append('trade too small for mandate')
    signal_key=json.dumps({'symbol':frame.symbol,'venue':frame.venue,'time':frame.observed_at.isoformat(),'direction':move.value},sort_keys=True)
    sid=hashlib.sha256(signal_key.encode()).hexdigest()[:24]
    if reasons:
        return EntryPlan(sid,frame.symbol,Direction.NONE,'NO_TRADE',None,None,None,Decimal('0'),Decimal('0'),frame.observed_at,tuple(accepted),tuple(reasons))
    return EntryPlan(sid,frame.symbol,move,'CANDIDATE',entry,stop,take,qty,qty*per_unit,frame.observed_at,tuple(accepted),('price momentum and volume confirmed','plan requires broker and account validation','not a probability of profit'))
