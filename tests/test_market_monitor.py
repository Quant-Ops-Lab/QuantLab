from datetime import datetime,timezone,timedelta
from quantlab.services.market_monitor import decode_quote,MarketPoller,QuoteJournal
import pytest

now=datetime(2026,11,12,18,tzinfo=timezone.utc)
example={'instrument':{'symbol':'NVDA','type':'EQUITY'},'outcome':'SUCCESS',
    'last':'200','bid':'199.5','ask':'200.25','previousClose':'190',
    'lastTimestamp':'2026-11-12T17:59:00Z'}

def test_quote_valid_and_stale():
    good=decode_quote(example,now)
    assert good.day_change_pct>5
    with pytest.raises(ValueError):decode_quote(example,now+timedelta(hours=1))

def test_market_poller_uses_durable_dedup(tmp_path):
    class Broker:
        def quotes(self,symbols):return {'quotes':[example]}
    journal=QuoteJournal(str(tmp_path/'quotes.sqlite'))
    poller=MarketPoller(Broker(),journal,['NVDA'])
    assert poller.cycle(now)['accepted']==1
    assert poller.cycle(now)['accepted']==0

def test_large_move_alert_fires_once_for_new_quote(tmp_path):
    class Broker:
        def quotes(self,symbols):return {'quotes':[example]}
    class Publisher:
        def __init__(self):self.events=[]
        def publish(self,topic,payload):self.events.append((topic,payload))
    sink=Publisher()
    poller=MarketPoller(Broker(),QuoteJournal(str(tmp_path/'quotes.sqlite')),['NVDA'],publisher=sink)
    poller.cycle(now)
    poller.cycle(now)
    assert len(sink.events)==1
    assert sink.events[0][0]=='quantlab/signals/alert'
