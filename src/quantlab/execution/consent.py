"""Explicit, bounded, persistent consent before any execution service is armed.

Never store a brokerage password/secret in a grant. No auto-extension.
This module does not bypass the existing ManagedExecutor policy checks.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import sqlite3
import uuid

@dataclass(frozen=True)
class Grant:
    grant_id:str
    principal:str
    account_id:str
    strategy_id:str
    max_order_notional:Decimal
    expires_at:datetime
    approved_at:datetime

class ConsentStore:
    def __init__(self,path:str):
        self.path=path
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS consent_grants
                (grant_id TEXT PRIMARY KEY, principal TEXT NOT NULL, account_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL, max_notional TEXT NOT NULL,
                approved_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')

    def approve(self,principal:str,account_id:str,strategy_id:str,max_order_notional:Decimal,
                duration:timedelta,now:datetime|None=None)->Grant:
        now=now or datetime.now(timezone.utc)
        if not (principal and account_id and strategy_id):raise ValueError('scope required')
        if not (Decimal('0')<max_order_notional<=Decimal('10000')):raise ValueError('invalid consent scope')
        if not timedelta(minutes=1)<=duration<=timedelta(hours=24):raise ValueError('consent duration out of range')
        if now.tzinfo is None:raise ValueError('timezone required')
        grant=Grant(str(uuid.uuid4()),principal,account_id,strategy_id,max_order_notional,now+duration,now)
        with sqlite3.connect(self.path) as db:
            db.execute('''INSERT INTO consent_grants VALUES (?,?,?,?,?,?,?,0)''',
                    (grant.grant_id,principal,account_id,strategy_id,str(max_order_notional),now.isoformat(),grant.expires_at.isoformat()))
        return grant

    def active(self,principal:str,account_id:str,strategy_id:str,notional:Decimal,now:datetime|None=None)->bool:
        now=now or datetime.now(timezone.utc)
        with sqlite3.connect(self.path) as db:
            result=db.execute('''SELECT max_notional,expires_at FROM consent_grants WHERE
                principal=? AND account_id=? AND strategy_id=? AND revoked=0
                ORDER BY approved_at DESC LIMIT 1''',(principal,account_id,strategy_id)).fetchone()
        return bool(result and datetime.fromisoformat(result[1])>now and Decimal(result[0])>=notional and notional>0)

    def revoke(self,grant_id:str)->None:
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE consent_grants SET revoked=1 WHERE grant_id=?',(grant_id,))


class ConsentRequired(RuntimeError):pass

class AuthorizedExecutor:
    """Consent boundary wrapping the existing broker-managed executor.

    Supports one-click, short-lived, strategy-scoped grants after a real admin
    identity check. Broker account and risk checks are still independent.
    """
    def __init__(self,consents:ConsentStore,managed,principal:str='admin'):
        self.consents,self.managed,self.principal=consents,managed,principal

    def execute(self,strategy_id,order,ctx,now=None):
        now=now or datetime.now(timezone.utc)
        notional=order.quantity*ctx.estimated_price
        if not self.consents.active(self.principal,self.managed.broker.account_id,strategy_id,notional,now):
            raise ConsentRequired('no active scoped consent grant')
        from quantlab.execution.public_api import OrderSide
        if order.side in (OrderSide.BUY,OrderSide.SELL_SHORT) and (order.stop_loss is None or order.take_profit is None):
            raise ConsentRequired('protected bracket order required for new entries')
        return self.managed.execute(strategy_id,order,ctx)
