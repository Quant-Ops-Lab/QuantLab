"""Source-verifiable, point-in-time event facts; no LLM trading permissions."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable
import json
from quantlab.services.storage import connect,bind,is_postgres


@dataclass(frozen=True)
class EventFact:
    source: str
    source_id: str
    kind: str
    headline: str
    symbols: tuple[str,...]
    published_at: datetime
    received_at: datetime
    source_url: str
    evidence: str = ""

    def __post_init__(self):
        if not self.source_id or not self.source or not self.source_url.startswith('https://'):
            raise ValueError('source, source_id, and HTTPS source_url are required')
        if self.published_at.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError('timestamp must contain UTC offset')
        if self.published_at > self.received_at:
            raise ValueError('event cannot be received before published')

    @property
    def event_id(self) -> str:
        return sha256(f'{self.source}:{self.source_id}'.encode()).hexdigest()

    def to_dict(self):
        out = asdict(self)
        out['published_at'] = self.published_at.isoformat()
        out['received_at'] = self.received_at.isoformat()
        out['event_id'] = self.event_id
        return out


class EventJournal:
    """Single-process durable SQLite research journal; production uses managed DB."""
    def __init__(self, db_path: str):
        self.db_path=db_path
        with connect(db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, published_at TEXT NOT NULL,
                received_at TEXT NOT NULL, source TEXT NOT NULL,
                event_json TEXT NOT NULL)''')

    def append(self,event:EventFact)->bool:
        with connect(self.db_path) as conn:
            sql=('''INSERT INTO events (event_id,published_at,received_at,source,event_json)
                 VALUES (%s,%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING'''
                 if is_postgres(self.db_path) else '''INSERT OR IGNORE INTO events
                (event_id,published_at,received_at,source,event_json) VALUES (?,?,?,?,?)''')
            r=conn.execute(sql,(
                event.event_id,event.published_at.isoformat(),
                event.received_at.isoformat(),event.source,
                json.dumps(event.to_dict(),sort_keys=True),))
            return r.rowcount==1

    def recent(self,limit:int=50)->list[dict]:
        with connect(self.db_path) as conn:
            result=conn.execute(f'''SELECT event_json FROM events
             ORDER BY received_at DESC, event_id DESC LIMIT {bind(self.db_path)}''',(min(500,max(1,limit)),))
            return [json.loads(r[0]) for r in result]


def classify_event(form:str,headline:str='')->str:
    form=form.upper().strip()
    h=headline.lower()
    if 'split' in h or 'reverse split' in h: return 'STOCK_SPLIT_CANDIDATE'
    if any(t in h for t in ('acquisition','merger','merging','to acquire')): return 'M_AND_A_CANDIDATE'
    if form in ('10-Q','10-K','20-F','6-K'):return 'FINANCIAL_FILING'
    if form in ('8-K','6-K'):return 'MATERIAL_DISCLOSURE'
    if form.startswith('SC 13'):return 'OWNERSHIP_DISCLOSURE'
    return 'OTHER_FILING'
