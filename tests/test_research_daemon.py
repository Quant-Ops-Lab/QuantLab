from datetime import datetime, timezone

from quantlab.services.research_daemon import seconds_until_run


def test_research_runs_after_next_day_provider_window():
    before = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)
    assert seconds_until_run(before) > 0
    assert seconds_until_run(after) > 20 * 60 * 60
