"""Continuous SEC monitor (headless). Relies on explicit verified ticker→CIK map.

SEC form sightings are research events, NEVER trade authorization. This service
is intentionally decoupled from the broker and operates without market hours.
"""
from __future__ import annotations
import os
import json
import logging
import signal
import time
from datetime import datetime,timezone
from quantlab.intelligence.edgar import SECSubmissions,CIKDirectory
from quantlab.intelligence.events import EventJournal
from quantlab.intelligence.pipeline import IntelligencePipeline
from quantlab.intelligence.news import TrustedRSS
from quantlab.control.notifications import JsonlPublisher,SNSEventPublisher,FanoutPublisher
from pathlib import Path

LOGGER=logging.getLogger(__name__)

class Source:
    def __init__(self,client, mapping:dict[str,int]):
        self.client,self.mapping=client,mapping
    def collect(self):
        events=[]
        now=datetime.now(timezone.utc)
        for symbol,cik in self.mapping.items():
            try: events.extend(self.client.filings(int(cik),symbol,now=now))
            except Exception as exc:LOGGER.warning('SEC error %s: %s',symbol,type(exc).__name__)
            time.sleep(0.35)  # well below SEC fair-access ceiling
        return events


def main():
    logging.basicConfig(level=logging.INFO)
    user_agent=os.environ.get('SEC_USER_AGENT','')
    cik_file=os.environ.get('QUANTLAB_CIK_MAP','config/cik_map.json')
    if os.path.exists(cik_file):
        with open(cik_file,encoding='utf-8') as handle:
            mapping=json.load(handle)
    else:
        from quantlab.universe.catalog import default_universe, AssetKind
        watch={s for s,a in default_universe().items() if a.kind==AssetKind.EQUITY}
        mapping=CIKDirectory(user_agent).lookup(watch)
        LOGGER.info('Resolved CIKs for %d of %d watched equities',len(mapping),len(watch))
    if not mapping:raise RuntimeError('verified SEC ticker-to-CIK mapping required')
    db_path=os.getenv('QUANTLAB_EVENT_DB','artifacts/events.sqlite')
    os.makedirs(os.path.dirname(db_path) or '.',exist_ok=True)
    journal=EventJournal(db_path)
    publishers=[JsonlPublisher(Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl')))]
    if os.getenv('QUANTLAB_SNS_TOPIC_ARN'):
        publishers.append(SNSEventPublisher(os.environ['QUANTLAB_SNS_TOPIC_ARN']))
    sources=[Source(SECSubmissions(user_agent),mapping)]
    news_file=os.getenv('QUANTLAB_NEWS_FEEDS','config/news_feeds.json')
    if os.path.exists(news_file):
        with open(news_file,encoding='utf-8') as handle:
            feeds=json.load(handle)
        for feed in feeds:
            sources.append(TrustedRSS(feed['url'],feed['source_name'],tuple(feed['symbols'])))
    pipeline=IntelligencePipeline(sources,journal,FanoutPublisher(*publishers))
    interval=max(60,int(os.getenv('SEC_POLL_SECONDS','900')))
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    while not stopped:
        result=pipeline.cycle()
        LOGGER.info('SEC poll %s',result)
        for _ in range(interval):
            if stopped:break
            time.sleep(1)

if __name__=='__main__':main()
