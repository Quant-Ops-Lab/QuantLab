# Audited source inventory (2026-11-12)

## GitHub repository facts confirmed through connected GitHub API

- `EPdacoder05/algorithmic-data-pipeline`, main snapshot at `0f19397b94a1f6bf7de632b0c5c3b34c5c23f556`
- `EPdacoder05/NullPointVector`, main snapshot at `60d02d5e7b5f0dec297c038828602df8bdbae76f`
- `Quant-Ops-Lab/QuantLab` and `EPdacoder05/Quant-lab`: GitHub integration returned 404 for both as of this checkpoint. This ZIP is not pushed to either.

## Sports pipeline: abstractions to reuse, not direct imports

| Committed path | Good abstraction | Stock-specific requirement |
|---|---|---|
| `analysis/rlm_detector.py` | Detect an opposing price/positioning pattern | Require actual positioning data; do not infer sharp money |
| `engine/signals.py` | Primary evidence and independent confirmations | Replace point-additive confidence with validated net-edge estimates |
| `engine/confidence_decay.py` | Invalidate stale signals and respond to new events | Use measured signal half-life and event timestamps |
| `engine/no_bet_detector.py` | Explicit opt-out | Default to no-trade when features/quotes/costs unavailable |
| `engine/ml/feature_engine.py` | Stable feature contracts | Do not silently impute missing as zero; use lagged bars |
| `engine/ml/pick_model.py` | Train and calibrate challengers | Its `np.random.permutation(total)` (line ~236) leaks time order; **do not reuse as is** |
| `engine/ml/anomaly_detector.py` | IsolationForest/z-score monitoring | Anomalies indicate uncertainty, not market direction |
| `engine/ml/model_monitor.py` | Page-Hinkley and PSI drift monitoring | Drift may quarantine, never auto-deploy a new strategy |
| `engine/clv_tracker.py` | Execution attribution | Replace CLV with arrival-price slippage / implementation shortfall |

`engine/live_under_protector_v2.py` contains 9 committed numbered entries:
`RULE_0`, `RULE_1`, `RULE_2`, `RULE_3`, `RULE_6`, `RULE_7`,
`RULE_9`, `RULE_10`, `RULE_11`. `RULE_19`/`RULE_20` weren't verified in this snapshot.
No quantum stock trading implementation was verified. `RLM` is reverse-line-
movement logic from sports markets, not quantum computing.

## NullPoint governance patterns

- `docs/AI_DEV_CHECKPOINT.md`: resumable handoff template.
- `common/idempotency.py`: deduplicate requests; real trading needs durable
  broker order IDs and reconciliation, not just API-level idempotency.
- `PhishGuard/phish_mlm/training/trainer.py`: candidate vs champion evaluation.
- `PhishGuard/phish_mlm/training/drift.py`: PSI drift diagnostics.
- `.github/workflows/ml-gate.yml`: automated quality tests.

These are conceptual references. No copyright/licensing assumptions are made about
redistributing code from the other repositories; QuantLab bootstrap is new code.
