import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from quantlab.control.contracts import StrategySpec,Direction,Mode,SignalObservation
from quantlab.control.engine import evaluate
from quantlab.control.planner import draft
from quantlab.control.sdk import QuantLabClient
from quantlab.control.notifications import JsonlPublisher,TOPIC_ALERT,SNSEventPublisher

def spec(mode='alert_only'):
 return draft('Bearish divergence alert for research',['SPY'], 'bearish',mode,30)

def obs(t,change=-50,confirmed=True,origin='market_feed'):
 return SignalObservation('SPY',t,change,confirmed,'test-market-source',origin)

def test_strategy_round_trip():
 x=spec(); y=StrategySpec.from_dict(x.to_dict());assert x==y and x.fingerprint==y.fingerprint

def test_fails_on_live_execution_mode():
 with pytest.raises(ValueError,match='not implemented'):
  draft('try live',['SPY'],'long','live_bounded')

def test_invalid_symbols_rejected():
 with pytest.raises(ValueError):draft('bad symbol',['SPY;DROP TABLE'])

def test_unknown_fields_rejected():
 raw=spec().to_dict();raw['command']='trade_now'
 with pytest.raises(ValueError):StrategySpec.from_dict(raw)

def test_bearish_matching_alert():
 now=datetime.now(timezone.utc)
 d=evaluate(spec(),obs(now),now)
 assert d.status=='ALERT_ONLY' and 'not a validated ML trade' in d.explanation

def test_manual_source_does_not_emit_alert():
 now=datetime.now(timezone.utc)
 assert evaluate(spec(),obs(now,origin='operator_input'),now).status=='NO_ACTION'

def test_old_feed_blocks_alert():
 now=datetime.now(timezone.utc)
 assert evaluate(spec(),obs(now-timedelta(minutes=5)),now).status=='NO_ACTION'

def test_future_feed_blocks_alert():
 now=datetime.now(timezone.utc)
 assert evaluate(spec(),obs(now+timedelta(seconds=10)),now).status=='NO_ACTION'

def test_missing_confirmation_blocks_alert():
 now=datetime.now(timezone.utc)
 assert evaluate(spec(),obs(now,confirmed=False),now).status=='NO_ACTION'

def test_below_threshold_blocks_alert():
 now=datetime.now(timezone.utc)
 assert evaluate(spec(),obs(now,change=-4),now).status=='NO_ACTION'

def test_approval_request_is_not_order():
 now=datetime.now(timezone.utc)
 assert evaluate(spec('approval_required'),obs(now),now).status=='ALERT_REVIEW'

def test_notifier_writes_only_alerts(tmp_path):
 now=datetime.now(timezone.utc); file=tmp_path/'alerts.jsonl'; publisher=JsonlPublisher(file)
 client=QuantLabClient(publisher)
 assert client.run_once(spec(),obs(now),now).status=='ALERT_ONLY'
 assert json.loads(file.read_text())['topic']==TOPIC_ALERT

def test_notifier_stays_silent_on_no_action(tmp_path):
 now=datetime.now(timezone.utc); file=tmp_path/'alerts.jsonl'
 assert QuantLabClient(JsonlPublisher(file)).run_once(spec(),obs(now,origin='operator_input'),now).status=='NO_ACTION'
 assert not file.exists()

class FakeSNS:
 def __init__(self):self.calls=[]
 def publish(self,**kwargs):self.calls.append(kwargs)

def test_sns_publisher_contract():
 fake=FakeSNS();publisher=SNSEventPublisher('arn:aws:sns:us-east-1:123:quantlab-alerts',client=fake)
 publisher.publish(TOPIC_ALERT,{'symbol':'SPY'})
 assert len(fake.calls)==1
 with pytest.raises(ValueError,match='topic not allowed'):
  publisher.publish('quantlab/orders/execute',{'symbol':'SPY'})
