"""Persistent interpretation worker using verified Kraken OHLC bars.

Creates candidate plans and alerts, NEVER market orders. Broker-agnostic
approval/execution lives in its own service; unattended shipping requires
validated prices, account reconciliation and a scoped consent grant.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import signal
import time
from quantlab.market.kraken_rest import KrakenPublic,TickerQuote
from quantlab.signals.entry import MarketFrame,SignalPolicy,propose
from quantlab.control.notifications import TOPIC_ALERT
from quantlab.services.publishers import build_publisher

log=logging.getLogger(__name__)


def frame_from_ohlc(pair,bars,quote:TickerQuote,now=None,max_quote_age_seconds:int=20):
    if len(bars)<22:raise ValueError('need 22 completed candles')
    if quote is None or quote.pair!=pair:raise ValueError('ticker quote unavailable')
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:raise ValueError('clock must be timezone aware')
    if quote.observed_at>now+timedelta(seconds=3) or now-quote.observed_at>timedelta(seconds=max_quote_age_seconds):
        raise ValueError('ticker quote is stale')
    recent=bars[-21:]
    prices=[Decimal(str(x.close)) for x in recent]
    true_ranges=[Decimal(str(x.high-x.low)) for x in recent]
    atr=sum(true_ranges[-14:])/Decimal('14')
    if atr<=0:raise ValueError('ATR unavailable')
    # Kraken OHLC volume is the traded base asset, not trade count.
    if any(x.volume is None for x in recent):raise ValueError('market volume unavailable')
    vols=[Decimal(str(x.volume)) for x in recent]
    average=sum(vols[:-1])/Decimal(len(vols)-1)
    ratio=vols[-1]/average if average>0 else Decimal('0')
    momentum=(prices[-1]/prices[-5]-1)*Decimal('10000')
    # Spread uses the public ticker, not the candle close. A zero spread from
    # bid=ask=close would hide an untradeable book.
    return MarketFrame(pair,quote.last,quote.bid,quote.ask,atr,ratio,momentum,recent[-1].start,'kraken_rest_ticker','crypto')

class CryptoEntryWorker:
    def __init__(self,market:KrakenPublic,publisher:JsonlPublisher,pairs:tuple[str,...]):
        self.market,self.publisher,self.pairs=market,publisher,pairs
        self.last_sent=set()
    def cycle(self,now=None):
        now=now or datetime.now(timezone.utc)
        results=[]
        for pair in self.pairs:
            try:
                candles=self.market.ohlc(pair,'1m')
                quote=self.market.ticker(pair,now)
                frame=frame_from_ohlc(pair,candles,quote,now)
                # Completed 1m bar available only after next bar starts.
                frame=MarketFrame(frame.symbol,frame.price,frame.bid,frame.ask,frame.atr,
                      frame.volume_ratio,frame.momentum_bps,frame.observed_at.replace(second=0),frame.venue,frame.asset)
                decision=propose(frame,[],SignalPolicy(market_freshness_seconds=180),now)
                if decision.status=='CANDIDATE' and decision.signal_id not in self.last_sent:
                    self.publisher.publish(TOPIC_ALERT,{'kind':'TRADE_CANDIDATE','signal':decision.to_dict(),
                        'execution':'NOT_AUTHORIZED','note':'Public ticker snapshot is not an authorized order'})
                    self.last_sent.add(decision.signal_id)
                results.append(decision)
            except Exception as exc:
                log.warning('crypto worker %s: %s',pair,type(exc).__name__)
        if len(self.last_sent)>1000:self.last_sent.clear()
        return results

def main():
    logging.basicConfig(level=logging.INFO)
    poll=max(15,int(os.getenv('QUANTLAB_CRYPTO_POLL_SECONDS','30')))
    pairs=tuple(x.strip() for x in os.getenv('QUANTLAB_CRYPTO_PAIRS','BTC/USD,ETH/USD').split(',') if x.strip())
    publisher=build_publisher()
    worker=CryptoEntryWorker(KrakenPublic(),publisher,pairs)
    stop=False
    def halt(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGINT,halt);signal.signal(signal.SIGTERM,halt)
    while not stop:
        worker.cycle()
        for _ in range(poll):
            if stop:break
            time.sleep(1)

if __name__=='__main__':main()
