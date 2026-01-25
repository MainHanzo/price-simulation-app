import asyncio
import os
import time as pytime

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.engine import PriceEngine


def parse_simulation_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("America/New_York"))
    return parsed


simulation_dt = parse_simulation_dt(os.getenv("SIMULATION_DT"))
engine = PriceEngine(
    tickers=["AAPL", "MSFT", "GOOG", "TSLA"],
    simulation_dt=simulation_dt,
)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.engine = engine
app.state.simulation_dt = simulation_dt
app.state.simulation_real_start = pytime.time()
app.state.simulation_cur_dt = app.state.simulation_dt
app.include_router(router)

@app.on_event("startup")
async def start_generator() -> None:
    async def loop() -> None:
        last_minute = None
        while True:
            now_real = pytime.time()
            elapsed = now_real - app.state.simulation_real_start
            app.state.simulation_cur_dt = app.state.simulation_dt + timedelta(seconds=elapsed)
            current_minute = app.state.simulation_cur_dt.replace(second=0, microsecond=0)
            if last_minute is None or current_minute > last_minute:
                last_minute = current_minute
                if app.state.simulation_cur_dt.time() < time(16, 0):
                    asyncio.create_task(engine.step())
            await asyncio.sleep(0.5)

    asyncio.create_task(loop())
