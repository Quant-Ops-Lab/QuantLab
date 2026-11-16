"""Conservative challenger comparison, deliberately independent from LLMs.

This policy returns a *candidate* promotion recommendation only; nothing here
loads a model in production or changes trading permissions.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    model_sha: str
    evaluated_periods: int
    trades: int
    after_cost_mean_return: float
    max_drawdown: float
    reproducible: bool


@dataclass(frozen=True)
class Decision:
    candidate_passes_gate: bool
    reasons: tuple[str, ...]


def challenger_gate(champion: Evidence, challenger: Evidence,
                    minimum_periods: int = 4, minimum_trades: int = 100,
                    maximum_drawdown: float = 0.05) -> Decision:
    reasons = []
    if champion.model_sha == challenger.model_sha or not champion.model_sha or not challenger.model_sha:
        reasons.append('invalid_model_identity')
    if not challenger.reproducible:
        reasons.append('not_reproducible')
    if challenger.evaluated_periods < minimum_periods or challenger.trades < minimum_trades:
        reasons.append('insufficient_out_of_sample_evidence')
    if (not 0 <= challenger.max_drawdown <= maximum_drawdown
        or not 0 <= champion.max_drawdown <= 1):
        reasons.append('drawdown_limit')
    if not (challenger.after_cost_mean_return > 0
            and challenger.after_cost_mean_return > champion.after_cost_mean_return):
        reasons.append('no_incremental_net_edge')
    return Decision(candidate_passes_gate=not reasons, reasons=tuple(reasons))
