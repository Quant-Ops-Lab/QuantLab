"""Two-agent prompt experiments with immutable, identical input evidence.

This module constructs prompts and archives claims. It does not call an LLM,
change strategy parameters, judge profitability, or promote a model.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any

PRESERVE_PROMPT = """You are the PRESERVE research reviewer. Defend the current
strategy against unjustified post-trade changes. Assume changing it can
introduce overfitting. The researcher claims: 'do not change your strategy;
whatever you did worked and we need to retain this same model for all future
trades.' Treat this claim as a hypothesis, not a fact. Identify evidence for
retention, counterexamples and falsifiable tests. Never submit an order.
Reply ONLY with a JSON object with keys verdict, claims, proposed_tests."""

CHALLENGE_PROMPT = """You are the CHALLENGE research reviewer. Assume serious
hidden defects may exist. The researcher claims: 'we need to completely change
the strategy; this lost all my money.' Treat this claim as a hypothesis, not a
fact. Find leakage, incorrect costs, selection bias, stale features and regime
failures; propose falsifiable tests. Never submit an order.
Reply ONLY with a JSON object with keys verdict, claims, proposed_tests."""

NEUTRAL_PROMPT = """You are the NEUTRAL control reviewer. Consider both
retention and modification; identify falsifiable tests. Never submit an order.
Reply ONLY with a JSON object with keys verdict, claims, proposed_tests."""


@dataclass(frozen=True)
class EvidencePacket:
    strategy_sha: str
    model_sha: str
    data_sha: str
    asof_utc: str
    outcomes: tuple[dict[str, Any], ...]
    cost_assumptions: dict[str, float]

    def canonical(self) -> str:
        if not all([self.strategy_sha, self.model_sha, self.data_sha, self.asof_utc]):
            raise ValueError("missing evidence snapshot identifiers")
        return json.dumps({
            'strategy_sha': self.strategy_sha, 'model_sha': self.model_sha,
            'data_sha': self.data_sha, 'asof_utc': self.asof_utc,
            'outcomes': self.outcomes, 'cost_assumptions': self.cost_assumptions,
        }, sort_keys=True, separators=(',', ':'), allow_nan=False)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


def trials(packet: EvidencePacket) -> dict[str, dict[str, str]]:
    """Each agent sees byte-identical evidence. Prompt role is the only treatment."""
    same_packet = packet.canonical()
    return {k: {'system_prompt': v, 'evidence_json': same_packet,
                'evidence_sha256': packet.sha256}
            for k, v in [('preserve', PRESERVE_PROMPT),
                         ('challenge', CHALLENGE_PROMPT),
                         ('neutral', NEUTRAL_PROMPT)]}


def validate_proposal(raw: str) -> dict[str, Any]:
    """Parse an untrusted agent answer: evidence, not approval."""
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != {'verdict','claims','proposed_tests'}:
        raise ValueError("invalid agent response schema")
    if obj['verdict'] not in {'retain', 'investigate', 'change_candidate'}:
        raise ValueError("invalid verdict")
    if not isinstance(obj['claims'], list) or not isinstance(obj['proposed_tests'], list):
        raise ValueError("claims/tests must be arrays")
    if any(not isinstance(x, str) for x in obj['claims'] + obj['proposed_tests']):
        raise ValueError("claims/tests must contain strings only")
    return obj  # CANNOT promote a model or authorize trading
