"""Shared research bars and autopsy reports.

The research worker and the console both use this store. A file under
QUANTLAB_OPPORTUNITY_DIR is an optional export, not a second source of truth.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from quantlab.research.opportunity import DailyBar
from quantlab.services.storage import bind, connect, is_postgres


def research_dsn(env: dict | None = None) -> str:
    """Database both the research worker and the console read.

    QUANTLAB_RESEARCH_DB wins. Otherwise the shared alert database is used so
    a deployment that already injects QUANTLAB_ALERT_DB on both services stays
    consistent. Local runs fall back to one SQLite file.
    """
    source = os.environ if env is None else env
    for key in ("QUANTLAB_RESEARCH_DB", "QUANTLAB_ALERT_DB"):
        value = (source.get(key) or "").strip()
        if value:
            return value
    return "artifacts/research.sqlite"


def _sqlite_path(dsn: str) -> str | None:
    if is_postgres(dsn) or dsn == ":memory:":
        return None
    if dsn.startswith("sqlite:///"):
        return dsn[len("sqlite:///") :]
    return dsn


class ResearchStore:
    def __init__(self, dsn: str):
        self.dsn = str(dsn)
        path = _sqlite_path(self.dsn)
        if path:
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with connect(self.dsn) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS quantlab_daily_bars (
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    session TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    adjusted_close TEXT,
                    source TEXT NOT NULL,
                    PRIMARY KEY (market, symbol, session)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS quantlab_research_reports (
                    data_asof TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    body TEXT NOT NULL,
                    markdown TEXT NOT NULL
                )"""
            )

    def sessions(self, market: str = "equity") -> list[str]:
        marker = bind(self.dsn)
        with connect(self.dsn) as db:
            rows = db.execute(
                f"""SELECT DISTINCT session FROM quantlab_daily_bars
                    WHERE market={marker} ORDER BY session""",
                (market,),
            ).fetchall()
        return [row[0] for row in rows]

    def upsert_bars(self, rows: list[DailyBar]) -> int:
        """Insert bars. An existing symbol/session is left unchanged."""
        if not rows:
            return 0
        marker = bind(self.dsn)
        sql = f"""INSERT INTO quantlab_daily_bars
            (market, symbol, session, close, volume, adjusted_close, source)
            VALUES ({marker},{marker},{marker},{marker},{marker},{marker},{marker})
            ON CONFLICT (market, symbol, session) DO NOTHING"""
        inserted = 0
        with connect(self.dsn) as db:
            for bar in rows:
                cursor = db.execute(
                    sql,
                    (
                        bar.market,
                        bar.symbol,
                        bar.session,
                        repr(float(bar.close)),
                        repr(float(bar.volume)),
                        None if bar.adjusted_close is None else repr(float(bar.adjusted_close)),
                        bar.source,
                    ),
                )
                inserted += int(cursor.rowcount or 0)
        return inserted

    def load_bars(self) -> list[DailyBar]:
        with connect(self.dsn) as db:
            rows = db.execute(
                """SELECT symbol, session, close, volume, market, adjusted_close, source
                   FROM quantlab_daily_bars ORDER BY session, market, symbol"""
            ).fetchall()
        bars = []
        for symbol, session, close, volume, market, adjusted, source in rows:
            bars.append(
                DailyBar(
                    symbol=symbol,
                    session=session,
                    close=float(close),
                    volume=float(volume),
                    market=market,
                    adjusted_close=None if adjusted is None else float(adjusted),
                    source=source,
                )
            )
        return bars

    def save_report(self, report: dict, markdown: str) -> None:
        body = json.dumps(report, allow_nan=False)
        marker = bind(self.dsn)
        with connect(self.dsn) as db:
            db.execute(
                f"""INSERT INTO quantlab_research_reports
                    (data_asof, generated_at, body, markdown)
                    VALUES ({marker},{marker},{marker},{marker})
                    ON CONFLICT (data_asof) DO UPDATE SET
                        generated_at=excluded.generated_at,
                        body=excluded.body,
                        markdown=excluded.markdown""",
                (report["data_asof"], report["generated_at"], body, markdown),
            )

    def latest_report(self) -> dict | None:
        with connect(self.dsn) as db:
            row = db.execute(
                """SELECT body FROM quantlab_research_reports
                   ORDER BY data_asof DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            return None
        report = json.loads(row[0])
        if not isinstance(report, dict):
            raise ValueError("research report body is not an object")
        return report

    def latest_markdown(self) -> str | None:
        with connect(self.dsn) as db:
            row = db.execute(
                """SELECT markdown FROM quantlab_research_reports
                   ORDER BY data_asof DESC LIMIT 1"""
            ).fetchone()
        return None if row is None else row[0]
