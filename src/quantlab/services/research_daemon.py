"""Scheduled EOD research process for the daily opportunity autopsy."""
from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from quantlab.control.notifications import TOPIC_AUDIT
from quantlab.market.massive_eod import append_bars, fetch_market_day
from quantlab.research.opportunity import Coverage, Decision, build_report, read_bars_csv, read_jsonl, render_markdown
from quantlab.services.publishers import build_publisher


LOG = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")
XNYS = xcals.get_calendar("XNYS")


def latest_session(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(NEW_YORK).date()
    sessions = XNYS.sessions_in_range(str(local - timedelta(days=7)), str(local))
    if len(sessions) == 0:
        raise RuntimeError("no recent XNYS session available")
    return sessions[-1].date()


def run_once() -> Path:
    api_key = os.getenv("MASSIVE_API_KEY", "")
    if not api_key:
        raise RuntimeError("MASSIVE_API_KEY is required")
    root = Path(os.getenv("QUANTLAB_OPPORTUNITY_DIR", "artifacts/opportunity"))
    bars_path = root / "daily_bars.csv"
    session = latest_session()
    rows = fetch_market_day(session.isoformat(), api_key)
    append_bars(bars_path, rows)
    decisions_path = root / "decisions.jsonl"
    coverage_path = root / "watchlist_history.jsonl"
    report = build_report(
        read_bars_csv(bars_path),
        read_jsonl(decisions_path, Decision) if decisions_path.exists() else [],
        read_jsonl(coverage_path, Coverage) if coverage_path.exists() else [],
        asof=session.isoformat(),
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path = root / "latest.md"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    build_publisher().publish(
        TOPIC_AUDIT,
        {"kind": "OPPORTUNITY_REPORT_READY", "data_asof": report["data_asof"],
         "path": str(markdown_path), "observed_bars": report["observed_bars"]},
    )
    return markdown_path


def seconds_until_run(now: datetime | None = None) -> float:
    """Schedule after the next-day EOD provider release window."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(NEW_YORK)
    # Massive Basic generally exposes the prior session after midnight ET.
    # Leave a release buffer rather than running at the old 22:30 ET time.
    target = datetime.combine(local.date(), clock_time(1, 30), tzinfo=NEW_YORK)
    if target <= local:
        target = datetime.combine(local.date() + timedelta(days=1), clock_time(1, 30), tzinfo=NEW_YORK)
    return max(1.0, (target - local).total_seconds())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        time.sleep(seconds_until_run())
        if stopped:
            break
        try:
            LOG.info("Opportunity report: %s", run_once())
        except Exception as exc:
            LOG.exception("Opportunity research cycle failed: %s", type(exc).__name__)


if __name__ == "__main__":
    main()