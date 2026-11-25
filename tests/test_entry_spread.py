"""Wide Kraken books must fail the spread filter. Candle close is not a quote."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from quantlab.console.charts import Candle
from quantlab.market.kraken_rest import KrakenDataError, KrakenPublic, TickerQuote
from quantlab.services.entry_worker import CryptoEntryWorker, frame_from_ohlc


NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def _bars(now=NOW):
    base = (now - timedelta(minutes=22)).replace(microsecond=0)
    bars = []
    for index in range(22):
        close = 102.0 if index == 21 else 100.0
        volume = 400.0 if index == 21 else 100.0
        start = base + timedelta(minutes=index)
        bars.append(Candle(start, close, close + 0.5, close - 0.2, close, 4, volume))
    return bars


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class _Market:
    def __init__(self, quote):
        self.quote = quote

    def ohlc(self, pair, timeframe):
        assert pair == "BTC/USD" and timeframe == "1m"
        return _bars()

    def ticker(self, pair, now=None):
        assert pair == "BTC/USD" and now == NOW
        return self.quote


class _Publisher:
    def __init__(self):
        self.rows = []

    def publish(self, topic, payload):
        self.rows.append((topic, payload))


def test_ticker_parses_public_bid_ask():
    payload = {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "a": ["102.01000", "1", "1.000"],
                "b": ["101.99000", "1", "1.000"],
                "c": ["102.00000", "0.01000000"],
            }
        },
    }
    quote = KrakenPublic(opener=lambda *args, **kwargs: _Response(payload)).ticker("BTC/USD", NOW)
    assert quote.bid == Decimal("101.99000")
    assert quote.ask == Decimal("102.01000")
    assert quote.last == Decimal("102.00000")
    bad = {"error": ["EGeneral:Invalid arguments"]}
    with pytest.raises(KrakenDataError):
        KrakenPublic(opener=lambda *args, **kwargs: _Response(bad)).ticker("BTC/USD", NOW)


def test_wide_spread_is_rejected_and_tight_spread_can_pass():
    bars = _bars()
    close = Decimal(str(bars[-1].close))
    wide = TickerQuote("BTC/USD", Decimal("100"), Decimal("101"), Decimal("100.5"), NOW)
    frame = frame_from_ohlc("BTC/USD", bars, wide, NOW)
    assert frame.bid == wide.bid and frame.ask == wide.ask
    assert frame.bid != close and frame.ask != close
    publisher = _Publisher()
    rejected = CryptoEntryWorker(_Market(wide), publisher, ("BTC/USD",)).cycle(NOW)
    assert rejected[0].status == "NO_TRADE"
    assert "spread too wide" in rejected[0].reasons
    assert publisher.rows == []

    tight = TickerQuote("BTC/USD", Decimal("101.99"), Decimal("102.01"), Decimal("102"), NOW)
    publisher = _Publisher()
    accepted = CryptoEntryWorker(_Market(tight), publisher, ("BTC/USD",)).cycle(NOW)
    assert "spread too wide" not in accepted[0].reasons
    assert accepted[0].status == "CANDIDATE"
    assert accepted[0].entry == Decimal("102.01")
    assert publisher.rows[0][1]["execution"] == "NOT_AUTHORIZED"


def test_stale_ticker_is_rejected():
    stale = TickerQuote("BTC/USD", Decimal("101.99"), Decimal("102.01"), Decimal("102"), NOW - timedelta(seconds=60))
    with pytest.raises(ValueError, match="stale"):
        frame_from_ohlc("BTC/USD", _bars(), stale, NOW)
