"""Load existing opportunity bars into the shared research database.

This writes research rows only. It does not place orders and it does not
connect anywhere unless --fetch is set. Do not point QUANTLAB_RESEARCH_DB at
production unless you intend to write those rows.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone
from pathlib import Path

from quantlab.market.massive_eod import fetch_market_day
from quantlab.research.opportunity import Coverage, Decision, build_report, read_bars_csv, read_jsonl, render_markdown
from quantlab.research.store import ResearchStore, research_dsn
from quantlab.services.research_daemon import closed_sessions_between, latest_session


def import_bars_csv(path: str | Path, store: ResearchStore) -> int:
    return store.upsert_bars(read_bars_csv(path))


def rebuild_report(
    store: ResearchStore,
    *,
    now: datetime | None = None,
    decisions: list | None = None,
    coverage: list | None = None,
) -> dict:
    """Build the autopsy from stored bars, as of the newest closed session present."""
    bars = store.load_bars()
    if not bars:
        raise RuntimeError("no stored bars to report")
    target = latest_session(now).isoformat()
    usable = [bar for bar in bars if bar.session <= target]
    if not usable:
        raise RuntimeError("no bars on or before the last closed session")
    asof = max(bar.session for bar in usable)
    report = build_report(usable, decisions or [], coverage or [], asof=asof)
    store.save_report(report, render_markdown(report))
    return report


def fetch_closed_sessions(
    start: str,
    end: str,
    store: ResearchStore,
    *,
    now: datetime | None = None,
    fetcher=None,
    sleeper=None,
    sleep_seconds: float = 13.0,
    api_key: str | None = None,
) -> list[str]:
    """Download closed sessions in [start, end]. Open sessions are skipped."""
    start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    if end_d < start_d or (end_d - start_d).days > 70:
        raise ValueError("Dates must be ordered and no more than 70 calendar days apart")
    if not 0 <= sleep_seconds <= 600:
        raise ValueError("sleep must be 0..600 seconds")
    moment = now or datetime.now(timezone.utc)
    days = closed_sessions_between(start_d, end_d, moment)
    if fetcher is None:
        key = api_key if api_key is not None else os.getenv("MASSIVE_API_KEY", "")
        if not key:
            raise RuntimeError("MASSIVE_API_KEY is required for --fetch")

        def fetcher(day: str):
            return fetch_market_day(day, key)

    pause = sleeper or __import__("time").sleep
    fetched: list[str] = []
    for index, session in enumerate(days):
        day = session.isoformat()
        rows = fetcher(day)
        if not rows or any(row.session != day for row in rows):
            raise RuntimeError(f"no bars for closed session {day}")
        store.upsert_bars(rows)
        fetched.append(day)
        if index + 1 < len(days):
            pause(sleep_seconds)
    return fetched


def _optional_jsonl(path: str | None, model):
    if not path:
        return []
    file = Path(path)
    if not file.exists():
        return []
    return read_jsonl(file, model)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Backfill research bars into QUANTLAB_RESEARCH_DB. Does not place orders."
    )
    parser.add_argument("--bars", help="Existing daily_bars.csv to import (no network)")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Download closed sessions from Massive. Requires MASSIVE_API_KEY.",
    )
    parser.add_argument("--start", help="First calendar day for --fetch (YYYY-MM-DD)")
    parser.add_argument("--end", help="Last calendar day for --fetch (YYYY-MM-DD)")
    parser.add_argument("--rebuild", action="store_true", help="Write the autopsy from stored bars")
    parser.add_argument("--dsn", help="Override QUANTLAB_RESEARCH_DB / QUANTLAB_ALERT_DB")
    parser.add_argument("--decisions", help="Optional decisions.jsonl used when rebuilding")
    parser.add_argument("--coverage", help="Optional watchlist_history.jsonl used when rebuilding")
    parser.add_argument("--sleep", type=float, default=13.0, help="Delay between provider requests")
    args = parser.parse_args(argv)
    if not args.bars and not args.fetch and not args.rebuild:
        parser.error("Choose --bars, --fetch, and/or --rebuild")
    if args.fetch and (not args.start or not args.end):
        parser.error("--fetch requires --start and --end")
    store = ResearchStore(args.dsn or research_dsn())
    if args.bars:
        print(f"imported {import_bars_csv(args.bars, store)} new bars from {args.bars}")
    if args.fetch:
        days = fetch_closed_sessions(args.start, args.end, store, sleep_seconds=args.sleep)
        print(f"fetched {len(days)} closed sessions")
        if days:
            print(f"last fetched session: {days[-1]}")
    if args.rebuild or args.bars or args.fetch:
        report = rebuild_report(
            store,
            decisions=_optional_jsonl(args.decisions, Decision),
            coverage=_optional_jsonl(args.coverage, Coverage),
        )
        print(f"report stored for {report['data_asof']} ({report['observed_bars']} bars)")


if __name__ == "__main__":
    main()
