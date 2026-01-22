import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import random
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from app.api import router
from app.engine import PriceEngine

def random_market_dt() -> datetime:
    tz = ZoneInfo("America/New_York")
    today = datetime.now(tz=tz).date()
    market_open = datetime.combine(today, dt_time(9, 30), tzinfo=tz)
    offset_minutes = random.randint(0, 389)
    return market_open + timedelta(minutes=offset_minutes)


engine = PriceEngine(tickers=["AAPL", "MSFT", "GOOG", "TSLA"], client_cur_dt=random_market_dt())
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.engine = engine
app.include_router(router)

@app.on_event("startup")
async def start_generator() -> None:
    async def loop() -> None:
        while True:
            await engine.step()
            await asyncio.sleep(60)

    asyncio.create_task(loop())

