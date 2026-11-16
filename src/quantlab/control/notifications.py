"""Notification targets are outbound ONLY; never accept trade commands from MQTT."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Protocol
from .contracts import AlertDecision

TOPIC_ALERT = 'quantlab/signals/alert'
TOPIC_REVIEW = 'quantlab/orders/review_requested'
TOPIC_AUDIT = 'quantlab/ops/audit'
TOPIC_INTEL = 'quantlab/intelligence/event'

class Publisher(Protocol):
    def publish(self, topic: str, payload: dict) -> None: ...

class JsonlPublisher:
    """Single-process local event sink for development. NOT a durable broker queue."""
    def __init__(self,path:Path):
        self.path=Path(path)
    def publish(self,topic,payload):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        event={'topic':topic,'payload':payload}
        with self.path.open('a',encoding='utf-8') as fh:
            fh.write(json.dumps(event,sort_keys=True,allow_nan=False)+'\n')

class SNSEventPublisher:
    """Optional production notification destination, requires boto3 + an allowed topic ARN.

    SNS is NOT an execution queue. Never include credentials or secrets in payloads.
    """
    def __init__(self,topic_arn:str,client=None):
        if not topic_arn.startswith('arn:aws:sns:'):
            raise ValueError('invalid SNS topic ARN')
        if client is None:
            import boto3
            client=boto3.client('sns')
        self.client=client
        self.topic_arn=topic_arn
    def publish(self,topic,payload):
        if topic not in (TOPIC_ALERT, TOPIC_REVIEW, TOPIC_AUDIT, TOPIC_INTEL):
            raise ValueError('topic not allowed')
        self.client.publish(TopicArn=self.topic_arn,
                            Message=json.dumps({'topic':topic,'payload':payload},allow_nan=False))

def publish_decision(publisher:Publisher,decision:AlertDecision)->bool:
    if decision.status=='NO_ACTION':
        return False
    topic=TOPIC_REVIEW if decision.status=='ALERT_REVIEW' else TOPIC_ALERT
    publisher.publish(topic, decision.to_dict())
    return True

class SQSEventPublisher:
    """Durable-queue publisher. Requires boto3 or an injected SQS client.

    SQS consumers must be idempotent; publishing isn't an order authorization.
    """
    def __init__(self,queue_url:str,client=None):
        if not queue_url.startswith('https://'):
            raise ValueError('invalid SQS queue URL')
        if client is None:
            import boto3
            client=boto3.client('sqs')
        self.client=client
        self.queue_url=queue_url
    def publish(self,topic,payload):
        if topic not in (TOPIC_ALERT,TOPIC_REVIEW,TOPIC_AUDIT,TOPIC_INTEL):
            raise ValueError('topic not allowed')
        self.client.send_message(QueueUrl=self.queue_url,
              MessageBody=json.dumps({'topic':topic,'payload':payload},allow_nan=False))

class MQTTNotificationPublisher:
    """Outbound-only MQTT notifier, requiring a configured TLS-enabled client.

    Do not subscribe to inbound 'execute' commands; MQTT is notification only.
    """
    def __init__(self,client,topic_prefix='quantlab'):
        if topic_prefix != 'quantlab':
            raise ValueError('unexpected MQTT namespace')
        self.client=client
    def publish(self,topic,payload):
        if topic not in (TOPIC_ALERT,TOPIC_REVIEW,TOPIC_AUDIT,TOPIC_INTEL):
            raise ValueError('topic not allowed')
        result=self.client.publish(topic,json.dumps(payload,allow_nan=False),qos=1,retain=False)
        if getattr(result,'rc',0)!=0:
            raise RuntimeError('mqtt publish rejected')


class FanoutPublisher:
    """Publish to multiple outbound sinks; caller handles partial failures."""
    def __init__(self,*publishers):
        self.publishers=publishers
    def publish(self,topic,payload):
        failures=[]
        for p in self.publishers:
            try:p.publish(topic,payload)
            except Exception as exc:failures.append(type(exc).__name__)
        if failures:raise RuntimeError('notification partial failure: '+','.join(failures))
