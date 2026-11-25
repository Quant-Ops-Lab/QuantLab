import csv
from datetime import datetime, timezone

from quantlab.research.backfill import fetch_closed_sessions, import_bars_csv, rebuild_report
from quantlab.research.opportunity import DailyBar
from quantlab.research.store import ResearchStore
from quantlab.services.research_daemon import closed_sessions


NOW = datetime(2026, 11, 24, 6, 30, tzinfo=timezone.utc)


def test_csv_backfill_covers_the_month_window(tmp_path):
    days = closed_sessions(NOW)[-22:]
    assert len(days) == 22 and days[-1].isoformat() == "2026-11-23"
    path = tmp_path / "daily_bars.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "session", "close", "volume", "market", "adjusted_close", "source"),
        )
        writer.writeheader()
        for index, day in enumerate(days):
            price = 100 + index
            writer.writerow(
                {
                    "symbol": "aaa",
                    "session": day.isoformat(),
                    "close": price,
                    "volume": 20_000,
                    "market": "equity",
                    "adjusted_close": price,
                    "source": "csv_backfill",
                }
            )
    store = ResearchStore(str(tmp_path / "research.sqlite"))
    assert import_bars_csv(path, store) == 22
    assert import_bars_csv(path, store) == 0
    report = rebuild_report(store, now=NOW)
    month = report["movers"]["equity"]["month"]
    assert report["data_asof"] == "2026-11-23"
    assert month[0]["start_session"] == days[0].isoformat()
    assert month[0]["end_session"] == days[-1].isoformat()
    assert "hindsight" in store.latest_markdown().lower() or "retrospective" in store.latest_markdown().lower()
    # Same database the console reader uses.
    assert ResearchStore(str(tmp_path / "research.sqlite")).latest_report()["observed_bars"] == 22


def test_fetch_backfill_requests_only_closed_sessions(tmp_path):
    store = ResearchStore(str(tmp_path / "research.sqlite"))
    seen = []

    def fetcher(day):
        seen.append(day)
        return [DailyBar("AAA", day, 12, 2_000_000, "equity", 12, "massive_grouped_adjusted")]

    fetched = fetch_closed_sessions(
        "2026-11-23",
        "2026-11-24",
        store,
        now=NOW,
        fetcher=fetcher,
        sleeper=lambda seconds: None,
        sleep_seconds=13,
    )
    assert fetched == ["2026-11-23"]
    assert seen == ["2026-11-23"]
    assert store.sessions() == ["2026-11-23"]
