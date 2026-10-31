import asyncio
import os
import time as pytime
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.engine import PriceEngine
from app.orderbook import OrderBook, is_session_open


def parse_simulation_dt(value: str | None) -> datetime:
    default = datetime(2024, 1, 2, 11, 30, tzinfo=ZoneInfo("America/New_York"))
    if not value:
        return default
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return default
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("America/New_York"))
    return parsed.astimezone(ZoneInfo("America/New_York"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    real_start = pytime.monotonic()

    async def generate() -> None:
        last_second = None
        while True:
            now = app.state.simulation_dt + timedelta(seconds=pytime.monotonic() - real_start)
            app.state.simulation_cur_dt = now
            second = int(now.timestamp())
            if second != last_second:
                last_second = second
                if is_session_open(now):
                    await app.state.engine.step(now)
                async with app.state.engine.lock:
                    for ticker in tuple(app.state.orderbook.snapshots):
                        point = app.state.engine.ticker_latest_cache[ticker]
                        app.state.orderbook.update(ticker, point.price, point.ts, now)
            await asyncio.sleep(0.1)

    task = asyncio.create_task(generate())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


simulation_dt = parse_simulation_dt(os.getenv("SIMULATION_DT"))
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.engine = PriceEngine(["AAPL", "MSFT", "GOOG", "TSLA"], simulation_dt)
app.state.orderbook = OrderBook()
app.state.simulation_dt = simulation_dt
app.state.simulation_cur_dt = simulation_dt
app.include_router(router)
