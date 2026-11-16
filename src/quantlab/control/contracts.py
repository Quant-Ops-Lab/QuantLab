"""Strict declarative contracts for approved operator workflows.

No arbitrary Python, broker credentials, or prompt-to-live-order bridge.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
import json
import hashlib

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")

class Mode(str, Enum):
    ALERT_ONLY = "alert_only"
    APPROVAL_REQUIRED = "approval_required"
    LIVE_BOUNDED = "live_bounded"

class Direction(str, Enum):
    LONG = "long"
    BEARISH = "bearish"

@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    description: str
    symbols: tuple[str, ...]
    direction: Direction
    mode: Mode
    threshold_bps: int = 30
    max_signal_age_seconds: int = 15
    version: int = 1

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{2,49}", self.strategy_id):
            raise ValueError("invalid strategy_id")
        if not self.description or len(self.description) > 2000:
            raise ValueError("missing or overly long description")
        if not self.symbols or len(self.symbols) > 20 or len(self.symbols) != len(set(self.symbols)):
            raise ValueError("symbols required, unique, maximum 20")
        if not all(_SYMBOL.fullmatch(s) for s in self.symbols):
            raise ValueError("invalid ticker symbol")
        if not isinstance(self.direction, Direction) or not isinstance(self.mode, Mode):
            raise ValueError("invalid direction or mode")
        if not (1 <= self.threshold_bps <= 1000):
            raise ValueError("threshold out of research range")
        if not (1 <= self.max_signal_age_seconds <= 300):
            raise ValueError("signal expiry out of range")
        if self.mode == Mode.LIVE_BOUNDED:
            raise ValueError("natural-language live bounded execution not implemented; use managed executor explicitly")

    def to_dict(self):
        return {'strategy_id':self.strategy_id, 'description':self.description,
                'symbols':list(self.symbols),'direction':self.direction.value,
                'mode':self.mode.value,'threshold_bps':self.threshold_bps,
                'max_signal_age_seconds':self.max_signal_age_seconds,'version':self.version}

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls,raw):
        if set(raw) != {'strategy_id','description','symbols','direction','mode',
                        'threshold_bps','max_signal_age_seconds','version'}:
            raise ValueError("unexpected or missing strategy fields")
        if type(raw['threshold_bps']) is not int or type(raw['max_signal_age_seconds']) is not int or type(raw['version']) is not int:
            raise ValueError('numeric fields must be integers')
        if raw['version']!=1 or not isinstance(raw['symbols'],list) or not all(isinstance(s,str) for s in raw['symbols']):
            raise ValueError('bad schema version or symbols')
        return cls(raw['strategy_id'],raw['description'],tuple(raw['symbols']),
                   Direction(raw['direction']),Mode(raw['mode']),
                   raw['threshold_bps'],raw['max_signal_age_seconds'],raw['version'])

@dataclass(frozen=True)
class SignalObservation:
    symbol: str
    asof_utc: datetime
    price_change_bps: float
    independent_confirmation: bool
    feed_source: str
    origin: str = "operator_input"

    def __post_init__(self):
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError('invalid observation symbol')
        if self.asof_utc.tzinfo is None or self.asof_utc.utcoffset() is None:
            raise ValueError('observation must be timezone aware')
        if not self.feed_source or not self.origin:
            raise ValueError('missing provenance')
        import math
        if not math.isfinite(self.price_change_bps):
            raise ValueError('invalid change')

@dataclass(frozen=True)
class AlertDecision:
    strategy_id: str
    symbol: str
    status: str
    explanation: str
    strategy_sha: str
    observation_source: str
    asof_utc: str

    def to_dict(self):
        return vars(self).copy()
