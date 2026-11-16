"""Durable single-writer order intent and broker status lifecycle.

SQLite is safe for a single worker process, NOT multiple replicas; production
Postgres needs transactional row locking and an account-scoped leader lease.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime,timezone
import sqlite3
import uuid
from .public_api import EquityOrder,OrderSide,SubmissionUnknown

class OrderJournal:
    def __init__(self,path:str):
        self.path=path
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS orders (
              order_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
              strategy_id TEXT NOT NULL,symbol TEXT NOT NULL,
              payload TEXT NOT NULL,status TEXT NOT NULL,
              updated_at TEXT NOT NULL)''')

    def reserve(self,account_id:str,strategy_id:str,order:EquityOrder)->bool:
        import json
        with sqlite3.connect(self.path) as db:
            inserted=db.execute('''INSERT OR IGNORE INTO orders
                (order_id,account_id,strategy_id,symbol,payload,status,updated_at)
                VALUES (?,?,?,?,?,?,?)''',(
                  order.order_id,account_id,strategy_id,order.symbol,
                  json.dumps(order.payload(),sort_keys=True),'RESERVED',
                  datetime.now(timezone.utc).isoformat()))
            return inserted.rowcount==1

    def state(self,order_id:str)->str|None:
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT status FROM orders WHERE order_id=?',(order_id,)).fetchone()
            return row[0] if row else None

    def mark(self,order_id:str,state:str)->None:
        if state not in ('RESERVED','SUBMITTING','ACKNOWLEDGED','UNKNOWN','FILLED','CANCELED','REJECTED'):
            raise ValueError('unknown order state')
        with sqlite3.connect(self.path) as db:
            r=db.execute('''UPDATE orders SET status=?,updated_at=? WHERE order_id=?''',(
                state,datetime.now(timezone.utc).isoformat(),order_id))
            if r.rowcount!=1:raise KeyError(order_id)


def deterministic_order_id(account_id:str,strategy_id:str,signal_id:str,side:OrderSide)->str:
    if not all((account_id,strategy_id,signal_id)):raise ValueError('source identifiers required')
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'quantlab:'+':'.join((account_id,strategy_id,signal_id,side.value))))

@dataclass(frozen=True)
class ExecutionPolicy:
    max_order_notional:Decimal=Decimal('150')
    max_daily_loss:Decimal=Decimal('10')
    max_total_allocation:Decimal=Decimal('1000')
    allow_short:bool=False
    allow_live:bool=False

@dataclass(frozen=True)
class ExecutionContext:
    fresh_quote:bool
    account_reconciled:bool
    available_cash:Decimal
    estimated_price:Decimal
    realized_daily_loss:Decimal
    estimated_total_exposure:Decimal
    shortable:bool=False
    margin_eligible:bool=False

class ExecutionDenied(RuntimeError):pass


class ManagedExecutor:
    def __init__(self,broker,journal:OrderJournal,policy:ExecutionPolicy):
        self.broker=broker
        self.journal=journal
        self.policy=policy

    def execute(self,strategy_id:str,order:EquityOrder,ctx:ExecutionContext)->dict:
        if not self.policy.allow_live:raise ExecutionDenied('execution is not armed')
        if not (ctx.fresh_quote and ctx.account_reconciled):raise ExecutionDenied('stale quote or unreconciled account')
        if ctx.estimated_price<=0:raise ExecutionDenied('price missing')
        notional=order.quantity*ctx.estimated_price
        if notional>self.policy.max_order_notional:raise ExecutionDenied('order exceeds notional cap')
        adds_exposure=order.side in (OrderSide.BUY,OrderSide.SELL_SHORT)
        if adds_exposure and ctx.realized_daily_loss>=self.policy.max_daily_loss:
            raise ExecutionDenied('daily loss stop')
        if adds_exposure and ctx.estimated_total_exposure+notional>self.policy.max_total_allocation:
            raise ExecutionDenied('portfolio exposure cap')
        if order.side==OrderSide.BUY and notional>ctx.available_cash:
            raise ExecutionDenied('cash requirement not met')
        if order.side==OrderSide.SELL_SHORT:
            if not(self.policy.allow_short and ctx.shortable and ctx.margin_eligible):
                raise ExecutionDenied('borrow/margin eligibility not established')
        # Real Public integration must pass the non-mutating server-side preflight.
        # A preflight result is an estimate and cannot guarantee a filled trade.
        if hasattr(self.broker,'preflight'):
            pre=self.broker.preflight(order)
            if pre.get('instrument',{}).get('symbol')!=order.symbol:
                raise ExecutionDenied('broker preflight mismatch')
            if order.side==OrderSide.SELL_SHORT:
                availability=pre.get('shortSelling',{}).get('availability')
                if availability!='EASY_TO_BORROW':
                    raise ExecutionDenied('broker preflight did not confirm easy borrow')
        if not self.journal.reserve(self.broker.account_id,strategy_id,order):
            raise ExecutionDenied('duplicate order ID: reconcile existing order')
        self.journal.mark(order.order_id,'SUBMITTING')
        try:
            acknowledgment=self.broker.submit(order)
        except SubmissionUnknown:
            self.journal.mark(order.order_id,'UNKNOWN')
            raise
        except Exception:
            self.journal.mark(order.order_id,'UNKNOWN')
            # Broker might have accepted before a transport failure.
            raise
        self.journal.mark(order.order_id,'ACKNOWLEDGED')
        return acknowledgment

    def reconcile(self,order_id:str)->dict:
        if self.journal.state(order_id) is None:raise KeyError(order_id)
        status=self.broker.order_status(order_id)
        broker_status=str(status.get('status','')).upper()
        normalized={'CANCELLED':'CANCELED','QUEUED_CANCELLED':'CANCELED'}.get(broker_status,broker_status)
        if normalized in ('FILLED','CANCELED','REJECTED'):
            self.journal.mark(order_id,normalized)
        return status
