"""Deterministic control engine for alert-only strategy evaluation.

This is NOT a market predictor and CANNOT execute orders. Bearish is an alert,
not a borrowed-share short sale. Observations are externally supplied and must
carry provenance and timezone-aware timestamps.
"""
from datetime import datetime, timezone
from .contracts import StrategySpec, SignalObservation, AlertDecision, Direction, Mode

def evaluate(spec: StrategySpec, observation: SignalObservation, now_utc: datetime | None = None) -> AlertDecision:
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError('now must be timezone aware')
    reasons = []
    if observation.symbol not in spec.symbols:
        reasons.append('symbol is not in approved strategy universe')
    age = (now_utc - observation.asof_utc).total_seconds()
    if age < 0 or age > spec.max_signal_age_seconds:
        reasons.append('observation stale or future dated')
    if observation.origin not in ('market_feed','operator_input'):
        reasons.append('unrecognized provenance')
    if observation.origin=='operator_input':
        reasons.append('operator input is not a verified live market feed')
    if not observation.independent_confirmation:
        reasons.append('independent signal confirmation missing')
    if spec.direction==Direction.BEARISH and observation.price_change_bps > -spec.threshold_bps:
        reasons.append('bearish movement threshold not met')
    if spec.direction==Direction.LONG and observation.price_change_bps < spec.threshold_bps:
        reasons.append('long movement threshold not met')
    if reasons:
        status='NO_ACTION'
        explanation='No eligible alert: ' + '; '.join(reasons) + '.'
    else:
        status='ALERT_REVIEW' if spec.mode==Mode.APPROVAL_REQUIRED else 'ALERT_ONLY'
        explanation=('Observed %s price change %.1f bps, independent confirmation present. '
                     'This is a rule match, not a validated ML trade or short-sale authorization.' %
                     (spec.direction.value,observation.price_change_bps))
    return AlertDecision(spec.strategy_id, observation.symbol,status,explanation,
                         spec.fingerprint,observation.feed_source,
                         observation.asof_utc.astimezone(timezone.utc).isoformat())
