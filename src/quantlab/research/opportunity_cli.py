"""Offline daily opportunity audit; external provider data supplied as CSV."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from quantlab.research.opportunity import (Coverage, Decision, build_report, read_bars_csv,
                                           read_jsonl, render_markdown)


def main(argv=None):
    p = argparse.ArgumentParser(description='Generate retrospective movers and model-miss audit')
    p.add_argument('--bars', required=True, help='CSV: symbol,session,close,volume,market,adjusted_close,source')
    p.add_argument('--decisions', help='Point-in-time model decision JSONL')
    p.add_argument('--coverage', help='Point-in-time watchlist snapshots JSONL')
    p.add_argument('--asof', help='YYYY-MM-DD, defaults to latest observed date')
    p.add_argument('--top', type=int, default=20)
    p.add_argument('--output', default='artifacts/opportunity')
    args = p.parse_args(argv)
    result = build_report(read_bars_csv(args.bars),
                          read_jsonl(args.decisions, Decision),
                          read_jsonl(args.coverage, Coverage),
                          asof=args.asof, top_n=args.top)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'latest.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'latest.md').write_text(render_markdown(result))
    print(f"Report: {output / 'latest.md'} (observed sessions ending {result['data_asof']})")


if __name__ == '__main__':
    main()
