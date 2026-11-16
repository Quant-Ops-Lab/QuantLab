"""Consistent time-bucketed news retrieval for UI and assistant consumers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Iterable


WINDOWS = {
    "today": timedelta(days=1),
    "7 days": timedelta(days=7),
    "14 days": timedelta(days=14),
    "31 days": timedelta(days=31),
}


@dataclass(frozen=True)
class NewsItem:
    headline: str
    summary: str
    source: str
    url: str
    published_at: datetime
    received_at: datetime | None
    kind: str
    provider: str


def _timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _value(item, name: str, default=""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def normalize_news(items: Iterable[object]) -> list[NewsItem]:
    result = []
    for item in items:
        published = _timestamp(_value(item, "published_at"))
        if published is None:
            continue
        received = _timestamp(_value(item, "received_at"))
        result.append(NewsItem(
            headline=str(_value(item, "headline", "Untitled story"))[:500],
            summary=str(_value(item, "summary", _value(item, "evidence", "")))[:1500],
            source=str(_value(item, "source", _value(item, "provider", "Unknown source"))),
            url=str(_value(item, "url", _value(item, "source_url", ""))),
            published_at=published,
            received_at=received,
            kind=str(_value(item, "kind", "NEWS")),
            provider=str(_value(item, "provider", "journal")),
        ))
    return sorted(result, key=lambda item: item.published_at, reverse=True)


def bucket_news(items: Iterable[object], now: datetime | None = None) -> dict[str, list[NewsItem]]:
    """Return public recent windows plus an unbounded archive for admin retrieval."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    now = now.astimezone(timezone.utc)
    normalized = normalize_news(items)
    return {
        name: [item for item in normalized if now - window <= item.published_at <= now]
        for name, window in WINDOWS.items()
    } | {"archive": normalized}
