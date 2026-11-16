"""Read-only U.S. market EOD grouped daily provider for broad discovery.

Massive Basic supports EOD grouped daily OHLC, subject to plan limits and
recency. This connector never trades and never calls a model.
"""
from __future__ import annotations
import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
from time import sleep
from urllib.request import Request, urlopen
from quantlab.research.opportunity import DailyBar

FIELDS = ('symbol','session','close','volume','market','adjusted_close','source')

class EODProviderError(RuntimeError):
    pass


def fetch_market_day(day: str, api_key: str, *, opener=None) -> list[DailyBar]:
    date.fromisoformat(day)
    if not api_key:
        raise ValueError('MASSIVE_API_KEY is required')
    if not day or not day[0].isdigit():
        raise ValueError('bad date')
    endpoint = f'https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{day}?adjusted=true&include_otc=false'
    req = Request(endpoint, headers={'Authorization':f'Bearer {api_key}',
                                     'Accept':'application/json',
                                     'User-Agent':'QuantLab/0.7-opportunity-audit'})
    try:
        with (opener or urlopen)(req, timeout=30) as resp:
            data=json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        raise EODProviderError(f'Market data request failed: {type(exc).__name__}') from None
    if not isinstance(data, dict) or data.get('status') not in ('OK','DELAYED'):
        raise EODProviderError('Invalid provider status or schema')
    if not isinstance(data.get('results'), list):
        # Weekends/holidays may return absent results with resultsCount=0.
        if data.get('resultsCount') == 0:
            return []
        raise EODProviderError('Missing grouped market results')
    adjusted = data.get('adjusted') is True
    result=[]
    for obj in data['results']:
        try:
            sym=obj['T']
            price=float(obj['c'])
            vol=float(obj['v'])
            result.append(DailyBar(sym,day,price,vol,'equity',price if adjusted else None,
                                   'massive_grouped_adjusted' if adjusted else 'massive_grouped_raw'))
        except (KeyError,ValueError,TypeError):
            continue  # Invalid rows excluded; coverage counts must show source shortfall.
    if data.get('resultsCount') is not None and len(result) < int(data['resultsCount']) * .90:
        raise EODProviderError('Excessive invalid rows in provider result')
    return result


def append_bars(path: Path, rows: list[DailyBar]) -> int:
    """Idempotent per-symbol/session, preserving data already collected."""
    path.parent.mkdir(parents=True,exist_ok=True)
    known=set()
    if path.exists():
        with path.open(newline='',encoding='utf-8') as fh:
            known={(r['market'],r['symbol'],r['session']) for r in csv.DictReader(fh)}
    fresh=[b for b in rows if (b.market,b.symbol,b.session) not in known]
    with path.open('a',newline='',encoding='utf-8') as fh:
        wr=csv.DictWriter(fh,fieldnames=FIELDS)
        if not known and path.stat().st_size == 0:
            wr.writeheader()
        for b in fresh:
            wr.writerow({f:getattr(b,f) for f in FIELDS})
    return len(fresh)


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description='Fetch whole-market adjusted EOD bars from Massive')
    p.add_argument('--start',required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--output',default='artifacts/opportunity/daily_bars.csv')
    p.add_argument('--sleep',type=float,default=13.0,help='Delay between requests for rate limits')
    args=p.parse_args(argv)
    start,end=date.fromisoformat(args.start),date.fromisoformat(args.end)
    if end<start or (end-start).days>70 or not 0 <= args.sleep <= 600:
        p.error('Dates must be ordered and no more than 70 calendar days apart')
    api_key=os.getenv('MASSIVE_API_KEY','')
    if not api_key:
        p.error('Set MASSIVE_API_KEY in the environment (never in source)')
    out=Path(args.output)
    d=start
    while d<=end:
        if d.weekday()<5:
            try:
                rows=fetch_market_day(d.isoformat(),api_key)
            except EODProviderError as exc:
                print(f'{d}: {exc}. Existing data preserved; aborting.')
                raise SystemExit(1) from None
            count=append_bars(out,rows) if rows else 0
            print(f'{d}: {count} new symbols, {len(rows)} observed')
            if d<end:
                sleep(args.sleep)
        d+=timedelta(days=1)
    print(f'Price history: {out}')


if __name__=='__main__':
    main()
