from datetime import datetime, timedelta, timezone

import pytest

from quantlab.research.challenger import (
    ModelWeightLedger,
    ReceiptEvent,
    fit_sgd_challenger,
    receipt_time_features,
)


NOW = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)


def test_receipt_time_features_exclude_future_and_unverified_events():
    events = [
        ReceiptEvent("official filing", "SEC_EDGAR", NOW - timedelta(minutes=5)),
        ReceiptEvent("future post", "X_GROK", NOW + timedelta(minutes=1)),
        ReceiptEvent("rumor", "X_GROK", NOW - timedelta(minutes=4), verified=False),
    ]
    rows = receipt_time_features([NOW], events, scorer=lambda texts, source: [0.8] * len(texts))
    assert rows[0].formal_mean == 0.8
    assert rows[0].formal_count == 1
    assert rows[0].social_velocity == 0


def test_sgd_challenger_fits_only_with_both_classes():
    model = fit_sgd_challenger([[0.0], [1.0], [0.1], [0.9]], [0, 1, 0, 1])
    assert model.predict_proba([[0.8]])[0, 1] > model.predict_proba([[0.2]])[0, 1]
    with pytest.raises(ValueError):
        fit_sgd_challenger([[1.0], [2.0]], [1, 1])


def test_model_weights_update_only_from_realized_returns():
    ledger = ModelWeightLedger.equal(["ridge", "sgd"])
    updated = ledger.update({"ridge": 0.01, "sgd": -0.01})
    assert updated.weights["ridge"] > updated.weights["sgd"]
    assert updated.observations == {"ridge": 1, "sgd": 1}
    assert 0.0 <= updated.blend({"ridge": 0.7, "sgd": 0.3}) <= 1.0