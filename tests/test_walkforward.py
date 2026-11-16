from quantlab.research.walkforward import walkforward


def test_strict_chronology_and_label_gap():
    folds=walkforward(250,100,30,label_horizon=3,embargo=2)
    assert folds
    for f in folds:
        assert f.train[-1] + 3 + 2 < f.test[0]
        assert not set(f.train) & set(f.test)
        assert len(f.test) == 30
