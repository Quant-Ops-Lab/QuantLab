from datetime import datetime, timezone

from quantlab.services.market_schedule import EquityPhase, equity_phase, equity_service_open, seconds_until_equity_boundary


def test_equity_worker_runs_weekday_nine_to_five_new_york():
    assert equity_phase(datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)) is EquityPhase.PREMARKET
    assert equity_phase(datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)) is EquityPhase.REGULAR
    assert equity_phase(datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc)) is EquityPhase.AFTER_HOURS
    assert not equity_service_open(datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc))


def test_equity_worker_sleeps_weekend_until_monday():
    now = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
    assert seconds_until_equity_boundary(now) == 18 * 60 * 60


def test_calendar_excludes_holiday_and_handles_half_day():
    assert equity_phase(datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)) is EquityPhase.OVERNIGHT
    assert equity_phase(datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc)) is EquityPhase.AFTER_HOURS