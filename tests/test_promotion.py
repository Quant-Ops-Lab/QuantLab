from quantlab.research.promotion import Evidence,challenger_gate


def ev(name, **kw):
    d=dict(model_sha=name,evaluated_periods=5,trades=120,
        after_cost_mean_return=.001,max_drawdown=.03,reproducible=True)
    d.update(kw)
    return Evidence(**d)


def test_no_auto_promote_without_improvement():
    result=challenger_gate(ev('champ'),ev('candidate',after_cost_mean_return=-.005))
    assert not result.candidate_passes_gate


def test_gate_only_recommends_not_deploys():
    result=challenger_gate(ev('champ',after_cost_mean_return=.001),
                           ev('candidate',after_cost_mean_return=.002))
    assert result.candidate_passes_gate
    assert not hasattr(result,'activate_model')


def test_requires_enough_periods():
    assert not challenger_gate(ev('champ'),
                ev('candidate',evaluated_periods=1)).candidate_passes_gate
