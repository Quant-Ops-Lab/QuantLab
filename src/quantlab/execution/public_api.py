"""Public Individual API adapter with read and order-write methods.

Source: https://public.com/api/docs/resources/order-placement/place-order
Do not pass a bearer key to models or browser clients. Submission only means
received, never filled. Unknown timeouts must be reconciled, not blindly retried.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Callable

BASE_URL='https://api.public.com'

class OrderSide(StrEnum):
    BUY='BUY'
    SELL='SELL'
    SELL_SHORT='SELL_SHORT'
    BUY_TO_COVER='BUY_TO_COVER'


@dataclass(frozen=True)
class EquityOrder:
    order_id:str
    symbol:str
    side:OrderSide
    quantity:Decimal
    limit_price:Decimal|None=None
    stop_loss:Decimal|None=None
    take_profit:Decimal|None=None

    def __post_init__(self):
        uuid.UUID(self.order_id)
        if not self.symbol.isascii() or not self.symbol or len(self.symbol)>15 or not self.symbol.replace('.','').isalpha():
            raise ValueError('unsupported symbol format')
        if self.quantity<=0:raise ValueError('quantity must be positive')
        if self.limit_price is not None and self.limit_price<=0:raise ValueError('limit must be positive')
        if (self.stop_loss is None)!=(self.take_profit is None):
            raise ValueError('both bracket exit legs are required for this engine')
        if self.stop_loss is not None:
            if self.quantity!=self.quantity.to_integral_value() or self.stop_loss<=0 or self.take_profit<=0:
                raise ValueError('Public bracket requires positive prices and whole shares')
            if self.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER) and self.stop_loss>=self.take_profit:
                raise ValueError('long bracket stop must be below take profit')
            if self.side in (OrderSide.SELL_SHORT, OrderSide.SELL) and self.stop_loss<=self.take_profit:
                raise ValueError('short bracket stop must be above take profit')

    def payload(self)->dict:
        short=self.side==OrderSide.SELL_SHORT
        cover=self.side==OrderSide.BUY_TO_COVER
        payload={
            'orderId':self.order_id,
            'instrument':{'symbol':self.symbol,'type':'EQUITY'},
            'orderSide':'BUY' if self.side in (OrderSide.BUY,OrderSide.BUY_TO_COVER) else 'SELL',
            'openCloseIndicator':'OPEN' if self.side in (OrderSide.BUY,OrderSide.SELL_SHORT) else 'CLOSE',
            'orderType':'LIMIT' if self.limit_price is not None else 'MARKET',
            'expiration':{'timeInForce':'DAY'},
            'quantity':str(self.quantity),
            'equityMarketSession':'CORE',
            'useMargin': bool(short or cover),
        }
        if self.limit_price is not None:payload['limitPrice']=str(self.limit_price)
        if self.stop_loss is not None:
            payload['orderClass']='BRACKET'
            payload['takeProfit']={'limitPrice':str(self.take_profit)}
            payload['stopLoss']={'stopPrice':str(self.stop_loss)}
        return payload


class PublicAPIError(RuntimeError):pass
class SubmissionUnknown(PublicAPIError):pass


class PublicBroker:
    """Uses standard library HTTP and a test-injectable transport.

    Credentials and account ID must be provided out-of-band. Zero automatic
    retries for write operations. Methods do not guarantee broker eligibility.
    """
    def __init__(self, account_id:str, token:str, transport:Callable|None=None):
        if not account_id or not token:raise ValueError('account_id and token required')
        self.account_id=account_id
        self.token=token
        self.transport=transport or self._http

    def _http(self, method:str,path:str,body:dict|None=None)->dict:
        url=BASE_URL+path
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/json',
                 'Content-Type':'application/json'}
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(url,method=method,headers=headers,data=data)
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                raw=response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            # Response errors are definitive failures or validation errors.
            raise PublicAPIError(f'Public HTTP {exc.code}') from exc
        except (TimeoutError,urllib.error.URLError,ConnectionError) as exc:
            # The order may have been accepted before the response was lost.
            raise SubmissionUnknown('unknown broker response; reconcile order ID') from exc

    def portfolio(self)->dict:
        return self.transport('GET',f'/userapigateway/trading/{self.account_id}/portfolio/v2')

    def instrument(self,symbol:str)->dict:
        return self.transport('GET',f'/userapigateway/trading/instruments/{symbol}/EQUITY')

    def quotes(self,symbols:list[str])->dict:
        if not symbols:raise ValueError('symbols required')
        return self.transport('POST',f'/userapigateway/marketdata/{self.account_id}/quotes',
                              {'instruments':[{'symbol':s,'type':'EQUITY'} for s in symbols]})

    def order_status(self,order_id:str)->dict:
        uuid.UUID(order_id)
        return self.transport('GET',f'/userapigateway/trading/{self.account_id}/order/{order_id}')

    def preflight(self,order:EquityOrder)->dict:
        payload=order.payload().copy()
        payload.pop('orderId',None)
        payload['validateOrder']=True
        return self.transport('POST',f'/userapigateway/trading/{self.account_id}/preflight/single-leg',payload)

    def submit(self,order:EquityOrder)->dict:
        result=self.transport('POST',f'/userapigateway/trading/{self.account_id}/order',order.payload())
        if result.get('orderId')!=order.order_id:
            raise SubmissionUnknown('order acknowledgment did not match requested UUID')
        return result
