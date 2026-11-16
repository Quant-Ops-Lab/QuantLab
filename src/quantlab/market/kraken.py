"""Free public crypto ticker through Kraken WebSocket v2.

Source-only adapter: no Kraken keys, no orders. web-socket transport injected
for testing. The worker must reconnect on errors with exponential backoff.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
import json

WS_URL='wss://ws.kraken.com/v2'

@dataclass(frozen=True)
class CryptoTick:
    symbol:str
    bid:Decimal
    ask:Decimal
    last:Decimal
    observed_at:datetime
    source:str='kraken_ws_v2'


def subscription(symbols:list[str]):
    if not symbols or len(symbols)>50 or any('/' not in s or not s.replace('/','').isalnum() for s in symbols):
        raise ValueError('invalid crypto symbols')
    return {'method':'subscribe','params':{'channel':'ticker','symbol':symbols,'event_trigger':'trades'}}


def decode(raw:dict,received_at:datetime|None=None)->list[CryptoTick]:
    if raw.get('channel')!='ticker' or raw.get('type') not in ('snapshot','update'):
        return []
    ts=received_at or datetime.now(timezone.utc)
    output=[]
    for d in raw.get('data',[]):
        try:
            bid=Decimal(str(d['bid']));ask=Decimal(str(d['ask']));last=Decimal(str(d['last']))
            if min(bid,ask,last)<=0 or ask<bid:continue
            output.append(CryptoTick(str(d['symbol']),bid,ask,last,ts))
        except (KeyError,ValueError,ArithmeticError):continue
    return output


async def ticks(symbols:list[str]):
    """Async market tick stream; library optional until crypto features enabled."""
    import websockets
    payload=subscription(symbols)
    async with websockets.connect(WS_URL,ping_interval=20,close_timeout=5) as ws:
        await ws.send(json.dumps(payload))
        async for msg in ws:
            for tick in decode(json.loads(msg)):
                yield tick
