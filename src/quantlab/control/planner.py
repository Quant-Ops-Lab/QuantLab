"""Drafting contract for future LLM strategy compiler.

An LLM should generate structured JSON matching StrategySpec.from_dict, not code.
This module currently provides a safe operator-specified sample template only.
"""
from .contracts import StrategySpec, Direction, Mode

def draft(description: str, symbols: list[str], direction: str='bearish',
          mode: str='alert_only', threshold_bps: int=30,
          strategy_id: str='operator-draft') -> StrategySpec:
    if not description.strip():
        raise ValueError('description required')
    return StrategySpec(strategy_id=strategy_id,description=description,
                        symbols=tuple(symbols),direction=Direction(direction),mode=Mode(mode),
                        threshold_bps=threshold_bps)
