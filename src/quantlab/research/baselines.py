"""Simple standardized Ridge baseline and out-of-sample diagnostics.

Each call fits on an already separated *training* fold only. The caller
must not reuse test labels during feature selection or tuning.
"""
from dataclasses import dataclass
from typing import Sequence
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from .features import Example
from .walkforward import Fold


@dataclass(frozen=True)
class FoldReport:
    observations: int
    mean_squared_error: float
    mean_net_return_for_positive_forecasts: float | None
    traded_fraction: float


def evaluate_ridge(items: Sequence[Example], fold: Fold, min_edge: float = 0.0002) -> FoldReport:
    if min_edge < 0 or not fold.train or not fold.test:
        raise ValueError("need positive folds and nonnegative edge")
    if max(fold.train) >= min(fold.test):
        raise ValueError("train indices must strictly precede test indices")
    x_train = np.asarray([items[i].features for i in fold.train], dtype=float)
    y_train = np.asarray([items[i].label_net_return for i in fold.train], dtype=float)
    x_test = np.asarray([items[i].features for i in fold.test], dtype=float)
    y_test = np.asarray([items[i].label_net_return for i in fold.test], dtype=float)
    pipe = Pipeline([('scaler', StandardScaler()), ('ridge', Ridge(alpha=10.0))])
    pipe.fit(x_train, y_train)
    forecasts = pipe.predict(x_test)
    selection = forecasts > min_edge
    trading_returns = y_test[selection]
    # Reports economic outcome but omits position sizing, liquidation and
    # intra-bar slippage. It is NOT an executable backtest.
    return FoldReport(
        observations=len(fold.test),
        mean_squared_error=float(mean_squared_error(y_test, forecasts)),
        mean_net_return_for_positive_forecasts=(float(np.mean(trading_returns)) if len(trading_returns) else None),
        traded_fraction=float(np.mean(selection)),
    )
