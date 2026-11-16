"""Tests for stochastic baseline, Markov regimes, and stop-first meta-labels."""
import numpy as np
import pytest
from quantlab.research.regimes import observed_regime,estimate_regime_transitions
from quantlab.research.stochastic import simulate_price_paths,stress_trade
from quantlab.research.triple_barrier import OHLC,label_trade


def test_deterministic_simulations_and_initial_price():
    a=simulate_price_paths(100,paths=24,steps=6,seed=44)
    b=simulate_price_paths(100,paths=24,steps=6,seed=44)
    assert a.shape==(24,7)
    assert np.array_equal(a,b)
    assert np.all(a[:,0]==100)


def test_zero_volatility_zero_drift_constant_prices():
    p=simulate_price_paths(100,annualized_drift=0,annualized_vol=0,paths=10,steps=4)
    assert np.all(p==100)
    r=stress_trade(p,stop=95,target=110)
    assert r.probability_horizon_exit==1
    assert r.mean_net_return==pytest.approx(-0.0005)


def test_target_stop_and_gap_aware_returns():
    p=np.array([[100,103,112],[100,95,90],[100,99,101],[100,88,110]],dtype=float)
    r=stress_trade(p,stop=96,target=110,round_trip_cost_bps=0)
    assert r.probability_target_first==.25
    assert r.probability_stop_first==.5
    assert r.probability_horizon_exit==.25
    assert r.worst_net_return==pytest.approx(-.12)


def test_shorts_and_invalid_direction():
    p=np.array([[100,90],[100,110],[100,99]])
    x=stress_trade(p,direction='SHORT',stop=105,target=95)
    assert x.probability_target_first==pytest.approx(1/3)
    assert x.probability_stop_first==pytest.approx(1/3)
    with pytest.raises(ValueError):stress_trade(p,direction='BUY',stop=95,target=105)


def test_limit_resource_demand_and_invalid_params():
    with pytest.raises(ValueError):simulate_price_paths(100,paths=50001)
    with pytest.raises(ValueError):simulate_price_paths(100,jump_probability_per_step=1.1)
    with pytest.raises(ValueError):simulate_price_paths(0)


def test_gbm_shock_scenario_has_rare_large_losses():
    p=simulate_price_paths(100,paths=200,steps=4,annualized_vol=0,seed=1,
                           jump_probability_per_step=0.5,jump_log_mean=-0.2,jump_log_std=0)
    r=stress_trade(p,stop=95,target=115)
    assert r.probability_stop_first>0.5
    assert r.cvar_95_net_return<-.15


def test_classify_trailing_closes():
    quiet=[100]*30
    trend=[100*(1.01**i) for i in range(30)]
    volatile=[100,120,99,130,98,122,90,110,88,130]*3
    assert observed_regime(quiet,lookback=10)=='QUIET'
    assert observed_regime(trend,lookback=10,stress_vol_per_bar=.1,trend_mean_per_bar=.004)=='TRENDING'
    assert observed_regime(volatile,lookback=10)=='STRESS'


def test_regime_probabilities_smoothed_and_train_prefix():
    prices=[100*(1.005**i) for i in range(60)]
    m=estimate_regime_transitions(prices[:40],lookback=10)
    assert m.asof_index==39
    assert m.training_observations==30
    assert sum(m.next_regime_probabilities.values())==pytest.approx(1)
    assert all(0<value<1 for value in m.next_regime_probabilities.values())
    assert m.transition_counts[1][1]==29
    later=estimate_regime_transitions(prices[:41],lookback=10)
    assert m.asof_index!=later.asof_index


def test_triple_barrier_target_label():
    outcome=label_trade(entry=100,stop=95,target=108,bars=[OHLC(100,102,99,101),OHLC(103,109,100,108)])
    assert outcome.label=='TARGET' and outcome.bars_to_exit==2
    assert outcome.realized_net_return==pytest.approx(.0795)


def test_triple_barrier_same_bar_is_conservative():
    both=label_trade(entry=100,stop=95,target=105,bars=[OHLC(100,110,90,100)])
    assert both.label=='STOP' and both.intrabar_ambiguous
    assert both.realized_net_return<0


def test_triple_barrier_gapped_open_worse_than_stop():
    a=label_trade(entry=100,stop=96,target=110,bars=[OHLC(90,94,86,92)],round_trip_cost_bps=0)
    assert a.exit_price==90 and a.realized_net_return==pytest.approx(-.1)
    b=label_trade(entry=100,stop=104,target=91,bars=[OHLC(110,111,107,108)],direction='SHORT',round_trip_cost_bps=0)
    assert b.exit_price==110 and b.realized_net_return==pytest.approx(-.1)


def test_triple_barrier_timeout_and_validation():
    a=label_trade(entry=100,stop=97,target=105,bars=[OHLC(100,101,99,101)])
    assert a.label=='TIMEOUT' and a.bars_to_exit==1
    with pytest.raises(ValueError):OHLC(100,99,101,100)
    with pytest.raises(ValueError):label_trade(entry=100,stop=105,target=95,bars=[OHLC(100,101,99,100)])


def test_delivery_ledger_creates_missing_artifacts_directory(tmp_path):
    from quantlab.delivery.dispatcher import DeliveryLedger
    path = tmp_path / 'fresh' / 'artifacts' / 'notifications.sqlite'
    ledger = DeliveryLedger(str(path))
    assert path.is_file()
    assert ledger.summary() == []
