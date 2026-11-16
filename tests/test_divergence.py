from datetime import datetime, timezone
from quantlab.strategy.divergence import PositioningObservation, observe_divergence


def obs(**kw):
    data = dict(timestamp=datetime.now(timezone.utc),symbol='SPY',
         reference_price=100,last_price=99.5,retail_long_fraction=0.75,
         relative_volume=1.8, independent_venue_confirms=True)
    data.update(kw)
    return PositioningObservation(**data)


def test_candidate_but_no_trade():
    result=observe_divergence(obs())
    assert result.flagged and result.direction == 'bearish_divergence'
    assert not hasattr(result,'submit_order')


def test_missing_positioning_rejects_flag():
    assert not observe_divergence(obs(retail_long_fraction=None)).flagged


def test_no_confirmation_no_flag():
    assert not observe_divergence(obs(independent_venue_confirms=False)).flagged
