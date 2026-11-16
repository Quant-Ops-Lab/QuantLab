"""Shared SQL signal journal for independently deployed web and worker services.

Records are research alerts, not fill confirmations or broker order instructions.
Postgres is recommended when Render services use isolated filesystems.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
from quantlab.services.storage import connect,is_postgres,bind

ALLOWED={'quantlab/signals/alert','quantlab/intelligence/event','quantlab/orders/review_requested','quantlab/ops/audit'}

class AlertJournal:
    def __init__(self,dsn):
        self.dsn=str(dsn)
        with connect(self.dsn) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS quantlab_alerts (
                event_hash TEXT PRIMARY KEY, topic TEXT NOT NULL,
                body TEXT NOT NULL, received_at TEXT NOT NULL)''')

    def publish(self,topic,payload):
        if topic not in ALLOWED:raise ValueError('alert topic not allowed')
        raw=json.dumps({'topic':topic,'payload':payload},sort_keys=True,allow_nan=False)
        digest=hashlib.sha256(raw.encode()).hexdigest()
        with connect(self.dsn) as db:
            token=bind(self.dsn)
            db.execute(f'''INSERT INTO quantlab_alerts (event_hash,topic,body,received_at)
                VALUES ({token},{token},{token},{token}) ON CONFLICT (event_hash) DO NOTHING''',
                (digest,topic,raw,datetime.now(timezone.utc).isoformat()))

    def recent(self,topic='quantlab/signals/alert',limit=30)->list[dict]:
        if topic not in ALLOWED or not 1<=limit<=500:raise ValueError('unsupported query')
        with connect(self.dsn) as db:
            token=bind(self.dsn)
            rows=db.execute(f'''SELECT body FROM quantlab_alerts WHERE topic={token}
                ORDER BY received_at DESC LIMIT {token}''',(topic,limit)).fetchall()
        return [json.loads(row[0]) for row in rows]
