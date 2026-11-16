"""Deterministic research answers for the consumer console.

This is deliberately not an LLM and never produces an order recommendation.
It summarizes only the selected instrument's observed candles, metadata, alerts,
and verified disclosures so an eventual model can be evaluated against a clear
baseline instead of hiding missing evidence behind fluent text.
"""
from __future__ import annotations

import json
from datetime import datetime
from math import sqrt
from statistics import mean
from typing import Iterable

from quantlab.console.charts import Candle


def _news_value(item, name: str, default=""):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _return(candles: list[Candle], periods: int) -> float | None:
    if len(candles) <= periods or candles[-periods - 1].close <= 0:
        return None
    return (candles[-1].close / candles[-periods - 1].close - 1.0) * 100.0


def _volatility(candles: list[Candle]) -> float | None:
    changes = [b.close / a.close - 1.0 for a, b in zip(candles[-21:-1], candles[-20:]) if a.close > 0]
    if len(changes) < 2:
        return None
    average = mean(changes)
    return sqrt(mean((change - average) ** 2 for change in changes)) * 100.0


def answer(
    symbol: str,
    question: str,
    candles: Iterable[Candle],
    *,
    asset=None,
    events: Iterable[dict] = (),
    alerts: Iterable[dict] = (),
    news: Iterable[object] = (),
    model=None,
) -> str:
    """Answer a bounded research question from observed evidence only."""
    series = list(candles)
    prompt = question.strip().lower()
    if not series:
        return f"I cannot assess {symbol}: there are no completed observed candles in the selected feed."
    latest = series[-1]
    day_return = _return(series, 1)
    week_return = _return(series, 5)
    month_return = _return(series, 21)
    volatility = _volatility(series)
    high = max(item.high for item in series)
    low = min(item.low for item in series)
    timestamp = latest.start.strftime("%Y-%m-%d %H:%M UTC")
    snapshot = (
        f"{symbol} last completed close: ${latest.close:,.2f} at {timestamp}. "
        f"Observed returns: 1 bar {day_return:+.2f}%" if day_return is not None else
        f"{symbol} last completed close: ${latest.close:,.2f} at {timestamp}."
    )
    if week_return is not None:
        snapshot += f", 5 bars {week_return:+.2f}%"
    if month_return is not None:
        snapshot += f", 21 bars {month_return:+.2f}%"
    if volatility is not None:
        snapshot += f". Recent close-to-close volatility is {volatility:.2f}% per bar"

    if model is not None:
        evidence = {
            "symbol": symbol,
            "question": question,
            "observed_candles": [
                {"timestamp": item.start.isoformat(), "open": item.open, "high": item.high,
                 "low": item.low, "close": item.close, "volume": item.volume}
                for item in series[-60:]
            ],
            "observed_high": high,
            "observed_low": low,
            "events": list(events)[:20],
            "news": [
                {"headline": _news_value(item, "headline"), "source": _news_value(item, "source"),
                 "published_at": _news_value(item, "published_at").isoformat()
                 if hasattr(_news_value(item, "published_at"), "isoformat") else str(_news_value(item, "published_at")),
                 "url": _news_value(item, "url")}
                for item in list(news)[:20]
            ],
        }
        if asset is not None:
            evidence["research_metadata"] = {
                "symbol": asset.symbol, "name": asset.name,
                "kind": asset.kind.value, "themes": list(asset.themes),
            }
        try:
            model_text = model(
                """You are a read-only market research assistant. Use only the supplied JSON evidence.
You may discuss observed momentum, highs, lows, utility, news context, and scenario-based risk.
Never invent facts, sources, prices, or returns. Never place, approve, or format a brokerage order.
Label opinions as research and include a heavy disclaimer that this is not personalized financial advice.""",
                json.dumps(evidence, sort_keys=True, default=str),
            )
            if isinstance(model_text, str) and model_text.strip():
                return "Model-assisted research view (not financial advice):\n\n" + model_text.strip() + "\n\nHeavy disclaimer: this is not personalized investment advice, a buy/sell instruction, or a guarantee of any outcome."
        except Exception:
            pass

    if any(term in prompt for term in ("high", "low", "range", "peak")):
        return (
            f"Factual chart summary for {symbol}: observed high ${high:,.2f}, observed low ${low:,.2f}, "
            f"latest completed close ${latest.close:,.2f}. {snapshot}. These are only the candles in the "
            "selected feed and timeframe; they are not lifetime or consolidated-market extremes."
        )

    if any(term in prompt for term in ("good trade", "good play", "buy", "enter", "short", "trade")):
        trend = "positive" if (day_return or 0) > 0 and (week_return or 0) > 0 else "mixed or negative"
        return (
            f"Research view, not financial advice: {symbol} has {trend} observed momentum. {snapshot}. "
            "That makes it a setup worth investigating, not a validated trade. The chart has no verified "
            "spread, depth, borrow status, fees, or current broker preflight. Heavy disclaimer: this is not "
            "personalized investment advice, is not a buy or sell instruction, and does not predict returns. "
            "Any real decision requires your own suitability review and independent execution checks."
        )
    if any(term in prompt for term in ("history", "historical", "news", "why", "happened")):
        records = list(events)
        articles = list(news)
        headlines = [str(item.get("headline", "Untitled disclosure")) for item in records[:3]]
        headlines.extend(str(_news_value(item, "headline", "Untitled article")) for item in articles[:3])
        if not headlines:
            return f"{snapshot}. No verified disclosures or recent news are stored for {symbol}."
        return f"{snapshot}. Recent verified context: {'; '.join(headlines)}. This is association, not proof of causality."
    if any(term in prompt for term in ("utility", "what is", "company", "asset", "use")):
        if asset is None:
            return f"{snapshot}. No instrument metadata is available beyond the ticker symbol."
        themes = ", ".join(asset.themes)
        return f"{asset.symbol} is listed as {asset.name} ({asset.kind.value}) in the research universe. Themes: {themes or 'none recorded'}. This describes research metadata, not an investment thesis."
    if any(term in prompt for term in ("hold", "exit", "take profit", "stop", "when should")):
        trend = "constructive" if (day_return or 0) > 0 and (week_return or 0) > 0 else "not clearly constructive"
        return (
            f"Scenario framework, not financial advice: the observed trend is {trend}. {snapshot}. "
            f"A research-only plan could reassess strength near the observed high ${high:,.2f} and treat a "
            f"break below the observed low ${low:,.2f} as a reason to revisit the thesis, not an automatic order. "
            "For a long-term hold, first document the utility/thesis, valuation, sizing, time horizon, and "
            "what evidence would invalidate it. Heavy disclaimer: this is not personalized investment advice, "
            "a guaranteed stop, or an instruction to enter or exit."
        )
    if any(term in prompt for term in ("safe", "risk", "risky")):
        return (
            f"Risk review, not a safety rating: {snapshot}. The current evidence does not establish safety. "
            "Check spread, depth, volatility, liquidity, news risk, corporate actions, borrow eligibility, "
            "fees, and your own loss tolerance before considering any position."
        )
    if alerts:
        return f"{snapshot}. There are {len(list(alerts))} recent research alerts for the account. Ask about trade quality, history, or utility for a focused answer."
    return f"{snapshot}. Ask whether it is a good trade, what verified history exists, or what utility the asset has."