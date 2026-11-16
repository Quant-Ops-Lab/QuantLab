"""Read-only contract for future Public/Alpaca/Webull API adapters.

The *absence* of an order-write method is deliberate.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Account:
    account_id: str
    equity: Decimal
    settled_cash: Decimal


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    feed_timestamp_utc: str


class ReadOnlyBroker(Protocol):
    def account(self) -> Account: ...
    def quote(self, symbol: str) -> Quote: ...
    def open_order_ids(self) -> frozenset[str]: ...
