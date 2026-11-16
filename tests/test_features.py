from datetime import datetime, timezone, timedelta
import pytest
from quantlab.research.features import Bar, examples


def sample():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Bar(t+timedelta(minutes=i), 100+i, 1000+i) for i in range(20)]


def test_feature_uses_only_history_and_future_target():
    bars = sample()
    a = examples(bars, lookback=3, horizon=2, costs_bps=5)
    assert len(a) == 15
    assert a[0].feature_time == bars[3].asof
    assert a[0].label_end_time == bars[5].asof
    future_changed = list(bars)
    future_changed[5] = Bar(bars[5].asof, 100000, bars[5].volume)
    b = examples(future_changed, lookback=3, horizon=2, costs_bps=5)
    assert a[0].features == b[0].features
    assert a[0].label_net_return != b[0].label_net_return


def test_missing_volume_is_explicit():
    bars=sample()
    bars[3]=Bar(bars[3].asof, bars[3].close, None)
    a=examples(bars, lookback=3, horizon=2)
    assert a[0].features[3] == 1.0


def test_rejects_time_travel():
    bars=sample()
    bars[3] = Bar(bars[2].asof, bars[3].close, 500)
    with pytest.raises(ValueError):
        examples(bars)
