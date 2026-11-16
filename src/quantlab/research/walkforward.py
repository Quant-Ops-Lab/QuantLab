"""Chronological rolling-origin splits with a label-overlap gap.

Indices refer to preconstructed, time-sorted examples. A gap of at least the
label horizon is required for leakage control. Additional embargo is optional.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Fold:
    train: tuple[int, ...]
    test: tuple[int, ...]


def walkforward(n: int, train_size: int, test_size: int,
                label_horizon: int = 1, embargo: int = 0) -> list[Fold]:
    if n < 1 or train_size < 5 or test_size < 1 or label_horizon < 1 or embargo < 0:
        raise ValueError("invalid fold parameters")
    folds: list[Fold] = []
    gap = label_horizon + embargo
    train_end = train_size
    while train_end + gap + test_size <= n:
        test_start = train_end + gap
        folds.append(Fold(
            train=tuple(range(train_end)),
            test=tuple(range(test_start, test_start + test_size)),
        ))
        train_end += test_size
    return folds
