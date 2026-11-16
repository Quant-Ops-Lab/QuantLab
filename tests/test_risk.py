from datetime import datetime,timedelta,timezone
from decimal import Decimal
from quantlab.risk.firewall import RiskState,DraftOrder,preflight

NOW=datetime(2026,11,12,tzinfo=timezone.utc)


def state(**kw):
    data = dict(trading_enabled=False,asof=NOW,known_order_ids=frozenset(),
       settled_cash=Decimal('100'),day_loss=Decimal('0'),
       day_loss_cap=Decimal('10'),account_equity=Decimal('1000'),
       max_notional_pct=Decimal('.05'))
    data.update(kw)
    return RiskState(**data)


def order(**kw):
    data=dict(client_order_id='demo-1',symbol='SPY',notional=Decimal('25'))
    data.update(kw)
    return DraftOrder(**data)


def test_defaults_fail_closed():
    decision=preflight(order(),state(),NOW)
    assert not decision.allowed_for_future_manual_review
    assert 'trading_disabled' in decision.reasons


def test_stale_rejected_even_if_switch_on():
    result=preflight(order(),state(trading_enabled=True,asof=NOW-timedelta(minutes=3)),NOW)
    assert 'stale_or_future_account_data' in result.reasons


def test_unsettled_and_duplicate_rejected():
    result=preflight(order(),state(trading_enabled=True, settled_cash=Decimal('5'),
         known_order_ids=frozenset({'demo-1'})),NOW)
    assert 'insufficient_settled_cash' in result.reasons
    assert 'duplicate_or_missing_order_id' in result.reasons


def test_daily_loss_rejected():
    assert 'daily_loss_limit' in preflight(order(),state(trading_enabled=True,
         day_loss=Decimal('10')),NOW).reasons


def test_with_all_preflight_checks_passed_still_no_execution():
    result=preflight(order(),state(trading_enabled=True),NOW)
    assert result.allowed_for_future_manual_review
    from quantlab.execution.broker import ReadOnlyBroker
    assert 'submit_order' not in ReadOnlyBroker.__dict__


def test_nonfinite_cash_fails_closed():
    result=preflight(order(),state(trading_enabled=True,settled_cash=Decimal('NaN')),NOW)
    assert not result.allowed_for_future_manual_review
    assert 'nonfinite_account_values' in result.reasons
