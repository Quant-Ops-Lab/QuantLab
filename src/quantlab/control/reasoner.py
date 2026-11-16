"""Read-only LLM explanation/strategy-compiler ports.

No network/model is connected in this release. Inject an independent callable
when the user configures a provider; never hand LLMs brokerage credentials.
"""
from __future__ import annotations
import json
from typing import Protocol, Any
from .contracts import StrategySpec,AlertDecision

class TextModel(Protocol):
    def __call__(self, system_prompt:str, evidence_json:str) -> str: ...

_EXPLAIN_SYSTEM = '''You are a read-only investment research explainer.
Use only the supplied verified evidence. No invented prices, timestamps, returns,
performance statistics, borrow availability, or categorical profit guarantees.
You cannot place orders, change risk parameters or approve a trade.
Output JSON with exactly these string fields: summary, limitations, next_checks.
Be explicit that a rule match is not a verified profitable prediction.'''

_COMPILE_SYSTEM = '''You convert the user's research description to a candidate
StrategySpec JSON object only. Do not produce Python, shell, network requests,
exchange orders, or brokerage actions. Allowed fields and values are described
in the supplied contract. Mode MUST be alert_only or approval_required.
Unknown requirements should be rejected rather than guessed. Return JSON.'''


def explain_read_only(model:TextModel,decision:AlertDecision)->dict[str,str]:
    raw=model(_EXPLAIN_SYSTEM,json.dumps(decision.to_dict(),sort_keys=True))
    obj=json.loads(raw)
    if set(obj)!={'summary','limitations','next_checks'} or not all(
        isinstance(v,str) and 0<len(v)<=3000 for v in obj.values()
    ):
        raise ValueError('invalid explanation response schema')
    return obj


def compile_description_read_only(model:TextModel,description:str)->StrategySpec:
    if not description.strip() or len(description)>2000:
        raise ValueError('invalid description')
    contract={'description':description,'required_fields':['strategy_id','description',
              'symbols','direction','mode','threshold_bps','max_signal_age_seconds','version'],
              'allowed_direction':['long','bearish'],
              'allowed_mode':['alert_only','approval_required'],
              'constraints':'no orders, validated symbols, finite integers; no guessed tickers'}
    raw=model(_COMPILE_SYSTEM,json.dumps(contract,sort_keys=True))
    obj=json.loads(raw)
    spec=StrategySpec.from_dict(obj)
    if spec.description!=description:
        raise ValueError('model changed operator description')
    return spec
