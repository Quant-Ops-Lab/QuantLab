from decimal import Decimal
from quantlab.portfolio.policy import Decision,Position,HarvestPolicy,evaluate_position
D=Decimal

def test_trim_preserves_core_and_does_not_repeat_at_same_peak():
    pos=Position('NVDA',D('10'),D('100'),D('120'),initial_core_qty=D('10'))
    dec=evaluate_position(pos,D('120'))
    assert dec.action==Decision.TRIM
    assert dec.shares==D('2.500000')
    later=Position('NVDA',D('7.5'),D('100'),D('120'),last_harvest_peak=D('120'),initial_core_qty=D('10'))
    assert evaluate_position(later,D('120')).action==Decision.HOLD

def test_exit_trigger_from_peak_not_basis():
    pos=Position('MU',D('10'),D('100'),D('200'))
    assert evaluate_position(pos,D('141')).action==Decision.HOLD
    assert evaluate_position(pos,D('140')).action==Decision.EXIT

def test_core_floor():
    pos=Position('NVDA',D('5'),D('100'),D('150'),initial_core_qty=D('10'))
    assert evaluate_position(pos,D('150')).action==Decision.HOLD

def test_decline_exits_tactical_sleeve_but_leaves_designated_core():
    pos=Position('NVDA',D('8'),D('100'),D('200'),initial_core_qty=D('10'))
    dec=evaluate_position(pos,D('140'))
    assert dec.action==Decision.EXIT and dec.shares==D('3.000000')
