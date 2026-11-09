from price_generator.market_session import USStockSession
from price_generator.order_book import SimulatedOrderBook


def test_opening_spread_is_wider_and_closing_depth_is_larger() -> None:
    snapshots = {}
    for preset in ("opening", "midday", "final_minute"):
        book = SimulatedOrderBook(1, seed=7)
        snapshots[preset] = book.update(100, 0, True, USStockSession(preset).conditions(0, .6))
    spread = lambda snapshot: snapshot["asks"][0]["price"] - snapshot["bids"][0]["price"]
    assert spread(snapshots["opening"]) > spread(snapshots["midday"]) >= spread(snapshots["final_minute"])
    for side in ("bids", "asks"):
        assert snapshots["final_minute"][side][-1]["cumulative_quantity"] > snapshots["midday"][side][-1]["cumulative_quantity"]
    assert snapshots["midday"]["bids"][-1]["cumulative_quantity"] > snapshots["midday"]["asks"][-1]["cumulative_quantity"]


def test_stock_book_depends_on_simulated_time_and_remains_positive_at_tiny_prices() -> None:
    session = USStockSession()
    book = SimulatedOrderBook(1, seed=2)
    initial = book.update(1e-9, 0, True, session.conditions(0, -.5))
    later = book.update(1e-9, 120, True, session.conditions(120, -.5))
    assert initial["asks"] != later["asks"]
    fresh = SimulatedOrderBook(1, seed=2).update(1e-9, 120, True, session.conditions(120, -.5))
    assert fresh["bids"] == later["bids"]
    for side in ("bids", "asks"):
        assert len({level["price"] for level in later[side]}) == 10
        assert all(level["price"] > 0 and level["quantity"] > 0 for level in later[side])
    stopped = book.update(1e-9, 120, False, session.conditions(120, -.5))
    assert book.update(1e-9, 120, False, session.conditions(120, -.5)) == stopped


def test_late_day_churn_does_not_accelerate_from_total_elapsed_time() -> None:
    book = SimulatedOrderBook(1, seed=2)
    session = USStockSession()
    # At 15:55, refresh cadence should be seconds rather than tenths of seconds.
    snapshots = [book.update(100, second, True, session.conditions(second, .5)) for second in (23100, 23100.2, 23100.4)]
    quantities = [[level["quantity"] for level in snapshot["bids"]] for snapshot in snapshots]
    # Smooth depth changes can move a rounded share; a new noise draw cannot.
    assert max(abs(a - b) for a, b in zip(quantities[0], quantities[-1])) <= 1
