"""Deterministic, fail-closed research preflight. NO ORDER SUBMISSION.

The checker is illustrative and intentionally incomplete for live trading.
A real broker adapter must implement atomic cash reservations, partial fills,
settlement, cancel/replace, reconciliation, halts and broker limits.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class RiskState:
    trading_enabled: bool
    asof: datetime
    known_order_ids: frozenset[str]
    settled_cash: Decimal
    day_loss: Decimal
    day_loss_cap: Decimal
    account_equity: Decimal
    max_notional_pct: Decimal


@dataclass(frozen=True)
class DraftOrder:
    client_order_id: str
    symbol: str
    notional: Decimal


@dataclass(frozen=True)
class RiskDecision:
    allowed_for_future_manual_review: bool
    reasons: tuple[str, ...]


def preflight(order: DraftOrder, state: RiskState, now: datetime,
              max_age: timedelta = timedelta(seconds=30)) -> RiskDecision:
    reasons: list[str] = []
    if not state.trading_enabled:
        reasons.append('trading_disabled')
    if now.tzinfo is None or now.utcoffset() is None or state.asof.tzinfo is None:
        reasons.append('bad_timestamp')
    else:
        age = now - state.asof
        if age < timedelta(0) or age > max_age:
            reasons.append('stale_or_future_account_data')
    if not order.client_order_id or order.client_order_id in state.known_order_ids:
        reasons.append('duplicate_or_missing_order_id')
    if not order.symbol or not order.symbol.isascii() or not order.symbol.replace('.', '').isalnum():
        reasons.append('invalid_symbol')
    if not order.notional.is_finite() or order.notional <= 0:
        reasons.append('invalid_notional')
    cash_values = (state.account_equity, state.max_notional_pct,
                   state.day_loss_cap, state.day_loss, state.settled_cash)
    if not all(x.is_finite() for x in cash_values):
        reasons.append('nonfinite_account_values')
    else:
        if (state.account_equity <= 0 or not Decimal('0') < state.max_notional_pct <= Decimal('1')
            or state.day_loss < 0 or state.settled_cash < 0):
            reasons.append('invalid_account_limits')
        if state.day_loss_cap <= 0 or state.day_loss >= state.day_loss_cap:
            reasons.append('daily_loss_limit')
        if order.notional.is_finite() and order.notional > state.settled_cash:
            reasons.append('insufficient_settled_cash')
        if order.notional.is_finite() and order.notional > state.account_equity * state.max_notional_pct:
            reasons.append('position_notional_limit')
    return RiskDecision(allowed_for_future_manual_review=not reasons,
                        reasons=tuple(reasons))
