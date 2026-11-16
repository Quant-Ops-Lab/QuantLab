"""QuantLab operator CLI. 'run' routes alerts only; never submits an order."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from .planner import draft
from .contracts import StrategySpec,SignalObservation
from .notifications import JsonlPublisher
from .sdk import QuantLabClient

def main():
    p=argparse.ArgumentParser(prog='quantlabctl',description='QuantLab v0.3 alert-only control plane')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('draft',help='generate a typed strategy draft from explicit settings')
    a.add_argument('--description',required=True)
    a.add_argument('--symbols',nargs='+',required=True)
    a.add_argument('--direction',choices=['long','bearish'],default='bearish')
    a.add_argument('--mode',choices=['alert_only','approval_required'],default='alert_only')
    a.add_argument('--threshold-bps',type=int,default=30)
    a.add_argument('--out',default='strategy.json')
    r=sub.add_parser('run',help='evaluate one explicit observation; local operator-input provenance blocks alerts')
    r.add_argument('--strategy',required=True)
    r.add_argument('--symbol',required=True)
    r.add_argument('--price-change-bps',type=float,required=True)
    r.add_argument('--confirmed',action='store_true')
    r.add_argument('--source',default='manual-cli')
    r.add_argument('--events',default='artifacts/alerts.jsonl')
    r.add_argument('--source-type',choices=['operator_input'],default='operator_input')
    c=sub.add_parser('check',help='validate strategy JSON and show hash')
    c.add_argument('--strategy',required=True)
    args=p.parse_args()
    if args.cmd=='draft':
        spec=draft(args.description,args.symbols,args.direction,args.mode,args.threshold_bps)
        out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(spec.to_dict(),indent=2)+'\n')
        print(json.dumps({'draft_path':str(out),'fingerprint':spec.fingerprint,'mode':spec.mode.value},indent=2))
    else:
        spec=StrategySpec.from_dict(json.loads(Path(args.strategy).read_text()))
        if args.cmd=='check':
            print(json.dumps({'valid':True,'fingerprint':spec.fingerprint,'mode':spec.mode.value},indent=2));return
        now=datetime.now(timezone.utc)
        obs=SignalObservation(args.symbol,now,args.price_change_bps,args.confirmed,args.source,args.source_type)
        result=QuantLabClient(JsonlPublisher(Path(args.events))).run_once(spec,obs,now)
        print(json.dumps(result.to_dict(),indent=2))

if __name__=='__main__': main()
