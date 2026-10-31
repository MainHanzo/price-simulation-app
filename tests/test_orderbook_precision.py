"""Deterministic cent-grid edge cases for the shared liquidity component."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.orderbook import OrderBook


@pytest.mark.parametrize("price", [1.1, 2.3, 100.01, 0.11, 1.0999999999999999, 1.1000000000000003])
def test_quotes_strictly_bracket_reference_despite_float_rounding(price: float) -> None:
    now = datetime(2024, 1, 2, 11, 30, tzinfo=ZoneInfo("America/New_York"))
    snapshot = OrderBook().update("AAPL", price, now.timestamp(), now)
    assert snapshot.bids[0].price < price < snapshot.asks[0].price
    assert snapshot.bids[-1].price > 0
