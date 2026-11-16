"""Independent monitoring worker. Needs a trusted market-data adapter to operate.

The worker survives a closed browser when run as a supervised OS service/container.
It only publishes research alerts; no order-write adapter exists.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import time
from typing import Protocol
from .contracts import StrategySpec, SignalObservation
from .sdk import QuantLabClient

class VerifiedFeed(Protocol):
    """Implemented by audited broker/data-provider adapter, not by user JSON."""
    def latest(self,symbol:str) -> SignalObservation: ...

@dataclass(frozen=True)
class ScanResult:
    observed: int
    alerts: int
    rejected: int
    errors: tuple[str,...]

class MarketWorker:
    def __init__(self, feed: VerifiedFeed, client: QuantLabClient, strategies: tuple[StrategySpec,...]):
        if not strategies:
            raise ValueError('at least one validated strategy is required')
        self.feed=feed
        self.client=client
        self.strategies=strategies
    def scan_once(self, now_utc:datetime|None=None)->ScanResult:
        now=now_utc or datetime.now(timezone.utc)
        observed=alerts=rejected=0
        errors=[]
        for spec in self.strategies:
            for symbol in spec.symbols:
                try:
                    obs=self.feed.latest(symbol)
                    if obs.symbol != symbol or obs.origin != 'market_feed':
                        raise ValueError('unverified or mismatched feed observation')
                    observed+=1
                    dec=self.client.run_once(spec,obs,now)
                    if dec.status=='NO_ACTION':rejected+=1
                    else: alerts+=1
                except Exception as exc:
                    # Fail closed per-symbol; a worker error cannot place trades.
                    errors.append(f'{spec.strategy_id}:{symbol}:{type(exc).__name__}')
        return ScanResult(observed,alerts,rejected,tuple(errors))
    def run_forever(self,interval_seconds:float=15.0,stop=None):
        if not (1<=interval_seconds<=3600):
            raise ValueError('interval must be between 1 second and 1 hour')
        while stop is None or not stop.is_set():
            yield self.scan_once()
            if stop is None:time.sleep(interval_seconds)
            elif stop.wait(interval_seconds):break
