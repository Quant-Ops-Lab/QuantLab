from datetime import date, datetime, timezone

from quantlab.control.notifications import TOPIC_AUDIT
from quantlab.research.opportunity import DailyBar
from quantlab.research.store import ResearchStore, research_dsn
from quantlab.services.research_daemon import (
    closed_sessions,
    latest_session,
    missing_sessions,
    run_once,
    seconds_until_run,
)


ONE_THIRTY = datetime(2026, 11, 24, 6, 30, tzinfo=timezone.utc)  # 01:30 ET


def test_research_runs_after_next_day_provider_window():
    before = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)
    assert seconds_until_run(before) > 0
    assert seconds_until_run(after) > 20 * 60 * 60


def test_one_thirty_et_uses_last_closed_session_not_today():
    assert latest_session(ONE_THIRTY) == date(2026, 11, 23)
    during = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)  # 15:00 ET
    before_close = datetime(2026, 11, 23, 20, 59, tzinfo=timezone.utc)  # 15:59 ET
    at_close = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)  # 16:00 ET
    assert latest_session(during) == date(2026, 11, 20)
    assert latest_session(before_close) == date(2026, 11, 20)
    assert latest_session(at_close) == date(2026, 11, 23)


def test_early_close_uses_exchange_close():
    before = datetime(2026, 11, 27, 17, 0, tzinfo=timezone.utc)  # 12:00 ET, before 13:00 close
    after = datetime(2026, 11, 27, 18, 5, tzinfo=timezone.utc)  # 13:05 ET
    assert latest_session(before) == date(2026, 11, 25)
    assert latest_session(after) == date(2026, 11, 27)


def test_backfill_skips_open_session_and_shares_the_console_store(tmp_path, monkeypatch):
    db = tmp_path / "research.sqlite"
    monkeypatch.setenv("QUANTLAB_RESEARCH_DB", str(db))
    monkeypatch.delenv("QUANTLAB_OPPORTUNITY_DIR", raising=False)
    store = ResearchStore(str(db))
    store.upsert_bars([DailyBar("AAA", "2026-11-20", 10, 1_000, "equity", 10, "seed")])
    fetched = []
    pauses = []

    def fetcher(day):
        fetched.append(day)
        return [DailyBar("AAA", day, 11, 2_000_000, "equity", 11, "test")]

    class Publisher:
        def __init__(self):
            self.rows = []

        def publish(self, topic, payload):
            self.rows.append((topic, payload))

    publisher = Publisher()
    asof = run_once(
        ONE_THIRTY,
        fetcher=fetcher,
        sleeper=lambda seconds: pauses.append(seconds),
        store=store,
        publisher=publisher,
        sleep_seconds=13,
    )
    assert asof == date(2026, 11, 23)
    assert "2026-11-24" not in fetched
    assert "2026-11-23" in fetched
    assert "2026-11-20" not in fetched
    assert fetched == [day.isoformat() for day in missing_sessions({"2026-11-20"}, ONE_THIRTY)]
    assert len(pauses) == len(fetched) - 1
    report = ResearchStore(research_dsn()).latest_report()
    assert report["data_asof"] == "2026-11-23"
    assert report["movers"]["equity"]["month"]
    payload = publisher.rows[0]
    assert payload[0] == TOPIC_AUDIT
    assert payload[1]["kind"] == "OPPORTUNITY_REPORT_READY"
    assert payload[1]["data_asof"] == "2026-11-23"
    assert "path" not in payload[1]
    assert "Research only" in payload[1]["summary"]


def test_complete_store_does_not_call_the_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("QUANTLAB_OPPORTUNITY_DIR", raising=False)
    store = ResearchStore(str(tmp_path / "research.sqlite"))
    bars = [
        DailyBar("AAA", day.isoformat(), 10 + index, 2_000_000, "equity", 10 + index, "seed")
        for index, day in enumerate(closed_sessions(ONE_THIRTY))
    ]
    store.upsert_bars(bars)

    def fetcher(day):
        raise AssertionError(day)

    class Publisher:
        def publish(self, topic, payload):
            self.payload = payload

    publisher = Publisher()
    assert run_once(ONE_THIRTY, fetcher=fetcher, sleeper=lambda *_: None, store=store, publisher=publisher) == date(2026, 11, 23)
    assert store.latest_report()["data_asof"] == "2026-11-23"
    assert publisher.payload["observed_bars"] == len(bars)
