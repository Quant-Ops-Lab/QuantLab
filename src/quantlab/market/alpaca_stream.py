"""Alpaca IEX minute bars/quotes and partner news WebSockets.

Real-time streaming is optional and gated by data subscription access. Never
send credentials to a browser or LLM. Exponential reconnects on disconnect.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
import asyncio
import json
from typing import AsyncIterator

BAR_URL='wss://stream.data.alpaca.markets/v2/iex'
NEWS_URL='wss://stream.data.alpaca.markets/v1beta1/news'

@dataclass(frozen=True)
class BarEvent:
    symbol:str
    start:datetime
    open:Decimal
    high:Decimal
    low:Decimal
    close:Decimal
    volume:int
    source:str='alpaca_iex'

@dataclass(frozen=True)
class QuoteEvent:
    symbol:str
    observed_at:datetime
    bid:Decimal
    ask:Decimal
    source:str='alpaca_iex'

@dataclass(frozen=True)
class NewsEvent:
    headline_id:str
    headline:str
    source:str
    url:str
    symbols:tuple[str,...]
    published_at:datetime
    received_at:datetime
    summary:str=''


def _dt(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('timestamp without timezone')
    return result.astimezone(timezone.utc)


def decode_events(raw,received_at=None):
    received_at=received_at or datetime.now(timezone.utc)
    out=[]
    for entry in raw if isinstance(raw,list) else [raw]:
        if not isinstance(entry,dict):continue
        try:
            kind=entry.get('T')
            if kind=='b':
                o,h,l,c=[Decimal(str(entry[k])) for k in ('o','h','l','c')]
                v=int(entry['v'])
                if 0<l<=min(o,c)<=max(o,c)<=h and v>=0:
                    out.append(BarEvent(str(entry['S']),_dt(entry['t']),o,h,l,c,v))
            elif kind=='q':
                b,a=Decimal(str(entry['bp'])),Decimal(str(entry['ap']))
                if 0<b<=a:out.append(QuoteEvent(str(entry['S']),_dt(entry['t']),b,a))
            elif kind=='n' and str(entry.get('url','')).startswith('https://'):
                out.append(NewsEvent(str(entry['id']),str(entry['headline'])[:500],
                    str(entry.get('source') or entry.get('author') or 'Alpaca news'),
                    str(entry['url']),tuple(str(s) for s in entry.get('symbols',[])[:30]),
                    _dt(entry['created_at']),received_at,str(entry.get('summary') or '')[:1000]))
        except (ValueError,KeyError,TypeError,ArithmeticError):continue
    return out


async def stream(key:str,secret:str,channel:str,symbols:list[str])->AsyncIterator[BarEvent|QuoteEvent|NewsEvent]:
    if channel not in ('market','news') or not key or not secret:raise ValueError('invalid stream credentials/channel')
    if not symbols or len(symbols)>30:raise ValueError('invalid subscription symbols')
    import websockets
    url=NEWS_URL if channel=='news' else BAR_URL
    delay=1
    while True:
        try:
            async with websockets.connect(url,ping_interval=20,close_timeout=10,max_size=4_000_000) as socket:
                await socket.send(json.dumps({'action':'auth','key':key,'secret':secret}))
                auth=json.loads(await asyncio.wait_for(socket.recv(),timeout=10))
                if not any(v.get('T')=='success' and v.get('msg')=='authenticated' for v in auth):
                    raise RuntimeError('Alpaca stream authentication failed')
                payload={'action':'subscribe','news':symbols} if channel=='news' else {'action':'subscribe','bars':symbols,'quotes':symbols}
                await socket.send(json.dumps(payload));delay=1
                async for message in socket:
                    for event in decode_events(json.loads(message)):
                        yield event
        except asyncio.CancelledError:raise
        except Exception:
            await asyncio.sleep(delay)
            delay=min(60,delay*2)
