from datetime import datetime,timezone
from quantlab.control.worker import MarketWorker
from quantlab.control.sdk import QuantLabClient
from quantlab.control.notifications import JsonlPublisher
from quantlab.control.contracts import SignalObservation
from quantlab.control.planner import draft

class GoodFeed:
 def __init__(self,now):self.now=now
 def latest(self,symbol):return SignalObservation(symbol,self.now,-80,True,'good-feed','market_feed')
class BadFeed:
 def __init__(self,now):self.now=now
 def latest(self,symbol):return SignalObservation(symbol,self.now,-80,True,'spoofed-user','operator_input')

def test_worker_emits_from_verified_interface(tmp_path):
 now=datetime.now(timezone.utc)
 w=MarketWorker(GoodFeed(now),QuantLabClient(JsonlPublisher(tmp_path/'alerts.jsonl')),(draft('observe',['SPY']),))
 result=w.scan_once(now)
 assert (result.observed,result.alerts,result.rejected,result.errors)==(1,1,0,())

def test_worker_fail_closed_on_unverified_feed(tmp_path):
 now=datetime.now(timezone.utc)
 out=tmp_path/'alerts.jsonl'
 w=MarketWorker(BadFeed(now),QuantLabClient(JsonlPublisher(out)),(draft('observe',['SPY']),))
 result=w.scan_once(now)
 assert result.alerts==0 and result.errors and not out.exists()
