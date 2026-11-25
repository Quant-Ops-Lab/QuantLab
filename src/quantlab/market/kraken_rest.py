"""Public Kraken spot market data: OHLC candles and top-of-book ticker.

No API key, no local synthetic fallback; last Kraken candle is unfinished.
Ticker bid/ask is the executable quote used by the spread filter. The ticker
payload has no exchange timestamp, so callers must treat observed_at as the
fetch time and reject quotes older than their freshness window.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
import json
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from quantlab.console.charts import Candle

PAIRS={'BTC/USD':'XBTUSD','ETH/USD':'ETHUSD','SOL/USD':'SOLUSD','XRP/USD':'XRPUSD'}
INTERVAL={'1m':1,'5m':5,'15m':15,'1h':60,'1d':1440}

class KrakenDataError(RuntimeError):pass

@dataclass(frozen=True)
class TickerQuote:
    pair: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    observed_at: datetime

    def __post_init__(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError('ticker timestamp requires timezone')
        if self.bid <= 0 or self.ask < self.bid or self.last <= 0:
            raise ValueError('invalid ticker prices')

class KrakenPublic:
    def __init__(self,opener=None):self.opener=opener or urlopen

    def ohlc(self,pair:str='BTC/USD',timeframe:str='5m')->list[Candle]:
        if pair not in PAIRS or timeframe not in INTERVAL:raise ValueError('unsupported pair/timeframe')
        url='https://api.kraken.com/0/public/OHLC?'+urlencode({'pair':PAIRS[pair],'interval':INTERVAL[timeframe]})
        try:
            with self.opener(Request(url,headers={'User-Agent':'QuantLab/0.5 research'}),timeout=12) as response:
                doc=json.loads(response.read().decode('utf-8'))
        except Exception as exc:raise KrakenDataError('Kraken OHLC access failed: '+type(exc).__name__) from None
        if not isinstance(doc,dict) or doc.get('error'):
            raise KrakenDataError('Kraken reported an error')
        result=doc.get('result') or {}
        keys=[k for k in result if k!='last']
        if len(keys)!=1 or not isinstance(result[keys[0]],list):raise KrakenDataError('Kraken OHLC response invalid')
        out=[]
        for row in result[keys[0]][:-1]:  # explicitly discard unfinished most-recent candle
            try:
                ts=datetime.fromtimestamp(int(row[0]),tz=timezone.utc)
                o,h,l,c=[float(Decimal(str(row[i]))) for i in (1,2,3,4)]
                if 0<l<=min(o,c)<=max(o,c)<=h:
                    out.append(Candle(ts,o,h,l,c,int(row[7]),float(Decimal(str(row[6])))))
            except (IndexError,ArithmeticError,ValueError,TypeError):continue
        return out

    def ticker(self, pair: str, now: datetime | None = None) -> TickerQuote:
        """Best bid/ask from the public Ticker endpoint. No key required."""
        if pair not in PAIRS:
            raise ValueError('unsupported pair')
        observed = now or datetime.now(timezone.utc)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError('ticker timestamp requires timezone')
        url = 'https://api.kraken.com/0/public/Ticker?' + urlencode({'pair': PAIRS[pair]})
        try:
            with self.opener(Request(url, headers={'User-Agent': 'QuantLab/0.5 research'}), timeout=12) as response:
                doc = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            raise KrakenDataError('Kraken ticker access failed: ' + type(exc).__name__) from None
        if not isinstance(doc, dict) or doc.get('error'):
            raise KrakenDataError('Kraken reported an error')
        result = doc.get('result') or {}
        if len(result) != 1:
            raise KrakenDataError('Kraken ticker response invalid')
        row = next(iter(result.values()))
        try:
            bid = Decimal(str(row['b'][0]))
            ask = Decimal(str(row['a'][0]))
            last = Decimal(str(row['c'][0]))
        except (KeyError, IndexError, ArithmeticError, TypeError, ValueError):
            raise KrakenDataError('Kraken ticker response invalid') from None
        if bid <= 0 or ask < bid or last <= 0:
            raise KrakenDataError('Kraken ticker prices invalid')
        return TickerQuote(pair, bid, ask, last, observed)
