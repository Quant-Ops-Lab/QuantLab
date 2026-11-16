"""Candlestick display primitives built only from timestamped observed trades/quotes.

If the quote store lacks enough observations, callers must show a conspicuous
DEMO/SYNTHETIC label instead of fabricating a live exchange candle.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from collections import defaultdict
from typing import Iterable
import random

TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}

@dataclass(frozen=True)
class Candle:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    samples: int = 1
    volume: float | None = None


def aggregate_quotes(rows: Iterable[dict], timeframe: str = "5m") -> list[Candle]:
    """Generate indicative OHLC from successive quote-last observations.

    These are *sampled quote* candles, not official trade OHLCV. Quotes can miss
    intrabar highs and lows, so the UI labels this data accordingly.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError("unsupported timeframe")
    seconds = TIMEFRAMES[timeframe]
    grouped = defaultdict(list)
    for row in rows:
        try:
            raw_time = row.get("timestamp") or row.get("provider_timestamp")
            dt = raw_time if isinstance(raw_time, datetime) else datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
            price = float(Decimal(str(row.get("last"))))
            if not (0 < price < 1e10):
                continue
        except (ValueError, TypeError, ArithmeticError):
            continue
        bucket = int(dt.timestamp()) // seconds * seconds
        grouped[bucket].append((dt.astimezone(timezone.utc), price))
    candles=[]
    for bucket in sorted(grouped):
        samples = sorted(grouped[bucket], key=lambda pair: pair[0])
        prices=[price for _,price in samples]
        candles.append(Candle(datetime.fromtimestamp(bucket,tz=timezone.utc),prices[0],max(prices),min(prices),prices[-1],len(prices)))
    return candles


def demo_candles(symbol: str, count: int = 72) -> list[Candle]:
    """Fixed-seed synthetic UI preview. NEVER suitable for inference or execution."""
    if not 1 <= count <= 300:
        raise ValueError("invalid demo candle count")
    rng = random.Random(f"quantlab-visual-preview:{symbol.upper()}")
    clock=datetime(2026, 1, 6, 14, 30, tzinfo=timezone.utc)
    price=100.0 + (sum(map(ord, symbol.upper())) % 180)
    out=[]
    for i in range(count):
        movement=rng.gauss(0,0.75) + (0.13 if i>count//2 else -0.03)
        new=max(1.0,price+movement)
        high=max(price,new)+rng.uniform(.05,.66)
        low=max(.01,min(price,new)-rng.uniform(.05,.64))
        out.append(Candle(clock+timedelta(minutes=5*i),price,high,low,new,1))
        price=new
    return out


def candlestick_figure(candles: list[Candle], symbol: str, *, demo: bool = False,
                       show_volume: bool = True, show_ema: bool = True,
                       show_range: bool = True):
    """Return a Plotly Figure; import is lazy for API/worker isolation."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    has_volume = show_volume and any(c.volume is not None and c.volume > 1 for c in candles)
    fig = make_subplots(rows=2 if has_volume else 1, cols=1, shared_xaxes=True,
                        vertical_spacing=.04, row_heights=[.78, .22] if has_volume else [1])
    if not candles:
        fig.add_annotation(text="No observed OHLC data",showarrow=False,font={"color":"#a9b9c7","size":18})
    else:
        xs=[c.start for c in candles]
        fig.add_trace(go.Candlestick(x=xs,open=[c.open for c in candles],high=[c.high for c in candles],
            low=[c.low for c in candles],close=[c.close for c in candles],name=symbol,
            increasing_line_color="#4ae7b4",increasing_fillcolor="#4ae7b4",
            decreasing_line_color="#ff6a86",decreasing_fillcolor="#ff6a86"), row=1, col=1)
        if show_ema and len(candles)>=20:
            closes=[c.close for c in candles]
            ema=[]; k=2/21; avg=closes[0]
            for value in closes:
                avg=value*k+avg*(1-k); ema.append(avg)
            fig.add_trace(go.Scatter(x=xs,y=ema,mode="lines",name="EMA 20 (indicative)",
                line={"color":"#dda5ff","width":1.6},opacity=.85), row=1, col=1)
            if len(candles) >= 50:
                slow=[]; k=2/51; avg=closes[0]
                for value in closes:
                    avg=value*k+avg*(1-k); slow.append(avg)
                fig.add_trace(go.Scatter(x=xs,y=slow,mode="lines",name="EMA 50 (indicative)",
                    line={"color":"#ffcb70","width":1.3},opacity=.8), row=1, col=1)
        if has_volume:
            fig.add_trace(go.Bar(x=xs,y=[c.volume for c in candles],name="Reported volume",
                marker_color="#416b82",opacity=.65), row=2, col=1)
    fig.update_layout(height=560 if has_volume else 450,margin={"l":8,"r":8,"t":14,"b":8},
        paper_bgcolor="#0d1520",plot_bgcolor="#0d1520",font={"color":"#99aabe"},
        xaxis={"showgrid":True,"gridcolor":"#1c2a37","rangeslider":{"visible":show_range},
               "rangeselector":{"buttons":[{"count":1,"label":"1D","step":"day","stepmode":"backward"},
                                             {"count":5,"label":"5D","step":"day","stepmode":"backward"},
                                             {"count":1,"label":"1M","step":"month","stepmode":"backward"},
                                             {"step":"all","label":"All"}]}},
        yaxis={"showgrid":True,"gridcolor":"#1c2a37","side":"right"},
        legend={"orientation":"h","y":1.08,"x":0,"font":{"size":10}},
        hovermode="x unified",showlegend=True)
    if demo:
        fig.add_annotation(text="SYNTHETIC DEMO · NOT MARKET DATA",showarrow=False,xref="paper",yref="paper",
            x=.5,y=.93,font={"color":"#ffcb70","size":12},bgcolor="#161d26",opacity=.95)
    return fig
