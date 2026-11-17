import numpy as np
import pandas as pd
import pytest

module = pytest.importorskip('quantlab.models.challenger_xgb_nlp')
DualFinancialNLPEncoder = module.DualFinancialNLPEncoder
NLPModelConfig = module.NLPModelConfig
CalibratedXGBChallenger = module.CalibratedXGBChallenger


def test_receipt_features_preserve_original_index_and_exclude_future_events():
    encoder = object.__new__(DualFinancialNLPEncoder)
    bars = pd.DataFrame({'close': [100.0, 101.0]}, index=['2026-11-16 15:00', '2026-11-16 15:05'])
    events = pd.DataFrame([
        {'receipt_timestamp': '2026-11-16T14:59:00Z', 'source_type': 'SEC_EDGAR', 'text': 'known'},
        {'receipt_timestamp': '2026-11-16T15:06:00Z', 'source_type': 'SEC_EDGAR', 'text': 'future'},
    ])
    encoder._score = lambda texts, *args: np.ones(len(texts))
    result = encoder.extract_point_in_time_features(bars, events, '30min')
    assert list(result.index) == list(bars.index)
    assert result.loc[bars.index[0], 'finbert_event_count'] == 1
    assert result.loc[bars.index[0], 'nlp_missing_flag'] == 0
    assert result.loc[bars.index[1], 'finbert_event_count'] == 1


def test_score_batches_texts():
    encoder = object.__new__(DualFinancialNLPEncoder)
    encoder.config = NLPModelConfig(device='cpu', batch_size=2)
    encoder.device = 'cpu'
    calls = []

    class Batch:
        def to(self, device):
            return self

    class Tokenizer:
        def __call__(self, texts, **kwargs):
            calls.append(list(texts))
            return Batch()

    class Model:
        def __call__(self, **kwargs):
            class Output:
                logits = __import__('torch').tensor([[2.0, 1.0], [1.0, 2.0]])[:len(calls[-1])]
            return Output()

    scores = encoder._score(['a', 'b', 'c'], Tokenizer(), Model(), 0, 1)
    assert len(calls) == 2 and len(scores) == 3


def test_sparse_class_challenger_skips_three_fold_calibration():
    model = CalibratedXGBChallenger().fit([[0.0], [1.0], [0.2], [0.8]], [0, 1, 0, 1])
    probabilities = model.predict_proba([[0.4]])
    assert probabilities.shape == (1, 2)
