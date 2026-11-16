"""Seeded stochastic stress scenarios for research only, never price forecasts.

Inspired by the Gaussian Cookbook and Q-Fin; original implementation.
GBM is a *scenario model* with constant volatility and independent increments.
Discontinuities may be modeled by rare log jumps, but these assumptions are
insufficient for many equities/crypto assets and do not establish an edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import numpy as np


@dataclass(frozen=True)
class StressSummary:
    simulated_paths: int
    probability_target_first: float
    probability_stop_first: float
    probability_horizon_exit: float
    mean_net_return: float
    cvar_95_net_return: float
    worst_net_return: float
    model_only: bool = True


def simulate_price_paths(
    entry: float, *, annualized_drift: float = 0.0,
    annualized_vol: float = 0.35, horizon_years: float = 5.0 / 252,
    steps: int = 20, paths: int = 1000, seed: int = 1,
    jump_probability_per_step: float = 0.0,
    jump_log_mean: float = -0.05, jump_log_std: float = 0.02,
) -> np.ndarray:
    """Return a (paths, steps+1) path matrix, initial price in first column.

    Independently sampled Gaussian log increments with optional compound
    Bernoulli shocks. Probabilities are *scenario assumptions*, not estimates.
    No network, broker, LLM or random global state is touched.
    """
    values = (entry, annualized_drift, annualized_vol, horizon_years,
              jump_probability_per_step, jump_log_mean, jump_log_std)
    if any(not isfinite(x) for x in values):
        raise ValueError('all scenario parameters must be finite')
    if entry <= 0 or annualized_vol < 0 or horizon_years <= 0:
        raise ValueError('entry, horizon and volatility must be valid')
    if not 0 <= jump_probability_per_step <= 1 or jump_log_std < 0:
        raise ValueError('invalid shock probability or magnitude')
    if isinstance(steps, bool) or isinstance(paths, bool) or not isinstance(steps,int) or not isinstance(paths,int):
        raise ValueError('integer steps and paths required')
    if not 1 <= steps <= 10000 or not 1 <= paths <= 50000 or steps*paths > 2_000_000:
        raise ValueError('scenario exceeds resource limits')
    dt = horizon_years / steps
    rng = np.random.default_rng(seed)
    innovations = rng.standard_normal((paths, steps))
    increments = ((annualized_drift - .5 * annualized_vol ** 2) * dt
                  + annualized_vol * np.sqrt(dt) * innovations)
    if jump_probability_per_step:
        triggers = rng.random((paths, steps)) < jump_probability_per_step
        magnitudes = rng.normal(jump_log_mean, jump_log_std, size=(paths, steps))
        increments += np.where(triggers, magnitudes, 0.0)
    logs = np.c_[np.zeros(paths), np.cumsum(increments, axis=1)]
    return entry * np.exp(logs)


def stress_trade(paths: np.ndarray, *, stop: float, target: float,
                 direction: str = 'LONG', round_trip_cost_bps: float = 5.0) -> StressSummary:
    """Check first sampled barrier touch; observed crossing is gap-aware.

    Conservative target execution at limit, stop at *crossed price* (which may
    be worse than stop after a jump). Ignores spread depth, latency, borrow,
    market hours and actual fill availability. This is NOT an execution backtest.
    """
    p = np.asarray(paths, dtype=float)
    if p.ndim != 2 or p.shape[0] < 1 or p.shape[1] < 2 or not np.all(np.isfinite(p)) or np.any(p <= 0):
        raise ValueError('finite positive path matrix required')
    if direction not in ('LONG', 'SHORT'):
        raise ValueError('direction must be LONG or SHORT')
    if not isfinite(stop) or not isfinite(target) or not isfinite(round_trip_cost_bps) or round_trip_cost_bps < 0:
        raise ValueError('invalid barrier or cost')
    entry = p[:, 0]
    if direction == 'LONG':
        if not (np.all(stop < entry) and np.all(entry < target)):
            raise ValueError('LONG requires stop < entry < target')
        stopped = p[:, 1:] <= stop
        targeted = p[:, 1:] >= target
    else:
        if not (np.all(target < entry) and np.all(entry < stop)):
            raise ValueError('SHORT requires target < entry < stop')
        stopped = p[:, 1:] >= stop
        targeted = p[:, 1:] <= target
    hit = stopped | targeted
    any_hit = hit.any(axis=1)
    first = np.where(any_hit, hit.argmax(axis=1) + 1, p.shape[1] - 1)
    idx = np.arange(p.shape[0])
    stopped_first = np.where(any_hit, stopped[idx, first - 1], False)
    target_first = np.where(any_hit, targeted[idx, first - 1], False)
    # A target fill is capped at target, even if the simulated step skips past it.
    exit_price = np.where(target_first, target, p[idx, first])
    sign = 1 if direction == 'LONG' else -1
    net = sign * (exit_price / entry - 1) - round_trip_cost_bps / 10000.0
    k = max(1, int(np.ceil(len(net) * 0.05)))
    tail = np.sort(net)[:k]
    return StressSummary(
        simulated_paths=len(net),
        probability_target_first=float(np.mean(target_first)),
        probability_stop_first=float(np.mean(stopped_first)),
        probability_horizon_exit=float(np.mean(~any_hit)),
        mean_net_return=float(np.mean(net)),
        cvar_95_net_return=float(np.mean(tail)),
        worst_net_return=float(np.min(net)),
    )
