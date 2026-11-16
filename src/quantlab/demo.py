"""Deterministic synthetic research smoke test, not real-market results."""
from datetime import datetime, timezone, timedelta
from .research.features import Bar, examples
from .research.walkforward import walkforward
from .research.baselines import evaluate_ridge
from .agents.experiment import EvidencePacket, trials


def main():
    start = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    # Invented series: verifying wiring, not profit or live performance.
    bars = [Bar(start + timedelta(minutes=i * 5),
                close=100 + i * 0.025 + ((i % 13) - 6) * 0.04,
                volume=5000 + ((i * 7) % 23) * 50) for i in range(220)]
    rows = examples(bars, lookback=3, horizon=2, costs_bps=2)
    folds = walkforward(len(rows), train_size=100, test_size=30, label_horizon=2, embargo=1)
    print(f'Synthetic rows: {len(rows)}; walk-forward folds: {len(folds)}')
    for i, fold in enumerate(folds, 1):
        result = evaluate_ridge(rows, fold)
        print(f'Fold {i}: mse={result.mean_squared_error:.8f}; selected={result.traded_fraction:.1%}')
    packet = EvidencePacket(strategy_sha='demo-strategy', model_sha='demo-model',
            data_sha='synthetic-not-real-data', asof_utc=start.isoformat(),
            outcomes=({'trade_id':'synthetic','realized_net_return':0.0},),
            cost_assumptions={'costs_bps':2.0})
    t = trials(packet)
    assert len({a['evidence_sha256'] for a in t.values()}) == 1
    print('Dual-agent evidence SHA:', packet.sha256)
    print('Orders submitted: 0 (synthetic demo never submits broker orders)')


if __name__ == '__main__':
    main()
