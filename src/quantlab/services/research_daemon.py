"""Scheduled EOD research process for the daily opportunity autopsy.

The job analyzes the most recent closed NYSE session, backfills closed sessions
that are missing from the shared research database, and publishes a brief.
It never places orders.
"""
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
from quantlab.market.massive_eod import fetch_market_day
from quantlab.research.opportunity import Coverage, Decision, build_report, read_jsonl, render_markdown
from quantlab.research.store import ResearchStore, research_dsn
from quantlab.services.publishers import build_publisher


LOG = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")
XNYS = xcals.get_calendar("XNYS")
# Long enough for the 21-session autopsy window, short of a multi-quarter pull.
LOOKBACK_DAYS = 45


def _aware(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone required")
    return now.astimezone(timezone.utc)


def _session_date(session) -> date:
    if isinstance(session, datetime):
        return session.date()
    return session


def _close_utc(session) -> datetime:
    close = XNYS.session_close(session).to_pydatetime()
    if close.tzinfo is None:
        close = close.replace(tzinfo=timezone.utc)
    return close.astimezone(timezone.utc)


def closed_sessions_between(start: date, end: date, now: datetime | None = None) -> list[date]:
    """XNYS sessions in the inclusive range whose official close is at or before now."""
    moment = _aware(now)
    if end < start:
        raise ValueError("end before start")
    sessions = XNYS.sessions_in_range(start.isoformat(), end.isoformat())
    closed = []
    for session in sessions:
        if _close_utc(session) <= moment:
            closed.append(_session_date(session))
    return closed


def closed_sessions(now: datetime | None = None, *, lookback_days: int = LOOKBACK_DAYS) -> list[date]:
    moment = _aware(now)
    local = moment.astimezone(NEW_YORK).date()
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")
    return closed_sessions_between(local - timedelta(days=lookback_days), local, moment)


def latest_session(now: datetime | None = None) -> date:
    """Most recent XNYS session that has already closed.

    A run at 01:30 America/New_York is before that calendar day's open, so the
    session for the local date is not eligible. Early closes use the exchange
    calendar's official close.
    """
    closed = closed_sessions(now)
    if not closed:
        raise RuntimeError("no recent closed XNYS session available")
    return closed[-1]


def missing_sessions(
    stored: set[date] | set[str],
    now: datetime | None = None,
    *,
    lookback_days: int = LOOKBACK_DAYS,
) -> list[date]:
    have: set[date] = set()
    for item in stored:
        have.add(item if isinstance(item, date) else date.fromisoformat(str(item)))
    return [session for session in closed_sessions(now, lookback_days=lookback_days) if session not in have]


def brief_payload(report: dict) -> dict:
    """Stable, secret-free summary for the notifier. Not an order."""
    movers = (report.get("movers") or {}).get("equity", {}).get("day") or []
    lines = [
        f"Session {report['data_asof']}",
        f"Observed bars: {report['observed_bars']}",
    ]
    for row in movers[:5]:
        symbol = "".join(ch for ch in str(row.get("symbol", "")) if ch.isalnum() or ch in ".-")
        if not symbol:
            continue
        try:
            change = float(row["return_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        lines.append(f"{symbol} {change:+.2f}% {row.get('classification', '')}".rstrip())
    lines.append("Research only. Not a trade instruction.")
    summary = "\n".join(lines).replace("@", "")[:1500]
    return {
        "kind": "OPPORTUNITY_REPORT_READY",
        "data_asof": report["data_asof"],
        "observed_bars": int(report["observed_bars"]),
        "generated_at": report["generated_at"],
        "title": f"QuantLab daily brief {report['data_asof']}"[:256],
        "summary": summary,
    }


def _sleep_seconds() -> float:
    raw = os.getenv("QUANTLAB_EOD_SLEEP_SECONDS", "13")
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("QUANTLAB_EOD_SLEEP_SECONDS must be a number") from exc
    if not 0 <= value <= 600:
        raise RuntimeError("QUANTLAB_EOD_SLEEP_SECONDS out of range")
    return value


def _load_side_inputs(root: Path) -> tuple[list, list]:
    decisions_path = root / "decisions.jsonl"
    coverage_path = root / "watchlist_history.jsonl"
    decisions = read_jsonl(decisions_path, Decision) if decisions_path.exists() else []
    coverage = read_jsonl(coverage_path, Coverage) if coverage_path.exists() else []
    return decisions, coverage


def _export_report(report: dict, markdown: str) -> None:
    raw = (os.getenv("QUANTLAB_OPPORTUNITY_DIR") or "").strip()
    if not raw:
        return
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (root / "latest.md").write_text(markdown, encoding="utf-8")


def run_once(
    now: datetime | None = None,
    *,
    fetcher=None,
    sleeper=None,
    store: ResearchStore | None = None,
    publisher=None,
    sleep_seconds: float | None = None,
) -> date:
    """Fetch missing closed sessions, store the autopsy, and publish a brief."""
    moment = _aware(now)
    store = store or ResearchStore(research_dsn())
    due = missing_sessions(set(store.sessions("equity")), moment)
    if due and fetcher is None:
        api_key = os.getenv("MASSIVE_API_KEY", "")
        if not api_key:
            raise RuntimeError("MASSIVE_API_KEY is required")

        def fetcher(day: str):
            return fetch_market_day(day, api_key)

    pause = sleeper or time.sleep
    gap = _sleep_seconds() if sleep_seconds is None else sleep_seconds
    for index, session in enumerate(due):
        day = session.isoformat()
        rows = fetcher(day)
        if not rows or any(row.session != day for row in rows):
            raise RuntimeError(f"no bars for closed session {day}")
        store.upsert_bars(rows)
        if index + 1 < len(due):
            pause(gap)
    target = latest_session(moment)
    bars = store.load_bars()
    if not any(bar.market == "equity" and bar.session == target.isoformat() for bar in bars):
        raise RuntimeError(f"missing closed session {target.isoformat()}")
    root = Path(os.getenv("QUANTLAB_OPPORTUNITY_DIR", "artifacts/opportunity"))
    decisions, coverage = _load_side_inputs(root)
    report = build_report(bars, decisions, coverage, asof=target.isoformat())
    markdown = render_markdown(report)
    store.save_report(report, markdown)
    _export_report(report, markdown)
    (publisher or build_publisher()).publish(TOPIC_AUDIT, brief_payload(report))
    return target


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
            LOG.info("Opportunity report session: %s", run_once().isoformat())
        except Exception as exc:
            LOG.exception("Opportunity research cycle failed: %s", type(exc).__name__)


if __name__ == "__main__":
    main()
