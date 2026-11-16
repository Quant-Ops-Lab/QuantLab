"""Market autopsy tests: no hindsight masquerading as predictive skill."""
from datetime import date, timedelta
import json
import pytest
from quantlab.research.opportunity import (DailyBar, Decision, Coverage, build_report,
                                           render_markdown, read_bars_csv)


def make_bars(days=35, crypto=False):
    market='crypto' if crypto else 'equity'
    start=date(2026,9,1)
    sessions=[start+timedelta(days=i) for i in range(days)] if crypto else [start+timedelta(days=i) for i in range(52) if (start+timedelta(days=i)).weekday()<5][:days]
    data=[]
    for j, d in enumerate(sessions):
        for s, price in [('WIN', 100+j), ('BASE',100), ('LOW',100+j/2)]:
            data.append(DailyBar(s,d.isoformat(),price,1_000_000,market,price,'fixture'))
    return data, sessions


def test_windows_and_ranked_returns():
    bars, sessions=make_bars()
    report=build_report(bars,asof=sessions[-1].isoformat())
    for w,n in [('day',1),('week',5),('month',21)]:
        rows=report['movers']['equity'][w]
        assert rows[0]['symbol']=='WIN'
        assert rows[0]['start_session']==sessions[-1-n].isoformat()
        assert rows[0]['return_pct']>0
        assert rows[0]['classification']=='COVERAGE_UNKNOWN'
    assert report['movers']['crypto']['day']==[]
    assert 'hindsight' in render_markdown(report).lower()


def test_pre_move_rejected_not_late_or_future_label():
    bars,sessions=make_bars()
    start=sessions[-2].isoformat()
    events=[Coverage('WIN','2026-08-30T00:00:00Z',True)]
    decisions=[Decision('WIN',start+'T14:00:00-04:00','REJECT','ridge','No edge')]
    r=build_report(bars,decisions,events)
    assert r['movers']['equity']['day'][0]['classification']=='REJECTED_BY_MODEL'
    assert r['movers']['equity']['day'][0]['strategy']=='ridge'
    decisions=[Decision('WIN',sessions[-1].isoformat()+'T12:00:00-04:00','ENTER','too_late')]
    r=build_report(bars,decisions,events)
    assert r['movers']['equity']['day'][0]['classification']=='LATE_DETECTION'
    decisions=[Decision('WIN',sessions[-1].isoformat()+'T23:00:00-04:00','ENTER','future')]
    r=build_report(bars,decisions,events)
    assert r['movers']['equity']['day'][0]['classification']=='NO_RECORDED_SIGNAL'


def test_not_watched_and_no_recorded_signal():
    bars,_=make_bars()
    outside=[Coverage('WIN','2026-08-31T12:00:00Z',False)]
    assert build_report(bars,coverage=outside)['movers']['equity']['day'][0]['classification']=='OUTSIDE_WATCHLIST'
    inside=[Coverage('WIN','2026-08-31T12:00:00Z',True)]
    assert build_report(bars,coverage=inside)['movers']['equity']['day'][0]['classification']=='NO_RECORDED_SIGNAL'


def test_spurious_raw_split_not_claimed_as_alpha():
    bars=[DailyBar('SPLIT','2026-09-01',100,100_000,source='raw'),
          DailyBar('SPLIT','2026-09-02',180,100_000,source='raw')]
    r=build_report(bars)
    assert r['movers']['equity']['day'][0]['classification']=='CORPORATE_ACTION_CHECK'
    assert r['movers']['equity']['day'][0]['price_basis']=='raw_unadjusted'


def test_missing_sessions_produce_gap_and_not_false_result():
    bars,_=make_bars()
    bars=[b for b in bars if not (b.symbol=='WIN' and b.session==bars[0].session)]
    r=build_report(bars)
    assert r['missing_start_bars']['equity']['month']==0 # month doesn't reference day 0
    assert r['movers']['equity']['month'][0]['symbol']=='WIN'


def test_crypto_uses_actual_calendar_days():
    bars,sessions=make_bars(35,crypto=True)
    r=build_report(bars)
    assert r['movers']['crypto']['month'][0]['start_session']==sessions[-31].isoformat()
    assert r['movers']['crypto']['week'][0]['start_session']==sessions[-8].isoformat()


def test_invalid_inputs_and_conflicts():
    with pytest.raises(ValueError):
        DailyBar('X','2026-01-01',-1,100)
    with pytest.raises(ValueError):
        Decision('X','2026-01-01T12:00:00','ENTER')
    with pytest.raises(ValueError):
        build_report([DailyBar('X','2026-01-01',10,10),DailyBar('X','2026-01-01',20,10)])


def test_csv_roundtrip(tmp_path):
    f=tmp_path/'bars.csv'
    f.write_text('symbol,session,close,volume,market,adjusted_close,source\nXYZ,2026-09-01,100,10000,equity,100,fixture\n')
    rows=read_bars_csv(f)
    assert rows[0].symbol=='XYZ' and rows[0].adjusted_close==100


def test_unbounded_exception_inventory_and_cohort():
    bars,sessions=make_bars()
    # Assemble > top_n assets that each rose 10% in the last day, with point-in-time watchlist logs.
    prior,new=sessions[-2].isoformat(),sessions[-1].isoformat()
    for i in range(30):
        bars += [DailyBar(f'T{i:02}',prior,10.0,1_000_000,adjusted_close=10),
                 DailyBar(f'T{i:02}',new,11.5,1_000_000,adjusted_close=11.5)]
    result=build_report(bars,top_n=3)
    assert len(result['movers']['equity']['day'])==3
    assert len(result['outsized_move_inventory']['equity']['day'])==30
    assert result['cohort']['equity']['day']['outsized_movers']==30
    assert result['cohort']['equity']['day']['observed_symbols']==33
