import uuid
from decimal import Decimal as D
import pytest
from quantlab.execution.public_api import PublicBroker,EquityOrder,OrderSide,SubmissionUnknown
from quantlab.execution.managed import (ManagedExecutor,OrderJournal,ExecutionContext,
    ExecutionPolicy,ExecutionDenied,deterministic_order_id)

OID=str(uuid.uuid4())

def test_public_order_mapping_long_short_and_cover():
    buy=EquityOrder(OID,'NVDA',OrderSide.BUY,D('0.5'),D('125'))
    assert buy.payload()['useMargin'] is False
    assert buy.payload()['limitPrice']=='125'
    short=EquityOrder(OID,'AMD',OrderSide.SELL_SHORT,D('1'))
    assert short.payload()['orderSide']=='SELL' and short.payload()['openCloseIndicator']=='OPEN'
    assert short.payload()['useMargin'] is True
    cover=EquityOrder(OID,'AMD',OrderSide.BUY_TO_COVER,D('1'))
    assert cover.payload()['openCloseIndicator']=='CLOSE'

class Broker:
    account_id='demo'
    def __init__(self):self.calls=0
    def submit(self,order):
        self.calls+=1
        return {'orderId':order.order_id}
    def order_status(self,order_id):return {'orderId':order_id,'status':'FILLED'}

CTX=ExecutionContext(fresh_quote=True,account_reconciled=True,available_cash=D('500'),
    estimated_price=D('100'),realized_daily_loss=D('0'),estimated_total_exposure=D('0'))

def test_execution_gates_and_idempotency(tmp_path):
    broker=Broker()
    journal=OrderJournal(str(tmp_path/'orders.sqlite'))
    order=EquityOrder(OID,'NVDA',OrderSide.BUY,D('1'))
    ex=ManagedExecutor(broker,journal,ExecutionPolicy())
    with pytest.raises(ExecutionDenied):ex.execute('s1',order,CTX)
    assert broker.calls==0
    ex=ManagedExecutor(broker,journal,ExecutionPolicy(allow_live=True))
    assert ex.execute('s1',order,CTX)['orderId']==OID
    assert journal.state(OID)=='ACKNOWLEDGED'
    assert ex.reconcile(OID)['status']=='FILLED'
    with pytest.raises(ExecutionDenied):ex.execute('s1',order,CTX)
    assert broker.calls==1

def test_short_requires_verified_margin_and_borrow(tmp_path):
    broker=Broker();journal=OrderJournal(str(tmp_path/'orders.sqlite'))
    ex=ManagedExecutor(broker,journal,ExecutionPolicy(allow_live=True,allow_short=True))
    with pytest.raises(ExecutionDenied):
        ex.execute('s1',EquityOrder(OID,'AMD',OrderSide.SELL_SHORT,D('1')),CTX)
    assert broker.calls==0

def test_order_uuid_is_stable_per_event():
    assert deterministic_order_id('a','b','c',OrderSide.BUY)==deterministic_order_id('a','b','c',OrderSide.BUY)
    assert deterministic_order_id('a','b','c',OrderSide.BUY)!=deterministic_order_id('a','b','c',OrderSide.SELL)

def test_public_broker_routes_and_requires_matching_ack():
    calls=[]
    def transport(method,path,body=None):
        calls.append((method,path,body))
        if path.endswith('/order'):return {'orderId':OID}
        return {'positions':[]}
    b=PublicBroker('acct','token',transport)
    assert b.portfolio()['positions']==[]
    b.submit(EquityOrder(OID,'NVDA',OrderSide.BUY,D('1')))
    assert calls[1][1]=='/userapigateway/trading/acct/order'

def test_public_preflight_is_nonmutating_contract():
    calls=[]
    def transport(method,path,body=None):
        calls.append((method,path,body))
        return {'instrument':{'symbol':'NVDA'},'orderValue':'100'}
    broker=PublicBroker('acct','token',transport)
    broker.preflight(EquityOrder(OID,'NVDA',OrderSide.BUY,D('1')))
    method,path,body=calls[0]
    assert method=='POST' and path.endswith('/preflight/single-leg')
    assert 'orderId' not in body and body['validateOrder'] is True

def test_liquidating_position_not_blocked_by_entry_only_risk_limits(tmp_path):
    broker=Broker();journal=OrderJournal(str(tmp_path/'orders.sqlite'))
    ex=ManagedExecutor(broker,journal,ExecutionPolicy(allow_live=True))
    from dataclasses import replace
    ctx=replace(CTX,realized_daily_loss=D('20'),estimated_total_exposure=D('999'))
    order=EquityOrder(str(uuid.uuid4()),'NVDA',OrderSide.SELL,D('1'))
    assert ex.execute('exit',order,ctx)['orderId']==order.order_id
