import pytest
from quantlab.control.notifications import MQTTNotificationPublisher,SQSEventPublisher,TOPIC_ALERT
from quantlab.control.reasoner import explain_read_only,compile_description_read_only
from quantlab.control.planner import draft
from quantlab.control.engine import evaluate
from quantlab.control.contracts import SignalObservation
from datetime import datetime,timezone
import json

class SQSFake:
 def __init__(self):self.sent=[]
 def send_message(self,**kw):self.sent.append(kw)
class MQTTFake:
 def __init__(self,rc=0):self.sent=[];self.rc=rc
 def publish(self,*a,**kw):
  self.sent.append((a,kw))
  return type('Response',(),{'rc':self.rc})()

def test_sqs_routes_events_without_execute_topic():
 fake=SQSFake();sink=SQSEventPublisher('https://sqs.us-east-1.amazonaws.com/123/alerts',fake)
 sink.publish(TOPIC_ALERT,{'symbol':'SPY'})
 assert len(fake.sent)==1
 with pytest.raises(ValueError):sink.publish('quantlab/orders/execute',{})

def test_mqtt_outbound_only():
 fake=MQTTFake();sink=MQTTNotificationPublisher(fake)
 sink.publish(TOPIC_ALERT,{'a':1})
 assert len(fake.sent)==1 and fake.sent[0][1]['retain'] is False
 with pytest.raises(ValueError):sink.publish('quantlab/orders/execute',{})
 with pytest.raises(RuntimeError):MQTTNotificationPublisher(MQTTFake(rc=1)).publish(TOPIC_ALERT,{})

def test_explain_accepts_valid_json_only():
 now=datetime.now(timezone.utc)
 dec=evaluate(draft('watch',['SPY']),SignalObservation('SPY',now,-90,True,'feed','market_feed'),now)
 out=explain_read_only(lambda a,b:json.dumps({'summary':'Candidate signal','limitations':'Not validated','next_checks':'Backtest'}),dec)
 assert out['summary']=='Candidate signal'
 with pytest.raises(ValueError):explain_read_only(lambda a,b:'{"summary":"x"}',dec)

def test_compile_description_schema_gate():
 description='Research SPY bearish moves'
 source=draft(description,['SPY'])
 received=compile_description_read_only(lambda a,b:json.dumps(source.to_dict()),description)
 assert received.description==description
 with pytest.raises(ValueError):compile_description_read_only(lambda a,b:'{"mode":"live_bounded"}',description)
