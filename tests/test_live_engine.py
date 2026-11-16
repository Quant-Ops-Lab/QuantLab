from datetime import datetime,timezone,timedelta
from decimal import Decimal
from io import BytesIO
import json
import tempfile
from pathlib import Path
import pytest
from quantlab.signals.entry import Evidence, MarketFrame,SignalPolicy,Direction,propose
from quantlab.intelligence.context import interpret
from quantlab.execution.consent import ConsentStore
from quantlab.market.kraken import subscription,decode as decode_kraken
from quantlab.market.alpaca_stream import decode_events,BarEvent,QuoteEvent,NewsEvent
from quantlab.market.kraken_rest import KrakenPublic
from quantlab.console.theme import THEMES,css
from quantlab.console.alerts import alert_wav
from quantlab.services.stock_stream import EquityInterpreter

NOW=datetime(2026,11,12,14,1,tzinfo=timezone.utc)
def frame(now=NOW,ratio='1.6',move='-60'):
    return MarketFrame('AMD',Decimal('100'),Decimal('99.98'),Decimal('100.02'),
                       Decimal('2'),Decimal(ratio),Decimal(move),now,'iex')

def test_entry_candidate_exits_and_precision():
    plan=propose(frame(),[],now=NOW)
    assert plan.status=='CANDIDATE' and plan.direction is Direction.SHORT
    assert plan.stop>plan.entry>plan.take_profit
    assert plan.risk_dollars<=Decimal('5')
    assert plan.shares*plan.entry<=Decimal('150')

def test_stale_and_slow_are_no_trade():
    assert propose(frame(NOW-timedelta(seconds=50)),[],now=NOW).status=='NO_TRADE'
    assert propose(frame(ratio='1.0'),[],now=NOW).status=='NO_TRADE'
    assert propose(frame(move='-3'),[],now=NOW).status=='NO_TRADE'

def test_events_verified_required_not_unverified():
    e=Evidence('X','rumor',NOW,NOW,False,-1)
    p=SignalPolicy(require_confirmed_event=True)
    assert propose(frame(),[e],p,NOW).status=='NO_TRADE'
    e2=Evidence('SEC','8K',NOW,NOW,True,-0.3,'https://sec.gov/filing')
    assert propose(frame(),[e2],p,NOW).status=='CANDIDATE'

def test_event_interpreter_keeps_allegation_unverified():
    ev=interpret('Company allegedly under investigation','quarterly revenue','Press','https://press.example/news',NOW,NOW,True)
    assert 'legal_risk' in ev.themes and 'earnings' in ev.themes
    assert ev.treatment=='VERIFY_MANUALLY'
    ev2=interpret('Quarterly results','revenue rose','Official','https://example.com',NOW,NOW,True)
    assert ev2.treatment=='PUBLIC_DISCLOSURE'

def test_consent_scope_revocation_and_expiry(tmp_path):
    store=ConsentStore(str(tmp_path/'grants.db'))
    grant=store.approve('admin','account-x','alpha',Decimal('100'),timedelta(minutes=15),NOW)
    assert store.active('admin','account-x','alpha',Decimal('99'),NOW)
    assert not store.active('admin','account-x','alpha',Decimal('101'),NOW)
    assert not store.active('admin','account-x','beta',Decimal('90'),NOW)
    assert not store.active('admin','account-x','alpha',Decimal('90'),NOW+timedelta(minutes=16))
    store.revoke(grant.grant_id)
    assert not store.active('admin','account-x','alpha',Decimal('90'),NOW)

def test_crypto_ws_decode():
    assert subscription(['BTC/USD'])['params']['channel']=='ticker'
    ticks=decode_kraken({'channel':'ticker','type':'update','data':[{'symbol':'BTC/USD','bid':101,'ask':102,'last':101.5}]},NOW)
    assert len(ticks)==1 and ticks[0].last==Decimal('101.5')
    assert decode_kraken({'channel':'heartbeat'},NOW)==[]

def test_alpaca_stream_decoding():
    v=[{'T':'b','S':'AMD','t':'2026-11-12T14:00:00Z','o':100,'h':103,'l':99,'c':102,'v':400},
       {'T':'q','S':'AMD','t':'2026-11-12T14:00:03Z','bp':100,'ap':101},
       {'T':'n','id':100,'headline':'Earnings announced','created_at':'2026-11-12T14:00:02Z','url':'https://example.com/news','symbols':['AMD']}]
    events=decode_events(v,NOW)
    assert len(events)==3 and isinstance(events[0],BarEvent)
    assert isinstance(events[1],QuoteEvent) and isinstance(events[2],NewsEvent)

class FakeResponse:
    def __init__(self,payload):self.payload=json.dumps(payload).encode()
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self):return self.payload

def test_kraken_rest_uses_complete_exchange_candles():
    records=[[1700000000,100,110,90,108,105,12,22],[1700000300,108,120,100,115,112,18,40]]
    provider=KrakenPublic(opener=lambda *a,**k:FakeResponse({'error':[],'result':{'XXBTZUSD':records,'last':1700000300}}))
    ohlc=provider.ohlc('BTC/USD','5m')
    assert len(ohlc)==1 and ohlc[0].close==108 and ohlc[0].volume==12

def test_theme_and_sound_tokens():
    assert set(THEMES)=={'Neon','Deck','Standard','Terminal','Blackout'}
    assert '--ql-surface' in css('Deck')
    assert alert_wav()[:4]==b'RIFF'

class Collector:
    def __init__(self):self.rows=[]
    def publish(self,topic,payload):self.rows.append((topic,payload))

def test_equity_news_does_not_execute_or_assume_truth():
    publisher=Collector();worker=EquityInterpreter(publisher)
    news=NewsEvent('1','Company allegedly acquired rival','News','https://example.com',('AMD',),NOW,NOW)
    worker.ingest(news,NOW)
    assert len(publisher.rows)==1
    assert publisher.rows[0][1]['treatment']=='VERIFY_MANUALLY'

def test_public_bracket_order_sizing():
    import uuid
    from quantlab.execution.public_api import EquityOrder,OrderSide
    order=EquityOrder(str(uuid.uuid4()),'AMD',OrderSide.BUY,Decimal('1'),
                      Decimal('100'),Decimal('97'),Decimal('106'))
    payload=order.payload()
    assert payload['orderClass']=='BRACKET'
    assert payload['stopLoss']['stopPrice']=='97'
    assert payload['takeProfit']['limitPrice']=='106'
    with pytest.raises(ValueError):
        EquityOrder(str(uuid.uuid4()),'AMD',OrderSide.BUY,Decimal('0.5'),None,Decimal('97'),Decimal('106'))

def test_executor_requires_scope_and_protective_exits(tmp_path):
    import uuid
    from quantlab.execution.consent import ConsentRequired,AuthorizedExecutor
    from quantlab.execution.public_api import EquityOrder,OrderSide
    from quantlab.execution.managed import ExecutionContext,ExecutionPolicy,ManagedExecutor,OrderJournal
    class Broker:
        account_id='account-x'
        def __init__(self):self.calls=0
        def submit(self,order):self.calls+=1;return {'orderId':order.order_id}
    broker=Broker()
    managed=ManagedExecutor(broker,OrderJournal(str(tmp_path/'orders.db')),ExecutionPolicy(allow_live=True))
    consents=ConsentStore(str(tmp_path/'consents.db'))
    ex=AuthorizedExecutor(consents,managed)
    order=EquityOrder(str(uuid.uuid4()),'AMD',OrderSide.BUY,Decimal('1'),None,Decimal('97'),Decimal('106'))
    ctx=ExecutionContext(True,True,Decimal('500'),Decimal('100'),Decimal('0'),Decimal('0'))
    with pytest.raises(ConsentRequired):ex.execute('s1',order,ctx,NOW)
    consents.approve('admin','account-x','s1',Decimal('150'),timedelta(hours=1))
    assert ex.execute('s1',order,ctx)['orderId']==order.order_id
    assert broker.calls==1

def test_shared_alert_journal_deduplicates(tmp_path):
    from quantlab.control.alert_store import AlertJournal
    db=AlertJournal(str(tmp_path/'alerts.sqlite'))
    db.publish('quantlab/signals/alert',{'symbol':'AMD','entry':'101'})
    db.publish('quantlab/signals/alert',{'symbol':'AMD','entry':'101'})
    assert len(db.recent())==1
    assert db.recent()[0]['payload']['symbol']=='AMD'
    with pytest.raises(ValueError):db.publish('execute/orders',{})

def test_equity_stream_generates_one_candidate_from_live_bars():
    from quantlab.market.alpaca_stream import BarEvent,QuoteEvent
    pub=Collector(); worker=EquityInterpreter(pub)
    worker.ingest(QuoteEvent('AMD',NOW,Decimal('102.19'),Decimal('102.21')),NOW)
    last=None
    for i in range(22):
        t=NOW-timedelta(minutes=22-i)
        close=Decimal('100')+Decimal(i)/Decimal('10')
        event=BarEvent('AMD',t,close-Decimal('.03'),close+Decimal('.10'),
                       close-Decimal('.12'),close,1000 if i==21 else 100)
        last=worker.ingest(event,NOW)
    assert last is not None and last.status=='CANDIDATE'
    assert last.direction is Direction.LONG
    assert len([e for e in pub.rows if e[0]=='quantlab/signals/alert'])==1
    assert pub.rows[-1][1]['execution']=='NOT_AUTHORIZED'
