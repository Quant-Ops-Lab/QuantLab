"""Embeddable Python control SDK. Safe alert-only operations in v0.3."""
from datetime import datetime, timezone
from .contracts import SignalObservation, StrategySpec
from .engine import evaluate
from .notifications import publish_decision, Publisher

class QuantLabClient:
    def __init__(self, publisher: Publisher):
        self.publisher=publisher
    def run_once(self, spec: StrategySpec, observation:SignalObservation, now_utc:datetime|None=None):
        decision=evaluate(spec,observation,now_utc)
        publish_decision(self.publisher,decision)
        return decision
