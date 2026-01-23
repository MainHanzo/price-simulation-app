import asyncio
import os
import schedule

from datetime import datetime
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
engine = PriceEngine(tickers=["AAPL", "MSFT", "GOOG", "TSLA"], simulation_dt=simulation_dt)
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
    def job() -> None:
        asyncio.create_task(engine.step())

    schedule.every().minute.at(":00").do(job)

    async def loop() -> None:
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)

    asyncio.create_task(loop())
