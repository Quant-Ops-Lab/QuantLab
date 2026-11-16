"""Trusted RSS/Atom discovery and read-only AI enrichment contract.

The entry headline/summary is untrusted. LLMs may create research annotations,
never orders, risk parameters or executable code. Always store source evidence.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Callable,Protocol
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from .events import EventFact,classify_event

_ALLOWED_KINDS={'MATERIAL_DISCLOSURE','FINANCIAL_FILING','STOCK_SPLIT_CANDIDATE',
                'M_AND_A_CANDIDATE','EARNINGS_CANDIDATE','SUPPLY_CHAIN_CANDIDATE','OTHER_NEWS'}

@dataclass(frozen=True)
class NewsAssessment:
    source_event_id:str
    classification:str
    symbols:tuple[str,...]
    novelty:str
    summary:str
    cautions:tuple[str,...]

class StructuredReasoner(Protocol):
    def assess(self, event:EventFact, allowed_symbols:frozenset[str])->NewsAssessment: ...


class RuleReasoner:
    """Honest fallback: event categorization, not a profitability forecast."""
    def assess(self,event:EventFact,allowed_symbols:frozenset[str])->NewsAssessment:
        h=event.headline.lower()
        kind=event.kind if event.kind in _ALLOWED_KINDS else 'OTHER_NEWS'
        if 'split' in h:kind='STOCK_SPLIT_CANDIDATE'
        elif any(t in h for t in ('acquir','acquisition','merger','takeover')):kind='M_AND_A_CANDIDATE'
        elif any(t in h for t in ('earnings','quarter','guidance')):kind='EARNINGS_CANDIDATE'
        elif any(t in h for t in ('contract','supply agreement','fabrication','fab capacity')):kind='SUPPLY_CHAIN_CANDIDATE'
        return NewsAssessment(event.event_id,kind,tuple(s for s in event.symbols if s in allowed_symbols),
            'unassessed',event.headline[:300],
            ('Classification is not a verified corporate action',
             'No trade direction or estimated return implied'))


class TrustedRSS:
    """Poll explicit trusted feeds; zero ticker inference from ambiguous text."""
    def __init__(self,url:str,source_name:str,linked_symbols:tuple[str,...],opener:Callable|None=None):
        if not url.startswith('https://'):raise ValueError('HTTPS source required')
        if not source_name or not linked_symbols:raise ValueError('source name and validated linked symbols required')
        self.url,self.source_name,self.symbols=url,source_name,linked_symbols
        self.opener=opener or urllib.request.urlopen

    def collect(self)->list[EventFact]:
        req=urllib.request.Request(self.url,headers={'User-Agent':'QuantLab-Research/0.3 (contact: configured operator)','Accept':'application/xml, application/rss+xml'})
        with self.opener(req,timeout=15) as resp: content=resp.read(1_000_001)
        if len(content)>1_000_000:raise ValueError('feed too large')
        root=ET.fromstring(content)
        now=datetime.now(timezone.utc)
        entries=root.findall('.//item')
        if not entries:
            entries=root.findall('.//{http://www.w3.org/2005/Atom}entry')
        out=[]
        for e in entries[:30]:
            title=(e.findtext('title') or e.findtext('{http://www.w3.org/2005/Atom}title') or '').strip()
            link=(e.findtext('link') or '').strip()
            if not link:
                el=e.find('{http://www.w3.org/2005/Atom}link')
                if el is not None:link=el.get('href','')
            stamp=e.findtext('pubDate') or e.findtext('{http://www.w3.org/2005/Atom}updated')
            if not(title and link.startswith('https://') and stamp):continue
            try:
                dt=parsedate_to_datetime(stamp) if ',' in stamp else datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if dt.tzinfo is None:continue
                dt=dt.astimezone(timezone.utc)
                if dt>now:continue
                uid=sha256(f'{link}|{stamp}'.encode()).hexdigest()
                out.append(EventFact(self.source_name,uid,'OTHER_NEWS',title,self.symbols,
                    dt,now,link,'RSS headline only. Original article not verified.'))
            except (ValueError,TypeError):continue
        return out
