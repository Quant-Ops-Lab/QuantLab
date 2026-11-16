"""Persistent read-only Public quote monitor; periodically collects curated assets.

Live signals are evidence for a strategy, not orders. This is a polling MVP,
not an HFT infrastructure. Quote freshness is evaluated per provider timestamp.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import json
import logging
import os
import signal
from quantlab.services.storage import connect,bind,is_postgres
import time
from quantlab.execution.public_api import PublicBroker
from quantlab.universe.catalog import default_universe
from quantlab.control.notifications import JsonlPublisher,SNSEventPublisher,FanoutPublisher,TOPIC_ALERT
from pathlib import Path

LOG=logging.getLogger(__name__)

@dataclass(frozen=True)
class MarketQuote:
    symbol:str
    last:Decimal
    bid:Decimal
    ask:Decimal
    timestamp:datetime
    previous_close:Decimal|None

    @property
    def day_change_pct(self)->Decimal|None:
        if self.previous_close is None or self.previous_close<=0:return None
        return (self.last/self.previous_close-1)*Decimal(100)


def decode_quote(raw:dict,now:datetime|None=None,max_age:timedelta=timedelta(minutes=10))->MarketQuote:
    if raw.get('outcome')!='SUCCESS':raise ValueError('quote provider did not return success')
    symbol=raw.get('instrument',{}).get('symbol')
    if not symbol:raise ValueError('missing instrument symbol')
    dt=datetime.fromisoformat(raw['lastTimestamp'].replace('Z','+00:00'))
    now=now or datetime.now(timezone.utc)
    if dt.tzinfo is None or dt>now+timedelta(seconds=15) or now-dt>max_age:
        raise ValueError('stale or invalid quote timestamp')
    last=Decimal(str(raw['last']))
    bid=Decimal(str(raw['bid']))
    ask=Decimal(str(raw['ask']))
    if min(last,bid,ask)<=0 or ask<bid:raise ValueError('bad quote prices')
    prev=raw.get('previousClose')
    return MarketQuote(symbol,last,bid,ask,dt,Decimal(str(prev)) if prev else None)


class QuoteJournal:
    def __init__(self,db_path):
        self.db_path=db_path
        with connect(db_path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS market_quotes (
                symbol TEXT NOT NULL, provider_timestamp TEXT NOT NULL,
                fetched_at TEXT NOT NULL, last TEXT NOT NULL,bid TEXT NOT NULL,
                ask TEXT NOT NULL,previous_close TEXT,
                PRIMARY KEY(symbol,provider_timestamp))''')

    def record(self,q:MarketQuote,now:datetime|None=None)->bool:
        now=now or datetime.now(timezone.utc)
        with connect(self.db_path) as db:
            sql=('''INSERT INTO market_quotes VALUES (%s,%s,%s,%s,%s,%s,%s)
                 ON CONFLICT (symbol,provider_timestamp) DO NOTHING''' if is_postgres(self.db_path) else
                 '''INSERT OR IGNORE INTO market_quotes VALUES (?,?,?,?,?,?,?)''')
            result=db.execute(sql,
                (q.symbol,q.timestamp.isoformat(),now.isoformat(),str(q.last),str(q.bid),
                 str(q.ask),str(q.previous_close) if q.previous_close is not None else None))
            return result.rowcount==1

    def latest(self,limit=150)->list[dict]:
        with connect(self.db_path) as db:
            sql=('''SELECT DISTINCT ON (symbol) symbol,provider_timestamp,last,bid,ask,previous_close
                 FROM market_quotes ORDER BY symbol,provider_timestamp DESC LIMIT %s''' if is_postgres(self.db_path)
                 else '''SELECT symbol,provider_timestamp,last,bid,ask,previous_close
                 FROM market_quotes WHERE (symbol,provider_timestamp) IN
                  (SELECT symbol,MAX(provider_timestamp) FROM market_quotes GROUP BY symbol)
                 ORDER BY symbol LIMIT ?''')
            cur=db.execute(sql,(limit,))
            return [dict(zip(('symbol','timestamp','last','bid','ask','previous_close'),row)) for row in cur]

    def history(self,symbol:str,limit:int=500)->list[dict]:
        """Timestamped quote snapshots, not authoritative exchange OHLC bars."""
        if not symbol or len(symbol)>15 or not all(c.isalnum() or c in '.-' for c in symbol):
            raise ValueError('invalid symbol')
        limit=min(10000,max(1,int(limit)))
        with connect(self.db_path) as db:
            sql=f'''SELECT provider_timestamp,last,bid,ask FROM market_quotes
                WHERE symbol={bind(self.db_path)} ORDER BY provider_timestamp DESC
                LIMIT {bind(self.db_path)}'''
            rows=db.execute(sql,(symbol,limit)).fetchall()
            return [dict(timestamp=r[0],last=r[1],bid=r[2],ask=r[3]) for r in reversed(rows)]


class MarketPoller:
    def __init__(self,broker:PublicBroker,journal:QuoteJournal,symbols:list[str],batch:int=15,
                 publisher=None,alert_change_pct:Decimal=Decimal('5')):
        self.broker,self.journal,self.symbols,self.batch=broker,journal,symbols,batch
        self.publisher=publisher
        self.alert_change_pct=alert_change_pct
        if not (1<=batch<=50):raise ValueError('invalid batch')

    def cycle(self,now:datetime|None=None)->dict:
        now=now or datetime.now(timezone.utc)
        accepted=ignored=0
        problems=[]
        for i in range(0,len(self.symbols),self.batch):
            symbols=self.symbols[i:i+self.batch]
            try:
                result=self.broker.quotes(symbols)
                for raw in result.get('quotes',[]):
                    try:
                        quote=decode_quote(raw,now)
                        if quote.symbol not in symbols:raise ValueError('unrequested symbol')
                        recorded=self.journal.record(quote,now)
                        accepted+=int(recorded)
                        change=quote.day_change_pct
                        if recorded and self.publisher is not None and change is not None and abs(change)>=self.alert_change_pct:
                            try:
                                self.publisher.publish(TOPIC_ALERT,{
                                    'symbol':quote.symbol,'kind':'LARGE_DAILY_MOVE','change_pct':str(change),
                                    'source':'public_quotes','asof_utc':quote.timestamp.isoformat(),
                                    'message':'Price movement alert, not a validated entry or exit.'})
                            except Exception as e:problems.append(f'publish:{type(e).__name__}')
                    except (ValueError,KeyError,ArithmeticError) as exc:
                        ignored+=1
                        problems.append(f'{raw.get("instrument",{}).get("symbol","?")}:{type(exc).__name__}')
            except Exception as exc:
                problems.append(f'batch-{i}:{type(exc).__name__}')
        return dict(accepted=accepted,ignored=ignored,problems=problems)


def main():
    logging.basicConfig(level=logging.INFO)
    key=os.getenv('PUBLIC_API_TOKEN','')
    account_id=os.getenv('PUBLIC_ACCOUNT_ID','')
    if not(key and account_id):raise RuntimeError('PUBLIC_API_TOKEN and PUBLIC_ACCOUNT_ID required')
    db_path=os.getenv('QUANTLAB_MARKET_DB','artifacts/market.sqlite')
    os.makedirs(os.path.dirname(db_path) or '.',exist_ok=True)
    symbols=list(default_universe())
    publishers=[JsonlPublisher(Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl')))]
    if os.getenv('QUANTLAB_SNS_TOPIC_ARN'):
        publishers.append(SNSEventPublisher(os.environ['QUANTLAB_SNS_TOPIC_ARN']))
    poller=MarketPoller(PublicBroker(account_id,key),QuoteJournal(db_path),symbols,
                        publisher=FanoutPublisher(*publishers))
    seconds=max(30,int(os.getenv('QUOTE_POLL_SECONDS','60')))
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    while not stopped:
        LOG.info('quote cycle: %s',poller.cycle())
        for _ in range(seconds):
            if stopped:break
            time.sleep(1)

if __name__=='__main__':main()
