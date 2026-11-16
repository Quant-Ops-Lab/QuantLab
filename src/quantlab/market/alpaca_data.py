"""Alpaca Data API (free Basic IEX feed) with testable transport.

Do not confuse IEX with the consolidated SIP feed. Pricing, limits and access
are enforced by Alpaca. This connector never sends orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable
import json
import re
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

DATA_ROOT = "https://data.alpaca.markets"
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

class MarketDataError(RuntimeError):
    """Market-data access, schema, or provider failure."""


def _when(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise MarketDataError('Provider timestamp has no timezone')
    return dt.astimezone(timezone.utc)


def _positive(value, field: str) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise MarketDataError(f'Invalid {field}') from exc
    if not number.is_finite() or number <= 0:
        raise MarketDataError(f'Nonpositive {field}')
    return float(number)


def _symbol(value: str) -> str:
    value = value.strip().upper()
    if not SYMBOL_RE.fullmatch(value):
        raise ValueError('Invalid market symbol')
    return value

@dataclass(frozen=True)
class ExchangeBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    provider: str = 'alpaca_iex'

    @classmethod
    def parse(cls, symbol: str, raw: dict):
        o,h,l,c = (_positive(raw.get(k),k) for k in ('o','h','l','c'))
        if not (l <= min(o,c) <= max(o,c) <= h):
            raise MarketDataError('Malformed OHLC candle')
        v=raw.get('v')
        if not isinstance(v, (int,float)) or v < 0:
            raise MarketDataError('Invalid exchange volume')
        return cls(_symbol(symbol),_when(raw['t']),o,h,l,c,int(v))

@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    price: float
    timestamp: datetime
    previous_close: float|None
    volume: int|None
    feed: str = 'iex'

    @property
    def change_pct(self) -> float|None:
        return round((self.price/self.previous_close-1)*100,2) if self.previous_close else None

@dataclass(frozen=True)
class MarketHeadline:
    headline_id: str
    headline: str
    summary: str
    url: str
    symbols: tuple[str,...]
    source: str
    published_at: datetime
    provider: str = 'alpaca_news'


class AlpacaData:
    """Read-only historical OHLCV, snapshots, latest news (not an execution API)."""
    def __init__(self, key: str, secret: str, opener: Callable|None=None):
        if not (key and secret):
            raise ValueError('Alpaca API key and secret required')
        self.key, self.secret = key, secret
        self.opener = opener or urlopen

    def _get(self,path:str,params:dict)->dict:
        url=DATA_ROOT+path+'?'+urlencode(params)
        req=Request(url,headers={
            'APCA-API-KEY-ID':self.key,
            'APCA-API-SECRET-KEY':self.secret,
            'Accept':'application/json',
            'User-Agent':'QuantLab/0.5 (read-only-market-data)'})
        try:
            with self.opener(req,timeout=15) as response:
                raw=json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            # Credential values, response bodies, URLs with secrets must never be logged.
            raise MarketDataError(f'Alpaca request failed: {type(exc).__name__}') from None
        if not isinstance(raw, dict):
            raise MarketDataError('Invalid Alpaca response')
        if 'code' in raw and 'message' in raw:
            raise MarketDataError(f'Alpaca rejected request (code {raw["code"]})')
        return raw

    def bars(self, symbol:str, timeframe:str='1Day', days:int=120, limit:int=500)->list[ExchangeBar]:
        symbol=_symbol(symbol)
        if timeframe not in ('1Min','5Min','15Min','1Hour','1Day'):
            raise ValueError('Invalid Alpaca bar timeframe')
        if not (1 <= days <= 730) or not (1 <= limit <= 1000):
            raise ValueError('Invalid lookback')
        now=datetime.now(timezone.utc)
        # Free Basic IEX users may not receive the most recent 15 min of historical bars.
        start=(now-timedelta(days=days)).isoformat().replace('+00:00','Z')
        out=[]
        next_token=None
        for _ in range(8):
            params={'timeframe':timeframe,'start':start,'end':now.isoformat().replace('+00:00','Z'),
                    'feed':'iex','adjustment':'raw','limit':min(limit-len(out),1000),'sort':'asc'}
            if next_token: params['page_token']=next_token
            doc=self._get('/v2/stocks/'+quote(symbol,safe='')+'/bars',params)
            for obj in doc.get('bars',[]) or []:
                out.append(ExchangeBar.parse(symbol,obj))
            next_token=doc.get('next_page_token')
            if not next_token or len(out)>=limit:break
        return sorted(out[:limit], key=lambda b:b.timestamp)

    def snapshots(self, symbols:list[str])->list[QuoteSnapshot]:
        symbols=[_symbol(s) for s in symbols]
        if not symbols or len(symbols)>30:
            raise ValueError('Supply 1-30 symbols')
        doc=self._get('/v2/stocks/snapshots',{'symbols':','.join(symbols),'feed':'iex'})
        payload=doc.get('snapshots',doc)
        results=[]
        for symbol in symbols:
            snap=payload.get(symbol,{})
            trade=snap.get('latestTrade') or {}
            minute=snap.get('minuteBar') or {}
            daily=snap.get('dailyBar') or {}
            prev=snap.get('prevDailyBar') or {}
            value=trade.get('p') or minute.get('c') or daily.get('c')
            instant=trade.get('t') or minute.get('t') or daily.get('t')
            if not (value and instant):continue
            previous=prev.get('c')
            results.append(QuoteSnapshot(symbol,_positive(value,'last price'),_when(instant),
                            _positive(previous,'previous close') if previous else None,
                            int(daily['v']) if isinstance(daily.get('v'),int) else None))
        return results

    def news(self, symbols:list[str],limit:int=20)->list[MarketHeadline]:
        symbols=[_symbol(s) for s in symbols]
        if not 1 <= limit <= 50 or len(symbols)>30:raise ValueError('Invalid news request')
        doc=self._get('/v1beta1/news',{'symbols':','.join(symbols),'limit':limit,'sort':'desc'})
        out=[]
        for article in doc.get('news',[]):
            if not (isinstance(article,dict) and str(article.get('url','')).startswith('https://')):
                continue
            try:
                out.append(MarketHeadline(str(article['id']),str(article['headline'])[:500],
                    str(article.get('summary') or '')[:1000],str(article['url']),
                    tuple(str(s).upper() for s in article.get('symbols',[]) if SYMBOL_RE.fullmatch(str(s).upper())),
                    str(article.get('source') or article.get('author') or 'Unspecified'),
                    _when(article.get('created_at') or article.get('updated_at'))))
            except (ValueError,KeyError,MarketDataError):continue
        return out
