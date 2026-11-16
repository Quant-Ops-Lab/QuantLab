"""Shared alert sink; SQL for UI, SNS optional for off-browser notifications."""
from __future__ import annotations
import os
from pathlib import Path
from quantlab.control.alert_store import AlertJournal
from quantlab.control.notifications import JsonlPublisher,SNSEventPublisher,FanoutPublisher

def build_publisher():
    if os.getenv('QUANTLAB_ALERT_DB'):
        store=AlertJournal(os.environ['QUANTLAB_ALERT_DB'])
    else:
        store=JsonlPublisher(Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl')))
    if os.getenv('QUANTLAB_SNS_TOPIC_ARN'):
        return FanoutPublisher(store,SNSEventPublisher(os.environ['QUANTLAB_SNS_TOPIC_ARN']))
    return store
