"""Small-price and floating-point regression cases for anonymous depth."""

import pytest

from price_generator.order_book import SimulatedOrderBook


@pytest.mark.parametrize("price", [1.1, 2.3, 100.01, 0.11, 0.001, 1e-9])
def test_depth_strictly_brackets_anonymous_reference(price: float) -> None:
    book = SimulatedOrderBook(1).update(price, 0, True)
    assert book["bids"][0]["price"] < price < book["asks"][0]["price"]
    assert book["bids"][-1]["price"] > 0
