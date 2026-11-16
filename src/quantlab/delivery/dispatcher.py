"""Durable, per-provider delivery with retry and deduplication.

Outbox is at-least-once, not exactly-once: an interrupted remote send can
succeed before its local SENT state commits. No provider acknowledgment is
mistaken for an actual message-read or broker fill.
"""
from __future__ import annotations
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import uuid
from quantlab.services.storage import connect,bind,is_postgres
from quantlab.delivery.channels import Message,Channel

TOPICS={'quantlab/signals/alert'}


def _utc(dt:datetime)->datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:raise ValueError('timezone required')
    return dt.astimezone(timezone.utc)


def _decimal(x):
    try:
        v=Decimal(str(x))
        if not v.is_finite() or v<=0:return None
        return v
    except (InvalidOperation,ValueError,TypeError):return None


def message_from_event(event:dict,now:datetime,max_age_seconds:int=600)->Message|None:
    """Suppress old/stale, malformed, untrusted and untradeable alerts."""
    try:
        if event.get('topic') not in TOPICS:return None
        p=event['payload']
        if p.get('kind')!='TRADE_CANDIDATE' or p.get('execution')!='NOT_AUTHORIZED':return None
        signal=p['signal']
        if signal.get('status')!='CANDIDATE' or signal.get('direction') not in ('LONG','SHORT'):
            return None
        asof=datetime.fromisoformat(signal['asof'].replace('Z','+00:00'))
        now=_utc(now);asof=_utc(asof)
        if asof>now+timedelta(seconds=3) or now-asof>timedelta(seconds=max_age_seconds):return None
        entry,stop,target,risk=(_decimal(signal.get(k)) for k in ('entry','stop','take_profit','risk_dollars'))
        if None in (entry,stop,target,risk):return None
        side=signal['direction']
        if not (stop<entry<target if side=='LONG' else target<entry<stop):return None
        evidence=signal.get('evidence',[])
        if not isinstance(evidence,list):return None
        return Message(event_id=str(signal['signal_id']),symbol=str(signal['symbol']).upper(),
            direction=side,entry=str(entry),stop=str(stop),target=str(target),risk=str(risk),
            asof=asof.isoformat(),evidence_count=len(evidence))
    except (KeyError,ValueError,AttributeError,TypeError):return None


def event_id(topic,payload)->str:
    raw=json.dumps({'topic':topic,'payload':payload},sort_keys=True,allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class AlertReader:
    """Read only the recent local JSONL or shared Postgres/SQLite alert journal."""
    def __init__(self,sql_dsn:str|None=None,jsonl_path:Path|None=None):
        self.sql_dsn=sql_dsn or None
        self.jsonl_path=Path(jsonl_path) if jsonl_path is not None else Path('artifacts/alerts.jsonl')

    def latest(self,now:datetime,lookback_seconds:int=900,limit:int=500)->list[tuple[str,dict]]:
        if not 0<limit<=2000 or not 0<lookback_seconds<=86400:raise ValueError('invalid scan window')
        cutoff=(_utc(now)-timedelta(seconds=lookback_seconds)).isoformat()
        if self.sql_dsn:
            marker=bind(self.sql_dsn)
            with connect(self.sql_dsn) as db:
                rows=db.execute(f'''SELECT event_hash,body FROM quantlab_alerts
                    WHERE topic={marker} AND received_at>={marker}
                    ORDER BY received_at DESC LIMIT {marker}''',
                    ('quantlab/signals/alert',cutoff,limit)).fetchall()
            return [(row[0],json.loads(row[1])) for row in reversed(rows)]
        if not self.jsonl_path.exists():return []
        with self.jsonl_path.open(encoding='utf-8') as fh:
            lines=deque(fh,maxlen=limit)
        result=[]
        for line in lines:
            try:
                obj=json.loads(line)
                if obj.get('topic') in TOPICS:
                    result.append((event_id(obj['topic'],obj['payload']),obj))
            except (ValueError,KeyError,TypeError):continue
        return result


class DeliveryLedger:
    def __init__(self,dsn:str):
        self.dsn=str(dsn)
        # A clean ZIP checkout has no artifacts/ directory. Create the local
        # SQLite parent without touching PostgreSQL URLs or in-memory stores.
        if not is_postgres(self.dsn) and self.dsn != ':memory:':
            path = self.dsn.removeprefix('sqlite:///')
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with connect(self.dsn) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS quantlab_notification_deliveries (
                event_hash TEXT NOT NULL, channel TEXT NOT NULL, state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, lease_token TEXT,
                locked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
                next_try DOUBLE PRECISION NOT NULL DEFAULT 0,
                updated_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(event_hash,channel))''')

    def claim(self,event_hash:str,channel:str,now:datetime,max_attempts:int=4,lease_seconds:int=60)->str|None:
        if len(event_hash)!=64 or channel not in ('discord','slack','sms','email'):
            raise ValueError('invalid event/channel')
        moment=_utc(now).timestamp();marker=bind(self.dsn)
        token=uuid.uuid4().hex
        with connect(self.dsn) as db:
            db.execute(f'''INSERT INTO quantlab_notification_deliveries
                (event_hash,channel,state,attempts,updated_at)
                VALUES ({marker},{marker},'PENDING',0,{marker})
                ON CONFLICT (event_hash,channel) DO NOTHING''',(event_hash,channel,moment))
            row=db.execute(f'''UPDATE quantlab_notification_deliveries
                SET state='LEASED', attempts=attempts+1, lease_token={marker},
                    locked_until={marker},updated_at={marker}
                WHERE event_hash={marker} AND channel={marker} AND state!='SENT'
                  AND attempts<{marker} AND (state!='LEASED' OR locked_until<={marker})
                  AND next_try<={marker} RETURNING attempts''',
                (token,moment+lease_seconds,moment,event_hash,channel,max_attempts,moment,moment)).fetchone()
        return token if row else None

    def finish(self,event_hash:str,channel:str,token:str,success:bool,now:datetime)->None:
        moment=_utc(now).timestamp();marker=bind(self.dsn)
        with connect(self.dsn) as db:
            row=db.execute(f'''SELECT attempts FROM quantlab_notification_deliveries
                WHERE event_hash={marker} AND channel={marker} AND lease_token={marker}
                  AND state='LEASED' ''',(event_hash,channel,token)).fetchone()
            if row is None:raise RuntimeError('notification lease no longer owned')
            retry_delay=min(3600,30*2**(row[0]-1))
            db.execute(f'''UPDATE quantlab_notification_deliveries
                SET state={marker},next_try={marker},locked_until=0,lease_token=NULL,updated_at={marker}
                WHERE event_hash={marker} AND channel={marker} AND lease_token={marker}''',
                ('SENT' if success else 'FAILED',0 if success else moment+retry_delay,
                 moment,event_hash,channel,token))

    def summary(self)->list[dict]:
        with connect(self.dsn) as db:
            rows=db.execute('''SELECT channel,state,COUNT(*) FROM quantlab_notification_deliveries
                GROUP BY channel,state ORDER BY channel,state''').fetchall()
        return [{'channel':r[0],'state':r[1],'count':r[2]} for r in rows]


class NotificationDispatcher:
    def __init__(self,reader:AlertReader,ledger:DeliveryLedger,channels:list[Channel],
                 max_signal_age:int=600):
        names=[c.name for c in channels]
        if len(names)!=len(set(names)):raise ValueError('duplicate notification channel')
        self.reader,self.ledger,self.channels=reader,ledger,channels
        if not 30<=max_signal_age<=3600:raise ValueError('invalid signal lifetime')
        self.max_signal_age=max_signal_age

    def run_once(self,now:datetime|None=None)->dict:
        now=now or datetime.now(timezone.utc)
        totals={'scanned':0,'eligible':0,'sent':0,'failed':0}
        for eid,event in self.reader.latest(now,lookback_seconds=self.max_signal_age+90):
            totals['scanned']+=1
            msg=message_from_event(event,now,max_age_seconds=self.max_signal_age)
            if msg is None:continue
            totals['eligible']+=1
            for channel in self.channels:
                token=self.ledger.claim(eid,channel.name,now)
                if token is None:continue
                try:
                    channel.send(msg)
                except Exception:
                    # Do not log webhook URLs, SMTP credentials or recipient numbers.
                    self.ledger.finish(eid,channel.name,token,False,now)
                    totals['failed']+=1
                else:
                    self.ledger.finish(eid,channel.name,token,True,now)
                    totals['sent']+=1
        return totals
