"""Whole-market opportunity autopsy, distinct from signal generation.

Data is externally supplied point-in-time observations; no invented prices.
An observed rally does NOT prove an executable missed trade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import json
import math

WINDOWS = {"equity": {"day": 1, "week": 5, "month": 21},
           "crypto": {"day": 1, "week": 7, "month": 30}}
EST = ZoneInfo("America/New_York")


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must have a timezone offset")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    session: str
    close: float
    volume: float
    market: str = "equity"
    adjusted_close: float | None = None
    source: str = "unspecified"

    def __post_init__(self):
        _day(self.session)
        if not self.symbol or self.market not in WINDOWS:
            raise ValueError("Unknown instrument or market")
        if not math.isfinite(self.close) or self.close <= 0 or not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError("Invalid price or volume")
        if self.adjusted_close is not None and (not math.isfinite(self.adjusted_close) or self.adjusted_close <= 0):
            raise ValueError("Invalid adjusted close")


@dataclass(frozen=True)
class Decision:
    symbol: str
    decision_at: str
    decision: str  # ENTER, REJECT, WATCH, EXIT
    strategy: str = "unknown"
    reason: str = ""

    def __post_init__(self):
        _utc(self.decision_at)
        if self.decision not in {"ENTER", "REJECT", "WATCH", "EXIT"}:
            raise ValueError("Invalid decision")


@dataclass(frozen=True)
class Coverage:
    """Point-in-time proof of the watcher's coverage. Retroactive lists not valid."""
    symbol: str
    asof: str
    monitored: bool

    def __post_init__(self):
        _utc(self.asof)


@dataclass(frozen=True)
class Move:
    symbol: str
    market: str
    window: str
    start_session: str
    end_session: str
    return_pct: float
    start_price: float
    end_price: float
    dollar_volume: float
    eligible_liquidity: bool
    price_basis: str
    classification: str
    strategy: str | None
    decision_at: str | None
    reason: str


def _cutoff(session: str, market: str) -> datetime:
    d = _day(session)
    if market == "equity":
        return datetime.combine(d, time(16, 0), tzinfo=EST).astimezone(timezone.utc)
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def _state(states: list[Coverage], symbol: str, cutoff: datetime) -> bool | None:
    valid = [s for s in states if s.symbol == symbol and _utc(s.asof) <= cutoff]
    if not valid:
        return None
    return max(valid, key=lambda s: _utc(s.asof)).monitored


def _classification(symbol: str, start: str, end: str, market: str,
                    decisions: list[Decision], coverage: list[Coverage],
                    liquid: bool, max_signal_age_days: int) -> tuple[str, Decision | None]:
    start_at = _cutoff(start, market)
    end_at = _cutoff(end, market)
    monitored = _state(coverage, symbol, start_at)
    if not liquid:
        return "NOT_LIQUID", None
    if monitored is False:
        return "OUTSIDE_WATCHLIST", None
    if monitored is None:
        return "COVERAGE_UNKNOWN", None
    earlier = [x for x in decisions if x.symbol == symbol and
               start_at - timedelta(days=max_signal_age_days) <= _utc(x.decision_at) <= start_at]
    if earlier:
        item = max(earlier, key=lambda x: _utc(x.decision_at))
        return {"ENTER": "ENTRY_IDENTIFIED", "REJECT": "REJECTED_BY_MODEL",
                "WATCH": "WATCHED_NO_ENTRY", "EXIT": "EXITED_BEFORE_MOVE"}[item.decision], item
    late = [x for x in decisions if x.symbol == symbol and start_at < _utc(x.decision_at) <= end_at]
    if late:
        return "LATE_DETECTION", min(late, key=lambda x: _utc(x.decision_at))
    return "NO_RECORDED_SIGNAL", None


def build_report(bars: list[DailyBar], decisions: list[Decision] | None = None,
                 coverage: list[Coverage] | None = None, *, asof: str | None = None,
                 top_n: int = 20, minimum_dollar_volume: float = 1_000_000,
                 max_signal_age_days: int = 7) -> dict:
    if not bars or top_n <= 0 or minimum_dollar_volume < 0 or max_signal_age_days < 0:
        raise ValueError("Valid observed bars and positive limits are required")
    decisions = decisions or []
    coverage = coverage or []
    indexed: dict[tuple[str, str], DailyBar] = {}
    days: dict[str, set[str]] = {market: set() for market in WINDOWS}
    for b in bars:
        key = (b.market, b.symbol, b.session)
        # Same symbol/day with two different prices is a conflict, not a reason to overwrite.
        if key in indexed and indexed[key] != b:
            raise ValueError(f"Conflicting price observations {key}")
        indexed[key] = b
        days[b.market].add(b.session)
    asof = asof or max(b.session for b in bars)
    _day(asof)
    results: dict[str, dict[str, list[dict]]] = {}
    gaps: dict[str, dict[str, int]] = {}
    exception_inventory: dict[str,dict[str,list[dict]]] = {}
    cohort: dict[str,dict[str,dict]] = {}
    opportunity_thresholds = {"day": 8.0, "week": 15.0, "month": 25.0}  # RETROSPECTIVE movement only
    for market, windows in WINDOWS.items():
        sessions = sorted(s for s in days[market] if s <= asof)
        results[market] = {}
        gaps[market] = {}
        exception_inventory[market] = {}
        cohort[market] = {}
        for window, lookback in windows.items():
            if len(sessions) <= lookback:
                results[market][window] = []
                gaps[market][window] = 0
                exception_inventory[market][window] = []
                cohort[market][window] = {"observed_symbols": 0, "liquid": 0, "classification_counts": {}}
                continue
            start, end = sessions[-lookback - 1], sessions[-1]
            symbols = sorted({sym for mk, sym, day in indexed if mk == market and day == end})
            moves = []
            missing = 0
            for symbol in symbols:
                before, after = indexed.get((market, symbol, start)), indexed[(market, symbol, end)]
                if before is None:
                    missing += 1
                    continue
                adjusted = before.adjusted_close is not None and after.adjusted_close is not None
                p0 = before.adjusted_close if adjusted else before.close
                p1 = after.adjusted_close if adjusted else after.close
                ret = 100 * (p1 / p0 - 1)
                # This is an average daily volume approximation, NOT guaranteed exit liquidity.
                dollar_volume = after.close * after.volume
                liquid = dollar_volume >= minimum_dollar_volume
                status, evidence = _classification(symbol, start, end, market, decisions, coverage,
                                                    liquid, max_signal_age_days)
                basis = "adjusted" if adjusted else ("spot" if market == "crypto" else "raw_unadjusted")
                if market == "equity" and not adjusted and abs(ret) >= 25:
                    status = "CORPORATE_ACTION_CHECK"  # possible split, not a verified rally
                moves.append(Move(symbol, market, window, start, end, round(ret, 4),
                                  round(p0, 8), round(p1, 8), round(dollar_volume, 2),
                                  liquid, basis, status,
                                  evidence.strategy if evidence else None,
                                  evidence.decision_at if evidence else None,
                                  evidence.reason if evidence else ""))
            # Rank price movement, not fabricated profits. Includes illiquid rows for transparency.
            moves.sort(key=lambda m: (-m.return_pct, m.symbol))
            results[market][window] = [asdict(x) for x in moves[:top_n]]
            # No top-N cut on this inventory: inspect ALL outsized movers for every window.
            exception_inventory[market][window] = [asdict(x) for x in moves
                                                    if x.return_pct >= opportunity_thresholds[window]]
            counts: dict[str, int] = {}
            for x in moves:
                counts[x.classification] = counts.get(x.classification, 0) + 1
            cohort[market][window] = {"observed_symbols": len(moves),
                                      "liquid": sum(x.eligible_liquidity for x in moves),
                                      "classification_counts": counts,
                                      "outsized_movers": len(exception_inventory[market][window])}
            gaps[market][window] = missing
    return {
        "schema_version": "1.0", "data_asof": asof,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "observed_inputs_only", "data_sources": sorted({b.source for b in bars}),
        "observed_bars": len(indexed), "decisions": len(decisions),
        "coverage_snapshots": len(coverage), "top_n": top_n,
        "movers": results, "outsized_move_inventory": exception_inventory,
        "cohort": cohort, "retrospective_move_threshold_pct": opportunity_thresholds,
        "missing_start_bars": gaps,
        "warnings": [
            "Top movers are hindsight rankings, never proof of actionable missed profit.",
            "No verified watchlist-at-time => COVERAGE_UNKNOWN, not a fabricated model miss.",
            "Raw equity prices may contain splits; large raw moves require corporate-action review.",
            "Earnings/news publication time, available bid-ask spread, market impact, halts, and borrow eligibility are not inferred.",
            "Crypto reported volume may not represent executable depth; zero-cost return is not achievable profit.",
        ],
    }


def render_markdown(report: dict) -> str:
    lines = [f"# QuantLab Daily Market Autopsy — {report['data_asof']}", "",
             "**Observed market data, retrospective returns. Not signals or executable P&L.**", "",
             f"Inputs: {report['observed_bars']} bars, {report['decisions']} decisions, "
             f"{report['coverage_snapshots']} coverage snapshots.", ""]
    for market, windows in report['movers'].items():
        for window, entries in windows.items():
            lines += [f"## {market.title()} — {window}", "",
                      "| Symbol | Return | Volume ($) | Audit | Price basis |",
                      "|---|---:|---:|---|---|"]
            for e in entries:
                lines.append(f"| {e['symbol']} | {e['return_pct']:+.2f}% | "
                             f"{e['dollar_volume']:,.0f} | {e['classification']} | {e['price_basis']} |")
            if not entries:
                lines.append("*Insufficient observations for this horizon.*")
            total=report['cohort'][market][window]
            lines.append(f"Scanned {total['observed_symbols']} complete symbols; "
                         f"{total.get('outsized_movers',0)} exceeded the retrospective move threshold. "
                         "Full set is in the JSON `outsized_move_inventory` (not cut to top-N).")
            lines.append("")
    lines += ["## Interpretation limits", ""] + ["- " + w for w in report['warnings']]
    return "\n".join(lines) + "\n"


def read_bars_csv(path: str | Path) -> list[DailyBar]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [DailyBar(symbol=row['symbol'].strip().upper(), session=row['session'],
                         close=float(row['close']), volume=float(row.get('volume') or 0),
                         market=row.get('market') or 'equity',
                         adjusted_close=float(row['adjusted_close']) if row.get('adjusted_close') else None,
                         source=row.get('source') or 'user_csv') for row in csv.DictReader(fh)]


def read_jsonl(path: str | Path, model):
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        return [model(**json.loads(s)) for s in fh if s.strip()]
