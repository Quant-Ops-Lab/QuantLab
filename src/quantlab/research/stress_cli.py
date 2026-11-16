"""Offline research command. Output probabilities are simulated, NOT forecasts."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from quantlab.research.stochastic import simulate_price_paths, stress_trade


def main() -> None:
    ap = argparse.ArgumentParser(description='QuantLab hypothetical stop/target stress testing')
    ap.add_argument('--entry', type=float, required=True)
    ap.add_argument('--stop', type=float, required=True)
    ap.add_argument('--target', type=float, required=True)
    ap.add_argument('--direction', choices=['LONG','SHORT'], default='LONG')
    ap.add_argument('--vol', type=float, default=.45, help='ASSUMED annualized volatility (0.45 = 45%%)')
    ap.add_argument('--drift', type=float, default=0, help='ASSUMED annualized log drift')
    ap.add_argument('--years', type=float, default=5/252)
    ap.add_argument('--paths', type=int, default=1000)
    ap.add_argument('--steps', type=int, default=20)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--cost-bps', type=float, default=5)
    ap.add_argument('--jump-prob', type=float, default=0)
    ap.add_argument('--jump-mean', type=float, default=-.05)
    ap.add_argument('--jump-std', type=float, default=.02)
    a=ap.parse_args()
    paths=simulate_price_paths(a.entry, annualized_drift=a.drift,
        annualized_vol=a.vol, horizon_years=a.years, paths=a.paths,
        steps=a.steps, seed=a.seed, jump_probability_per_step=a.jump_prob,
        jump_log_mean=a.jump_mean, jump_log_std=a.jump_std)
    out=stress_trade(paths, stop=a.stop, target=a.target,
        direction=a.direction, round_trip_cost_bps=a.cost_bps)
    print(json.dumps({'kind':'HYPOTHETICAL_STRESS_SIMULATION',
        'disclaimer':'Assumed price-path distribution; not calibrated forecast, execution backtest or trade authorization',
        'assumptions':vars(a), 'result':asdict(out)},indent=2))

if __name__ == '__main__':main()
