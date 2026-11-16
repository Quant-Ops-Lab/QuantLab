"""Stock/news streaming research worker — never submits orders.

Maintains a bounded in-memory candle window per ticker, publishes candidate
entry/stop/target data only when corroborated by fresh quote and volume.
"""
from __future__ import annotations
import asyncio
from collections import deque
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import logging
import os
from pathlib import Path
from quantlab.market.alpaca_stream import BarEvent,QuoteEvent,NewsEvent,stream
from quantlab.signals.entry import MarketFrame,SignalPolicy,propose
from quantlab.intelligence.context import interpret
from quantlab.control.notifications import TOPIC_ALERT,TOPIC_INTEL
from quantlab.services.publishers import build_publisher
from quantlab.services.market_schedule import equity_order_eligible, equity_phase

log=logging.getLogger(__name__)

class EquityInterpreter:
    def __init__(self,publisher):
        self.publisher=publisher
        self.bars={}
        self.quotes={}
        self.sent=set()

    def ingest(self,event,now=None):
        now=now or datetime.now(timezone.utc)
        if isinstance(event,NewsEvent):
            record=interpret(event.headline,event.summary,event.source,event.url,event.published_at,event.received_at,True)
            self.publisher.publish(TOPIC_INTEL,{'headline':record.headline,'themes':list(record.themes),
                 'treatment':record.treatment,'url':record.url,'source':event.source,
                 'symbols':list(event.symbols),'published_at':record.published_at.isoformat(),
                 'received_at':record.observed_at.isoformat()})
            return None
        if isinstance(event,QuoteEvent):
            self.quotes[event.symbol]=event
            return None
        if not isinstance(event,BarEvent):return None
        history=self.bars.setdefault(event.symbol,deque(maxlen=120))
        if history and event.start<=history[-1].start:
            if event.start==history[-1].start:history[-1]=event
            return None
        history.append(event)
        if len(history)<22:return None
        q=self.quotes.get(event.symbol)
        if q is None or now-q.observed_at>timedelta(seconds=30):return None
        candles=list(history)[-21:]
        last=candles[-1]
        true_ranges=[max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close))
                     for c,p in zip(candles[1:],candles[:-1])]
        atr=sum(true_ranges[-14:])/Decimal('14')
        volume_baseline=sum((Decimal(str(b.volume)) for b in candles[:-1]),Decimal(0))/Decimal('20')
        ratio=Decimal(last.volume)/volume_baseline if volume_baseline else Decimal('0')
        momentum=(last.close/candles[-5].close-Decimal(1))*Decimal('10000')
        frame=MarketFrame(last.symbol if hasattr(last,'symbol') else event.symbol,
                          (q.bid+q.ask)/2,q.bid,q.ask,atr,ratio,momentum,q.observed_at,'alpaca_iex','equity')
        result=propose(frame,[],SignalPolicy(),now)
        if result.status=='CANDIDATE' and result.signal_id not in self.sent:
            self.publisher.publish(TOPIC_ALERT,{'kind':'TRADE_CANDIDATE','signal':result.to_dict(),
                    'execution':'NOT_AUTHORIZED','session_phase':equity_phase(now).value,
                    'execution_eligible':equity_order_eligible(now),
                    'note':'Research entry requires independent broker preflight'})
            self.sent.add(result.signal_id)
        if len(self.sent)>2000:self.sent.clear()
        return result

async def main_async():
    key=os.getenv('APCA_API_KEY_ID','');secret=os.getenv('APCA_API_SECRET_KEY','')
    if not (key and secret):raise RuntimeError('Alpaca market-data credentials required')
    symbols=[s.strip().upper() for s in os.getenv('QUANTLAB_EQUITY_SYMBOLS','NVDA,AMD,MU,AVGO,TSM,MSFT').split(',') if s.strip()]
    if len(symbols)>15:raise ValueError('Cap initial free-tier stream symbol list at 15 for quotes and bars')
    publisher=build_publisher()
    interpreter=EquityInterpreter(publisher)
    async def market():
        async for event in stream(key,secret,'market',symbols):
            interpreter.ingest(event)
    async def news():
        async for event in stream(key,secret,'news',symbols):
            interpreter.ingest(event)
    await asyncio.gather(market(),news())

def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())

if __name__=='__main__':main()
