"""Public Kraken spot OHLC API: observed, exchange-native crypto candles.

No API key, no local synthetic fallback; last Kraken candle is unfinished.
"""
from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal
import json
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from quantlab.console.charts import Candle

PAIRS={'BTC/USD':'XBTUSD','ETH/USD':'ETHUSD','SOL/USD':'SOLUSD','XRP/USD':'XRPUSD'}
INTERVAL={'1m':1,'5m':5,'15m':15,'1h':60,'1d':1440}

class KrakenDataError(RuntimeError):pass

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
