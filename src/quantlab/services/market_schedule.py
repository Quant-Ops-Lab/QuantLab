"""Calendar-aware equity monitoring and execution phases."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo
import exchange_calendars as xcals


NEW_YORK = ZoneInfo("America/New_York")
PREMARKET_START = time(4, 0)
AFTER_HOURS_END = time(20, 0)
XNYS = xcals.get_calendar("XNYS")


class EquityPhase(StrEnum):
    OVERNIGHT = "overnight"
    PREMARKET = "premarket"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


def _local(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    return now.astimezone(NEW_YORK)


def _session_bounds(local: datetime) -> tuple[datetime, datetime, datetime] | None:
    session = local.date().isoformat()
    if not XNYS.is_session(session):
        return None
    open_at = XNYS.session_open(session).to_pydatetime().astimezone(NEW_YORK)
    close_at = XNYS.session_close(session).to_pydatetime().astimezone(NEW_YORK)
    premarket = datetime.combine(local.date(), PREMARKET_START, tzinfo=NEW_YORK)
    after_hours = min(
        datetime.combine(local.date(), AFTER_HOURS_END, tzinfo=NEW_YORK),
        close_at + timedelta(hours=4),
    )
    return premarket, open_at, min(after_hours, datetime.combine(local.date(), AFTER_HOURS_END, tzinfo=NEW_YORK))


def equity_phase(now: datetime) -> EquityPhase:
    """Classify monitoring state using XNYS holidays, DST, and half-days."""
    local = _local(now)
    bounds = _session_bounds(local)
    if bounds is None:
        return EquityPhase.OVERNIGHT
    premarket, regular_open, after_hours = bounds
    if local < premarket or local >= after_hours:
        return EquityPhase.OVERNIGHT
    if local < regular_open:
        return EquityPhase.PREMARKET
    if local < XNYS.session_close(local.date().isoformat()).to_pydatetime().astimezone(NEW_YORK):
        return EquityPhase.REGULAR
    return EquityPhase.AFTER_HOURS


def equity_service_open(now: datetime) -> bool:
    """Return whether the equity monitor should be connected."""
    return equity_phase(now) is not EquityPhase.OVERNIGHT


def equity_order_eligible(now: datetime) -> bool:
    """Regular-session eligibility; broker extended-hours support is separate."""
    return equity_phase(now) is EquityPhase.REGULAR


def _next_session_premarket(local: datetime) -> datetime:
    candidate = local.date() + timedelta(days=1)
    for _ in range(14):
        if XNYS.is_session(candidate.isoformat()):
            return datetime.combine(candidate, PREMARKET_START, tzinfo=NEW_YORK)
        candidate += timedelta(days=1)
    raise RuntimeError("could not find a future XNYS session")


def seconds_until_equity_boundary(now: datetime) -> float:
    """Return seconds until the next monitoring phase boundary."""
    local = _local(now)
    bounds = _session_bounds(local)
    if bounds is None:
        boundary = _next_session_premarket(local)
    else:
        premarket, regular_open, after_hours = bounds
        close_at = XNYS.session_close(local.date().isoformat()).to_pydatetime().astimezone(NEW_YORK)
        phase = equity_phase(now)
        boundary = {
            EquityPhase.PREMARKET: regular_open,
            EquityPhase.REGULAR: close_at,
            EquityPhase.AFTER_HOURS: after_hours,
            EquityPhase.OVERNIGHT: _next_session_premarket(local),
        }[phase]
    return max(1.0, (boundary - local).total_seconds())