import asyncio
from datetime import datetime

from app.engine import CACHE_MAX_SIZE, PriceEngine, PricePoint


def test_step_updates_latest_and_history():
    engine = PriceEngine(tickers=["AAPL"], simulation_dt=datetime.fromisoformat("2024-01-02T09:30:00"))
    engine.ticker_latest_cache["AAPL"] = PricePoint(ts=engine.market_open_dt.timestamp(), price=100.0)
    engine.ticker_history_map["AAPL"] = [None] * CACHE_MAX_SIZE
    engine.ticker_history_map["AAPL"][0] = engine.ticker_latest_cache["AAPL"]

    asyncio.run(engine.step())

    assert engine.minute_index == 1
    latest = engine.ticker_latest_cache["AAPL"]
    assert latest.ts == engine.market_open_dt.timestamp()
    assert engine.ticker_history_map["AAPL"][0] is not None
