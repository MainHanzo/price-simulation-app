import asyncio
import os
import time as pytime

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import socketio
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


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
)
simulation_dt = parse_simulation_dt(os.getenv("SIMULATION_DT"))
engine = PriceEngine(
    tickers=["AAPL", "MSFT", "GOOG", "TSLA"],
    simulation_dt=simulation_dt,
)
fastapi_app = FastAPI()
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.state.engine = engine
fastapi_app.state.simulation_dt = simulation_dt
fastapi_app.state.simulation_real_start = pytime.time()
fastapi_app.state.simulation_cur_dt = fastapi_app.state.simulation_dt
fastapi_app.state.sio = sio
fastapi_app.include_router(router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

ticker_subscribers: dict[str, int] = {}
sid_to_tickers: dict[str, set[str]] = {}

def _room_for_ticker(ticker: str) -> str:
    return f"ticker:{ticker}"

@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    sid_to_tickers[sid] = set()

@sio.event
async def disconnect(sid: str) -> None:
    tickers = sid_to_tickers.pop(sid, set())
    for ticker in tickers:
        count = ticker_subscribers.get(ticker, 0) - 1
        if count <= 0:
            ticker_subscribers.pop(ticker, None)
            engine.ticker_requested.discard(ticker)
        else:
            ticker_subscribers[ticker] = count

@sio.on("subscribe")
async def subscribe(sid: str, payload: dict) -> None:
    ticker = str(payload.get("ticker", "")).upper()
    if not ticker or ticker not in engine.ticker_params_map:
        await sio.emit("error", {"message": "Unknown ticker"}, to=sid)
        return
    await sio.enter_room(sid, _room_for_ticker(ticker))
    sid_to_tickers.setdefault(sid, set()).add(ticker)
    ticker_subscribers[ticker] = ticker_subscribers.get(ticker, 0) + 1
    engine.ticker_requested.add(ticker)
    latest = engine.ticker_latest_cache.get(ticker)
    if latest:
        await sio.emit(
            "price_update",
            {"ticker": ticker, "ts": latest.ts, "price": latest.price},
            to=sid,
        )

@sio.on("unsubscribe")
async def unsubscribe(sid: str, payload: dict) -> None:
    ticker = str(payload.get("ticker", "")).upper()
    if not ticker:
        return
    await sio.leave_room(sid, _room_for_ticker(ticker))
    if sid in sid_to_tickers and ticker in sid_to_tickers[sid]:
        sid_to_tickers[sid].remove(ticker)
        count = ticker_subscribers.get(ticker, 0) - 1
        if count <= 0:
            ticker_subscribers.pop(ticker, None)
            engine.ticker_requested.discard(ticker)
        else:
            ticker_subscribers[ticker] = count

@fastapi_app.on_event("startup")
async def start_generator() -> None:
    async def loop() -> None:
        last_minute = None
        while True:
            now_real = pytime.time()
            elapsed = now_real - fastapi_app.state.simulation_real_start
            fastapi_app.state.simulation_cur_dt = fastapi_app.state.simulation_dt + timedelta(seconds=elapsed)
            current_minute = fastapi_app.state.simulation_cur_dt.replace(second=0, microsecond=0)
            if last_minute is None or current_minute > last_minute:
                last_minute = current_minute
                if fastapi_app.state.simulation_cur_dt.time() < time(16, 0):
                    updates = await engine.step()
                    for update in updates:
                        await sio.emit(
                            "price_update",
                            update,
                            room=_room_for_ticker(update["ticker"]),
                        )
            await asyncio.sleep(0.5)

    asyncio.create_task(loop())
